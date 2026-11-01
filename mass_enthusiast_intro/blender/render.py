"""Build a shot in Blender (bpy) and render its frames to multilayer EXR.

    python blender/render.py --shot s13_title --variant 16x9
    python blender/render.py --shot s01_chain --variant 9x16 --scale 0.75
    python blender/render.py --shot s13_title --frames 600,640 --scale 0.5 --preview

Frames already on disk are skipped, so an interrupted render can simply be resumed.
Camera matrices and effect metadata are written next to the frames for the compositor.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, os.path.join(HERE, "shots"))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
import timeline as TL  # noqa: E402

MODULE_FOR = {
    "s01_chain": "chain", "s02_reel": "reel", "s03_film": "film", "s04_projector": "projector",
    "s05_ticket": "ticket", "s06_lens": "lens", "s07_speaker": "speaker", "s08_redline": "redline",
    "s09_sparks": "sparks", "s10_spot": "spot", "s11_vortex": "vortex",
    "s13_title": "title", "s14_hero": "title",
}


def parse_frames(spec, lo, hi, step):
    if not spec:
        return list(range(lo, hi + 1, step))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1, step))
        else:
            out.append(int(part))
    return [f for f in out if lo <= f <= hi]


def dump_camera(sc, cam_for, frames, path, track=None):
    data = {}
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    for f in frames:
        cam = cam_for(f)
        sc.frame_set(f)
        d = cam.data
        data[str(f)] = dict(
            name=cam.name,
            matrix=[list(r) for r in cam.matrix_world],
            lens=d.lens, sensor_width=d.sensor_width, sensor_height=d.sensor_height, sensor_fit=d.sensor_fit,
            shift_x=d.shift_x, shift_y=d.shift_y, res=[rx, ry],
            focus=d.dof.focus_distance if d.dof.use_dof else None,
        )
        if track:
            data[str(f)]["track"] = {k: list(o.matrix_world.translation) + list(o.matrix_world.to_3x3().col[2])
                                     for k, o in track.items()}
    with open(path, "w") as fh:
        json.dump(data, fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--variant", default="16x9", choices=["16x9", "9x16"])
    ap.add_argument("--frames", default="")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--samples", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(ROOT, "render"))
    ap.add_argument("--preview", action="store_true", help="write tone-mapped PNGs instead of EXR")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--save-blend", action="store_true")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

    mod = importlib.import_module(MODULE_FOR[a.shot])
    kw = dict(variant=a.variant, scale=a.scale)
    import inspect
    if "shot" in inspect.signature(mod.build).parameters:
        kw["shot"] = a.shot
    if a.samples:
        kw["samples"] = a.samples
    t0 = time.time()
    built = mod.build(**kw)
    sc = built["scene"]
    lo, hi = TL.SHOT[a.shot]
    frames = parse_frames(a.frames, lo, hi, a.step)
    outdir = os.path.join(a.out, ("preview_" if a.preview else "") + a.variant, a.shot)
    os.makedirs(outdir, exist_ok=True)
    print(f"[build] {a.shot} {a.variant} built in {time.time() - t0:.1f}s; {len(frames)} frames -> {outdir}", flush=True)

    if not a.preview:
        dump_camera(sc, built["camera_for"], list(range(lo, hi + 1)), os.path.join(outdir, "camera.json"),
                    built.get("track"))
        with open(os.path.join(outdir, "meta.json"), "w") as fh:
            json.dump(built.get("meta", {}), fh)
    if a.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "models", f"{a.shot}_{a.variant}.blend"))

    if a.preview:
        sc.render.image_settings.media_type = "IMAGE"
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_depth = "8"
        sc.render.image_settings.color_mode = "RGB"
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Punchy"
    ext = ".png" if a.preview else ".exr"
    for f in frames:
        path = os.path.join(outdir, f"{f:04d}{ext}")
        if os.path.exists(path) and not a.force:
            continue
        sc.camera = built["camera_for"](f)
        sc.frame_set(f)
        sc.render.filepath = path
        t = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"[frame] {a.shot} {a.variant} {f} {time.time() - t:.1f}s", flush=True)
    print(f"[done] {a.shot} {a.variant} total {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
