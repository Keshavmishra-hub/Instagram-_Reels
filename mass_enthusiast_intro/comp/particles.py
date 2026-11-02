"""World-space particle systems (sparks, embers, dust) drawn with the shot's real camera.

Motion is analytic (gravity + linear drag), so any frame can be evaluated on its own.
Particles are projected with the camera matrices exported from Blender and depth-tested
against the render's Z pass, so sparks fly behind and in front of the letters correctly.
"""
from __future__ import annotations

import math

import cv2
import numpy as np


def splat(layer, xs, ys, cols):
    """Additive bilinear splat of points (xs, ys) with RGB weights cols (N,3) into layer (H,W,3)."""
    h, w = layer.shape[:2]
    keep = (xs > -2) & (xs < w + 1) & (ys > -2) & (ys < h + 1)
    if not keep.any():
        return
    xs, ys, cols = xs[keep], ys[keep], cols[keep]
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    fx = (xs - x0).astype(np.float32)
    fy = (ys - y0).astype(np.float32)
    xi = np.concatenate([x0, x0 + 1, x0, x0 + 1])
    yi = np.concatenate([y0, y0, y0 + 1, y0 + 1])
    wt = np.concatenate([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy])
    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    xi, yi, wt = xi[ok], yi[ok], wt[ok]
    cc = np.concatenate([cols, cols, cols, cols])[ok]
    bx0, bx1, by0, by1 = xi.min(), xi.max() + 1, yi.min(), yi.max() + 1
    bw, bh = bx1 - bx0, by1 - by0
    idx = (yi - by0) * bw + (xi - bx0)
    sub = layer[by0:by1, bx0:bx1]
    for c in range(3):
        sub[..., c] += np.bincount(idx, weights=wt * cc[:, c], minlength=bw * bh).reshape(bh, bw).astype(np.float32)


def splat_lines(layer, x0, y0, x1, y1, cols, step=0.5):
    """Streaks as dense point samples; energy is spread along the streak like a moving light."""
    if len(x0) == 0:
        return
    L = np.hypot(x1 - x0, y1 - y0)
    n = np.maximum(1, np.ceil(L / step)).astype(np.int64)
    rep = np.repeat(np.arange(len(x0)), n)
    start = np.repeat(np.cumsum(n) - n, n)
    t = (np.arange(n.sum()) - start + 0.5) / n[rep]
    xs = x0[rep] + (x1 - x0)[rep] * t
    ys = y0[rep] + (y1 - y0)[rep] * t
    # per-sample weight: total streak energy grows sub-linearly with length
    wgt = (np.maximum(L, 1.0) ** 0.45 / n)[rep]
    splat(layer, xs, ys, cols[rep] * wgt[:, None].astype(np.float32))


class Camera:
    def __init__(self, entry, w, h):
        M = np.array(entry["matrix"], np.float64)
        self.world = M
        self.view = np.linalg.inv(M)
        self.w, self.h = w, h
        fit = entry.get("sensor_fit", "AUTO")
        if fit == "VERTICAL":
            self.f = entry["lens"] / entry["sensor_height"] * h
        elif fit == "HORIZONTAL":
            self.f = entry["lens"] / entry["sensor_width"] * w
        else:
            self.f = entry["lens"] / entry["sensor_width"] * max(w, h)
        self.focus = entry.get("focus") or 5.0
        self.pos = M[:3, 3]

    def project(self, P):
        """P: (N,3) world -> (u, v, depth) arrays; depth > 0 in front of the camera."""
        P = np.asarray(P, np.float64)
        pc = P @ self.view[:3, :3].T + self.view[:3, 3]
        z = -pc[:, 2]
        zs = np.where(np.abs(z) < 1e-6, 1e-6, z)
        u = self.w / 2 + self.f * pc[:, 0] / zs
        v = self.h / 2 - self.f * pc[:, 1] / zs
        return u, v, z


def heat_color(h):
    """h in [0,1]: 1 = white-yellow hot, 0 = dull red."""
    h = np.clip(h, 0, 1)[:, None]
    hot = np.array([1.0, 0.82, 0.45], np.float32)
    mid = np.array([1.0, 0.38, 0.08], np.float32)
    cold = np.array([0.55, 0.04, 0.01], np.float32)
    a = np.clip(h * 2 - 1, 0, 1)
    b = np.clip(h * 2, 0, 1)
    return np.where(h > 0.5, mid * (1 - a) + hot * a, cold * (1 - b) + mid * b)


