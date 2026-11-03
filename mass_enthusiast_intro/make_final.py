"""Final assembly: composite the picture, mux the soundtrack, verify the delivery specs.

    python make_final.py --variant 16x9          # -> exports/MASS_ENTHUSIAST_Intro_16x9_1080p.mp4
    python make_final.py --variant 9x16          # -> exports/MASS_ENTHUSIAST_Intro_9x16_Reels.mp4
    python make_final.py --variant 16x9 --skip-comp   # re-mux only (e.g. after changing the audio)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
NAMES = {"16x9": "MASS_ENTHUSIAST_Intro_16x9_1080p.mp4", "9x16": "MASS_ENTHUSIAST_Intro_9x16_Reels.mp4"}
SIZES = {"16x9": (1920, 1080), "9x16": (1080, 1920)}


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def verify(path, variant):
    info = probe(path)
    v = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"][0]
    W, H = SIZES[variant]
    checks = {
        "resolution": (v["width"], v["height"]) == (W, H),
        "fps 30/1": v["r_frame_rate"] == "30/1" and v["avg_frame_rate"] == "30/1",
        "H.264 High": v["codec_name"] == "h264" and v.get("profile") == "High",
        "yuv420p": v["pix_fmt"] == "yuv420p",
        "AAC 48 kHz stereo": a["codec_name"] == "aac" and a["sample_rate"] == "48000" and a["channels"] == 2,
        "duration 33.0 s": abs(float(info["format"]["duration"]) - 33.0) < 0.05,
        "frames 990": int(v.get("nb_frames", 0)) == 990,
    }
    for k, ok in checks.items():
        print(f"  [{'ok' if ok else 'FAIL'}] {k}")
    return all(checks.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="16x9", choices=list(NAMES))
    ap.add_argument("--skip-comp", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()
    frames = os.path.join(ROOT, "build", f"frames_{a.variant}")
    audio = os.path.join(ROOT, "audio", "mass_enthusiast_mix.wav")
    out = os.path.join(ROOT, "exports", NAMES[a.variant])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not a.skip_comp:   # resumable: frames already in the sequence are kept
        run([PY, os.path.join(ROOT, "comp", "comp.py"), "--variant", a.variant, "--workers", str(a.workers),
             "--png", frames, "--resume"])
    if not os.path.exists(audio):
        run([PY, os.path.join(ROOT, "audio", "sound_design.py")])
    W, H = SIZES[a.variant]
    run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-start_number", "0", "-i",
         os.path.join(frames, "%04d.png"), "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
         "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-tune", "film", "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-r", "30", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-shortest",
         "-movflags", "+faststart", "-metadata", "title=MASS ENTHUSIAST - Intro", out])
    ok = verify(out, a.variant)
    print("delivery", "OK" if ok else "has problems", "->", out)


if __name__ == "__main__":
    main()
