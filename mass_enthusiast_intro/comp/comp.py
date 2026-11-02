"""Compositor: turns the Blender EXR renders into the finished picture.

    python comp/comp.py --variant 16x9                       # full film -> build/picture_16x9.mp4
    python comp/comp.py --variant 16x9 --frames 570-640 --png build/qc   # QC stills

Per shot it adds what is cheaper and more controllable in 2D than in the renderer:
world-space sparks / embers / dust (projected with the real camera and depth-tested
against the Z pass), god rays, the projector beam, flares, smoke, the title's floor
reflection, flashes; then bloom, filmic tone mapping, grade, vignette, chromatic
aberration and grain. Hard cuts happen on the beats defined in timeline.py.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from functools import lru_cache

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import timeline as TL  # noqa: E402
import fx  # noqa: E402
import particles as P  # noqa: E402
from timeline import lerp, clamp, smoothstep  # noqa: E402

SIZES = {"16x9": (1920, 1080), "9x16": (1080, 1920)}
CRIMSON = (0.55, 0.02, 0.015)
EMBER = (1.0, 0.36, 0.08)


# ----------------------------------------------------------------------------- data access
class Shot:
    def __init__(self, variant, sid):
        self.sid = sid
        self.dir = os.path.join(os.environ.get("COMP_RENDER_DIR", os.path.join(ROOT, "render")), variant, sid)
        self.W, self.H = SIZES[variant]
        self._cam = None
        self._meta = None

    @property
    def cams(self):
        if self._cam is None:
            p = os.path.join(self.dir, "camera.json")
            self._cam = json.load(open(p)) if os.path.exists(p) else {}
        return self._cam

    @property
    def meta(self):
        if self._meta is None:
            p = os.path.join(self.dir, "meta.json")
            self._meta = json.load(open(p)) if os.path.exists(p) else {}
        return self._meta

    def camera(self, f):
        e = self.cams.get(str(f))
        return P.Camera(e, self.W, self.H) if e else None

    def track(self, f, name):
        e = self.cams.get(str(f), {}).get("track", {}).get(name)
        return (np.array(e[:3]), np.array(e[3:6])) if e else (None, None)

    def frame(self, f):
        p = os.path.join(self.dir, f"{f:04d}.exr")
        if not os.path.exists(p):
            return None
        rgb, alpha, depth = fx.load_exr(p)
        self.upscale = self.W / rgb.shape[1]
        rgb = fx.fit(rgb, self.W, self.H)
        if depth is not None:
            depth = cv2.resize(depth, (self.W, self.H), interpolation=cv2.INTER_NEAREST)
            # the renders have an opaque world, so build the object mask from the Z pass
            alpha = cv2.GaussianBlur((depth < 1e6).astype(np.float32), (0, 0), 0.8)
        else:
            alpha = fx.fit(alpha, self.W, self.H, cv2.INTER_LINEAR)
        return rgb, alpha, depth


# ----------------------------------------------------------------------------- particle caches
@lru_cache(maxsize=None)
def title_sparks(variant):
    sh = Shot(variant, "s13_title")
    ems = sh.meta.get("emitters", [])
    rng = np.random.default_rng(13)
    parts = []
    for e in ems:
        pts = np.array(e["points"], np.float64)
        if len(pts) == 0:
            continue
        big = e["index"] < 4
        n = 900 if big else 160
        cap = e["cap"]
        d = P.burst(rng, n, e["frame"] / TL.FPS, pts[:, :3], pts[:, 3:], (0.0, -1.0, 0.0),
                    speed=(1.5 * cap, 5.5 * cap) if big else (0.8, 2.6), spread=0.45, up=0.5,
                    life=(0.25, 1.1) if big else (0.15, 0.6), size=0.006 * cap ** 0.5, jitter_t=0.03)
        parts.append(d)
    if not parts:
        return None
    return P.Sparks(**P.merge(parts), drag=1.4, gravity=(0, 0, -7.5), floor=-0.06, bounce=0.3)


@lru_cache(maxsize=None)
def fountain(variant, sid, rate, spread, speed, life, seed, dirv, t0, t1, size=0.005):
    """Continuous spark emission from a tracked point (positions sampled per frame)."""
    sh = Shot(variant, sid)
    rng = np.random.default_rng(seed)
    parts = []
    f0, f1 = TL.SHOT[sid]
    for f in range(f0, f1 + 1):
        tt = f / TL.FPS
        if not (t0 <= tt <= t1):
            continue
        p, _ = sh.track(f, {"s09_sparks": "contact", "s08_redline": "red"}[sid])
        if p is None:
            continue
        n = rng.poisson(rate / TL.FPS)
        if n == 0:
            continue
        dirn = np.array(dirv, np.float64)
        dirn /= np.linalg.norm(dirn)
        V = (dirn + rng.normal(0, spread, (n, 3))) * rng.uniform(*speed, (n, 1))
        parts.append(dict(tb=tt + rng.uniform(0, 1 / TL.FPS, n), p0=np.tile(p, (n, 1)) + rng.normal(0, 0.01, (n, 3)),
                          v0=V, life=rng.uniform(*life, n), heat=rng.uniform(0.75, 1.0, n),
                          size=rng.uniform(0.5, 1.5, n) * size))
    if not parts:
        return None
    return P.Sparks(**P.merge(parts), drag=1.0, gravity=(0, 0, -9.0))


@lru_cache(maxsize=None)
def embers(kind):
    if kind == "title":
        return P.Embers(260, (-4.5, -4.5, -0.5), (4.5, 3.0, 4.0), seed=3, rise=0.3, size=0.010)
    if kind == "dust":
        return P.Embers(220, (-2.5, -2.5, 0.0), (2.5, 2.5, 8.0), seed=4, rise=0.05, size=0.004,
                        color=(0.75, 0.8, 0.9))
    if kind == "ticket":
        return P.Embers(160, (-1.4, -0.8, -0.8), (1.4, 0.8, 1.6), seed=5, rise=0.55, size=0.007)
    if kind == "vortex":
        return P.Embers(500, (-3.0, -2.0, -2.0), (3.0, 34.0, 2.0), seed=6, rise=0.2, size=0.012)
    if kind == "screen":
        return P.Embers(140, (-2.0, 1.5, -1.0), (2.0, 13.0, 1.6), seed=7, rise=0.03, size=0.005,
                        color=(1.0, 0.8, 0.6))
    raise KeyError(kind)


# ----------------------------------------------------------------------------- helpers
def screen_pt(cam, p):
    u, v, z = cam.project(np.asarray(p, np.float64)[None, :])
    return float(u[0]), float(v[0]), float(z[0])


def add_layer_particles(ctx, draw_fn):
    layer = np.zeros_like(ctx["rgb"])
    draw_fn(layer)
    ctx["rgb"] += layer


def floor_reflection(ctx, src, floor_z=-0.06, y=-0.06, strength=0.24, decay=0.2):
    cam = ctx["cam"]
    W, H = ctx["W"], ctx["H"]
    xs = np.linspace(-3.5, 3.5, 15)
    pts = np.stack([xs, np.full_like(xs, y), np.full_like(xs, floor_z)], 1)
    u, v, z = cam.project(pts)
    ok = z > 0.1
    if ok.sum() < 3:
        return
    a, b = np.polyfit(u[ok], v[ok], 1)
    uu, vv = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    line = a * uu + b
    d = vv - line
    map_y = (2 * line - vv).astype(np.float32)
    refl = cv2.remap(src, uu, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    below = (d > 0).astype(np.float32)
    dn = d / H
    att = np.exp(-dn / decay) * below
    r1 = fx.blur(refl, 2.0)
    r2 = fx.blur(refl, 9.0)
    k = np.clip(dn / 0.12, 0, 1)[..., None]
    refl = r1 * (1 - k) + r2 * k
    noise = ctx["noise"].sample(0, W, H, 0.08, 0.3, 0.1, 0.0)
    mod = (0.75 + 0.5 * noise)[..., None]
    ctx["rgb"] += refl * (att[..., None] * strength) * mod * (1 - ctx["alpha"][..., None])
    # faint sheen on the floor surface itself
    sheen = np.exp(-np.abs(dn) / 0.05) * below
    ctx["rgb"] += sheen[..., None] * np.array(CRIMSON, np.float32) * 0.05


def atmosphere(ctx, glow=0.6, smoke_d=0.18, top=True, color=CRIMSON, smoke_color=(0.5, 0.08, 0.04)):
    W, H, t = ctx["W"], ctx["H"], ctx["t"]
    bg = 1.0 - np.clip(ctx["alpha"], 0, 1)[..., None]
    if top and glow > 0:
        g = fx.soft_glow(W, H, W * 0.5, -H * 0.12, max(W, H) * 0.55, color, glow * 0.32)
        ctx["rgb"] += g * (0.4 + 0.6 * bg)
    if smoke_d > 0:
        sm = fx.smoke(ctx["noise"], W, H, t, smoke_color, density=smoke_d * 0.4, seed=ctx["shot_index"])
        ctx["rgb"] += sm * (0.3 + 0.7 * bg)


# ----------------------------------------------------------------------------- recipes
def r_s01(ctx):
    f, t = ctx["f"], ctx["t"]
    add_layer_particles(ctx, lambda L: embers("dust").draw(L, ctx["cam"], t, ctx["depth"], gain=0.25 * smoothstep(10, 60, f)))
    atmosphere(ctx, glow=0.25 * smoothstep(40, 140, f), smoke_d=0.05)
    ctx["exposure"] *= smoothstep(-2, 14, f) * 0.85 + 0.15 * (f > 14)


def r_s02(ctx):
    p, _ = ctx["shot"].track(ctx["f"], "lamp")
    if p is not None:
        u, v, z = screen_pt(ctx["cam"], p)
        ctx["rgb"] = fx.god_rays(ctx["rgb"], u, v, strength=1.0, decay=0.95, threshold=0.5)
    add_layer_particles(ctx, lambda L: embers("dust").draw(L, ctx["cam"], ctx["t"], ctx["depth"], gain=0.3))
    atmosphere(ctx, glow=0.15, smoke_d=0.06, smoke_color=(0.35, 0.18, 0.08))


def r_s03(ctx):
    f = ctx["f"]
    k = 0.0
    for p in TL.BEATS["gate_pulldowns"]:
        if 0 <= f - p < 6:
            k = max(k, math.exp(-(f - p) / 1.5))
    ctx["shake"] = (0.0, 3.5 * k * ctx["H"] / 1080.0)
    ctx["exposure"] *= 1.0 + 0.07 * TL.value_noise_1d(f * 3.1, 6) - 0.12 * k
    W, H = ctx["W"], ctx["H"]
    ctx["rgb"] += fx.soft_glow(W, H, W * 0.5, H * 0.5, max(W, H) * 0.6, (0.5, 0.3, 0.15), 0.08)
    atmosphere(ctx, glow=0.1, smoke_d=0.05, smoke_color=(0.3, 0.16, 0.08))


def r_s04(ctx):
    f, t = ctx["f"], ctx["t"]
    sh = ctx["shot"]
    lens, _ = sh.track(f, "lens")
    scr, _ = sh.track(f, "screen")
    ign = TL.BEATS["lamp_ignite"]
    on = smoothstep(ign, ign + 4, f)
    if lens is not None and on > 0:
        u0, v0, z0 = screen_pt(ctx["cam"], lens)
        u1, v1, z1 = screen_pt(ctx["cam"], scr)
        W, H = ctx["W"], ctx["H"]
        if z0 > 0 and z1 > 0:
            ctx["rgb"] += fx.beam(W, H, (u0, v0), (u1, v1), 0.012 * W, 0.42 * W, (1.0, 0.75, 0.5),
                                  0.55 * on, ctx["noise"], t)
        if z0 > 0:
            flash = 1.0 + 3.0 * math.exp(-max(f - ign, 0) / 3.0)
            ctx["rgb"] += fx.soft_glow(W, H, u0, v0, 0.05 * W, (1.0, 0.8, 0.55), 2.5 * on * flash)
        add_layer_particles(ctx, lambda L: embers("screen").draw(L, ctx["cam"], t, ctx["depth"], gain=0.5 * on))
    ctx["rgb"] = fx.anamorphic_streak(ctx["rgb"], threshold=3.0, strength=0.06)
    atmosphere(ctx, glow=0.0, smoke_d=0.08 * on, smoke_color=(0.4, 0.3, 0.2))


def r_s05(ctx):
    t = ctx["t"]
    add_layer_particles(ctx, lambda L: embers("ticket").draw(L, ctx["cam"], t, ctx["depth"], gain=1.2))
    W, H = ctx["W"], ctx["H"]
    sm = fx.smoke(ctx["noise"], W, H, t * 2.0, (0.35, 0.22, 0.16), density=0.16, scale=0.6, speed=(0.0, -0.09), seed=4)
    ctx["rgb"] += sm * (1 - ctx["alpha"][..., None])
    atmosphere(ctx, glow=0.2, smoke_d=0.0)


def r_s06(ctx):
    a, b = TL.BEATS["iris_close"]
    p, _ = ctx["shot"].track(ctx["f"], "lens")
    if p is not None:
        u, v, z = screen_pt(ctx["cam"], p)
        k = 1 - smoothstep(a, b, ctx["f"])
        ctx["rgb"] += fx.soft_glow(ctx["W"], ctx["H"], u, v, 0.12 * ctx["W"], (1.0, 0.05, 0.02), 0.5 * k)
    atmosphere(ctx, glow=0.15, smoke_d=0.04)


def r_s07(ctx):
    f = ctx["f"]
    k = 0.0
    for h in TL.BEATS["bass_hits"]:
        if 0 <= f - h < 10:
            k = max(k, math.exp(-(f - h) / 2.5))
    H = ctx["H"]
    ctx["shake"] = (5.0 * k * math.sin(f * 2.7) * H / 1080, 7.0 * k * math.cos(f * 3.1) * H / 1080)
    ctx["zoom"] = 1.0 + 0.015 * k
    ctx["ca"] += 0.004 * k
    ctx["exposure"] *= 1.0 + 0.25 * k
    atmosphere(ctx, glow=0.2, smoke_d=0.06)


def r_s08(ctx):
    sp = fountain(ctx["variant"], "s08_redline", 420.0, 0.6, (0.6, 2.2), (0.15, 0.5), 8, (0.0, -0.4, 1.0),
                  TL.BEATS["redline_start"] / TL.FPS, 99.0, 0.004)
    if sp is not None:
        add_layer_particles(ctx, lambda L: sp.draw(L, ctx["cam"], ctx["t"], ctx["depth"], gain=0.9))
    p, _ = ctx["shot"].track(ctx["f"], "red")
    if p is not None:
        u, v, z = screen_pt(ctx["cam"], p)
        if z > 0:
            ctx["rgb"] += fx.soft_glow(ctx["W"], ctx["H"], u, v, 0.07 * ctx["W"], (1.0, 0.04, 0.02), 0.3)
    atmosphere(ctx, glow=0.25, smoke_d=0.07)


def r_s09(ctx):
    a, b = TL.BEATS["grinder"]
    sp = fountain(ctx["variant"], "s09_sparks", 1400.0, 0.38, (2.5, 7.5), (0.25, 0.9), 9, (-0.55, -0.75, 0.35),
                  a / TL.FPS, b / TL.FPS + 1, 0.005)
    if sp is not None:
        add_layer_particles(ctx, lambda L: sp.draw(L, ctx["cam"], ctx["t"], ctx["depth"], gain=1.3))
    p, _ = ctx["shot"].track(ctx["f"], "contact")
    if p is not None:
        u, v, z = screen_pt(ctx["cam"], p)
        fl = 1 + 0.4 * TL.value_noise_1d(ctx["f"] * 3.7, 12)
        ctx["rgb"] += fx.soft_glow(ctx["W"], ctx["H"], u, v, 0.06 * ctx["W"], (1.0, 0.5, 0.15), 1.2 * fl)
    ctx["rgb"] = fx.anamorphic_streak(ctx["rgb"], threshold=4.0, strength=0.04)
    atmosphere(ctx, glow=0.2, smoke_d=0.08, smoke_color=(0.45, 0.2, 0.08))


def r_s10(ctx):
    f = ctx["f"]
    p, axis = ctx["shot"].track(f, "lens")
    face = 0.0
    if p is not None:
        u, v, z = screen_pt(ctx["cam"], p)
        to_cam = ctx["cam"].pos - p
        to_cam /= np.linalg.norm(to_cam)
        face = max(0.0, float(np.dot(axis / np.linalg.norm(axis), to_cam)))
        k = face ** 6
        W, H = ctx["W"], ctx["H"]
        ctx["rgb"] += fx.soft_glow(W, H, u, v, 0.18 * W, (1.0, 0.18, 0.06), 3.5 * k)
        ctx["rgb"] += fx.soft_glow(W, H, u, v, 0.05 * W, (1.0, 0.7, 0.5), 6.0 * k ** 2)
        if k > 0.02:
            ctx["rgb"] = fx.god_rays(ctx["rgb"], u, v, strength=0.8 * k, decay=0.96, threshold=1.5)
        ctx["flash_xy"] = (u, v)
    ctx["rgb"] = fx.anamorphic_streak(ctx["rgb"], threshold=2.5, strength=0.10, color=(1.0, 0.25, 0.12))
    atmosphere(ctx, glow=0.3, smoke_d=0.14, smoke_color=(0.55, 0.08, 0.04))
    # the flare swallows the frame right before the cut into the vortex
    f1 = TL.SHOT["s10_spot"][1]
    ctx["white"] = max(ctx.get("white", 0.0), smoothstep(f1 - 5, f1, f) ** 1.5 * 0.9)


def r_s11(ctx):
    f, t = ctx["f"], ctx["t"]
    sh = ctx["shot"]
    prev = sh.camera(f - 1) or ctx["cam"]
    em = embers("vortex")
    # streaked dust: static world points smeared by the camera motion
    pts = em.pos(t)
    u1, v1, z1 = ctx["cam"].project(pts)
    u0, v0, z0 = prev.project(pts)
    ok = (z1 > 0.2) & (z0 > 0.2)
    cols = np.tile(np.array(EMBER, np.float32), (ok.sum(), 1)) * em.bright[ok, None].astype(np.float32) * 2.0
    layer = np.zeros_like(ctx["rgb"])
    u0s = u1[ok] + (u0[ok] - u1[ok]) * 0.5
    v0s = v1[ok] + (v0[ok] - v1[ok]) * 0.5
    P.splat_lines(layer, u0s, v0s, u1[ok], v1[ok], cols)
    ctx["rgb"] += cv2.GaussianBlur(layer, (0, 0), 0.8)
    e = 0.0
    for h in TL.BEATS["vortex_hits"]:
        if 0 <= f - h < 4:
            e = max(e, math.exp(-(f - h) / 0.7))
    ctx["exposure"] *= 1.0 + 0.4 * e
    ctx["white"] = max(ctx.get("white", 0.0), 0.22 * e)
    k0 = f - TL.SHOT["s11_vortex"][0]
    if k0 < 4:                                   # coming out of the spotlight burst
        ctx["white"] = max(ctx["white"], 0.9 * math.exp(-k0 / 1.2))
    atmosphere(ctx, glow=0.45, smoke_d=0.12, smoke_color=(0.6, 0.12, 0.04))


def r_s12(ctx):
    """Flash and suck-back to black, generated entirely in 2D."""
    f = ctx["f"]
    f0, f1 = TL.SHOT["s12_flash"]
    W, H = ctx["W"], ctx["H"]
    k = (f - f0)
    rgb = np.zeros((H, W, 3), np.float32)
    if k < 6:
        a = math.exp(-k / 1.6)
        rgb += fx.soft_glow(W, H, W * 0.5, H * 0.5, 0.8 * max(W, H), (1.0, 0.88, 0.78), 6.0 * a ** 1.5)
        rgb += fx.soft_glow(W, H, W * 0.5, H * 0.5, 0.33 * max(W, H), (1.0, 0.06, 0.02), 2.5 * (1 - a))
    else:
        u = (f - f0 - 6) / max(1, f1 - f0 - 6)
        g = fx.soft_glow(W, H, W * 0.5, H * 0.5, max(W, H) * (0.33 - 0.28 * u), (1.0, 0.05, 0.02),
                         2.0 * (1 - u) ** 2.2)
        rgb += g
    ctx["rgb"] = rgb
    ctx["alpha"] = np.zeros((H, W), np.float32)
    ctx["vig"] = 0.5


def r_title(ctx):
    f, t = ctx["f"], ctx["t"]
    v = ctx["variant"]
    src = ctx["rgb"].copy()
    TT = TL.TITLE
    cams = dict(TL.TITLE_CAMS)
    if f >= cams["cam_enth"]:
        floor_reflection(ctx, src)
    sp = title_sparks(v)
    if sp is not None:
        add_layer_particles(ctx, lambda L: sp.draw(L, ctx["cam"], t, ctx["depth"], gain=1.15))
    add_layer_particles(ctx, lambda L: embers("title").draw(L, ctx["cam"], t, ctx["depth"], gain=0.55))
    hero = TT["hero_impact"]
    pulse = math.exp(-max(f - hero, 0) / 12.0) * (f >= hero)
    atmosphere(ctx, glow=0.55 + 0.35 * pulse, smoke_d=0.13)
    # impact flashes on the four MASS slams and the hero hit
    fl = 0.0
    for s in (TT["slam_M"], TT["slam_A"], TT["slam_S1"], TT["slam_S2"]):
        if 0 <= f - s < 4:
            fl = max(fl, math.exp(-(f - s) / 1.2))
    ctx["exposure"] *= 1.0 + 0.45 * fl + 0.12 * pulse
    ctx["ca"] += 0.003 * fl
    ctx["rgb"] = fx.anamorphic_streak(ctx["rgb"], threshold=14.0, strength=0.015)
    if f < TL.SHOT["s13_title"][0] + 3:        # out of black
        ctx["exposure"] *= smoothstep(TL.SHOT["s13_title"][0] - 1, TL.SHOT["s13_title"][0] + 3, f)
    a, b = TT["fade"]
    if f >= a:
        ctx["exposure"] *= 1 - smoothstep(a, b, f) ** 1.3


RECIPES = {"s01_chain": r_s01, "s02_reel": r_s02, "s03_film": r_s03, "s04_projector": r_s04, "s05_ticket": r_s05,
           "s06_lens": r_s06, "s07_speaker": r_s07, "s08_redline": r_s08, "s09_sparks": r_s09, "s10_spot": r_s10,
           "s11_vortex": r_s11, "s12_flash": r_s12, "s13_title": r_title, "s14_hero": r_title}
GRADE = {   # exposure, gain (rgb), saturation, contrast
    "s01_chain": (1.15, (0.98, 1.0, 1.05), 0.95, 1.05),
    "s02_reel": (1.05, (1.05, 1.0, 0.95), 1.0, 1.05),
    "s03_film": (1.0, (1.06, 1.0, 0.92), 1.0, 1.04),
    "s04_projector": (1.0, (1.05, 1.0, 0.94), 1.0, 1.05),
    "s05_ticket": (1.05, (1.05, 1.0, 0.94), 1.05, 1.05),
    "s06_lens": (1.1, (1.02, 1.0, 1.0), 1.0, 1.05),
    "s07_speaker": (1.15, (1.02, 1.0, 1.0), 1.0, 1.06),
    "s08_redline": (1.15, (1.03, 1.0, 0.98), 1.0, 1.06),
    "s09_sparks": (1.2, (1.04, 1.0, 0.96), 1.0, 1.06),
    "s10_spot": (1.1, (1.03, 1.0, 0.98), 1.0, 1.06),
    "s11_vortex": (1.15, (1.04, 1.0, 0.97), 1.0, 1.06),
    "s12_flash": (1.0, (1.0, 1.0, 1.0), 1.0, 1.0),
    "s13_title": (1.0, (1.01, 1.0, 1.0), 1.0, 1.06),
    "s14_hero": (1.0, (1.01, 1.0, 1.0), 1.0, 1.06),
}


class Context(dict):
    pass


_SHOTS = {}
_NOISE = None
_GRAIN = {}


def shot_obj(variant, sid):
    key = (variant, sid)
    if key not in _SHOTS:
        _SHOTS[key] = Shot(variant, sid)
    return _SHOTS[key]


def render_frame(variant, f):
    global _NOISE
    W, H = SIZES[variant]
    if _NOISE is None:
        _NOISE = fx.NoiseBank()
    if variant not in _GRAIN:
        _GRAIN[variant] = fx.Grain(W, H)
    sid = TL.shot_of(f)
    sh = shot_obj(variant, sid)
    ctx = Context(f=f, t=f / TL.FPS, variant=variant, shot=sh, W=W, H=H, noise=_NOISE, exposure=1.0, ca=0.0012,
                  shake=(0.0, 0.0), zoom=1.0, white=0.0, vig=0.38,
                  shot_index=[s[0] for s in TL.SHOTS].index(sid))
    if sid == "s12_flash":
        ctx["cam"] = None
        r_s12(ctx)
    else:
        data = sh.frame(f)
        if data is None:
            rgb = np.zeros((H, W, 3), np.float32)
            alpha = np.zeros((H, W), np.float32)
            depth = np.full((H, W), 1e10, np.float32)
        else:
            rgb, alpha, depth = data
        ctx.update(rgb=fx.rolloff(rgb), alpha=alpha, depth=depth, cam=sh.camera(f))
        if ctx["cam"] is not None:
            RECIPES[sid](ctx)
    exp, gain, sat, con = GRADE[sid]
    img = ctx["rgb"]
    img = fx.bloom(img, strength=0.16, threshold=0.85)
    img = fx.chromatic(img, ctx["ca"])
    if ctx["white"] > 0:      # light burst: brighten the scene and blow out a hot centre
        w_ = ctx["white"]
        cx, cy = ctx.get("flash_xy", (ctx["W"] / 2, ctx["H"] / 2))
        img = img * (1.0 + 1.6 * w_) + fx.soft_glow(ctx["W"], ctx["H"], cx, cy, 0.6 * max(ctx["W"], ctx["H"]),
                                                     (1.0, 0.86, 0.72), 2.4 * w_ ** 1.3)
    img = fx.tonemap(img, exposure=exp * ctx["exposure"])
    img = fx.grade(img, gain=gain, sat=sat, contrast=con)
    up = getattr(sh, "upscale", 1.0)
    if up > 1.05:   # frames rendered below output size: restore some acuity after the upscale
        amt = min(0.6, 0.35 * (up - 1.0) / 0.33)
        img = np.clip(img + amt * (img - cv2.GaussianBlur(img, (0, 0), 1.1 * up)), 0, 1)
    img = fx.shake(img, *ctx["shake"], zoom=ctx["zoom"])
    img = fx.vignette_cached(img, amount=ctx["vig"])
    img = _GRAIN[variant].apply(img, f, amount=0.022)
    return np.clip(img, 0, 1)


def to_u8(img):
    rng = np.random.default_rng()
    return np.clip(img * 255.0 + rng.uniform(-0.5, 0.5, img.shape), 0, 255).astype(np.uint8)


def _worker(args):
    variant, f = args
    img = render_frame(variant, f)
    return f, to_u8(img).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="16x9", choices=list(SIZES))
    ap.add_argument("--frames", default="")
    ap.add_argument("--png", default="", help="write PNG stills to this folder instead of a video")
    ap.add_argument("--out", default="")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--crf", type=int, default=14)
    a = ap.parse_args()
    W, H = SIZES[a.variant]
    if a.frames:
        frames = []
        for part in a.frames.split(","):
            if "-" in part:
                x, y = part.split("-")
                frames += list(range(int(x), int(y) + 1))
            else:
                frames.append(int(part))
    else:
        frames = list(range(TL.N_FRAMES))
    jobs = [(a.variant, f) for f in frames]
    from multiprocessing import Pool
    if a.png:
        os.makedirs(a.png, exist_ok=True)
        with Pool(a.workers) as pool:
            for f, buf in pool.imap(_worker, jobs):
                img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                cv2.imwrite(os.path.join(a.png, f"{f:04d}.png"), img[..., ::-1])
                print("png", f, flush=True)
        return
    out = a.out or os.path.join(ROOT, "build", f"picture_{a.variant}.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(TL.FPS),
           "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-tune", "film",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(a.workers) as pool:
        for f, buf in pool.imap(_worker, jobs, chunksize=2):
            proc.stdin.write(buf)
            if f % 30 == 0:
                print("frame", f, flush=True)
    proc.stdin.close()
    proc.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
