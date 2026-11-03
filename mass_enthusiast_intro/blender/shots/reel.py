"""s02_reel - out of the ring's darkness: a 35mm reel spinning, lamp light through its windows."""
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
from timeline import lerp, clamp, ease_out_cubic, smoothstep  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s02_reel"]
    reel = A.film_reel("reel", M)
    reel.rotation_euler = (math.radians(90), 0, 0)        # axis -> -Y (towards camera)
    reel2 = A.film_reel("reel_bg", M)
    reel2.location = (2.4, 3.5, 1.3)
    reel2.rotation_euler = (math.radians(80), math.radians(20), 0)

    lamp_m, lamp_e = C.mat_emission("lamp_m", (1.0, 0.6, 0.3), 0.0)
    lamp = A.disc("lamp", 0.75)
    lamp.location = (0.1, 1.6, 0.05)
    lamp.rotation_euler = (math.radians(90), 0, 0)
    C.assign(lamp, lamp_m)
    lamp.visible_camera = True
    C.area_light("key", (-2.2, -2.6, 2.4), (0, 0, 0), energy=260, size=1.6, color=(0.92, 0.95, 1.0))
    C.area_light("rim", (2.6, 1.0, 1.4), (0, 0, 0), energy=900, size=1.5, color=(1.0, 0.1, 0.04))
    C.card("card", (0, -6, 2.5), (0, 0, 0), 8, 1.0, color=(0.95, 0.96, 1.0), strength=2.5)
    C.card("card2", (-3, -5, -1.5), (0, 0, 0), 6, 0.5, color=(1.0, 0.4, 0.15), strength=1.2)

    for f in range(f0 - 3, f1 + 4):
        t = (f - f0) / TL.FPS
        C.key_obj(reel, f, rot=(math.radians(90), -2.4 * t - 0.3, 0))
        C.key_obj(reel2, f, rot=(math.radians(80), math.radians(20), 1.5 * t))
        flick = 1.0 + 0.12 * TL.value_noise_1d(f * 1.7, 5) + 0.06 * math.sin(f * 2.9)
        C.key_value(lamp_e.inputs["Strength"], f, 9.0 * flick * smoothstep(f0 - 2, f0 + 6, f))

    v = variant == "9x16"

    def loc(f):
        u = ease_out_cubic((f - f0) / (f1 - f0))
        d = lerp(0.55, 3.3 if not v else 3.6, u)
        a = lerp(0.0, -0.42, u)
        return (d * math.sin(a), -d * math.cos(a), lerp(0.0, 0.55, u))

    def tgt(f):
        u = ease_out_cubic((f - f0) / (f1 - f0))
        return (lerp(0.0, 0.15, u), 0.0, lerp(0.0, 0.05, u))

    cam = C.camera("cam", lens=40, loc=loc(f0), target=tgt(f0), fstop=2.2)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(lerp(10, -3, (f - f0) / (f1 - f0))),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length - 0.1, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(rays=dict(name="lamp", color=[1.0, 0.7, 0.4], strength=0.9)),
                track={"lamp": lamp})
