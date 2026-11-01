"""s11_vortex - every object of the sequence tumbles toward camera through firelight; the
camera accelerates through them. Hits on the beat flash the whole tunnel white-hot."""
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
from timeline import lerp, smoothstep, ease_in_cubic, clamp  # noqa: E402


def cam_y(f, f0, f1):
    u = clamp((f - f0) / (f1 - f0))
    # slow drift that ramps into a rush (speed ramp)
    return lerp(-2.0, 30.0, 0.18 * u + 0.82 * ease_in_cubic(u))


def build(variant="16x9", samples=16, scale=1.0):
    random.seed(31)
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s11_vortex"]
    objs = []
    kinds = ["chain", "reel", "lens", "ring", "chain", "proj", "reel", "chain", "ring", "lens", "chain", "reel",
             "ring", "chain", "proj", "chain", "reel", "lens", "chain", "ring", "chain", "reel", "chain", "lens"]
    for k, kind in enumerate(kinds):
        if kind == "chain":
            o, _ = A.hanging_chain(f"vc{k}", 3, mat=M["chain"])
        elif kind == "reel":
            o = A.film_reel(f"vr{k}", M)
        elif kind == "lens":
            o, blades, be = A.cine_lens(f"vl{k}", M)
            A.set_iris(blades, 0.35, 0.3)
            be.inputs["Strength"].default_value = 6.0
        elif kind == "ring":
            o = C.empty(f"vg{k}")
            A.ring(f"vg{k}_r", R=0.62, t=0.15, mat=M["chain"]).parent = o
        else:
            o, le = A.projector(f"vp{k}", M)
            le.inputs["Strength"].default_value = 12.0
        y = 2.0 + k * 1.35 + random.uniform(-0.3, 0.3)
        ang = k * 2.39996 + random.uniform(-0.3, 0.3)          # golden-angle spiral around the path
        rad = random.uniform(0.95, 1.55)
        sc_ = random.uniform(0.9, 1.3)
        spin = Vector((random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.5), random.uniform(-1.5, 1.5)))
        base = Vector((random.uniform(0, 6.28), random.uniform(0, 6.28), random.uniform(0, 6.28)))
        objs.append((o, y, ang, rad, sc_, spin, base))
    fire_lights = [C.point_light(f"fire{k}", (0, 0, 0), energy=0.0, color=(1.0, 0.33, 0.07), radius=0.6)
                   for k in range(4)]
    C.area_light("red_top", (0, 12, 6), (0, 12, 0), energy=0.0, size=12, size_y=30, color=(1.0, 0.05, 0.03))
    flash = C.area_light("flash", (0, -1, 3), (0, 10, 0), energy=0.0, size=8, color=(1.0, 0.92, 0.85))
    C.card("card", (0, -6, 3), (0, 10, 0), 12, 1.0, strength=2.0)
    hits = TL.BEATS["vortex_hits"]
    for f in range(f0 - 3, f1 + 4):
        t = (f - f0) / TL.FPS
        cy = cam_y(f, f0, f1)
        for (o, y, ang, rad, s_, spin, base) in objs:
            a = ang + 0.55 * t
            C.key_obj(o, f, loc=(rad * math.cos(a), y, rad * math.sin(a) * 0.75),
                      rot=tuple(base[i] + spin[i] * t for i in range(3)), scale=s_)
        for k, L in enumerate(fire_lights):
            L.location = (1.6 * math.cos(k * 1.57 + t * 0.8), cy + 3.0 + 3.5 * k, -1.6)
            L.keyframe_insert("location", frame=f)
            C.key_value(L.data, f, 2600.0 * (1.0 + 0.3 * TL.value_noise_1d(f * 1.3, k)), attr="energy")
        e = 0.0
        for h in hits:
            d = f - h
            if 0 <= d < 8:
                e = max(e, 3500.0 * math.exp(-d / 1.8))
        C.key_value(flash.data, f, e, attr="energy")
        flash.location = (0, cy - 1.0, 3.0)
        flash.keyframe_insert("location", frame=f)
    bpy.data.objects["red_top"].data.energy = 3500.0
    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        return (0.25 * math.sin(u * 3.0), cam_y(f, f0, f1), 0.1 * math.cos(u * 2.0))

    def tgt(f):
        p = loc(f)
        return (p[0] * 0.3, p[1] + 10.0, p[2])

    cam = C.camera("cam", lens=24 if not v else 20, loc=loc(f0), target=tgt(f0), fstop=2.8)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(lerp(-8, 25, ((f - f0) / (f1 - f0)) ** 2)),
                  focus_fn=lambda f: 4.0, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam), meta=dict(hits=hits), track={})
