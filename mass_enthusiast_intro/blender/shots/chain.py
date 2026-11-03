"""s01_chain - a heavy steel chain turning in the dark; light finds it link by link.

The camera tracks down the chain in macro, the bottom ring turns to face us and we
push into its hole: darkness inside a circle, which match-cuts to the reel hub.
"""
from __future__ import annotations

import math
import os
import random
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common as C  # noqa: E402
import assets as A  # noqa: E402
import timeline as TL  # noqa: E402
from timeline import lerp, clamp, smoothstep, ease_in_out, ease_in_cubic  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    random.seed(4)
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s01_chain"]
    top = 7.2
    root, links = A.hanging_chain("chain", 7, mat=M["chain"])
    root.location = (0, 0, top)
    sp = A.chain_spacing()
    ring = A.ring("ring", R=0.62, t=0.15, mat=M["chain"])
    ring_piv = C.empty("ring_pivot")
    ring_piv.parent = root
    ring_piv.location = (0, 0, -(len(links) - 1) * sp - 0.91)
    ring.parent = ring_piv
    ring.location = (0, 0, 0)

    # --- lights (all dark at frame 0)
    strip = C.area_light("strip", (2.8, -1.5, 6.0), (0, 0, 5.5), energy=0.0, size=0.12, size_y=5.0,
                         color=(0.92, 0.95, 1.0))
    key = C.spot_light("key", (1.0, -1.2, 9.5), (0, 0, 4.0), energy=0.0, color=(0.9, 0.93, 1.0), size_deg=28,
                       blend=0.6, radius=0.2)
    red = C.area_light("red_rim", (-3.2, 2.6, 2.0), (0, 0, 2.0), energy=0.0, size=2.5, color=(1.0, 0.06, 0.03))
    warm = C.area_light("warm_low", (2.5, 1.8, -0.5), (0, 0, 1.5), energy=0.0, size=2.0, color=(1.0, 0.35, 0.08))
    card, card_e = C.card("card", (0.0, -6.0, 6.0), (0, 0, 4), 6.0, 1.2, color=(0.9, 0.93, 1.0), strength=0.0)
    beat = TL.BEATS

    def chain_rot(f):
        t = f / TL.FPS
        return (math.radians(2.0) * math.sin(t * 1.4), math.radians(1.6) * math.sin(t * 1.1 + 1), 0.6 + 0.22 * t)

    for f in range(f0 - 3, f1 + 4):
        t = f / TL.FPS
        C.key_obj(root, f, rot=chain_rot(f))
        # the bottom ring swings round to face the camera near the end
        u = smoothstep(beat["ring_turn"] - 6, beat["ring_turn"] + 18, f)
        C.key_obj(ring_piv, f, rot=(0.0, 0.0, lerp(0.9, 0.12 - chain_rot(f)[2], u)))
        # light build-up: the strip light orbits and brightens, then the key and rims join
        g = smoothstep(beat["chain_first_glint"] - 6, beat["chain_first_glint"] + 30, f)
        ang = lerp(-0.9, 1.6, t / 5.0)
        strip.location = (3.0 * math.cos(ang), 3.0 * math.sin(ang) - 1.2, lerp(6.6, 1.0, ease_in_out(t / 5.0)))
        C.look_at(strip, (0, 0, strip.location.z - 0.3))
        strip.keyframe_insert("location", frame=f)
        strip.keyframe_insert("rotation_euler", frame=f)
        C.key_value(strip.data, f, 520.0 * g, attr="energy")
        C.key_value(key.data, f, 900.0 * smoothstep(sec(0.9), sec(2.2), f), attr="energy")
        C.key_value(red.data, f, 1400.0 * smoothstep(sec(1.8), sec(4.4), f) ** 1.5, attr="energy")
        C.key_value(warm.data, f, 300.0 * smoothstep(sec(3.0), sec(4.6), f), attr="energy")
        C.key_value(card_e.inputs["Strength"], f, 3.0 * g)

    # --- camera: macro tracking down the chain, then into the ring
    v = variant == "9x16"
    ring_z = top + ring_piv.location.z

    def loc(f):
        t = (f - f0) / (f1 - f0)
        z = lerp(ring_z + 3.3, ring_z + 0.12, ease_in_out(clamp(t / 0.80)))
        orbit = lerp(-0.5, 0.12, ease_in_out(clamp(t / 0.9)))
        d = lerp(3.5, 2.7, t)
        push = ease_in_cubic(clamp((t - 0.88) / 0.12))
        d = lerp(d, 0.4, push)
        return (d * math.sin(orbit), -d * math.cos(orbit), z + 0.04 * math.sin(t * 5))

    def tgt(f):
        t = (f - f0) / (f1 - f0)
        z = lerp(ring_z + 3.0, ring_z, ease_in_out(clamp(t / 0.80)))
        return (0.0, 0.0, z)

    cam = C.camera("cam", lens=50, loc=loc(f0), target=tgt(f0), fstop=2.0)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(-4 + 6 * (f - f0) / (f1 - f0)),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length - 0.05, pad=3)
    meta = dict(dust=True)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam), meta=meta,
                track={"ring": ring})


def sec(t):
    return TL.sec(t)
