"""Shared Blender helpers: render setup, procedural materials, lights, cameras, baking.

Written for Blender 5.2 (the `bpy` module from PyPI), Cycles on CPU.
All animation is baked per frame from Python functions so that shots are fully
deterministic and the compositor/audio can reuse the same maths.
"""
from __future__ import annotations

import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector, Euler, Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import timeline as TL  # noqa: E402

VARIANTS = {"16x9": (1920, 1080), "9x16": (1080, 1920)}


# ----------------------------------------------------------------------------- scene
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    prefs = bpy.context.preferences
    prefs.edit.keyframe_new_interpolation_type = "LINEAR"
    sc = bpy.context.scene
    sc.render.fps = TL.FPS
    sc.render.fps_base = 1.0
    world = bpy.data.worlds.new("World")
    sc.world = world
    nt = world.node_tree
    bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs[1].default_value = 1.0
    out = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs[0], out.inputs[0])
    return sc


def world_color(sc, rgb, strength=1.0):
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*rgb, 1.0)
    bg.inputs[1].default_value = strength


def setup_render(sc, variant="16x9", samples=16, scale=1.0, motion_blur=True, shutter=0.5,
                 glossy_bounces=3, transparent=True):
    w, h = VARIANTS[variant]
    sc.render.resolution_x = int(round(w * scale / 2) * 2)
    sc.render.resolution_y = int(round(h * scale / 2) * 2)
    sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.preview_samples = 8
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.025
    cy.adaptive_min_samples = 0
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.denoising_prefilter = "FAST"
    cy.denoising_quality = "HIGH"
    cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    cy.max_bounces = 8
    cy.diffuse_bounces = 2
    cy.glossy_bounces = glossy_bounces
    cy.transmission_bounces = 4
    cy.transparent_max_bounces = 8 if transparent else 2
    cy.volume_bounces = 0
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = 6.0
    cy.blur_glossy = 0.6
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.use_light_tree = True
    cy.use_animated_seed = True
    sc.render.use_persistent_data = True
    sc.render.film_transparent = False
    sc.render.filter_size = 1.5
    sc.render.use_motion_blur = motion_blur
    sc.render.motion_blur_shutter = shutter
    sc.view_settings.view_transform = "Standard"   # EXR is scene-linear anyway
    sc.view_settings.look = "None"
    im = sc.render.image_settings
    im.media_type = "MULTI_LAYER_IMAGE"
    im.file_format = "OPEN_EXR_MULTILAYER"
    im.color_depth = "16"
    im.exr_codec = "DWAA"
    im.color_mode = "RGBA"
    vl = sc.view_layers[0]
    vl.use_pass_z = True
    return sc


def shot_scene(variant, samples, scale, **kw):
    sc = reset_scene()
    setup_render(sc, variant, samples=samples, scale=scale, **kw)
    return sc


def single_camera(cam):
    return lambda f: cam


