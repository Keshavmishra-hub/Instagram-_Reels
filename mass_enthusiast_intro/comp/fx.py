"""Image-space effects for the compositor (numpy + OpenCV, all in linear HDR float32)."""
from __future__ import annotations

import math
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

cv2.setNumThreads(2)


# ----------------------------------------------------------------------------- io
def load_exr(path):
    import OpenEXR
    f = OpenEXR.File(path)
    rgba = depth = None
    for part in f.parts:
        for name, ch in part.channels.items():
            if name.endswith("Combined") and ch.pixels.ndim == 3:
                rgba = ch.pixels.astype(np.float32)
            elif name.endswith("Depth.Z") or name.endswith("Depth"):
                depth = ch.pixels.astype(np.float32)
    rgb = np.nan_to_num(rgba[..., :3], nan=0.0, posinf=60.0)
    alpha = rgba[..., 3]
    return rgb, alpha, depth


def fit(img, w, h, interp=cv2.INTER_CUBIC):
    if img.shape[1] == w and img.shape[0] == h:
        return img
    out = cv2.resize(img, (w, h), interpolation=interp)
    return np.maximum(out, 0) if out.dtype == np.float32 else out


# ----------------------------------------------------------------------------- blur / bloom
def blur(img, sigma):
    if sigma <= 0:
        return img
    if sigma > 12:   # blur a downsampled copy for speed
        k = int(min(8, sigma // 6))
        h, w = img.shape[:2]
        small = cv2.resize(img, (max(1, w // k), max(1, h // k)), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma / k)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(img, (0, 0), sigma)


def bloom(img, strength=0.12, threshold=0.9, knee=0.6, radii=(3, 9, 24, 60, 140), weights=(0.3, 0.26, 0.2, 0.14, 0.1)):
    lum = img.max(axis=2, keepdims=True)
    soft = np.clip(lum - threshold + knee, 0, 2 * knee)
    soft = soft * soft / (4 * knee + 1e-5)
    contrib = np.maximum(soft, lum - threshold) / np.maximum(lum, 1e-4)
    bright = img * contrib
    out = np.zeros_like(img)
    for r, w in zip(radii, weights):
        out += w * blur(bright, r)
    return img + strength * out / sum(weights)


def anamorphic_streak(img, threshold=4.0, strength=0.05, length=0.25, color=(1.0, 0.45, 0.25)):
    """Horizontal lens streaks from very bright points."""
    lum = img.max(axis=2)
    src = np.clip(lum - threshold, 0, 50)[..., None] * np.array(color, np.float32)
    h, w = lum.shape
    small = cv2.resize(src, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    k = max(3, int(w // 4 * length)) | 1
    small = cv2.blur(small, (k, 1))
    small = cv2.blur(small, (k // 2 | 1, 1))
    return img + strength * cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR) * 6.0


def god_rays(img, cx, cy, strength=0.5, decay=0.94, samples=40, mask=None, threshold=0.6):
    """Radial (volumetric-looking) light shafts from screen point (cx, cy), computed at 1/4 res."""
    h, w = img.shape[:2]
    s = 4
    src = cv2.resize(img if mask is None else img * mask[..., None], (w // s, h // s), interpolation=cv2.INTER_AREA)
    lum = src.max(axis=2, keepdims=True)
    src = src * np.clip((lum - threshold) / (lum + 1e-4), 0, 1)
    acc = np.zeros_like(src)
    hh, ww = src.shape[:2]
    c = (cx / s, cy / s)
    wsum = 0.0
    for i in range(samples):
        sc = 1.0 - 0.5 * i / samples
        M = np.float32([[sc, 0, c[0] * (1 - sc)], [0, sc, c[1] * (1 - sc)]])
        wgt = decay ** i
        acc += wgt * cv2.warpAffine(src, M, (ww, hh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        wsum += wgt
    acc /= wsum
    return img + strength * cv2.resize(acc, (w, h), interpolation=cv2.INTER_LINEAR)


# ----------------------------------------------------------------------------- tone / grade
def rolloff(img, knee=2.0, soft=1.5):
    """Hue-preserving highlight compression for very hot emitters (molten metal, lamps):
    keeps texture inside them instead of clipping to a flat blob."""
    L = img.max(axis=2, keepdims=True)
    over = np.maximum(L - knee, 0.0)
    Lc = np.where(L > knee, knee + soft * np.log1p(over / soft), L)
    return img * (Lc / np.maximum(L, 1e-6))


def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)


def tonemap(img, exposure=1.0):
    x = img * exposure
    # keep very bright saturated colours from turning flat white too early
    lum = (x @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
    sat = x - lum
    x = lum + sat * 1.0
    return aces(np.maximum(x, 0))


def grade(img, lift=(0, 0, 0), gamma=(1, 1, 1), gain=(1, 1, 1), sat=1.0, contrast=1.0):
    x = img * np.array(gain, np.float32) + np.array(lift, np.float32) * (1 - img)
    x = np.clip(x, 0, 1) ** (1.0 / np.array(gamma, np.float32))
    if contrast != 1.0:
        x = np.clip(0.5 + (x - 0.5) * contrast, 0, 1)
        # soft S around mid grey
    if sat != 1.0:
        lum = (x @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        x = np.clip(lum + (x - lum) * sat, 0, 1)
    return x


def s_curve(x, amount=0.12):
    return np.clip(x + amount * np.sin(2 * math.pi * x) * -0.5 / math.pi * 2 * 0 + amount * (x - x * x) * (2 * x - 1) * -2, 0, 1)


def vignette(img, amount=0.35, power=2.2):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 * (w / max(w, h)) ** 0 + ((yy - h / 2) / (h / 2)) ** 2)
    v = 1 - amount * np.clip(r / 1.4142, 0, 1) ** power
    return img * v[..., None]


_VIG = {}


def vignette_cached(img, amount=0.35, power=2.2):
    key = (img.shape[0], img.shape[1], amount, power)
    if key not in _VIG:
        h, w = img.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / 1.4142
        _VIG[key] = (1 - amount * np.clip(r, 0, 1) ** power)[..., None].astype(np.float32)
    return img * _VIG[key]


def chromatic(img, amount=0.0012):
    if amount <= 0:
        return img
    h, w = img.shape[:2]
    out = img.copy()
    for ch, k in ((0, 1 + amount), (2, 1 - amount)):
        M = np.float32([[k, 0, w / 2 * (1 - k)], [0, k, h / 2 * (1 - k)]])
        out[..., ch] = cv2.warpAffine(img[..., ch], M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out


def shake(img, dx, dy, rot=0.0, zoom=1.0):
    if abs(dx) < 1e-3 and abs(dy) < 1e-3 and abs(rot) < 1e-5 and abs(zoom - 1) < 1e-5:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), math.degrees(rot), zoom)
    M[0, 2] += dx
    M[1, 2] += dy
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ----------------------------------------------------------------------------- noise layers
class NoiseBank:
    """Tileable fractal noise textures, sampled with drifting offsets for smoke and haze."""

    def __init__(self, size=512, n=3, seed=5):
        rng = np.random.default_rng(seed)
        self.tiles = []
        for _ in range(n):
            acc = np.zeros((size, size), np.float32)
            amp, tot = 1.0, 0.0
            for octave in range(6):
                cells = 4 * 2 ** octave
                g = rng.random((cells, cells)).astype(np.float32)
                g = np.tile(g, (3, 3))
                up = cv2.resize(g, (size * 3, size * 3), interpolation=cv2.INTER_CUBIC)[size:2 * size, size:2 * size]
                acc += amp * up
                tot += amp
                amp *= 0.55
            acc /= tot
            acc = (acc - acc.min()) / (acc.max() - acc.min())
            self.tiles.append(acc)

    def sample(self, i, w, h, scale, ox, oy, angle=0.0):
        t = self.tiles[i % len(self.tiles)]
        size = t.shape[0]
        k = size / (scale * max(w, h))
        c, s = math.cos(angle) * k, math.sin(angle) * k
        M = np.float32([[c, -s, ox * size], [s, c, oy * size]])
        return cv2.warpAffine(t, M, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP * 0,
                              borderMode=cv2.BORDER_WRAP)


def smoke(noise, w, h, t, color, density=0.25, scale=0.9, speed=(0.02, -0.035), seed=0, contrast=2.2):
    a = noise.sample(seed, w, h, scale, 0.13 * seed + speed[0] * t, 0.37 * seed + speed[1] * t, 0.3)
    b = noise.sample(seed + 1, w, h, scale * 0.55, 0.51 + speed[0] * 1.7 * t, 0.2 + speed[1] * 1.4 * t, -0.5)
    m = np.clip((a * 0.6 + b * 0.4 - 0.42) * contrast, 0, 1) ** 1.5
    return (m * density)[..., None] * np.array(color, np.float32)


class Grain:
    def __init__(self, w, h, n=6, seed=9):
        rng = np.random.default_rng(seed)
        self.frames = []
        for _ in range(n):
            g = rng.normal(0, 1, (h, w)).astype(np.float32)
            g = cv2.GaussianBlur(g, (0, 0), 0.65)
            g /= g.std()
            self.frames.append(g)

    def apply(self, img, f, amount=0.03):
        g = self.frames[f % len(self.frames)]
        lum = img.mean(axis=2, keepdims=True)
        k = amount * (0.35 + 0.65 * np.sqrt(np.clip(lum, 0, 1)) * (1 - np.clip(lum, 0, 1)) * 2.2)
        return np.clip(img + g[..., None] * k, 0, 1)


# ----------------------------------------------------------------------------- shapes
def radial(w, h, cx, cy, rx, ry, power=2.0):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    return np.clip(1 - d, 0, 1) ** power


def soft_glow(w, h, cx, cy, radius, color, strength):
    s = 8
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32)
    d2 = ((xx * s - cx) ** 2 + (yy * s - cy) ** 2) / (radius ** 2)
    g = np.exp(-d2)[..., None] * np.array(color, np.float32) * strength
    return cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)


def beam(w, h, p0, p1, r0, r1, color, strength, noise=None, t=0.0):
    """Soft volumetric cone between screen points p0 (narrow) and p1 (wide)."""
    s = 4
    ww, hh = w // s, h // s
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    ax, ay = p0[0] / s, p0[1] / s
    bx, by = p1[0] / s, p1[1] / s
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy + 1e-6
    u = ((xx - ax) * dx + (yy - ay) * dy) / L2
    px, py = ax + u * dx, ay + u * dy
    dist = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
    rad = (r0 + (r1 - r0) * np.clip(u, 0, 1)) / s
    m = np.clip(1 - dist / np.maximum(rad, 1e-3), 0, 1) ** 1.6
    m *= np.clip(u * 8, 0, 1) * np.clip((1.05 - u) * 4, 0, 1)
    m *= (0.55 + 0.45 * np.exp(-u * 1.5))
    if noise is not None:
        n = noise.sample(2, ww, hh, 0.35, 0.05 * t, 0.02 * t, 0.2)
        m *= 0.55 + 0.9 * n
    g = m[..., None] * np.array(color, np.float32) * strength
    return cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)
