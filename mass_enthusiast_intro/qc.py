"""Quality control for a finished export.

    python qc.py exports/MASS_ENTHUSIAST_Intro_16x9_1080p.mp4

* contact sheets of the whole film (every 0.25 s) and of the title section (every frame/2)
* luminance jumps between frames that are not on a planned cut or flash (flicker check)
* unintended black stretches (ffmpeg blackdetect)
* audio onsets vs. the visual beats in timeline.py (sync check)
* the title's spelling, read back from the geometry that builds it
"""
from __future__ import annotations

import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "blender", "lib"))
import timeline as TL  # noqa: E402


def frames_of(path, w=480):
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(",")
    W, H = int(info[0]), int(info[1])
    h = int(round(H * w / W / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3), (W, H)


def sheet(frames, idx, path, cols=8, label=True):
    from PIL import Image, ImageDraw
    tiles = [Image.fromarray(frames[i]) for i in idx]
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new("RGB", (cols * (w + 4), rows * (h + 20)), (24, 24, 24))
    d = ImageDraw.Draw(out)
    for k, (i, t) in enumerate(zip(idx, tiles)):
        x, y = (k % cols) * (w + 4), (k // cols) * (h + 20)
        out.paste(t, (x, y))
        if label:
            d.text((x + 4, y + h + 3), f"{i / TL.FPS:5.2f}s  f{i}", fill=(230, 230, 230))
    out.save(path)


def main():
    path = sys.argv[1]
    outdir = os.path.join(ROOT, "build", "qc", os.path.splitext(os.path.basename(path))[0])
    os.makedirs(outdir, exist_ok=True)
    fr, (W, H) = frames_of(path, 480 if W_guess(path) >= 1920 else 270)
    n = len(fr)
    print(f"{n} frames decoded ({W}x{H})")
    sheet(fr, list(range(0, n, 8)), os.path.join(outdir, "sheet_all.png"), cols=10)
    a, b = TL.SHOT["s13_title"]
    sheet(fr, list(range(a, b + 1, 4)), os.path.join(outdir, "sheet_title.png"), cols=10)
    # flicker: frame-to-frame luminance change away from cuts/flashes
    lum = fr.mean(axis=(1, 2, 3))
    d = np.abs(np.diff(lum))
    planned = set()
    for sid, a, b, _ in TL.SHOTS:
        planned.update(range(a - 1, a + 2))
    for k in list(TL.TITLE.values()) + list(TL.BEATS.values()):
        for v in (k if isinstance(k, (list, tuple)) else [k]):
            if isinstance(v, int):
                planned.update(range(v - 1, v + 6))
    sus = [(i, round(float(d[i]), 1)) for i in range(len(d)) if d[i] > 12 and i not in planned]
    print("unplanned luminance jumps (>12/255):", sus[:20] or "none")
    # black stretches
    bd = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-vf", "blackdetect=d=0.15:pix_th=0.04", "-an", "-f", "null",
                         "-"], capture_output=True, text=True).stderr
    blacks = [l.split("blackdetect")[1].strip() for l in bd.splitlines() if "black_start" in l]
    print("black stretches:", blacks or "none")
    # audio onsets vs visual beats
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    au = np.frombuffer(raw, np.float32)
    hop = 80  # 10 ms
    env = np.sqrt(np.convolve(au ** 2, np.ones(hop) / hop, "same"))[::hop]
    flux = np.maximum(np.diff(20 * np.log10(env + 1e-5)), 0)
    beats = [TL.TITLE[k] for k in ("slam_M", "slam_A", "slam_S1", "slam_S2", "mass_lock", "hero_impact")]
    beats += TL.BEATS["bass_hits"] + TL.BEATS["vortex_hits"] + [TL.BEATS["flash"], TL.BEATS["lamp_ignite"]]
    print("beat  frame  time   nearest audio onset (ms offset)")
    worst = 0
    for f in sorted(beats):
        t = f / TL.FPS
        i0 = int((t - 0.15) * 100)
        i1 = int((t + 0.15) * 100)
        seg = flux[max(i0, 0):i1]
        j = int(np.argmax(seg)) + max(i0, 0)
        off = (j / 100.0 - t) * 1000
        worst = max(worst, abs(off))
        print(f"       {f:4d}  {t:5.2f}s  {off:+6.0f} ms  (flux {seg.max():.1f} dB)")
    print(f"max |offset| = {worst:.0f} ms")
    # spelling, straight from the geometry that is rendered
    from glyphs import lockup
    placed, *_ = lockup()
    words = {}
    for g in placed:
        words.setdefault(g.word, []).append(g.char)
    spelled = " ".join("".join(v) for v in words.values())
    print("title spelled from geometry:", spelled, "OK" if spelled == "MASS ENTHUSIAST" else "MISMATCH")
    print("sheets in", outdir)


def W_guess(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    return int(out or 0)


if __name__ == "__main__":
    main()
