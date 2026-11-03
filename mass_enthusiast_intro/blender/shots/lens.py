"""s06_lens - a cine lens stares back; its iris snaps shut over a red glow."""
from __future__ import annotations

import math
import os
import sys

from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common as C  # noqa: E402
import assets as A  # noqa: E402
import timeline as TL  # noqa: E402
from timeline import lerp, smoothstep, ease_in_out, ease_in_cubic  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s06_lens"]
    lens, blades, back_e = A.cine_lens("lens", M)
    lens.rotation_euler = (math.radians(90), 0, 0)          # optical axis (+Z local) -> -Y world
    lens.rotation_euler = (math.radians(-90), 0, math.radians(180))
    C.area_light("key", (-1.6, -2.4, 1.8), (0, 0, 0), energy=160, size=1.2, color=(0.92, 0.95, 1.0))
    C.area_light("rim", (1.9, -0.6, -1.4), (0, 0, 0), energy=300, size=1.0, color=(1.0, 0.25, 0.06))
    C.card("card", (-0.6, -5.0, 2.2), (0, 0, 0), 2.4, 0.12, strength=6.0)
    C.card("card2", (2.4, -4.5, -0.6), (0, 0, 0), 0.12, 1.6, color=(1.0, 0.2, 0.08), strength=4.0)
    a, b = TL.BEATS["iris_close"]
    for f in range(f0 - 3, f1 + 4):
        u = ease_in_cubic(smoothstep(a, b, f) ** 0.8)
        opening = lerp(0.6, 0.012, u)
        A.set_iris(blades, opening, rot=lerp(0.0, 0.9, u))
        for bl in blades:
            bl.keyframe_insert("location", frame=f)
            bl.keyframe_insert("rotation_euler", frame=f)
        C.key_value(back_e.outputs[0], f, 5.0 * (1.0 + 0.1 * math.sin(f * 1.3)))
    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        d = lerp(2.6, 2.1, ease_in_out(u)) * (1.1 if v else 1.0)
        a_ = lerp(0.32, 0.18, u)
        return (d * math.sin(a_), -d * math.cos(a_), lerp(0.28, 0.12, u))

    def tgt(f):
        return (0.0, 0.0, 0.0)

    cam = C.camera("cam", lens=50, loc=loc(f0), target=tgt(f0), fstop=2.8)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(-4.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length - 0.1, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam), meta={}, track={"lens": lens})
