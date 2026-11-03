"""s10_spot - a stage spotlight swings round on its yoke and stares straight into the lens."""
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
from timeline import lerp, smoothstep, ease_in_out, clamp  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s10_spot"]
    root, head, lens_e = A.spotlight("spot", M)
    root.location = (0, 0, 0)
    beam = C.spot_light("beam", (0, 0, 0.5), (0, -5, 0), energy=0.0, color=(1.0, 0.2, 0.08), size_deg=24,
                        blend=0.4, radius=0.3)
    beam.parent = head
    beam.location = (0, 0, 0.5)
    beam.rotation_euler = (math.pi, 0, 0)          # spot lights shine along their local -Z
    C.area_light("key", (-2.2, -1.8, 2.6), (0, 0, 0), energy=150, size=1.6, color=(0.9, 0.93, 1.0))
    C.area_light("rim", (2.0, 2.4, 1.0), (0, 0, 0), energy=1800, size=1.5, color=(1.0, 0.1, 0.04))
    C.area_light("top", (-0.5, 0.5, 3.0), (0, 0, 0), energy=400, size=1.5, color=(0.92, 0.95, 1.0))
    C.card("card", (0.0, -5.0, 2.2), (0, 0, 0), 6, 0.5, strength=3.0)
    face = TL.BEATS["spot_face"]
    for f in range(f0 - 3, f1 + 4):
        u = ease_in_out(clamp((f - f0) / (face - f0)))
        settle = math.exp(-max(f - face, 0) / 6.0) * math.sin(max(f - face, 0) * 0.7) * 0.04
        # head local +Z is the beam axis; rotate from pointing up-left to pointing at the camera (-Y)
        tilt = lerp(math.radians(-25), math.radians(90), u) + settle
        pan = lerp(math.radians(-55), math.radians(-6), u)
        C.key_obj(head, f, rot=(tilt, 0.0, pan))
        C.key_obj(root, f, rot=(0.0, 0.0, pan * 0.0))
        C.key_value(lens_e.inputs["Strength"], f, 3.0 * (1.0 + 0.05 * math.sin(f * 1.9)))
        C.key_value(beam.data, f, 2500.0, attr="energy")
    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        return (lerp(0.55, 0.25, u), lerp(-3.3, -2.9, u) * (1.12 if v else 1.0), lerp(-0.25, -0.12, u))

    def tgt(f):
        return (0.0, 0.0, 0.05)

    cam = C.camera("cam", lens=40, loc=loc(f0), target=tgt(f0), fstop=2.4)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(-4.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length - 0.4, pad=3)
    lens_pt = C.empty("lens_pt")
    lens_pt.parent = head
    lens_pt.location = (0, 0, 0.46)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(flare=dict(src="lens", color=[1.0, 0.22, 0.1]), face=face), track={"lens": lens_pt})
