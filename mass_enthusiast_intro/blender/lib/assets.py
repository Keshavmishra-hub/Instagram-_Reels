"""Procedural models for the object montage (all built from code, no external assets).

Every builder returns a root empty (plus handles to the parts that get animated).
Units are arbitrary but consistent: a chain link is ~1.3 units long, the reel ~2 wide.
"""
from __future__ import annotations

import math
import os
import random

import bpy
import bmesh
from mathutils import Vector, Matrix

import common as C

TEX = os.path.join(C.ROOT, "assets", "textures")


# ----------------------------------------------------------------------------- primitives
def sweep(name, path, radius, closed=True, segs=16, radius_fn=None):
    """Tube of circular cross-section swept along a polyline path (list of Vectors)."""
    bm = bmesh.new()
    n = len(path)
    rings = []
    prev_nrm = None
    for i, p in enumerate(path):
        a = path[(i - 1) % n] if (closed or i > 0) else path[i]
        b = path[(i + 1) % n] if (closed or i < n - 1) else path[i]
        t = (Vector(b) - Vector(a)).normalized()
        if prev_nrm is None:
            ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            nrm = t.cross(ref).normalized()
        else:   # parallel transport keeps the ring orientation stable
            nrm = (prev_nrm - t * prev_nrm.dot(t)).normalized()
        bin_ = t.cross(nrm).normalized()
        prev_nrm = nrm
        r = radius_fn(i / n) if radius_fn else radius
        ring = []
        for k in range(segs):
            ang = 2 * math.pi * k / segs
            ring.append(bm.verts.new(Vector(p) + (nrm * math.cos(ang) + bin_ * math.sin(ang)) * r))
        rings.append(ring)
    last = n if closed else n - 1
    for i in range(last):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            bm.faces.new((r0[k], r0[(k + 1) % segs], r1[(k + 1) % segs], r1[k]))
    if not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = C.mesh_object(name, bm)
    C.shade_smooth(ob, 60)
    return ob


