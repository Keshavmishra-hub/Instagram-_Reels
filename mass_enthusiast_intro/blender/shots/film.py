"""s03_film - the film strip clacks through the gate, frame by frame (intermittent pull-down).

Each held frame shows a moment from the user's own photos, back-lit by the lamp.
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
from timeline import lerp, clamp, ease_in_out, smoothstep  # noqa: E402


def pulldown_offset(f):
    """Strip travel in frame pitches: holds, then a 2-frame snap to the next frame."""
    pulls = TL.BEATS["gate_pulldowns"]
    k = 0.0
    for p in pulls:
        if f >= p + 2:
            k += 1.0
        elif f > p:
            k += ease_in_out((f - p) / 2.0)
    return k


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s03_film"]
    strip, mapping, strength, pitch_v = A.film_strip("strip", length=7.0, width=1.375)
    strip.rotation_euler = (math.radians(90), 0, 0)             # strip runs vertically, faces -Y
    frame_pitch = 1.375 * (660.0 / 1100.0)                      # world height of one frame pitch
    # gate plate with a window around one frame
    from shapely.geometry import box
    gate_poly = box(-0.62, -0.47, 0.62, 0.47).difference(box(-0.53, -0.39, 0.53, 0.39))
    gate = C.polygon_to_mesh("gate", gate_poly, 0.06, z0=0.0)
    gate.rotation_euler = (math.radians(90), 0, 0)
    gate.location = (0, -0.035, 0)
    C.assign(gate, M["gunmetal"])
    C.add_bevel(gate, width=0.01, segments=2)
    # sprocket drum above the gate
    drum = A.lathe("drum", [(0.0, -0.8), (0.45, -0.8), (0.45, 0.8), (0.0, 0.8)], segs=64)
    drum.rotation_euler = (0, math.radians(90), 0)
    drum.location = (0, 0.15, 2.35)
    C.assign(drum, M["steel"])
    # back light panel (the lamp)
    lamp_m, lamp_e = C.mat_emission("lamp_m", (1.0, 0.8, 0.6), 0.0)
    panel = A.disc("lamp", 2.2)
    panel.rotation_euler = (math.radians(90), 0, 0)
    panel.location = (0, 0.9, 0)
    C.assign(panel, lamp_m)
    panel.visible_camera = False
    C.area_light("side", (-2.5, -1.6, 1.5), (0, 0, 0), energy=120, size=1.0, color=(0.9, 0.93, 1.0))
    C.area_light("rim", (2.0, 0.5, -1.2), (0, 0, 0), energy=500, size=1.0, color=(1.0, 0.12, 0.04))
    C.card("card", (0, -5, 1.5), (0, 0, 0), 6, 1.0, strength=2.0)

    # UV v of the strip centre, and the offset that centres picture 0 in the gate
    v_mid = (7.0 / 2.0) / pitch_v
    start = (1.0 - 0.5 / 6.0) - v_mid
    for f in range(f0 - 3, f1 + 4):
        k = pulldown_offset(f)
        mapping.inputs["Location"].default_value = (0.0, start - k / 6.0, 0.0)
        mapping.inputs["Location"].keyframe_insert("default_value", frame=f)
        flick = 1.0 + 0.08 * TL.value_noise_1d(f * 2.3, 2)
        C.key_value(strength.outputs[0], f, 3.2 * flick)
        C.key_value(lamp_e.inputs["Strength"], f, 6.0 * flick)
        C.key_obj(drum, f, rot=(k * 2 * math.pi / 8, math.radians(90), 0))

    v = variant == "9x16"

    def loc(f):
        u = (f - f0) / (f1 - f0)
        a = lerp(-0.45, -0.3, u)
        d = lerp(3.1, 2.75, u) * (1.1 if v else 1.0)
        return (d * math.sin(a), -d * math.cos(a), lerp(0.35, 0.2, u))

    def tgt(f):
        return (0.05, 0.0, 0.0)

    cam = C.camera("cam", lens=45, loc=loc(f0), target=tgt(f0), fstop=2.4)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(-5.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(gate_shake=TL.BEATS["gate_pulldowns"]), track={"lamp": panel})
