"""Generate every 2D texture used by the 3D scenes (run once; outputs go to assets/textures).

  * film frames graded from the user's own photos (+ a still from the speech video)
  * the 35mm film strip (frames, frame lines, sprocket holes, edge print)
  * the projector-screen image, the theatre ticket and the lens aperture-ring markings
"""
from __future__ import annotations

import math
import os
import random
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(ROOT, "assets", "images", "source")
OUT = os.path.join(ROOT, "assets", "textures")
FONTS = os.path.join(ROOT, "..", "renderer", "public", "fonts")
os.makedirs(OUT, exist_ok=True)
UP = os.environ.get("UPLOADS", "/root/.claude/uploads/ad94efc1-bc6d-55bc-98f8-6b0fb53aeed0")

# (source, centre x, centre y, crop width as fraction of the image width) -> 4:3 frame
FRAMES = [
    ("e5aa232e-image.jpg", 0.53, 0.40, 0.62),       # childhood photo
    ("382cc9d2-image.jpg", 0.47, 0.50, 0.95),       # ancient temple ruins
    ("cd9da197-image.jpg", 0.55, 0.52, 0.80),       # field work in the village
    ("speech_peak.jpg", 0.52, 0.52, 1.00),          # the speech - finger raised
    ("5c7132ca-image.jpg", 0.50, 0.46, 0.80),       # portrait
    ("4a8cf1c0-image.jpg", 0.52, 0.50, 0.95),       # school-gate selfie
]


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def load(name):
    p = os.path.join(SRC, name) if os.path.exists(os.path.join(SRC, name)) else os.path.join(UP, name)
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def crop_aspect(im, cx, cy, wfrac, aspect):
    W, H = im.size
    w = W * wfrac
    h = w / aspect
    if h > H:
        h = H
        w = h * aspect
    x0 = min(max(cx * W - w / 2, 0), W - w)
    y0 = min(max(cy * H - h / 2, 0), H - h)
    return im.crop((int(x0), int(y0), int(x0 + w), int(y0 + h)))


def grade_film(im, warm=True, seed=0):
    """Print-film look: rich contrast, warm highlights, lifted blacks, vignette, grain, dust."""
    rng = np.random.default_rng(seed)
    a = np.asarray(im).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    a = 0.55 * a + 0.45 * lum[..., None]                       # partial desaturation
    a = np.clip((a - 0.5) * 1.25 + 0.5, 0, 1)                  # contrast
    a = a ** np.array([0.92, 1.0, 1.12], np.float32) if warm else a
    a = a * np.array([1.06, 0.97, 0.85], np.float32)           # amber
    a = 0.035 + a * 0.95
    h, w = lum.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a *= (1 - 0.45 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None]
    a += rng.normal(0, 0.03, a.shape).astype(np.float32)
    out = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(out)
    for _ in range(14):                                         # dust and hairline scratches
        x, y = rng.integers(0, w), rng.integers(0, h)
        rr = rng.integers(1, 3)
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(20, 16, 12))
    for _ in range(2):
        x = int(rng.integers(0, w))
        d.line((x, 0, x + int(rng.integers(-8, 8)), h), fill=(225, 210, 190), width=1)
    return out


def film_frames():
    ffmpeg_still("speech_peak.jpg", 1.42)
    frames = []
    for i, (name, cx, cy, wf) in enumerate(FRAMES):
        im = load(name)
        im = crop_aspect(im, cx, cy, wf, 4 / 3).resize((800, 600), Image.LANCZOS)
        im = grade_film(im, seed=i)
        im.save(os.path.join(OUT, f"frame_{i}.jpg"), quality=92)
        frames.append(im)
    return frames


def ffmpeg_still(name, t):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i",
                        os.path.join(UP, "6d71ed82-VID-20260828-WA0013.mp4"), "-frames:v", "1", "-q:v", "2", p],
                       check=True)