# ----------------------------------------------------------------------------- nodes
class NodeBuilder:
    """Tiny helper to write shader graphs compactly."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nodes = self.nt.nodes
        self.links = self.nt.links
        self.x = 0

    def n(self, kind, **inputs):
        node = self.nodes.new(kind)
        node.location = (self.x, 0)
        self.x -= 220
        for k, v in inputs.items():
            if k.startswith("_"):
                setattr(node, k[1:], v)
            else:
                node.inputs[k].default_value = v
        return node

    def l(self, a, b):
        self.links.new(a, b)
        return b


def new_material(name):
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    return m, out


def principled(nb, **kw):
    p = nb.n("ShaderNodeBsdfPrincipled")
    for k, v in kw.items():
        p.inputs[k].default_value = v
    return p


def mat_metal(name, color=(0.56, 0.57, 0.6), rough=0.25, rough_var=0.08, aniso=0.0,
              brushed=False, bump=0.0, scratches=0.0, tangent_uv=None, coat=0.0, dirt=0.0,
              coord="Object", scale=8.0):
    """Physically based metal with procedural roughness breakup, brushing and scratches."""
    m, out = new_material(name)
    nb = NodeBuilder(m)
    p = principled(nb, **{"Base Color": (*color, 1.0), "Metallic": 1.0, "Roughness": rough})
    nb.l(p.outputs[0], out.inputs[0])
    tc = nb.n("ShaderNodeTexCoord")
    co = tc.outputs[coord]
    # roughness breakup
    rough_sum = None
    if rough_var > 0 or brushed or scratches > 0:
        mp = nb.n("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (scale * (1.0 if not brushed else 0.35), scale * (60.0 if brushed else 1.0), scale)
        if brushed:
            mp.inputs["Scale"].default_value = (scale * 0.25, scale * 0.25, scale * 0.25)
        nb.l(co, mp.inputs["Vector"])
        nz = nb.n("ShaderNodeTexNoise", Scale=2.5, Detail=3.0, Roughness=0.6)
        nb.l(mp.outputs[0], nz.inputs["Vector"])
        mr = nb.n("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough - rough_var
        mr.inputs["To Max"].default_value = rough + rough_var
        nb.l(nz.outputs["Fac"], mr.inputs["Value"])
        rough_sum = mr.outputs[0]
        if brushed:
            # long streaks: wave/noise stretched along X
            mp2 = nb.n("ShaderNodeMapping")
            mp2.inputs["Scale"].default_value = (2.0, 260.0, 260.0)
            nb.l(co, mp2.inputs["Vector"])
            nz2 = nb.n("ShaderNodeTexNoise", Scale=1.0, Detail=2.0, Roughness=0.5)
            nb.l(mp2.outputs[0], nz2.inputs["Vector"])
            mr2 = nb.n("ShaderNodeMapRange")
            mr2.inputs["To Min"].default_value = -0.07
            mr2.inputs["To Max"].default_value = 0.07
            nb.l(nz2.outputs["Fac"], mr2.inputs["Value"])
            add = nb.n("ShaderNodeMath", _operation="ADD")
            nb.l(rough_sum, add.inputs[0])
            nb.l(mr2.outputs[0], add.inputs[1])
            rough_sum = add.outputs[0]
            bmp = nb.n("ShaderNodeBump", Strength=0.04, Distance=0.002)
            nb.l(nz2.outputs["Fac"], bmp.inputs["Height"])
            nb.l(bmp.outputs[0], p.inputs["Normal"])
        if scratches > 0:
            mp3 = nb.n("ShaderNodeMapping")
            mp3.inputs["Scale"].default_value = (40.0, 3.0, 40.0)
            mp3.inputs["Rotation"].default_value = (0.3, 0.7, 0.2)
            nb.l(co, mp3.inputs["Vector"])
            vor = nb.n("ShaderNodeTexVoronoi", _feature="DISTANCE_TO_EDGE", Scale=6.0)
            nb.l(mp3.outputs[0], vor.inputs["Vector"])
            mr3 = nb.n("ShaderNodeMapRange")
            mr3.inputs["From Min"].default_value = 0.0
            mr3.inputs["From Max"].default_value = 0.03
            mr3.inputs["To Min"].default_value = -scratches
            mr3.inputs["To Max"].default_value = 0.0
            nb.l(vor.outputs["Distance"], mr3.inputs["Value"])
            add2 = nb.n("ShaderNodeMath", _operation="ADD")
            nb.l(rough_sum, add2.inputs[0])
            nb.l(mr3.outputs[0], add2.inputs[1])
            rough_sum = add2.outputs[0]
        nb.l(rough_sum, p.inputs["Roughness"])
    if aniso > 0:
        p.inputs["Anisotropic"].default_value = aniso
        if tangent_uv:
            tg = nb.n("ShaderNodeTangent", _direction_type="UV_MAP")
            tg.uv_map = tangent_uv
        else:
            tg = nb.n("ShaderNodeTangent", _direction_type="RADIAL", _axis="Z")
        nb.l(tg.outputs[0], p.inputs["Tangent"])
    if bump > 0 and not brushed:
        nz3 = nb.n("ShaderNodeTexNoise", Scale=scale * 6, Detail=4.0)
        nb.l(co, nz3.inputs["Vector"])
        bmp2 = nb.n("ShaderNodeBump", Strength=bump, Distance=0.01)
        nb.l(nz3.outputs["Fac"], bmp2.inputs["Height"])
        nb.l(bmp2.outputs[0], p.inputs["Normal"])
    if dirt > 0:
        # darken crevices / random grime on base colour
        nz4 = nb.n("ShaderNodeTexNoise", Scale=scale * 1.5, Detail=4.0, Roughness=0.7)
        nb.l(co, nz4.inputs["Vector"])
        mix = nb.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY")
        mix.inputs[0].default_value = dirt
        nb.l(nz4.outputs["Color"], mix.inputs[7])
        mix.inputs[6].default_value = (*color, 1.0)
        nb.l(mix.outputs[2], p.inputs["Base Color"])
    if coat > 0:
        p.inputs["Coat Weight"].default_value = coat
        p.inputs["Coat Roughness"].default_value = 0.05
    return m


def mat_dielectric(name, color, rough=0.5, spec=0.5, bump=0.0, scale=10.0, coord="Object"):
    m, out = new_material(name)
    nb = NodeBuilder(m)
    p = principled(nb, **{"Base Color": (*color, 1.0), "Metallic": 0.0, "Roughness": rough,
                          "Specular IOR Level": spec})
    nb.l(p.outputs[0], out.inputs[0])
    if bump > 0:
        tc = nb.n("ShaderNodeTexCoord")
        nz = nb.n("ShaderNodeTexNoise", Scale=scale, Detail=6.0)
        nb.l(tc.outputs[coord], nz.inputs["Vector"])
        b = nb.n("ShaderNodeBump", Strength=bump, Distance=0.01)
        nb.l(nz.outputs["Fac"], b.inputs["Height"])
        nb.l(b.outputs[0], p.inputs["Normal"])
    return m


def mat_emission(name, color=(1, 0.3, 0.05), strength=10.0):
    m, out = new_material(name)
    nb = NodeBuilder(m)
    e = nb.n("ShaderNodeEmission", Color=(*color, 1.0), Strength=strength)
    nb.l(e.outputs[0], out.inputs[0])
    return m, e


def mat_blackbody_glow(name, temp=1500.0, strength=5.0):
    """Emission tinted by a blackbody temperature; both are animatable values."""
    m, out = new_material(name)
    nb = NodeBuilder(m)
    e = nb.n("ShaderNodeEmission", Strength=strength)
    bb = nb.n("ShaderNodeBlackbody", Temperature=temp)
    nb.l(bb.outputs[0], e.inputs["Color"])
    nb.l(e.outputs[0], out.inputs[0])
    return m, bb, e


def mat_molten(name, crust=True):
    """Molten metal: blackbody emission broken up by a drifting crust pattern.

    Returns (material, blackbody node, emission node, noise node) - animate the blackbody
    temperature, the emission strength and the noise 'W' input per frame.
    """
    m, out = new_material(name)
    nb = NodeBuilder(m)
    e = nb.n("ShaderNodeEmission", Strength=0.0)
    nb.l(e.outputs[0], out.inputs[0])
    bb = nb.n("ShaderNodeBlackbody", Temperature=1500.0)
    tc = nb.n("ShaderNodeTexCoord")
    nz = nb.n("ShaderNodeTexNoise", _noise_dimensions="4D", Scale=6.0, Detail=4.0, Roughness=0.6,
              Distortion=1.2)
    nb.l(tc.outputs["Object"], nz.inputs["Vector"])
    # wobble the crack pattern with the noise so the crust is irregular, not cellular
    warp = nb.n("ShaderNodeVectorMath", _operation="MULTIPLY_ADD")
    nb.l(nz.outputs["Color"], warp.inputs[0])
    warp.inputs[1].default_value = (0.12, 0.12, 0.12)
    nb.l(tc.outputs["Object"], warp.inputs[2])
    use_crust = crust
    crust = nb.n("ShaderNodeMapRange")
    crust.inputs["From Min"].default_value = 0.0
    crust.inputs["From Max"].default_value = 0.11
    crust.inputs["To Min"].default_value = 1.35
    crust.inputs["To Max"].default_value = 0.06
    vor = None
    if use_crust:
        vor = nb.n("ShaderNodeTexVoronoi", _feature="DISTANCE_TO_EDGE", Scale=17.0)
        vor.voronoi_dimensions = "4D"
        nb.l(warp.outputs[0], vor.inputs["Vector"])
        nb.l(vor.outputs["Distance"], crust.inputs["Value"])
    else:
        crust.inputs["Value"].default_value = 0.11
    flow = nb.n("ShaderNodeMapRange")
    flow.inputs["From Min"].default_value = 0.32
    flow.inputs["From Max"].default_value = 0.7
    flow.inputs["To Min"].default_value = 0.15
    flow.inputs["To Max"].default_value = 1.6
    nb.l(nz.outputs["Fac"], flow.inputs["Value"])
    mul = nb.n("ShaderNodeMath", _operation="MAXIMUM")
    nb.l(crust.outputs[0], mul.inputs[0])
    nb.l(flow.outputs[0], mul.inputs[1])
    mul2 = nb.n("ShaderNodeMath", _operation="MULTIPLY")
    nb.l(mul.outputs[0], mul2.inputs[0])
    nb.l(flow.outputs[0], mul2.inputs[1])
    mul = mul2
    # hotter where the melt is bright: colour = blackbody(T) * (0.6 + 0.6*mask)
    tint = nb.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY")
    tint.inputs[0].default_value = 1.0
    nb.l(bb.outputs[0], tint.inputs[6])
    nb.l(mul.outputs[0], tint.inputs[7])
    nb.l(tint.outputs[2], e.inputs["Color"])
    strength = nb.n("ShaderNodeValue")
    strength.outputs[0].default_value = 0.0
    sm = nb.n("ShaderNodeMath", _operation="MULTIPLY")
    nb.l(strength.outputs[0], sm.inputs[0])
    nb.l(mul.outputs[0], sm.inputs[1])
    nb.l(sm.outputs[0], e.inputs["Strength"])
    return m, bb, strength, tuple(n for n in (nz, vor) if n is not None)


def mat_image(name, path, emission=0.0, rough=0.5, alpha=False, metallic=0.0, extension="CLIP"):
    m, out = new_material(name)
    nb = NodeBuilder(m)
    p = principled(nb, Roughness=rough, Metallic=metallic)
    nb.l(p.outputs[0], out.inputs[0])
    tex = nb.n("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.extension = extension
    tex.interpolation = "Cubic"
    nb.l(tex.outputs["Color"], p.inputs["Base Color"])
    nb.l(tex.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = emission
    if alpha:
        nb.l(tex.outputs["Alpha"], p.inputs["Alpha"])
    return m, tex, p


def assign(obj, *mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)


# ----------------------------------------------------------------------------- objects
def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_object(name, bm_or_mesh):
    if isinstance(bm_or_mesh, bpy.types.Mesh):
        me = bm_or_mesh
    else:
        me = bpy.data.meshes.new(name)
        bm_or_mesh.to_mesh(me)
        bm_or_mesh.free()
    ob = bpy.data.objects.new(name, me)
    return link(ob)


def shade_smooth(obj, angle=35.0):
    me = obj.data
    for p in me.polygons:
        p.use_smooth = True
    try:
        me.set_sharp_from_angle(angle=math.radians(angle))
    except Exception:
        pass


def add_bevel(obj, width=0.01, segments=3, angle=30.0, harden=True, material=-1, profile=0.5):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    mod.profile = profile
    mod.harden_normals = harden
    mod.material = material
    mod.miter_outer = "MITER_ARC"
    return mod


def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    obj.modifiers.clear()
    old = obj.data
    obj.data = me
    bpy.data.meshes.remove(old)


def empty(name, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    return link(e)


def look_at(obj, target, roll=0.0):
    d = Vector(target) - obj.location
    q = d.to_track_quat("-Z", "Y")
    obj.rotation_mode = "XYZ"
    e = q.to_euler()
    if roll:
        e = (q @ Euler((0, 0, roll)).to_quaternion()).to_euler()
    obj.rotation_euler = e


def camera(name, lens=50.0, loc=(0, -10, 0), target=(0, 0, 0), fstop=2.8, focus=None,
           blades=7, ratio=1.0, sensor=36.0, clip=(0.01, 500)):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = sensor
    cd.sensor_fit = "HORIZONTAL"
    cd.clip_start, cd.clip_end = clip
    cd.dof.use_dof = fstop is not None
    if fstop:
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = blades
        cd.dof.aperture_ratio = ratio
        cd.dof.focus_distance = focus if focus else (Vector(target) - Vector(loc)).length
    ob = bpy.data.objects.new(name, cd)
    ob.location = loc
    link(ob)
    look_at(ob, target)
    return ob


def fit_camera_for_variant(cam, variant, lens16=None):
    """Vertical renders keep the same horizontal field on the long axis by fitting
    the sensor vertically - framing is then adjusted per shot where needed."""
    if variant == "9x16":
        cam.data.sensor_fit = "VERTICAL"
        cam.data.sensor_height = 24.0


def area_light(name, loc, target=(0, 0, 0), energy=100.0, size=1.0, size_y=None, color=(1, 1, 1),
               spread=180.0, visible=False, shape=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.color = color
    ld.spread = math.radians(spread)
    if size_y is not None:
        ld.shape = shape or "RECTANGLE"
        ld.size, ld.size_y = size, size_y
    else:
        ld.shape = shape or "SQUARE"
        ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    link(ob)
    look_at(ob, target)
    ob.visible_camera = visible
    return ob


def point_light(name, loc, energy=100.0, color=(1, 1, 1), radius=0.05):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = energy
    ld.color = color
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    return link(ob)


def spot_light(name, loc, target, energy=500.0, color=(1, 1, 1), size_deg=40.0, blend=0.3, radius=0.05):
    ld = bpy.data.lights.new(name, "SPOT")
    ld.energy = energy
    ld.color = color
    ld.spot_size = math.radians(size_deg)
    ld.spot_blend = blend
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    link(ob)
    look_at(ob, target)
    return ob


def card(name, loc, target, w, h, color=(1, 1, 1), strength=2.0, camera_visible=False, gradient=None):
    """Emissive reflection card (invisible to camera by default)."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= h
    ob = mesh_object(name, bm)
    ob.location = loc
    look_at(ob, target)
    m, out = new_material(name + "_m")
    nb = NodeBuilder(m)
    e = nb.n("ShaderNodeEmission", Color=(*color, 1.0), Strength=strength)
    nb.l(e.outputs[0], out.inputs[0])
    if gradient:   # soft edges: fade the card with a radial-ish gradient over its UV
        tc = nb.n("ShaderNodeTexCoord")
        sep = nb.n("ShaderNodeSeparateXYZ")
        nb.l(tc.outputs["Generated"], sep.inputs[0])
        f1 = nb.n("ShaderNodeMath", _operation="PINGPONG")
        f1.inputs[1].default_value = 0.5
        nb.l(sep.outputs[0], f1.inputs[0])
        f2 = nb.n("ShaderNodeMath", _operation="PINGPONG")
        f2.inputs[1].default_value = 0.5
        nb.l(sep.outputs[1], f2.inputs[0])
        mul = nb.n("ShaderNodeMath", _operation="MULTIPLY")
        nb.l(f1.outputs[0], mul.inputs[0])
        nb.l(f2.outputs[0], mul.inputs[1])
        pw = nb.n("ShaderNodeMath", _operation="POWER")
        pw.inputs[1].default_value = gradient
        nb.l(mul.outputs[0], pw.inputs[0])
        sc4 = nb.n("ShaderNodeMath", _operation="MULTIPLY")
        sc4.inputs[1].default_value = strength * 16.0 ** gradient
        nb.l(pw.outputs[0], sc4.inputs[0])
        nb.l(sc4.outputs[0], e.inputs["Strength"])
    assign(ob, m)
    ob.visible_camera = camera_visible
    ob.visible_shadow = False
    ob.visible_diffuse = True
    return ob, e


