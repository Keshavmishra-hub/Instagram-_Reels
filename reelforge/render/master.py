"""Audio mastering and final encode with FFmpeg.

Mix: processed narration + score (EQ-carved and side-chain ducked under the voice) + SFX,
two-pass EBU R128 loudness normalisation to -14 LUFS / -1.5 dBTP (a common target for
short-form social video), then mux with the silent Remotion render into an Instagram-ready
MP4 (H.264 High, yuv420p, 30 fps CFR, AAC-LC 48 kHz stereo, faststart).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from ..config import Settings, settings as default_settings

TARGET_LUFS = -14.0
TARGET_TP = -1.5


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {' '.join(cmd[:6])} ...\n{proc.stderr[-1800:]}")
    return proc


def probe(path: Path, s: Settings = default_settings) -> dict:
    proc = subprocess.run(
        [s.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
    return json.loads(proc.stdout)


def media_duration(path: Path, s: Settings = default_settings) -> float:
    try:
        return float(probe(path, s)["format"].get("duration", 0.0))
    except Exception:
        return 0.0


def loudness(path: Path, s: Settings = default_settings) -> dict:
    """Integrated loudness / true peak / LRA via the loudnorm analyser."""
    proc = subprocess.run(
        [s.ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(path), "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"\{\s*\"input_i\".*?\}", proc.stderr, re.S)
    if not m:
        raise RuntimeError("loudness analysis failed")
    return json.loads(m.group(0))


def master_audio(
    narration: Path,
    out: Path,
    music: Optional[Path] = None,
    sfx: Optional[Path] = None,
    music_gain_db: float = -12.0,
    duration: Optional[float] = None,
    stems_dir: Optional[Path] = None,
    s: Settings = default_settings,
) -> dict:
    inputs = ["-i", str(narration)]
    idx_music = idx_sfx = None
    if music and music.exists():
        idx_music = len(inputs) // 2
        inputs += ["-i", str(music)]
    if sfx and sfx.exists():
        idx_sfx = len(inputs) // 2
        inputs += ["-i", str(sfx)]

    voice_chain = (
        "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono,"
        "highpass=f=75,"
        "equalizer=f=250:t=q:w=1.2:g=-1.5,"  # tame boxiness
        "equalizer=f=3600:t=q:w=1.0:g=2.0,"  # presence for intelligibility on phone speakers
        "acompressor=threshold=-20dB:ratio=3:attack=6:release=80:makeup=2,"
        "aformat=channel_layouts=stereo,asplit=2[voice][key]"
    )
    parts = [voice_chain]
    mix_inputs = ["[voice]"]
    if idx_music is not None:
        parts.append(
            f"[{idx_music}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"highpass=f=45,equalizer=f=3000:t=q:w=1.2:g=-4,volume={music_gain_db}dB[mus]"
        )
        parts.append("[mus][key]sidechaincompress=threshold=0.05:ratio=3.5:attack=20:release=500:makeup=1[mduck]")
        mix_inputs.append("[mduck]")
    else:
        parts.append("[key]anullsink")
    if idx_sfx is not None:
        parts.append(f"[{idx_sfx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=-6dB[fx]")
        mix_inputs.append("[fx]")
    pre = out.with_name(out.stem + "_premaster.wav")
    if len(mix_inputs) > 1:
        parts.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:normalize=0[mix]")
    else:
        parts.append("[voice]anull[mix]")
    graph = ";".join(parts)
    cmd = [s.ffmpeg_bin, "-y", "-hide_banner", *inputs, "-filter_complex", graph, "-map", "[mix]"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-ar", "48000", "-c:a", "pcm_s24le", str(pre)]
    _run(cmd)

    # stems for QC (music bed after ducking, processed voice)
    if stems_dir and idx_music is not None:
        stems_dir.mkdir(parents=True, exist_ok=True)
        stem_graph = ";".join([voice_chain.replace("asplit=2[voice][key]", "asplit=2[voice][key]"), parts[1], parts[2], "[voice]anullsink"])
        _run([s.ffmpeg_bin, "-y", "-hide_banner", *inputs[: (idx_music + 1) * 2], "-filter_complex", stem_graph, "-map", "[mduck]",
              *(["-t", f"{duration:.3f}"] if duration else []), "-ar", "48000", "-c:a", "pcm_s16le", str(stems_dir / "music_ducked.wav")])

    # two-pass loudness normalisation
    m = loudness(pre, s)
    ln = (
        f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=summary"
    )
    _run([s.ffmpeg_bin, "-y", "-hide_banner", "-i", str(pre), "-af", f"{ln},aresample=48000", "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
    pre.unlink(missing_ok=True)
    return loudness(out, s)


def mux(video: Path, audio: Path, out: Path, title: str = "", s: Settings = default_settings) -> Path:
    """Copy the H.264 stream (no second lossy encode), add AAC audio, move moov atom to the front.

    AAC encoding can push inter-sample peaks above the mastered ceiling, so the encoded file is
    re-measured and, if needed, re-encoded with a small gain trim until true peak <= -1 dBTP.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    info = probe(video, s)
    v = next(st for st in info["streams"] if st["codec_type"] == "video")
    reencode = v.get("codec_name") != "h264" or v.get("pix_fmt") != "yuv420p"
    vcodec = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30"] if reencode else ["-c:v", "copy"]
    trim_db = 0.0
    for _ in range(4):
        af = "lowpass=f=17000" + (f",volume={trim_db:.2f}dB" if trim_db else "")
        _run([
            s.ffmpeg_bin, "-y", "-hide_banner", "-i", str(video), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0", *vcodec,
            "-af", af, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
            "-shortest", "-movflags", "+faststart",
            "-metadata", f"title={title}", "-metadata", "comment=Made with ReelForge",
            str(out),
        ])
        tp = float(loudness(out, s)["input_tp"])
        if tp <= -1.0:
            break
        trim_db -= (tp + 1.2)
    return out


def extract_frame(video: Path, t: float, out: Path, s: Settings = default_settings) -> Path:
    _run([s.ffmpeg_bin, "-y", "-hide_banner", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(out)])
    return out
