"""s05_ticket - a theatre ticket tumbles in slow motion, burning in from its edges."""
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
from timeline import lerp, smoothstep, ease_in_out  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale, transparent=True)
    f0, f1 = TL.SHOT["s05_ticket"]
    tk, prog = A.ticket("ticket")
    fire = C.point_light("fire", (0.0, -0.25, -0.75), energy=0.0, color=(1.0, 0.42, 0.1), radius=0.25)
    fire.parent = tk
    C.area_light("key", (-1.8, -2.4, 2.0), (0, 0, 0), energy=90, size=1.4, color=(0.95, 0.95, 1.0))
    C.area_light("rim", (2.2, 1.5, 0.8), (0, 0, 0), energy=350, size=1.2, color=(1.0, 0.1, 0.04))
    for f in range(f0 - 3, f1 + 4):
        t = (f - f0) / TL.FPS
        u = (f - f0) / (f1 - f0)
        loc = (lerp(-0.12, 0.1, u), 0.0, lerp(0.35, -0.35, u))
        rot = (math.radians(lerp(58, 44, u)), math.radians(lerp(10, -12, u)), math.radians(lerp(-6, 8, u)))
        C.key_obj(tk, f, loc=loc, rot=rot)
        C.key_value(prog.outputs[0], f, lerp(0.02, 0.27, ease_in_out(u) ** 0.9))
        fl = 1.0 + 0.3 * TL.value_noise_1d(f * 1.9, 8)
        C.key_value(fire.data, f, 60.0 * fl * smoothstep(f0 - 3, f0 + 6, f), attr="energy")
    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        d = lerp(2.5, 2.1, u) * (1.15 if v else 1.0)
        return (lerp(-0.3, 0.2, u), -d, lerp(0.9, 0.5, u))

    def tgt(f):
        u = (f - f0) / (f1 - f0)
        return (lerp(-0.1, 0.1, u), 0.0, lerp(0.3, -0.3, u))

    cam = C.camera("cam", lens=45, loc=loc(f0), target=tgt(f0), fstop=2.0)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(6.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(embers=dict(src="ticket", rate=60)), track={"ticket": tk})
