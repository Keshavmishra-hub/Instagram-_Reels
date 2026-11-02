"""s08_redline - the chain lies across a steel floor; a red light races along it, link by link."""
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
from timeline import lerp, smoothstep, ease_in_out, clamp  # noqa: E402


def path_point(s):
    """Floor curve: a lazy S running away from camera (s in [0,1])."""
    x = 1.6 * math.sin(s * 2.6 - 0.4) * (1 - 0.3 * s)
    y = -1.0 + 11.0 * s
    return Vector((x, y, 0.0))


def build(variant="16x9", samples=16, scale=1.0):
    random.seed(21)
    sc = C.shot_scene(variant, samples, scale)
    M = A.mats()
    f0, f1 = TL.SHOT["s08_redline"]
    # floor
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20)
    floor = C.mesh_object("floor", bm)
    floor.location = (0, 6, 0)
    C.assign(floor, M["floor"])
    # chain along the curve: the 'u' object property drives the red glow in the shader
    chain_m = C.mat_metal("m_chain_red", color=(0.5, 0.5, 0.52), rough=0.25, rough_var=0.1, scratches=0.06,
                          dirt=0.3, scale=6.0)
    nt = chain_m.node_tree
    pr = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "u"
    head = nt.nodes.new("ShaderNodeValue")
    head.outputs[0].default_value = -1.0
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    nt.links.new(head.outputs[0], sub.inputs[0])
    nt.links.new(attr.outputs["Fac"], sub.inputs[1])
    # glow = exp(-max(d,0)*12) for links behind the head, nothing ahead of it
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = -0.004
    nt.links.new(sub.outputs[0], gt.inputs[0])
    mx = nt.nodes.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    mx.inputs[1].default_value = 0.0
    nt.links.new(sub.outputs[0], mx.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = -18.0
    nt.links.new(mx.outputs[0], mul.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(mul.outputs[0], ex.inputs[0])
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    nt.links.new(ex.outputs[0], m2.inputs[0])
    nt.links.new(gt.outputs[0], m2.inputs[1])
    m3 = nt.nodes.new("ShaderNodeMath")
    m3.operation = "MULTIPLY"
    m3.inputs[1].default_value = 3.5
    nt.links.new(m2.outputs[0], m3.inputs[0])
    pr.inputs["Emission Color"].default_value = (1.0, 0.015, 0.008, 1.0)
    nt.links.new(m3.outputs[0], pr.inputs["Emission Strength"])
    chain_m.cycles.emission_sampling = "NONE"

    sp = A.chain_spacing() * 0.98
    links = []
    s, k = 0.0, 0
    L = sum((path_point((i + 1) / 400) - path_point(i / 400)).length for i in range(400))
    ds = sp / L
    while s <= 1.0:
        p = path_point(s)
        q = path_point(min(s + 0.002, 1.0))
        tan = (q - p).normalized()
        lk = A.chain_link(f"lk{k:03d}", mat=chain_m)
        yaw = math.atan2(tan.y, tan.x)
        if k % 2 == 0:   # lying flat
            lk.rotation_euler = (0.0, math.radians(90), yaw)
            lk.location = (p.x, p.y, 0.11)
        else:            # standing on edge
            lk.rotation_euler = (math.radians(90), math.radians(90), yaw)
            lk.location = (p.x, p.y, 0.41)
        lk.rotation_euler.z += random.uniform(-0.08, 0.08)
        lk["u"] = s
        links.append(lk)
        s += ds
        k += 1
    red = C.point_light("red", (0, 0, 0.35), energy=0.0, color=(1.0, 0.05, 0.02), radius=0.15)
    C.area_light("key", (-3.0, -2.0, 4.0), (0, 3, 0), energy=150, size=3.0, color=(0.9, 0.93, 1.0))
    C.area_light("back", (1.0, 14.0, 2.0), (0, 3, 0), energy=700, size=3.0, color=(1.0, 0.25, 0.06))
    C.card("card", (0.0, -8.0, 2.5), (0, 3, 0), 10, 1.2, strength=1.2)

    t0 = TL.BEATS["redline_start"]

    def head_u(f):
        return lerp(-0.02, 1.05, ease_in_out(clamp((f - t0) / (f1 - t0 - 3))) ** 0.85)

    for f in range(f0 - 3, f1 + 4):
        u = head_u(f)
        C.key_value(head.outputs[0], f, u)
        p = path_point(clamp(u))
        C.key_obj(red, f, loc=(p.x, p.y, 0.45))
        C.key_value(red.data, f, 130.0 * smoothstep(t0, t0 + 3, f), attr="energy")
    v = variant == "9x16"

    def loc(f):
        u = head_u(f)
        p = path_point(clamp(u - 0.10))
        return (p.x - 1.7, p.y - 2.3, 0.85 if not v else 1.0)

    def tgt(f):
        u = head_u(f)
        p = path_point(clamp(u + 0.02))
        return (p.x * 0.7, p.y, 0.2)

    cam = C.camera("cam", lens=28, loc=loc(f0), target=tgt(f0), fstop=2.4)
    C.bake_camera(cam, f0, f1, loc, tgt, roll_fn=lambda f: math.radians(-6.0),
                  focus_fn=lambda f: (Vector(loc(f)) - Vector(tgt(f))).length, pad=3)
    return dict(scene=sc, frames=(f0, f1), camera_for=C.single_camera(cam),
                meta=dict(head_sparks=True), track={"red": red})