def film_strip(frames):
    """Vertical 35mm strip: 4 perfs per frame, black frame lines, edge print. RGBA (holes = 0)."""
    FW, FH = 800, 600            # picture area
    margin = 150                 # perforation margins left/right
    pitch = FH + 60              # frame pitch incl. frame line
    W = FW + 2 * margin
    n = len(frames)
    H = pitch * n
    strip = Image.new("RGBA", (W, H), (14, 10, 8, 255))     # dense black print base
    d = ImageDraw.Draw(strip)
    edge = font("Teko-Variable.ttf", 34)
    for k, fr in enumerate(frames):
        y0 = k * pitch + 30
        strip.paste(fr, (margin, y0))
        for p in range(4):                                   # 4 perforations per frame, both sides
            py = k * pitch + p * pitch / 4 + pitch / 8 - 26
            for px in (margin / 2 - 34, W - margin / 2 - 34):
                d.rounded_rectangle((px, py, px + 68, py + 52), radius=9, fill=(0, 0, 0, 0))
        d.text((margin / 2 - 14, y0 + 220), f"{k + 1:02d}", fill=(205, 150, 70, 255), font=edge)
        d.text((W - margin / 2 - 14, y0 + 300), "ME", fill=(205, 150, 70, 255), font=edge)
    strip.save(os.path.join(OUT, "film_strip.png"))
    return strip


def screen_image():
    im = load("speech_peak.jpg")
    im = crop_aspect(im, 0.52, 0.47, 1.0, 16 / 9).resize((1280, 720), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    a = 0.35 * a + 0.65 * lum[..., None]
    a = np.clip((a - 0.45) * 1.5 + 0.45, 0, 1)
    a = a * np.array([1.08, 0.86, 0.72], np.float32)
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(os.path.join(OUT, "screen.jpg"), quality=92)


def ticket():
    W, H = 2000, 820
    im = Image.new("RGB", (W, H), (226, 207, 170))
    rng = np.random.default_rng(7)
    paper = (rng.normal(0, 7, (H, W, 1)) + np.array([226, 207, 170])).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(paper).filter(ImageFilter.GaussianBlur(0.8))
    d = ImageDraw.Draw(im)
    red = (128, 18, 22)
    ink = (40, 26, 20)
    d.rectangle((26, 26, W - 26, H - 26), outline=red, width=8)
    d.rectangle((46, 46, W - 46, H - 46), outline=red, width=3)
    stub_x = 1520
    for y in range(40, H - 40, 26):                        # perforation
        d.ellipse((stub_x - 6, y, stub_x + 6, y + 12), fill=(150, 135, 110))
    big = font("Anton-Regular.ttf", 260)
    mid = font("Teko-Variable.ttf", 96)
    sml = font("Teko-Variable.ttf", 64)
    d.text((110, 70), "ADMIT ONE", font=big, fill=red)
    d.text((118, 400), "PREMIERE  NIGHT  ·  ROW  M  ·  SEAT  01", font=mid, fill=ink)
    d.text((118, 520), "THIS TICKET MUST BE RETAINED", font=sml, fill=ink)
    d.text((118, 620), "Nº 000001", font=mid, fill=red)
    for k, txt in enumerate(("ADMIT", "ONE")):
        t = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
        ImageDraw.Draw(t).text((10, 0), txt, font=font("Anton-Regular.ttf", 150), fill=red + (255,))
        t = t.rotate(90, expand=True)
        im.paste(t, (stub_x + 60 + k * 170, 110), t)
    im = ImageEnhance.Contrast(im).enhance(1.05)
    im.save(os.path.join(OUT, "ticket.jpg"), quality=93)


def aperture_ring():
    """Unwrapped markings for a lens aperture/focus ring (white on black)."""
    W, H = 4096, 256
    im = Image.new("RGB", (W, H), (8, 8, 9))
    d = ImageDraw.Draw(im)
    f = font("Teko-Variable.ttf", 120)
    stops = ["1.4", "2", "2.8", "4", "5.6", "8", "11", "16", "22"]
    for k, s in enumerate(stops * 2):
        x = 60 + k * (W - 120) / (len(stops) * 2)
        d.text((x, 40), s, font=f, fill=(235, 235, 230) if k % 9 != 1 else (220, 40, 30))
        d.line((x + 20, 200, x + 20, 250), fill=(235, 235, 230), width=6)
    im.save(os.path.join(OUT, "aperture_ring.png"))


if __name__ == "__main__":
    fr = film_frames()
    film_strip(fr)
    screen_image()
    ticket()
    aperture_ring()
    print("textures written to", OUT)