class Sparks:
    def __init__(self, tb, p0, v0, life, heat, size, drag=1.6, gravity=(0, 0, -9.0), floor=None, bounce=0.35):
        self.tb = np.asarray(tb, np.float64)
        self.p0 = np.asarray(p0, np.float64)
        self.v0 = np.asarray(v0, np.float64)
        self.life = np.asarray(life, np.float64)
        self.heat = np.asarray(heat, np.float64)
        self.size = np.asarray(size, np.float64)
        self.k = drag
        self.g = np.asarray(gravity, np.float64)
        self.floor = floor
        self.bounce = bounce

    def pos(self, t):
        a = np.maximum(t - self.tb, 0.0)[:, None]
        k = self.k
        e = 1 - np.exp(-k * a)
        p = self.p0 + self.v0 * e / k + self.g * (a - e / k) / k
        if self.floor is not None:
            below = p[:, 2] < self.floor
            p[below, 2] = self.floor + (self.floor - p[below, 2]) * self.bounce
        return p

    def draw(self, layer, cam, t, depth=None, shutter=1 / 50.0, gain=1.0, min_px=0.6):
        age = t - self.tb
        alive = (age >= 0) & (age <= self.life)
        if not alive.any():
            return
        idx = np.nonzero(alive)[0]
        p1 = self.pos(t)[idx]
        p0 = self.pos(max(t - shutter, 0.0))[idx]
        p0 = np.where((t - shutter - self.tb[idx])[:, None] < 0, self.p0[idx], p0)
        u1, v1, z1 = cam.project(p1)
        u0, v0, z0 = cam.project(p0)
        ok = (z1 > 0.05) & (z0 > 0.05)
        h, w = layer.shape[:2]
        rel = np.clip(age[idx] / self.life[idx], 0, 1)
        heat = self.heat[idx] * (1 - rel) ** 0.8
        col = heat_color(heat) * (gain * (0.25 + 0.75 * (1 - rel)) * 6.0)[:, None]
        thick = np.clip(self.size[idx] * cam.f / np.maximum(z1, 0.05), 0.6, 6.0)
        h, w = layer.shape[:2]
        vis = ok & (u1 > -50) & (u1 < w + 50) & (v1 > -50) & (v1 < h + 50)
        if depth is not None and vis.any():
            xi = np.clip(u1.astype(np.int64), 0, w - 1)
            yi = np.clip(v1.astype(np.int64), 0, h - 1)
            vis &= depth[yi, xi] >= z1 - 0.02
        if not vis.any():
            return
        thin = vis & (thick < 1.8)
        fat = vis & ~thin
        splat_lines(layer, u0[thin], v0[thin], u1[thin], v1[thin], col[thin])
        if fat.any():
            tmp = np.zeros_like(layer)
            splat_lines(tmp, u0[fat], v0[fat], u1[fat], v1[fat], col[fat] * 1.6)
            layer += cv2.GaussianBlur(tmp, (0, 0), 1.1)


class Embers:
    """Slow, flickering glowing motes rising through the frame."""

    def __init__(self, n, box_min, box_max, seed=0, rise=0.25, size=0.012, color=(1.0, 0.36, 0.08), span=40.0):
        rng = np.random.default_rng(seed)
        self.p0 = rng.uniform(box_min, box_max, (n, 3))
        self.v = np.stack([rng.normal(0, 0.05, n), rng.normal(0, 0.05, n), rng.uniform(0.4, 1.0, n) * rise], 1)
        self.phase = rng.uniform(0, 6.28, (n, 3))
        self.freq = rng.uniform(0.3, 1.2, (n, 3))
        self.size = rng.uniform(0.5, 1.6, n) * size
        self.bright = rng.uniform(0.3, 1.0, n)
        self.flick = rng.uniform(2.0, 7.0, n)
        self.lo = np.asarray(box_min, np.float64)
        self.hi = np.asarray(box_max, np.float64)
        self.color = np.array(color, np.float32)

    def pos(self, t):
        p = self.p0 + self.v * t + 0.12 * np.sin(self.phase + self.freq * t)
        span = self.hi - self.lo
        return self.lo + np.mod(p - self.lo, span)

    def draw(self, layer, cam, t, depth=None, gain=1.0, focus=None, aperture=0.06):
        p = self.pos(t)
        u, v, z = cam.project(p)
        h, w = layer.shape[:2]
        f = focus if focus is not None else cam.focus
        vis = (z > 0.1) & (u > -40) & (u < w + 40) & (v > -40) & (v < h + 40)
        if depth is not None:
            xi = np.clip(u.astype(np.int64), 0, w - 1)
            yi = np.clip(v.astype(np.int64), 0, h - 1)
            vis &= depth[yi, xi] >= z
        if not vis.any():
            return
        zz = np.maximum(z, 0.1)
        r = self.size * cam.f / zz
        coc = aperture * cam.f * np.abs(zz - f) / (zz * max(f, 0.1))
        rad = np.maximum(r, coc * 0.5)
        fl = 0.6 + 0.4 * np.sin(self.flick * t + self.phase[:, 0])
        energy = gain * self.bright * fl * 4.0 * np.minimum(1.0, (r / np.maximum(rad, 1e-3)) ** 2 * 3 + 0.15)
        energy *= np.pi * np.maximum(rad, 0.7) ** 2 * 0.35
        cols = energy[:, None] * self.color[None, :]
        for lo, hi, sig in ((0, 1.2, 0.7), (1.2, 3.0, 1.8), (3.0, 7.0, 4.0), (7.0, 1e9, 9.0)):
            m = vis & (rad >= lo) & (rad < hi)
            if not m.any():
                continue
            tmp = np.zeros_like(layer)
            splat(tmp, u[m], v[m], cols[m])
            layer += cv2.GaussianBlur(tmp, (0, 0), sig)


def burst(rng, n, t0, points, normals, forward, speed=(2.0, 6.0), spread=0.6, life=(0.25, 0.9), up=0.6,
          size=0.006, heat=(0.75, 1.0), jitter_t=0.05):
    """Sparks squeezed out along a set of emitter points (with outward normals)."""
    idx = rng.integers(0, len(points), n)
    P = np.asarray(points, np.float64)[idx]
    N = np.asarray(normals, np.float64)[idx]
    F = np.asarray(forward, np.float64)
    sp = rng.uniform(*speed, n)[:, None]
    rnd = rng.normal(0, spread, (n, 3))
    V = (N * 0.9 + F * rng.uniform(0.2, 1.0, (n, 1)) + rnd + np.array([0, 0, up])) * sp
    tb = t0 + rng.exponential(jitter_t, n)
    return dict(tb=tb, p0=P, v0=V, life=rng.uniform(*life, n), heat=rng.uniform(*heat, n),
                size=rng.uniform(0.5, 1.4, n) * size)


def merge(parts):
    keys = parts[0].keys()
    return {k: np.concatenate([p[k] for p in parts]) for k in keys}
