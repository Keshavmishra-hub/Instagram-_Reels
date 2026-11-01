"""Choreography of the title reveal (pure Python, shared by Blender and the compositor).

Concept - "forged, then assembled": every letter is a heavy gunmetal frame whose
interior is filled with molten metal. A brushed-steel face plate slams into each
frame; the impact squeezes sparks out through the glowing groove, and the molten
line cools to a dark crimson seam that stays alive in the hero shot.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import timeline as TL  # noqa: E402
from timeline import clamp, smoothstep, ease_in_cubic, ease_out_cubic, lerp  # noqa: E402

DEPTH = 0.22          # letter depth (in MASS cap-height units, scaled per glyph)
RAISE = 0.022         # rim / plate height above the molten floor
PLATE_TRAVEL = 1.6    # how far the plate travels for its slam (cap-height units)
SLAM_FRAMES = 5       # frames for the plate to travel into the frame


def slam_frames():
    """Global slam frame for each glyph index in lockup order (M A S S E N T H U S I A S T)."""
    t = TL.TITLE
    return [t["slam_M"], t["slam_A"], t["slam_S1"], t["slam_S2"], *t["enth_slams"]]


def pour_frame(i):
    """Frame at which the molten interior starts to glow."""
    s = slam_frames()[i]
    if i < 4:   # MASS: the interior is already glowing when its close-up starts
        cam_starts = [TL.sec(19.0), TL.sec(19.6), TL.sec(20.2), TL.sec(20.8)]
        return cam_starts[i] - 8
    return s - 9


def plate_direction(i):
    """Unit direction (letter-local: x right, y up, z towards camera) the plate comes from."""
    dirs = [(-0.45, 0.85, 0.75), (0.5, 0.9, 0.7), (-0.35, 0.95, 0.6), (0.4, 0.9, 0.75)]
    d = dirs[i] if i < 4 else ((0.15, 1.0, 0.55) if i % 2 else (-0.15, 1.0, 0.55))
    L = math.sqrt(sum(c * c for c in d))
    return tuple(c / L for c in d)


def plate_offset(i, f):
    """Plate displacement from its seat (letter-local units of cap height); 0 = seated."""
    s = slam_frames()[i]
    if f >= s:
        return (0.0, 0.0, 0.0)
    t = (f - (s - SLAM_FRAMES)) / SLAM_FRAMES
    dist = PLATE_TRAVEL * (1.0 + 0.3 * (-t)) if t <= 0 else PLATE_TRAVEL * (1.0 - ease_in_cubic(t))
    d = plate_direction(i)
    return (d[0] * dist, d[1] * dist, d[2] * dist)


def flip(i, f):
    """ENTHUSIAST letters lie flat (face up, toppled backwards) and flip upright just
    before their plate strikes. Returns the tilt in radians (0 = upright)."""
    if i < 4:
        return 0.0
    s = slam_frames()[i]
    a, b = s - 10, s - 2
    if f <= a:
        return math.radians(90.0)
    if f >= b:
        t = (f - b) / TL.FPS          # tiny settle wobble after landing
        return math.radians(-4.0) * math.exp(-t / 0.08) * math.cos(2 * math.pi * 9 * t)
    u = (f - a) / (b - a)
    return math.radians(90.0) * (1 - ease_in_cubic(u))


def plate_visible(i, f):
    s = slam_frames()[i]
    return f >= s - SLAM_FRAMES - 6


def recoil(i, f):
    """Whole-letter jolt backwards after the slam (damped), in units."""
    s = slam_frames()[i]
    t = (f - s) / TL.FPS
    if t < 0:
        return 0.0
    return -0.035 * math.exp(-9 * t) * math.cos(2 * math.pi * 7 * t)


def glow(i, f):
    """(temperature K, emission strength) of the molten floor of glyph i."""
    s = slam_frames()[i]
    p = pour_frame(i)
    hero = TL.TITLE["hero_impact"]
    if f < p:
        return 900.0, 0.0
    if f < s:
        k = smoothstep(p, p + 6, f)
        flick = 0.9 + 0.1 * math.sin(f * 1.7 + i)
        return 1650.0 + 150 * k, 22.0 * k * flick
    # after the slam: white-hot flash, then cooling
    t = (f - s) / TL.FPS
    temp = 980.0 + 1500.0 * math.exp(-t / 0.5)
    stren = 2.6 + 70.0 * math.exp(-t / 0.3)
    # the sweeps re-energise the seam a little
    for a, b in (TL.TITLE["sweep_mass"], TL.TITLE["sweep_all"]):
        if a <= f <= b + 15:
            stren += 4.0 * math.sin(math.pi * clamp((f - a) / (b + 15 - a)))
    if f >= hero:
        th = (f - hero) / TL.FPS
        temp += 420.0 * math.exp(-th / 0.45)
        stren += 14.0 * math.exp(-th / 0.35)
    # breathing in the hero shot
    if f >= TL.SHOT["s14_hero"][0]:
        stren *= 1.0 + 0.08 * math.sin(f * 0.21)
    return temp, stren


# ----------------------------------------------------------------------------- cameras
def _cam_shake(f, events, amp=0.025, decay=0.25, seed=3):
    dx = dy = dz = 0.0
    for e in events:
        t = (f - e) / TL.FPS
        if t < 0 or t > 1.2:
            continue
        k = amp * math.exp(-t / decay)
        dx += k * TL.value_noise_1d(f * 0.9, seed)
        dy += k * TL.value_noise_1d(f * 0.9, seed + 11) * 0.5
        dz += k * TL.value_noise_1d(f * 0.9, seed + 23)
    return dx, dy, dz


def camera_plan(variant, letters):
    """Return list of (name, f0, f1, loc_fn, tgt_fn, lens_fn, roll_fn, fstop).

    `letters` maps glyph index -> (cx, cz, cap) of the letter centre in world space.
    """
    v = variant == "9x16"
    W = TL.TITLE
    slams = slam_frames()
    plan = []

    def letter_cam(name, f0, f1, i, side, height, dist0, dist1, lens, roll):
        cx, cz, cap = letters[i]

        def loc(f):
            t = (f - f0) / (f1 - f0)
            d = lerp(dist0, dist1, ease_out_cubic(t))
            sx, sy, sz = _cam_shake(f, [slams[i]], amp=0.03)
            ang = math.radians(side + 10 * t)
            return (cx + d * math.sin(ang) + sx, -d * math.cos(ang) + sy, cz + height + 0.15 * t + sz)

        def tgt(f):
            return (cx + 0.02 * math.sin(f * 0.3), 0.0, cz + 0.02)

        return (name, f0, f1, loc, tgt, (lambda f: lens), (lambda f: math.radians(roll)), 2.2)

    # vertical frames keep the horizontal field of view; letters should fill more of
    # the narrow frame, so the camera moves in a little on the wide shots
    k = 0.95 if v else 1.0
    cams = dict(TL.TITLE_CAMS)
    plan.append(letter_cam("cam_M", cams["cam_M"], cams["cam_A"] - 1, 0, -28, -0.35, 2.6 * k, 2.15 * k, 32, -6))
    plan.append(letter_cam("cam_A", cams["cam_A"], cams["cam_S1"] - 1, 1, 24, 0.25, 2.4 * k, 2.0 * k, 35, 5))
    plan.append(letter_cam("cam_S1", cams["cam_S1"], cams["cam_S2"] - 1, 2, -16, -0.55, 2.5 * k, 2.1 * k, 30, 4))
    plan.append(letter_cam("cam_S2", cams["cam_S2"], cams["cam_wide"] - 1, 3, 12, 0.1, 2.3 * k, 1.95 * k, 35, -3))

    # wide: start close on the second S, pull back and centre MASS
    mx = sum(letters[i][0] for i in range(4)) / 4.0
    mz = letters[0][1]
    fw0, fw1 = cams["cam_wide"], cams["cam_enth"] - 1

    def wide_loc(f):
        t = ease_out_cubic((f - fw0) / 26.0)
        t2 = clamp((f - fw0) / (fw1 - fw0))
        d = lerp(2.6, 6.2 if not v else 4.95, t) + 0.25 * t2
        x = lerp(letters[3][0] * 0.6, mx, t)
        sx, sy, sz = _cam_shake(f, [W["mass_lock"]], amp=0.05)
        return (x + 0.25 * math.sin(t2 * 1.2) + sx, -d + sy, mz - 0.55 + 0.25 * t2 + sz)

    def wide_tgt(f):
        t = ease_out_cubic((f - fw0) / 26.0)
        return (lerp(letters[3][0] * 0.6, mx, t), 0.0, mz + 0.05)

    plan.append(("cam_wide", fw0, fw1, wide_loc, wide_tgt, (lambda f: 40.0),
                 (lambda f: math.radians(-2 + 2 * clamp((f - fw0) / (fw1 - fw0)))), 4.0))

    # ENTHUSIAST tracking shot, low angle, travelling with the cascade
    ex0 = letters[4][0]
    ex1 = letters[13][0]
    ez = letters[4][1]
    fe0, fe1 = cams["cam_enth"], cams["cam_pull"] - 1
    first, last = slams[4], slams[13]

    def enth_x(f):
        return lerp(ex0 + 0.25, ex1 - 0.55, smoothstep(first - 12, last + 4, f))

    def enth_loc(f):
        sx, sy, sz = _cam_shake(f, slams[4:], amp=0.012, decay=0.12)
        d = 2.9 if not v else 2.5
        return (enth_x(f) - 0.85 + sx, -d + sy, ez - 0.05 + sz)

    def enth_tgt(f):
        return (enth_x(f) + 0.15, 0.0, ez + 0.12)

    plan.append(("cam_enth", fe0, fe1, enth_loc, enth_tgt, (lambda f: 35.0), (lambda f: math.radians(3.0)), 3.5))

    # pull back to the full lock-up
    fp0, fp1 = cams["cam_pull"], TL.SHOT["s13_title"][1]
    cz = 0.80

    def pull_loc(f):
        t = ease_out_cubic((f - fp0) / (fp1 - fp0))
        d = lerp(3.4, 8.0, t) * (0.86 if v else 1.0)
        x = lerp(ex1 * 0.55, 0.0, t)
        return (x, -d, lerp(0.02, 0.10, t))

    def pull_tgt(f):
        t = ease_out_cubic((f - fp0) / (fp1 - fp0))
        return (lerp(ex1 * 0.55, 0.0, t), 0.0, lerp(0.3, 0.86, t))

    plan.append(("cam_pull", fp0, fp1, pull_loc, pull_tgt, (lambda f: 45.0),
                 (lambda f: math.radians(lerp(2.5, 0.0, clamp((f - fp0) / (fp1 - fp0))))), 5.6))
    return plan


def hero_camera(variant):
    v = variant == "9x16"
    f0, f1 = TL.SHOT["s14_hero"]
    hero = TL.TITLE["hero_impact"]

    def loc(f):
        t = clamp((f - f0) / (f1 - f0))
        d = lerp(8.0, 6.65, 1 - (1 - t) ** 1.6) * (0.86 if v else 1.0)
        sx, sy, sz = _cam_shake(f, [hero], amp=0.02, decay=0.3, seed=9)
        return (0.0 + sx, -d + sy, 0.10 + 0.04 * t + sz)

    def tgt(f):
        return (0.0, 0.0, 0.86)

    return ("cam_hero", f0, f1, loc, tgt, (lambda f: 45.0), (lambda f: 0.0), 5.6)
