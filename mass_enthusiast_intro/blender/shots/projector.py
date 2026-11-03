"""s04_projector - over the projector's shoulder: the lamp ignites, the beam finds the screen,
and the screen fills with the user's speech - the first 'mass' moment of the sequence."""
from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common as C  # noqa: E402
import assets as A  # noqa: E402
import timeline as TL  # noqa: E402
from timeline import lerp, clamp, ease_in_out, smoothstep, ease_out_cubic  # noqa: E402


def build(variant="16x9", samples=16, scale=1.0):
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s04_projector"]
    proj, lamp_e = A.projector("proj", M)
    proj.rotation_euler = (math.radians(-90), 0, 0)          # lens axis (+Z local) -> +Y world
    proj.location = (0.0, 0.0, 0.0)

    # cinema screen far down the beam, with curtains
    sm, tex, p = C.mat_image("screen_m", os.path.join(A.TEX, "screen.jpg"), emission=0.0, rough=0.9)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    uv = bm.loops.layers.uv.new("UVMap")
    for fc in bm.faces:
        for lp in fc.loops:
            lp[uv].uv = (lp.vert.co.x + 0.5, lp.vert.co.y + 0.5)
    for vv in bm.verts:
        vv.co.x *= 6.4
        vv.co.y *= 3.6
    screen = C.mesh_object("screen", bm)
    screen.rotation_euler = (math.radians(90), 0, 0)
    screen.location = (0.0, 14.0, 0.55)
    C.assign(screen, sm)
    curtain_m = C.mat_dielectric("velvet", (0.08, 0.004, 0.006), rough=0.75, spec=0.2)
    curtain_m.node_tree.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 0.8
    for side in (-1, 1):
        bmc = bmesh.new()
        nx, ny = 40, 10
        vs = [[bmc.verts.new((i / nx * 2.4, 0.12 * math.sin(i / nx * 2.4 * 9), -3 + 6 * j / ny))
               for j in range(ny + 1)] for i in range(nx + 1)]
        for i in range(nx):
            for j in range(ny):
                bmc.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
        cur = C.mesh_object(f"curtain{side}", bmc)
        C.shade_smooth(cur, 80)
        cur.location = (side * 3.1 - (2.4 if side < 0 else 0), 13.8, 0.55)
        if side > 0:
            cur.location = (3.1, 13.8, 0.55)
        C.assign(cur, curtain_m)
    C.area_light("key", (-2.0, -2.0, 2.5), (0, 0.6, 0), energy=140, size=1.5, color=(0.92, 0.95, 1.0))
    C.area_light("rim", (1.8, 1.6, 1.6), (0, 0.6, 0), energy=600, size=1.2, color=(1.0, 0.12, 0.04))
    C.card("card", (-1.0, -5, 1.5), (0, 0, 0), 6, 1.0, strength=2.2)
    spill = C.point_light("spill", (0.0, 13.2, 0.6), energy=0.0, color=(1.0, 0.75, 0.55), radius=2.0)

    ign, on = TL.BEATS["lamp_ignite"], TL.BEATS["screen_on"]
    for f in range(f0 - 3, f1 + 4):
        # ignition: sputter, then full power with a gentle flicker
        if f < ign:
            e = 0.0
        else:
            t = f - ign
            e = 40.0 * (0.25 + 0.75 * smoothstep(0, 5, t)) * (1.0 + 0.1 * TL.value_noise_1d(f * 2.1, 3))
            if t in (1, 3):
                e *= 0.3
        C.key_value(lamp_e.inputs["Strength"], f, e)
        s = 0.0 if f < on else 2.6 * smoothstep(on, on + 6, f) * (1.0 + 0.06 * TL.value_noise_1d(f * 3.3, 4))
        C.key_value(p.inputs["Emission Strength"], f, s)
        C.key_value(spill.data, f, 600.0 * s / 2.6, attr="energy")

    v = variant == "9x16"
    lens_front = Vector((0.0, 1.47, 0.0))
    scr = Vector((0.15, 14.0, 0.6))
    whip0, whip1 = ign + 6, ign + 13

    def loc(f):
        u = ease_in_out((f - f0) / (f1 - f0))
        return (lerp(-1.0, -0.8, u), lerp(2.45, 2.8, u), lerp(0.36, 0.44, u))

    def yaw_pitch(d):
        return math.atan2(d.x, d.y), math.atan2(d.z, math.hypot(d.x, d.y))

    def tgt(f):
        c = Vector(loc(f))
        y0, p0 = yaw_pitch(lens_front - c)
        y1, p1 = yaw_pitch(scr - c)
        w = smoothstep(whip0, whip1, f)
        yaw, pit = lerp(y0, y1, w), lerp(p0, p1, w)
        d = Vector((math.sin(yaw) * math.cos(pit), math.cos(yaw) * math.cos(pit), math.sin(pit)))
        return tuple(c + d * 3.0)

    def focus(f):
        w = smoothstep(whip0 + 1, whip1 + 2, f)
        return lerp((Vector(loc(f)) - lens_front).length, (Vector(loc(f)) - scr).length, w)

    cam = C.camera("cam", lens=32 if not v else 30, loc=loc(f0), target=tgt(f0), fstop=2.0)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(lerp(4.0, -2.0, smoothstep(whip0, whip1, f))),
                  focus_fn=focus, pad=3)
    lensobj = C.empty("lens_front")
    lensobj.parent = proj
    lensobj.location = (0, 0, 1.49)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(beam=dict(src="lens", dst="screen", color=[1.0, 0.78, 0.55], ignite=ign)),
                track={"lens": lensobj, "screen": screen})
