"""s09_sparks - an unseen grinder bites into a steel edge; sparks scream across the frame.

The steel block's edge is chamfered like the title letters: a quiet foreshadowing.
The spark particles themselves are simulated in the compositor from the tracked
contact point, so they can be tuned without re-rendering.
"""
from __future__ import annotations

import math
import os
import sys

import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common as C  # noqa: E402
import assets as A  # noqa: E402
import timeline as TL  # noqa: E402
from timeline import lerp, smoothstep  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s09_sparks"]
    from shapely.geometry import Polygon
    prof = Polygon([(-3, -0.6), (3, -0.6), (3, 0.45), (2.85, 0.6), (-2.85, 0.6), (-3, 0.45)])
    block = C.polygon_to_mesh("block", prof, 1.6, z0=-0.8)
    block.rotation_euler = (math.radians(90), 0, 0)
    C.assign(block, M["steel"])
    C.add_bevel(block, width=0.01, segments=2)
    # hot spot where the wheel bites
    hot_m, hot_e = C.mat_emission("hot", (1.0, 0.55, 0.2), 0.0)
    nt = hot_m.node_tree
    bb = nt.nodes.new("ShaderNodeBlackbody")
    bb.inputs[0].default_value = 2200
    nt.links.new(bb.outputs[0], hot_e.inputs["Color"])
    bmh = bmesh.new()
    bmesh.ops.create_circle(bmh, cap_ends=True, radius=0.05, segments=24)
    hot = C.mesh_object("hotspot", bmh)
    hot.location = (0.4, -0.8 - 0.001, 0.55)
    hot.rotation_euler = (math.radians(90), 0, 0)
    C.assign(hot, hot_m)
    spark_light = C.point_light("spark_light", (0.4, -0.95, 0.62), energy=0.0, color=(1.0, 0.5, 0.15), radius=0.1)
    C.area_light("key", (-2.0, -2.5, 2.5), (0, 0, 0.3), energy=420, size=2.0, color=(0.9, 0.93, 1.0))
    C.area_light("rim", (2.5, 2.0, 1.5), (0, 0, 0.3), energy=600, size=1.5, color=(1.0, 0.1, 0.04))
    C.card("card", (2.5, -6.0, 1.2), (0, 0, 0.3), 8, 0.4, strength=7.0)
    a, b = TL.BEATS["grinder"]
    for f in range(f0 - 3, f1 + 4):
        on = smoothstep(a - 1, a + 2, f)
        fl = 1.0 + 0.45 * TL.value_noise_1d(f * 3.7, 12) + 0.2 * math.sin(f * 5.1)
        C.key_value(spark_light.data, f, 220.0 * on * fl, attr="energy")
        C.key_value(hot_e.inputs["Strength"], f, 40.0 * on * fl)
    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        return (lerp(2.3, 2.0, u), lerp(-2.6, -2.2, u), lerp(0.75, 0.68, u))

    def tgt(f):
        return (0.35, -0.8, 0.5)

    cam = C.camera("cam", lens=35 if not v else 30, loc=loc(f0), target=tgt(f0), fstop=2.0)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(8.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length, pad=3)
    contact = C.empty("contact", (0.4, -0.82, 0.58))
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(fountain=dict(src="contact", dir=[-0.55, -0.75, 0.35], rate=900)),
                track={"contact": contact})
