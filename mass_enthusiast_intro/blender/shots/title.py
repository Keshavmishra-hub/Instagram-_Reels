"""s13_title + s14_hero: the MASS ENTHUSIAST lock-up is forged and assembled.

Each glyph = gunmetal frame (body + raised rim) holding a molten floor, plus a
brushed-steel face plate that slams into the frame. Lights: soft top key, crimson
rims from behind, an ember under-light, a reflection card behind the camera and a
moving strip for the light sweeps.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import common as C  # noqa: E402
import glyphs as G  # noqa: E402
import title_rig as R  # noqa: E402
import timeline as TL  # noqa: E402

SHOTS = ("s13_title", "s14_hero")


def _materials():
    M = {}
    M["gunmetal"] = C.mat_metal("gunmetal", color=(0.085, 0.086, 0.092), rough=0.36, rough_var=0.12,
                                dirt=0.35, scale=3.0)
    M["polished"] = C.mat_metal("polished", color=(0.82, 0.82, 0.84), rough=0.11, rough_var=0.035, scale=6.0)
    M["brushed"] = C.mat_metal("brushed", color=(0.62, 0.62, 0.645), rough=0.17, rough_var=0.05, brushed=True,
                               aniso=0.65, tangent_uv="UVMap", scale=2.0)
    M["floor"] = C.mat_dielectric("floor", color=(0.006, 0.006, 0.007), rough=0.16, spec=0.6, bump=0.15,
                                  scale=3.0)
    return M


def _letter(i, g, M, coll, crust=True):
    cap = g.scale
    D = R.DEPTH * cap
    RZ = R.RAISE * cap
    cx = (g.poly.bounds[0] + g.poly.bounds[2]) / 2
    cy = (g.poly.bounds[1] + g.poly.bounds[3]) / 2
    from shapely import affinity
    sh = lambda p: affinity.translate(p, -cx, -cy)
    poly, groove, inset = sh(g.poly), sh(g.groove_outer), sh(g.inset)

    root = C.empty(f"L{i:02d}_{g.char}", (cx, 0.0, cy))
    root.rotation_euler = (math.radians(90), 0, 0)

    glow_m, bb, em, noise = C.mat_molten(f"molten_{i:02d}", crust=crust)

    body = C.polygon_to_mesh(f"L{i:02d}_body", poly, D - RZ)
    C.assign(body, glow_m, M["gunmetal"])
    C.set_face_materials_by_normal(body, front=0, side=1)
    C.shade_smooth(body, 30)
    C.add_bevel(body, width=0.006 * cap, segments=2, angle=40, material=1)

    rim_ring = poly.difference(groove)
    rim = C.polygon_to_mesh(f"L{i:02d}_rim", rim_ring, RZ, z0=D - RZ)
    C.assign(rim, M["polished"], M["gunmetal"])
    C.set_face_materials_by_normal(rim, front=0, side=1)
    C.shade_smooth(rim, 30)
    C.add_bevel(rim, width=0.0045 * cap, segments=3, angle=40, material=0)

    plate = C.polygon_to_mesh(f"L{i:02d}_plate", inset, RZ + 0.004 * cap, z0=D - RZ)
    C.assign(plate, M["brushed"], M["polished"])
    C.set_face_materials_by_normal(plate, front=0, side=1)
    C.shade_smooth(plate, 30)
    C.add_bevel(plate, width=0.005 * cap, segments=3, angle=40, material=1)

    for ob in (body, rim, plate):
        ob.parent = root
    body.location = rim.location = (0, 0, 0)

    # spark emitters: points on the groove mid-line, outward normals (letter-local 2D)
    mid = poly.buffer(-0.040 * cap, join_style=2, mitre_limit=3.0)
    pts = []
    for ring in G.rings(mid):
        L = G.ring_length(ring)
        n = max(8, int(L / (0.035 * cap)))
        for k in range(n):
            u = k / n
            p = G.point_on_ring(ring, u)
            q = G.point_on_ring(ring, u + 0.5 / n / 4)
            tx, ty = q[0] - p[0], q[1] - p[1]
            ln = math.hypot(tx, ty) or 1.0
            nx, ny = ty / ln, -tx / ln
            # make sure the normal points away from the solid plate (into the groove/outwards)
            from shapely.geometry import Point
            if inset.contains(Point(p[0] + nx * 0.03 * cap, p[1] + ny * 0.03 * cap)):
                nx, ny = -nx, -ny
            pts.append((p[0], p[1], nx, ny))
    base = g.poly.bounds[1]
    return dict(root=root, plate=plate, bb=bb, em=em, noise=noise, cap=cap, cx=cx, cy=cy, D=D, pts=pts,
                char=g.char, meshes=(body, rim, plate), base=base, h=cy - base)


def build(variant="16x9", samples=16, scale=1.0, floor=False, shot="s13_title"):
    sc = C.reset_scene()
    C.setup_render(sc, variant, samples=samples, scale=scale, glossy_bounces=4)
    C.world_color(sc, (0.0, 0.0, 0.0))
    M = _materials()
    placed, W, H, cap2 = G.lockup()
    # in the hero shot the interiors are covered by the plates: skip the costly crust
    L = [_letter(i, g, M, None, crust=(shot != "s14_hero")) for i, g in enumerate(placed)]
    for m in bpy.data.materials:
        if m.name.startswith("molten"):
            m.cycles.emission_sampling = "NONE"     # glow is seen, the flash lights do the lighting

    if floor:
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
        fl = C.mesh_object("floor", bm)
        fl.location = (0, 0, -0.06)
        C.assign(fl, M["floor"])

    # ------------------------------------------------------------------ lights
    rx = bpy.data.collections.new("rx_letters")
    for l in L:
        for ob in l["meshes"]:
            rx.objects.link(ob)
    C.area_light("key_top", (0.4, -3.6, 5.2), (0, 0, 0.9), energy=420, size=5.0, size_y=2.2,
                 color=(0.97, 0.97, 1.0))
    for lt in (C.area_light("rim_L", (-5.2, 3.6, 2.9), (0, 0, 0.8), energy=2600, size=3.0, color=(1.0, 0.05, 0.03)),
               C.area_light("rim_R", (5.4, 3.3, 2.3), (0, 0, 0.8), energy=2100, size=3.0, color=(1.0, 0.16, 0.04))):
        lt.light_linking.receiver_collection = rx
    # reflection environment behind the camera: dim wide wash + bright thin "horizon" strips
    C.card("card_wash", (0.0, -16.0, 5.0), (0, 0, 1.0), 22.0, 6.0, color=(0.95, 0.96, 1.0),
           strength=0.22, gradient=0.8)
    C.card("card_line_hi", (0.0, -14.0, 3.2), (0, 0, 1.0), 26.0, 0.35, color=(0.96, 0.97, 1.0), strength=6.0)
    C.card("card_low", (0.0, -15.0, 0.9), (0, 0, 0.4), 26.0, 2.2, color=(0.93, 0.95, 1.0), strength=0.9,
           gradient=0.7)
    C.card("card_line_lo", (0.0, -14.0, -0.9), (0, 0, 0.6), 26.0, 0.25, color=(1.0, 0.06, 0.04), strength=0.7)
    sweep, sweep_em = C.card("sweep", (-12.0, -9.0, 1.2), (0, 0, 0.9), 0.55, 9.0, color=(1.0, 0.95, 0.9),
                             strength=0.0)
    flashes = []
    for i, l in enumerate(L):
        p = C.point_light(f"flash_{i:02d}", (l["cx"], -0.9 * l["cap"] - 0.2, l["cy"] + 0.1),
                          energy=0.0, color=(1.0, 0.45, 0.12), radius=0.3)
        flashes.append(p)

    # ------------------------------------------------------------------ animation
    f_lo, f_hi = TL.SHOT["s13_title"][0], TL.SHOT["s14_hero"][1]
    slams = R.slam_frames()
    for f in range(f_lo - 3, f_hi + 3):
        for i, l in enumerate(L):
            cap = l["cap"]
            rc = R.recoil(i, f) * cap
            if i >= 4:   # ENTHUSIAST shares the shudder of the big MASS lock a little
                rc += 0.25 * R.recoil(3, f) * 0
            phi = R.flip(i, f)
            h = l["h"]
            C.key_obj(l["root"], f, loc=(l["cx"], -rc + h * math.sin(phi), l["base"] + h * math.cos(phi)),
                      rot=(math.radians(90.0) - phi, 0.0, 0.0))
            off = R.plate_offset(i, f)
            C.key_obj(l["plate"], f, loc=(off[0] * cap, off[1] * cap, off[2] * cap))
            vis = R.plate_visible(i, f)
            l["plate"].hide_render = not vis
            l["plate"].keyframe_insert("hide_render", frame=f)
            temp, stren = R.glow(i, f)
            C.key_value(l["bb"].inputs["Temperature"], f, temp)
            C.key_value(l["em"].outputs[0], f, stren)
            for nz in l["noise"]:
                C.key_value(nz.inputs["W"], f, f * 0.035 + i * 3.1)
            # impact flash light
            t = (f - slams[i]) / TL.FPS
            e = 0.0 if t < 0 else (900.0 if i < 4 else 220.0) * math.exp(-t / 0.09)
            C.key_value(flashes[i].data, f, e, attr="energy")
        # light sweeps: strip card travels behind the camera
        x, s = -14.0, 0.0
        for (a, b) in (TL.TITLE["sweep_mass"], TL.TITLE["sweep_all"]):
            if a - 2 <= f <= b + 2:
                u = TL.clamp((f - a) / (b - a))
                x = TL.lerp(-11.0, 11.0, TL.ease_in_out(u))
                s = 38.0 * math.sin(math.pi * u) ** 0.5
        hero = TL.TITLE["hero_impact"]
        if hero - 3 <= f <= hero + 40:   # final glint
            u = TL.clamp((f - hero) / 40.0)
            x = TL.lerp(-9.0, 9.0, TL.ease_out_cubic(u))
            s = max(s, 30.0 * (1 - u) ** 0.7)
        C.key_obj(sweep, f, loc=(x, -9.0, 1.2))
        C.key_value(sweep_em.inputs["Strength"], f, s)

    # ------------------------------------------------------------------ cameras
    letters = {i: (l["cx"], l["cy"], l["cap"]) for i, l in enumerate(L)}
    plan = R.camera_plan(variant, letters) + [R.hero_camera(variant)]
    cams = []
    for (name, f0, f1, loc_fn, tgt_fn, lens_fn, roll_fn, fstop) in plan:
        cam = C.camera(name, lens=lens_fn(f0), loc=loc_fn(f0), target=tgt_fn(f0), fstop=fstop)
        focus = lambda f, lf=loc_fn, tf=tgt_fn: (Vector(lf(f)) - Vector(tf(f))).length
        C.bake_camera(cam, f0, f1, loc_fn, tgt_fn, roll_fn=roll_fn, focus_fn=focus, lens_fn=lens_fn, pad=3)
        C.fix_euler_flips(cam)
        cams.append((cam, f0, f1))

    def camera_for(f):
        for cam, a, b in cams:
            if a <= f <= b:
                return cam
        return cams[-1][0]

    emitters = []
    for i, l in enumerate(L):
        root = l["root"]
        mw = Matrix.Translation((l["cx"], 0.0, l["cy"])) @ Matrix.Rotation(math.radians(90), 4, "X")
        world = []
        for (x, y, nx, ny) in l["pts"]:
            p = mw @ Vector((x, y, l["D"]))
            n = (mw.to_3x3() @ Vector((nx, ny, 0.0))).normalized()
            world.append([round(p.x, 4), round(p.y, 4), round(p.z, 4), round(n.x, 4), round(n.y, 4), round(n.z, 4)])
        emitters.append(dict(index=i, char=l["char"], frame=slams[i], cap=l["cap"], center=[l["cx"], -l["D"], l["cy"]],
                             points=world, pour=R.pour_frame(i)))
    meta = dict(emitters=emitters, sweeps=[TL.TITLE["sweep_mass"], TL.TITLE["sweep_all"]])
    return dict(scene=sc, frames=(f_lo, f_hi), camera_for=camera_for, meta=meta)
