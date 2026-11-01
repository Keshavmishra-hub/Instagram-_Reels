"""s07_speaker - a big driver thumps twice; steel beads leap off the cone in slow motion."""
from __future__ import annotations

import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common as C  # noqa: E402
import assets as A  # noqa: E402
import timeline as TL  # noqa: E402
from timeline import lerp, smoothstep  # noqa: E402


def cone_z(r):
    """Height of the cone surface at radius r (matches assets.speaker's profile)."""
    t = min(max((r - 0.24) / 0.71, 0.0), 1.0)
    return 0.36 * t ** 0.75


def pump(f, hits):
    s = 0.0
    for h in hits:
        t = (f - h) / TL.FPS
        if t < -0.02:
            continue
        if t < 0:
            s += 0.5 * (1 + t / 0.02)
            continue
        s += math.exp(-t / 0.09) * math.cos(2 * math.pi * 5.5 * t)
    return s


def build(variant="16x9", samples=16, scale=1.0):
    random.seed(11)
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s07_speaker"]
    spk, moving, surround = A.speaker("spk", M)
    hits = TL.BEATS["bass_hits"]
    # steel beads resting on the cone
    bead_mesh = None
    beads = []
    for k in range(70):
        r = random.uniform(0.32, 0.9)
        a = random.uniform(0, 2 * math.pi)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=random.uniform(0.012, 0.024))
        b = C.mesh_object(f"bead{k}", bm)
        C.shade_smooth(b, 80)
        C.assign(b, M["chrome"])
        beads.append((b, r, a, random.uniform(0.75, 1.35)))
    C.area_light("key", (-1.5, -1.6, 2.4), (0, 0, 0.2), energy=260, size=1.5, color=(0.92, 0.95, 1.0))
    C.area_light("rim", (1.8, 2.2, 0.9), (0, 0, 0.2), energy=1300, size=1.4, color=(1.0, 0.08, 0.03))
    C.area_light("low", (2.2, -1.4, 0.4), (0, 0, 0.2), energy=180, size=1.0, color=(1.0, 0.4, 0.1))
    C.card("card", (-1.0, -3.6, 2.6), (0, 0, 0), 5, 0.6, strength=3.0)
    g = 3.2   # slow-motion gravity (units/s^2)
    for f in range(f0 - 3, f1 + 4):
        p = pump(f, hits)
        C.key_obj(moving, f, loc=(0, 0, 0.075 * p))
        C.key_obj(surround, f, scale=(1.0, 1.0, 1.0 + 0.2 * p))
        for (b, r, a, kv) in beads:
            z = 0.0
            for h in hits:
                t = (f - h) / TL.FPS
                if t <= 0:
                    continue
                v0 = 1.25 * kv * (1.0 - 0.4 * (r - 0.3))
                zz = v0 * t - 0.5 * g * t * t
                if zz > 0:
                    z = max(z, zz)
            drift = 0.03 * z
            x = (r + drift) * math.cos(a)
            y = (r + drift) * math.sin(a)
            C.key_obj(b, f, loc=(x, y, cone_z(r) + 0.02 + z + 0.075 * max(p, 0) * (z == 0)))
    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        a = lerp(-1.95, -1.6, u)
        d = lerp(2.25, 1.95, u) * (1.1 if v else 1.0)
        return (d * math.cos(a), d * math.sin(a), lerp(0.78, 0.68, u))

    def tgt(f):
        return (0.05, 0.1, 0.28)

    cam = C.camera("cam", lens=35, loc=loc(f0), target=tgt(f0), fstop=2.4)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(3.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam), meta=dict(shock=hits),
                track={"speaker": spk})