def lathe(name, profile, segs=96, cap_start=False, cap_end=False, smooth_angle=35):
    """Revolve a (radius, z) profile around the Z axis."""
    bm = bmesh.new()
    rings = []
    for (r, z) in profile:
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(segs):
            try:
                bm.faces.new((r0[k], r0[(k + 1) % segs], r1[(k + 1) % segs], r1[k]))
            except ValueError:
                pass
    if cap_start:
        bm.faces.new(list(reversed(rings[0])))
    if cap_end:
        bm.faces.new(rings[-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = C.mesh_object(name, bm)
    C.shade_smooth(ob, smooth_angle)
    return ob


def rounded_box(name, sx, sy, sz, bevel=0.02):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= sx
        v.co.y *= sy
        v.co.z *= sz
    ob = C.mesh_object(name, bm)
    C.add_bevel(ob, width=bevel, segments=3, angle=30)
    C.shade_smooth(ob, 30)
    return ob


def disc(name, radius, segs=96):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=radius, segments=segs)
    return C.mesh_object(name, bm)


def parent(children, root):
    for c in children:
        c.parent = root
    return root


# ----------------------------------------------------------------------------- materials
_MATS = {}


def mats():
    if _MATS and all(m.name in bpy.data.materials for m in _MATS.values()):
        return _MATS
    _MATS.clear()
    M = _MATS
    M["chain"] = C.mat_metal("m_chain", color=(0.52, 0.52, 0.54), rough=0.24, rough_var=0.10, scratches=0.06,
                             dirt=0.25, scale=6.0, bump=0.08)
    M["steel"] = C.mat_metal("m_steel", color=(0.62, 0.62, 0.64), rough=0.2, rough_var=0.06, scale=4.0)
    M["chrome"] = C.mat_metal("m_chrome", color=(0.9, 0.9, 0.92), rough=0.06, rough_var=0.02, scale=8.0)
    M["alu"] = C.mat_metal("m_alu", color=(0.78, 0.78, 0.8), rough=0.26, rough_var=0.08, brushed=True,
                           aniso=0.5, scale=3.0)
    M["gunmetal"] = C.mat_metal("m_gunmetal", color=(0.08, 0.08, 0.085), rough=0.33, rough_var=0.1, dirt=0.3,
                                scale=3.0)
    M["brass"] = C.mat_metal("m_brass", color=(0.78, 0.55, 0.26), rough=0.24, rough_var=0.08, dirt=0.4, scale=5.0)
    M["enamel"] = C.mat_dielectric("m_enamel", (0.012, 0.012, 0.013), rough=0.28, spec=0.5, bump=0.03, scale=40)
    M["rubber"] = C.mat_dielectric("m_rubber", (0.015, 0.015, 0.016), rough=0.62, spec=0.3, bump=0.05, scale=60)
    M["cone"] = C.mat_dielectric("m_cone", (0.02, 0.02, 0.021), rough=0.5, spec=0.35, bump=0.12, scale=180)
    M["floor"] = C.mat_metal("m_floor", color=(0.05, 0.05, 0.052), rough=0.3, rough_var=0.2, scratches=0.12,
                             dirt=0.6, scale=0.8, bump=0.05)
    M["glass"] = _glass()
    return M


def _glass():
    m, out = C.new_material("m_lensglass")
    nb = C.NodeBuilder(m)
    p = C.principled(nb, **{"Base Color": (0.92, 0.95, 0.97, 1), "Metallic": 0.0, "Roughness": 0.0,
                            "Transmission Weight": 1.0, "Thin Film Thickness": 380.0,
                            "Thin Film IOR": 1.38, "IOR": 1.52})
    nb.l(p.outputs[0], out.inputs[0])
    return m


def mat_film(path):
    """Back-lit film: the image glows (emission) and the sprocket holes are see-through."""
    m, out = C.new_material("m_film")
    nb = C.NodeBuilder(m)
    tex = nb.n("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.interpolation = "Cubic"
    tex.extension = "REPEAT"
    mapping = nb.n("ShaderNodeMapping")
    tc = nb.n("ShaderNodeTexCoord")
    nb.l(tc.outputs["UV"], mapping.inputs["Vector"])
    nb.l(mapping.outputs[0], tex.inputs["Vector"])
    em = nb.n("ShaderNodeEmission")
    strength = nb.n("ShaderNodeValue")
    strength.outputs[0].default_value = 4.0
    nb.l(tex.outputs["Color"], em.inputs["Color"])
    nb.l(strength.outputs[0], em.inputs["Strength"])
    gl = nb.n("ShaderNodeBsdfGlossy", Roughness=0.15)
    gl.inputs["Color"].default_value = (0.3, 0.3, 0.3, 1)
    add = nb.n("ShaderNodeAddShader")
    nb.l(em.outputs[0], add.inputs[0])
    nb.l(gl.outputs[0], add.inputs[1])
    tr = nb.n("ShaderNodeBsdfTransparent")
    mix = nb.n("ShaderNodeMixShader")
    nb.l(tex.outputs["Alpha"], mix.inputs[0])
    nb.l(tr.outputs[0], mix.inputs[1])
    nb.l(add.outputs[0], mix.inputs[2])
    nb.l(mix.outputs[0], out.inputs[0])
    m.cycles.emission_sampling = "NONE"
    return m, mapping, strength


def mat_ticket_burn(path, aspect):
    """Paper ticket that burns in from the edges: progress value 0 (intact) .. 1 (gone)."""
    m, out = C.new_material("m_ticket")
    nb = C.NodeBuilder(m)
    tc = nb.n("ShaderNodeTexCoord")
    tex = nb.n("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.interpolation = "Cubic"
    nb.l(tc.outputs["UV"], tex.inputs["Vector"])
    sep = nb.n("ShaderNodeSeparateXYZ")
    nb.l(tc.outputs["UV"], sep.inputs[0])
    # distance to the nearest edge (in units of the ticket height)
    def edge(axis, scale):
        a = nb.n("ShaderNodeMath", _operation="PINGPONG")
        a.inputs[1].default_value = 0.5
        nb.l(sep.outputs[axis], a.inputs[0])
        s = nb.n("ShaderNodeMath", _operation="MULTIPLY")
        s.inputs[1].default_value = scale
        nb.l(a.outputs[0], s.inputs[0])
        return s
    ex, ey = edge(0, aspect), edge(1, 1.0)
    mn = nb.n("ShaderNodeMath", _operation="MINIMUM")
    nb.l(ex.outputs[0], mn.inputs[0])
    nb.l(ey.outputs[0], mn.inputs[1])
    nz = nb.n("ShaderNodeTexNoise", Scale=4.0, Detail=8.0, Roughness=0.62)
    nb.l(tc.outputs["Object"], nz.inputs["Vector"])
    nzr = nb.n("ShaderNodeMapRange")
    nzr.inputs["To Min"].default_value = -0.16
    nzr.inputs["To Max"].default_value = 0.16
    nb.l(nz.outputs["Fac"], nzr.inputs["Value"])
    field = nb.n("ShaderNodeMath", _operation="ADD")
    nb.l(mn.outputs[0], field.inputs[0])
    nb.l(nzr.outputs[0], field.inputs[1])
    prog = nb.n("ShaderNodeValue")
    prog.outputs[0].default_value = 0.0
    # d = field - progress  (<0 burnt away, 0..0.02 glowing ember, 0.02..0.09 charred)
    d = nb.n("ShaderNodeMath", _operation="SUBTRACT")
    nb.l(field.outputs[0], d.inputs[0])
    nb.l(prog.outputs[0], d.inputs[1])
    alpha = nb.n("ShaderNodeMath", _operation="GREATER_THAN")
    alpha.inputs[1].default_value = 0.0
    nb.l(d.outputs[0], alpha.inputs[0])
    char = nb.n("ShaderNodeMapRange")
    char.inputs["From Min"].default_value = 0.015
    char.inputs["From Max"].default_value = 0.10
    char.inputs["To Min"].default_value = 0.0
    char.inputs["To Max"].default_value = 1.0
    nb.l(d.outputs[0], char.inputs["Value"])
    col = nb.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MIX")
    col.inputs[6].default_value = (0.012, 0.008, 0.006, 1.0)
    nb.l(char.outputs[0], col.inputs[0])
    nb.l(tex.outputs["Color"], col.inputs[7])
    p = C.principled(nb, Roughness=0.7)
    nb.l(col.outputs[2], p.inputs["Base Color"])
    # ember band
    ember = nb.n("ShaderNodeMapRange")
    ember.inputs["From Min"].default_value = 0.0
    ember.inputs["From Max"].default_value = 0.018
    ember.inputs["To Min"].default_value = 1.0
    ember.inputs["To Max"].default_value = 0.0
    nb.l(d.outputs[0], ember.inputs["Value"])
    emn = nb.n("ShaderNodeTexNoise", Scale=40.0, Detail=3.0)
    nb.l(tc.outputs["Object"], emn.inputs["Vector"])
    emul = nb.n("ShaderNodeMath", _operation="MULTIPLY")
    nb.l(ember.outputs[0], emul.inputs[0])
    nb.l(emn.outputs["Fac"], emul.inputs[1])
    estr = nb.n("ShaderNodeMath", _operation="MULTIPLY")
    estr.inputs[1].default_value = 16.0
    nb.l(emul.outputs[0], estr.inputs[0])
    bb = nb.n("ShaderNodeBlackbody", Temperature=1700.0)
    nb.l(bb.outputs[0], p.inputs["Emission Color"])
    nb.l(estr.outputs[0], p.inputs["Emission Strength"])
    tr = nb.n("ShaderNodeBsdfTransparent")
    mix = nb.n("ShaderNodeMixShader")
    nb.l(alpha.outputs[0], mix.inputs[0])
    nb.l(tr.outputs[0], mix.inputs[1])
    nb.l(p.outputs[0], mix.inputs[2])
    nb.l(mix.outputs[0], out.inputs[0])
    m.cycles.emission_sampling = "NONE"
    return m, prog


# ----------------------------------------------------------------------------- chain
def link_path(L=0.5, r=0.3, n=64):
    """Stadium centre-line in the XZ plane (long axis = Z)."""
    pts = []
    per = 2 * L + 2 * math.pi * r
    for i in range(n):
        s = per * i / n
        if s < L:
            pts.append(Vector((r, 0, -L / 2 + s)))
        elif s < L + math.pi * r:
            a = (s - L) / r
            pts.append(Vector((r * math.cos(a), 0, L / 2 + r * math.sin(a))))
        elif s < 2 * L + math.pi * r:
            pts.append(Vector((-r, 0, L / 2 - (s - L - math.pi * r))))
        else:
            a = math.pi + (s - 2 * L - math.pi * r) / r
            pts.append(Vector((r * math.cos(a), 0, -L / 2 + r * math.sin(a))))
    return pts


_LINK_MESH = {}


def chain_link(name, L=0.5, r=0.3, t=0.11, mat=None):
    key = (L, r, t)
    if key in _LINK_MESH and _LINK_MESH[key].name in bpy.data.meshes:
        ob = bpy.data.objects.new(name, _LINK_MESH[key])
        C.link(ob)
    else:
        ob = sweep(name, link_path(L, r), t, closed=True, segs=20)
        _LINK_MESH[key] = ob.data
        if mat:
            C.assign(ob, mat)
    return ob


def chain_spacing(L=0.5, r=0.3, t=0.11):
    return L + 2 * r - 2 * t


def hanging_chain(name, n, L=0.5, r=0.3, t=0.11, mat=None):
    """Links stacked downwards from the root (z=0), alternating 90 degrees."""
    root = C.empty(name)
    sp = chain_spacing(L, r, t)
    links = []
    for i in range(n):
        lk = chain_link(f"{name}_{i:02d}", L, r, t, mat)
        lk.parent = root
        lk.location = (0, 0, -i * sp)
        lk.rotation_euler = (0, 0, (i % 2) * math.pi / 2 + random.uniform(-0.06, 0.06))
        links.append(lk)
    return root, links


def ring(name, R=0.7, t=0.15, mat=None):
    pts = [Vector((R * math.cos(a), 0, R * math.sin(a))) for a in [2 * math.pi * i / 96 for i in range(96)]]
    ob = sweep(name, pts, t, closed=True, segs=24)
    if mat:
        C.assign(ob, mat)
    return ob


# ----------------------------------------------------------------------------- film reel
def film_reel(name, M):
    """35mm split reel: two aluminium flanges with six tear-drop windows, a hub and a film pack."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    root = C.empty(name)
    R = 1.0
    flange = Point(0, 0).buffer(R, 128)
    holes = []
    for k in range(6):
        a = 2 * math.pi * k / 6
        ca, sa = math.cos(a), math.sin(a)
        # tear-drop window between radius 0.30 and 0.86
        tri = Polygon([(0.30 * ca - 0.05 * sa, 0.30 * sa + 0.05 * ca), (0.30 * ca + 0.05 * sa, 0.30 * sa - 0.05 * ca),
                       (0.86 * ca + 0.25 * sa, 0.86 * sa - 0.25 * ca), (0.86 * ca - 0.25 * sa, 0.86 * sa + 0.25 * ca)])
        holes.append(tri.buffer(0.04, join_style=1))
    flange = flange.difference(unary_union(holes)).difference(Point(0, 0).buffer(0.09, 64))
    parts = []
    for side, z0 in (("front", 0.09), ("back", -0.12)):
        fl = C.polygon_to_mesh(f"{name}_flange_{side}", flange, 0.03, z0=z0)
        C.assign(fl, M["alu"])
        C.add_bevel(fl, width=0.008, segments=2, angle=30)
        C.shade_smooth(fl, 30)
        parts.append(fl)
    hub = lathe(f"{name}_hub", [(0.09, -0.16), (0.2, -0.16), (0.2, 0.14), (0.16, 0.16), (0.09, 0.16)],
                segs=64, smooth_angle=30)
    C.assign(hub, M["steel"])
    pack = lathe(f"{name}_film", [(0.21, -0.088), (0.80, -0.088), (0.80, 0.088), (0.21, 0.088)], segs=128,
                 smooth_angle=20)
    fm = C.mat_dielectric(f"{name}_filmpack", (0.035, 0.022, 0.015), rough=0.22, spec=0.6)
    # concentric winding grooves on the pack
    nt = fm.node_tree
    p = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    w.inputs["Scale"].default_value = 60.0
    w.inputs["Distortion"].default_value = 2.0
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = 0.15
    nt.links.new(w.outputs["Fac"], b.inputs["Height"])
    nt.links.new(b.outputs[0], p.inputs["Normal"])
    C.assign(pack, fm)
    parts += [hub, pack]
    parent(parts, root)
    return root


# ----------------------------------------------------------------------------- film strip
def film_strip(name, length=8.0, width=1.375, tex="film_strip.png"):
    """Long plane UV-mapped to the vertical strip texture; scroll it via the returned mapping."""
    from PIL import Image
    im = Image.open(os.path.join(TEX, tex))
    aspect = im.size[1] / im.size[0]          # texture height / width (one repeat)
    bm = bmesh.new()
    nseg = 80
    verts = []
    for i in range(nseg + 1):
        y = -length / 2 + length * i / nseg
        verts.append((bm.verts.new((-width / 2, y, 0)), bm.verts.new((width / 2, y, 0))))
    uv = bm.loops.layers.uv.new("UVMap")
    for i in range(nseg):
        a0, a1 = verts[i]
        b0, b1 = verts[i + 1]
        f = bm.faces.new((a0, a1, b1, b0))
        for lp in f.loops:
            x, y = lp.vert.co.x, lp.vert.co.y
            lp[uv].uv = ((x + width / 2) / width, (y + length / 2) / (width * aspect))
    ob = C.mesh_object(name, bm)
    m, mapping, strength = mat_film(os.path.join(TEX, tex))
    C.assign(ob, m)
    return ob, mapping, strength, width * aspect


# ----------------------------------------------------------------------------- projector
def projector(name, M):
    root = C.empty(name)
    prof = [(0.0, -0.02), (0.30, -0.02), (0.30, 0.0), (0.33, 0.02), (0.33, 0.24), (0.31, 0.26), (0.31, 0.62),
            (0.345, 0.64), (0.345, 0.96), (0.31, 0.98), (0.31, 1.32), (0.36, 1.34), (0.38, 1.40), (0.38, 1.46),
            (0.34, 1.48), (0.27, 1.48)]
    barrel = lathe(f"{name}_barrel", prof, segs=96)
    C.assign(barrel, M["enamel"])
    knurl = lathe(f"{name}_knurl", [(0.346, 0.64), (0.352, 0.65), (0.352, 0.95), (0.346, 0.96)], segs=180)
    km = C.mat_metal(f"{name}_knurl_m", color=(0.6, 0.6, 0.62), rough=0.3, scale=4)
    kn = km.node_tree
    kp = [n for n in kn.nodes if n.type == "BSDF_PRINCIPLED"][0]
    wv = kn.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Z"
    wv.inputs["Scale"].default_value = 30.0
    tcn = kn.nodes.new("ShaderNodeTexCoord")
    gr = kn.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "RADIAL"
    kn.links.new(tcn.outputs["Object"], gr.inputs["Vector"])
    mth = kn.nodes.new("ShaderNodeMath")
    mth.operation = "MULTIPLY"
    mth.inputs[1].default_value = 120.0
    kn.links.new(gr.outputs["Fac"], mth.inputs[0])
    snt = kn.nodes.new("ShaderNodeMath")
    snt.operation = "SINE"
    kn.links.new(mth.outputs[0], snt.inputs[0])
    bmp = kn.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.6
    kn.links.new(snt.outputs[0], bmp.inputs["Height"])
    kn.links.new(bmp.outputs[0], kp.inputs["Normal"])
    C.assign(knurl, km)
    rings = []
    for z in (0.25, 0.62, 1.33):
        rg = lathe(f"{name}_ring{z}", [(0.30, z - 0.012), (0.345, z - 0.008), (0.345, z + 0.008), (0.30, z + 0.012)],
                   segs=96)
        C.assign(rg, M["chrome"])
        rings.append(rg)
    glass = lathe(f"{name}_glass", [(0.0, 1.47), (0.15, 1.465), (0.27, 1.45), (0.275, 1.44)], segs=96)
    C.assign(glass, M["glass"])
    lamp_m, lamp_e = C.mat_emission(f"{name}_lamp_m", (1.0, 0.82, 0.6), 0.0)
    lamp = disc(f"{name}_lamp", 0.26)
    lamp.location = (0, 0, 1.38)
    C.assign(lamp, lamp_m)
    body = rounded_box(f"{name}_body", 1.6, 1.4, 1.2, bevel=0.06)
    body.location = (0, 0, -0.62)
    bm_ = C.mat_dielectric(f"{name}_body_m", (0.02, 0.025, 0.022), rough=0.35, spec=0.5, bump=0.05, scale=30)
    C.assign(body, bm_)
    parent([barrel, knurl, glass, lamp, body] + rings, root)
    return root, lamp_e


# ----------------------------------------------------------------------------- ticket
def ticket(name, w=2.0, h=0.82):
    bm = bmesh.new()
    nx, ny = 40, 16
    vs = [[bm.verts.new((-w / 2 + w * i / nx, -h / 2 + h * j / ny, 0)) for j in range(ny + 1)] for i in range(nx + 1)]
    uv = bm.loops.layers.uv.new("UVMap")
    for i in range(nx):
        for j in range(ny):
            f = bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
            for lp in f.loops:
                lp[uv].uv = ((lp.vert.co.x + w / 2) / w, (lp.vert.co.y + h / 2) / h)
    ob = C.mesh_object(name, bm)
    sol = ob.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.006
    m, prog = mat_ticket_burn(os.path.join(TEX, "ticket.jpg"), w / h)
    C.assign(ob, m)
    # gentle paper curl
    sd = ob.modifiers.new("curl", "SIMPLE_DEFORM")
    sd.deform_method = "BEND"
    sd.deform_axis = "Y"
    sd.angle = math.radians(18)
    return ob, prog


# ----------------------------------------------------------------------------- cine lens + iris
def cine_lens(name, M, n_blades=9, R=0.62):
    root = C.empty(name)
    prof = [(R, -0.6), (R + 0.06, -0.6), (R + 0.16, -0.5), (R + 0.16, -0.05), (R + 0.22, 0.0), (R + 0.22, 0.12),
            (R + 0.12, 0.16), (R + 0.02, 0.16), (R, 0.1)]
    barrel = lathe(f"{name}_barrel", prof, segs=128)
    C.assign(barrel, M["enamel"])
    ring_tex_m, tex_node, _ = C.mat_image(f"{name}_ringm", os.path.join(TEX, "aperture_ring.png"), rough=0.35,
                                          extension="REPEAT")
    marks = lathe(f"{name}_marks", [(R + 0.161, -0.42), (R + 0.161, -0.2)], segs=180)
    bmu = bmesh.new()
    bmu.from_mesh(marks.data)
    uvl = bmu.loops.layers.uv.new("UVMap")
    for f in bmu.faces:
        for lp in f.loops:
            co = lp.vert.co
            lp[uvl].uv = ((math.atan2(co.y, co.x) / (2 * math.pi)) % 1.0, (co.z + 0.42) / 0.22)
    bmu.to_mesh(marks.data)
    bmu.free()
    C.assign(marks, ring_tex_m)
    front = lathe(f"{name}_front", [(R - 0.02, 0.1), (R + 0.03, 0.12), (R + 0.03, 0.15)], segs=128)
    C.assign(front, M["chrome"])
    glass = lathe(f"{name}_glass", [(0.0, -0.05), (R * 0.6, -0.07), (R * 0.97, -0.12)], segs=96)
    C.assign(glass, M["glass"])
    glass.location = (0, 0, 0.16)
    blades = []
    bm_m = C.mat_metal(f"{name}_blade_m", color=(0.05, 0.05, 0.055), rough=0.45, scale=20)
    for k in range(n_blades):
        bmb = bmesh.new()
        a, h = 1.25 * R, 1.3 * R
        pts = [(-a, 0.0), (a, 0.0), (a * 0.7, h), (-a * 1.1, h * 0.9)]
        vs = [bmb.verts.new((x, y, 0)) for x, y in pts]
        bmb.faces.new(vs)
        bl = C.mesh_object(f"{name}_blade{k}", bmb)
        C.assign(bl, bm_m)
        bl.parent = root
        blades.append(bl)
    back_m, back_e = C.mat_emission(f"{name}_backlight", (1.0, 0.02, 0.01), 0.0)
    back = disc(f"{name}_back", R * 1.1)
    back.location = (0, 0, -0.55)
    C.assign(back, back_m)
    parent([barrel, marks, front, glass, back], root)
    return root, blades, back_e


def set_iris(blades, opening, rot, R=0.62, z0=-0.2):
    """Place blades so their inner edges form a regular polygon of inradius `opening`."""
    n = len(blades)
    for k, bl in enumerate(blades):
        th = 2 * math.pi * k / n + rot
        # blade-local +y points outwards; its inner edge (y=0) sits at distance `opening`
        bl.location = (opening * math.cos(th), opening * math.sin(th), z0 + 0.0015 * k)
        bl.rotation_euler = (0, 0, th - math.pi / 2 + math.radians(18))


# ----------------------------------------------------------------------------- speaker
def speaker(name, M):
    root = C.empty(name)
    cone_prof = [(0.24 + 0.71 * (i / 20), 0.36 * (i / 20) ** 0.75) for i in range(21)]
    cone = lathe(f"{name}_cone", cone_prof, segs=128)
    C.assign(cone, M["cone"])
    cap = lathe(f"{name}_cap", [(0.0, 0.06), (0.12, 0.05), (0.2, 0.03), (0.25, 0.0)], segs=96)
    cm = C.mat_dielectric(f"{name}_capm", (0.03, 0.03, 0.032), rough=0.25, spec=0.6)
    C.assign(cap, cm)
    sur = [(0.95 + 0.075 * (1 - math.cos(a)), 0.36 + 0.075 * math.sin(a)) for a in [math.pi * i / 16 for i in range(17)]]
    surround = lathe(f"{name}_surround", sur, segs=128)
    C.assign(surround, M["rubber"])
    frame = lathe(f"{name}_frame", [(1.1, 0.36), (1.32, 0.36), (1.34, 0.34), (1.34, 0.28), (1.12, 0.28)], segs=128)
    C.assign(frame, M["gunmetal"])
    screws = []
    for k in range(8):
        a = 2 * math.pi * k / 8 + 0.2
        s = lathe(f"{name}_screw{k}", [(0.0, 0.38), (0.035, 0.375), (0.045, 0.36), (0.045, 0.355)], segs=24)
        s.location = (1.23 * math.cos(a), 1.23 * math.sin(a), 0)
        C.assign(s, M["chrome"])
        screws.append(s)
    basket = lathe(f"{name}_basket", [(1.12, 0.28), (0.7, -0.2), (0.45, -0.45), (0.45, -0.6), (0.0, -0.6)], segs=64)
    C.assign(basket, M["gunmetal"])
    moving = C.empty(f"{name}_moving")
    moving.parent = root
    cone.parent = moving
    cap.parent = moving
    parent([surround, frame, basket] + screws, root)
    return root, moving, surround


# ----------------------------------------------------------------------------- spotlight
def spotlight(name, M):
    root = C.empty(name)
    head = C.empty(f"{name}_head")
    head.parent = root
    body = lathe(f"{name}_body", [(0.0, -0.9), (0.42, -0.9), (0.55, -0.75), (0.6, -0.6), (0.6, 0.35), (0.64, 0.38),
                                  (0.64, 0.46), (0.52, 0.48)], segs=96)
    C.assign(body, M["enamel"])
    fins = []
    for k in range(6):
        z = -0.5 + k * 0.14
        f = lathe(f"{name}_fin{k}", [(0.6, z), (0.68, z + 0.01), (0.68, z + 0.05), (0.6, z + 0.06)], segs=96)
        C.assign(f, M["gunmetal"])
        fins.append(f)
    lens_m, lens_e = C.mat_emission(f"{name}_lens_m", (1.0, 0.25, 0.12), 0.0)
    # fresnel rings: add a glossy layer with a ring bump on top of the emission
    nt = lens_m.node_tree
    em = [n for n in nt.nodes if n.type == "EMISSION"][0]
    out = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.08
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "RINGS"
    wv.inputs["Scale"].default_value = 9.0
    wv.wave_profile = "SAW"
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.5
    nt.links.new(wv.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs[0], gl.inputs["Normal"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(gl.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    lens = disc(f"{name}_lens", 0.52)
    lens.location = (0, 0, 0.44)
    C.assign(lens, lens_m)
    doors = []
    for k in range(4):
        d = rounded_box(f"{name}_door{k}", 0.9, 0.42, 0.012, bevel=0.004)
        C.assign(d, M["gunmetal"])
        pivot = C.empty(f"{name}_doorpiv{k}")
        pivot.parent = head
        a = k * math.pi / 2
        pivot.location = (0.66 * math.cos(a), 0.66 * math.sin(a), 0.47)
        pivot.rotation_euler = (0, 0, a)
        d.parent = pivot
        d.location = (0.0, 0.0, 0.0)
        d.rotation_euler = (0, math.radians(-65), 0)
        d.location = (0.19 * math.cos(math.radians(65)), 0, 0.19 * math.sin(math.radians(65)))
        doors.append(d)
    yoke = sweep(f"{name}_yoke", [Vector((-0.78, 0, 0.0)), Vector((-0.78, 0, -1.2)), Vector((0.78, 0, -1.2)),
                                   Vector((0.78, 0, 0.0))], 0.05, closed=False, segs=12)
    C.assign(yoke, M["gunmetal"])
    yoke.parent = root
    parent([body, lens] + fins, head)
    return root, head, lens_e