# ----------------------------------------------------------------------------- baking
def key_obj(obj, frame, loc=None, rot=None, scale=None):
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert("location", frame=frame)
    if rot is not None:
        obj.rotation_euler = rot
        obj.keyframe_insert("rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale if hasattr(scale, "__len__") else (scale, scale, scale)
        obj.keyframe_insert("scale", frame=frame)


def key_value(socket_or_owner, frame, value, attr="default_value"):
    setattr(socket_or_owner, attr, value)
    socket_or_owner.keyframe_insert(attr, frame=frame)


def bake_range(f0, f1, fn, pad=2):
    """Call fn(frame) for every frame (with padding for motion blur sub-frames)."""
    for f in range(f0 - pad, f1 + pad + 1):
        fn(f)


def bake_camera(cam, f0, f1, loc_fn, target_fn, roll_fn=None, focus_fn=None, lens_fn=None, pad=2):
    for f in range(f0 - pad, f1 + pad + 1):
        cam.location = loc_fn(f)
        look_at(cam, target_fn(f), roll_fn(f) if roll_fn else 0.0)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        if focus_fn:
            cam.data.dof.focus_distance = focus_fn(f)
            cam.data.dof.keyframe_insert("focus_distance", frame=f)
        if lens_fn:
            cam.data.lens = lens_fn(f)
            cam.data.keyframe_insert("lens", frame=f)


def fix_euler_flips(obj):
    """Make baked euler keys continuous (avoid 2*pi jumps that wreck motion blur)."""
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    try:
        fcs = [fc for fc in _action_fcurves(ad.action, obj) if fc.data_path == "rotation_euler"]
    except Exception:
        return
    for fc in fcs:
        prev = None
        for kp in fc.keyframe_points:
            v = kp.co[1]
            if prev is not None:
                while v - prev > math.pi:
                    v -= 2 * math.pi
                while v - prev < -math.pi:
                    v += 2 * math.pi
                kp.co[1] = v
                kp.handle_left[1] = v
                kp.handle_right[1] = v
            prev = v


def _action_fcurves(action, owner):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out


# ----------------------------------------------------------------------------- geometry
def polygon_to_mesh(name, poly, depth, z0=0.0, uv_scale=1.0):
    """Extrude a shapely polygon (with holes) into a closed mesh via a 2D curve."""
    from shapely.geometry import MultiPolygon
    cu = bpy.data.curves.new(name + "_cu", "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = depth / 2.0
    cu.resolution_u = 1
    polys = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            coords = list(ring.coords)[:-1]
            sp = cu.splines.new("POLY")
            sp.points.add(len(coords) - 1)
            for i, (x, y) in enumerate(coords):
                sp.points[i].co = (x, y, 0.0, 1.0)
            sp.use_cyclic_u = True
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.name = name
    # shift so that the back face sits at z0 and the front at z0+depth
    for v in me.vertices:
        v.co.z += depth / 2.0 + z0
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uv].uv = (lp.vert.co.x * uv_scale, lp.vert.co.y * uv_scale)
    bm.to_mesh(me)
    bm.free()
    return mesh_object(name, me)


def set_face_materials_by_normal(obj, front=0, side=1, back=None, thresh=0.7):
    me = obj.data
    for p in me.polygons:
        nz = p.normal.z
        if nz > thresh:
            p.material_index = front
        elif nz < -thresh:
            p.material_index = back if back is not None else side
        else:
            p.material_index = side
