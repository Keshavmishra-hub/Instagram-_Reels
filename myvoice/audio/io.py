"""Audio I/O helpers: decode uploads, resample, dither, waveform peaks."""

from __future__ import annotations

import io
import subprocess
from math import gcd
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


class AudioDecodeError(ValueError):
    pass


def decode_upload(data: bytes, ffmpeg_bin: str = "") -> tuple[np.ndarray, int, dict]:
    """Decode an uploaded take. The studio sends 32-bit float WAV (lossless copy of what the browser
    captured). Other containers are accepted via FFmpeg for robustness. Returns mono float32."""
    info: dict = {}
    try:
        with sf.SoundFile(io.BytesIO(data)) as f:
            info = {"container": f.format, "subtype": f.subtype, "channels": f.channels, "sample_rate": f.samplerate}
            audio = f.read(dtype="float32", always_2d=True)
            sr = f.samplerate
    except Exception as e:
        if not ffmpeg_bin:
            raise AudioDecodeError(f"could not decode audio: {e}") from e
        proc = subprocess.run([ffmpeg_bin, "-v", "error", "-i", "pipe:0", "-f", "wav", "-c:a", "pcm_f32le", "pipe:1"],
                              input=data, capture_output=True)
        if proc.returncode != 0:
            raise AudioDecodeError(f"could not decode audio: {proc.stderr.decode(errors='ignore')[:200]}") from e
        audio, sr = sf.read(io.BytesIO(proc.stdout), dtype="float32", always_2d=True)
        info = {"container": "ffmpeg", "subtype": "FLOAT", "channels": audio.shape[1], "sample_rate": sr}
    if audio.shape[0] == 0:
        raise AudioDecodeError("the recording is empty")
    mono = audio.mean(axis=1) if audio.shape[1] > 1 else audio[:, 0]
    nonfinite = int(np.count_nonzero(~np.isfinite(mono)))
    if nonfinite:
        mono = np.nan_to_num(mono, nan=0.0, posinf=1.0, neginf=-1.0)
    info["nonfinite_samples"] = nonfinite
    if not 8000 <= sr <= 192000:
        raise AudioDecodeError(f"unsupported sample rate {sr}")
    return mono.astype(np.float32), int(sr), info


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return (audio.mean(axis=1) if audio.shape[1] > 1 else audio[:, 0]).astype(np.float32), int(sr)


def resample(audio: np.ndarray, sr: int, target: int) -> np.ndarray:
    if sr == target:
        return audio.astype(np.float32, copy=False)
    g = gcd(int(sr), int(target))
    return resample_poly(audio.astype(np.float64), target // g, sr // g).astype(np.float32)


def tpdf_dither_to_int16(audio: np.ndarray, seed: Optional[int] = 0) -> np.ndarray:
    """Quantise to 16-bit with triangular dither (avoids quantisation distortion on quiet passages)."""
    rng = np.random.default_rng(seed)
    lsb = 1.0 / 32768.0
    d = (rng.random(audio.shape) - rng.random(audio.shape)) * lsb
    return np.clip(np.round((audio + d) * 32767.0), -32768, 32767).astype(np.int16)


def write_wav(path: Path, audio: np.ndarray, sr: int, subtype: str = "PCM_16", dither: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if subtype == "PCM_16" and dither:
        sf.write(str(path), tpdf_dither_to_int16(np.clip(audio, -1.0, 1.0)), sr, subtype="PCM_16")
    else:
        sf.write(str(path), np.clip(audio, -1.0, 1.0), sr, subtype=subtype)


def wav_bytes(audio: np.ndarray, sr: int, subtype: str = "PCM_16") -> bytes:
    buf = io.BytesIO()
    data = tpdf_dither_to_int16(np.clip(audio, -1.0, 1.0)) if subtype == "PCM_16" else np.clip(audio, -1.0, 1.0)
    sf.write(buf, data, sr, subtype=subtype, format="WAV")
    return buf.getvalue()


def peaks(audio: np.ndarray, buckets: int = 800) -> list[list[float]]:
    """Min/max pairs for drawing a waveform without downloading the audio."""
    n = len(audio)
    if n == 0:
        return []
    buckets = max(1, min(buckets, n))
    edges = np.linspace(0, n, buckets + 1).astype(int)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = audio[a:max(b, a + 1)]
        out.append([round(float(seg.min()), 4), round(float(seg.max()), 4)])
    return out


def db(x: float, floor: float = -120.0) -> float:
    return float(max(floor, 20.0 * np.log10(max(float(x), 1e-12))))
