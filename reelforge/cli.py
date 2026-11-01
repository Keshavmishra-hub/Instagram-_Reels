"""Command-line interface:  python -m reelforge <command> ...  (see README)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import settings
from .models import NarrationSettings, ProjectSettings
from .storage import store


def _p(*a):
    print(*a, flush=True)


def cmd_setup_models(args):
    from .voice.kokoro_tts import ensure_models

    _p("Kokoro TTS:", ensure_models(settings, _p))
    if args.asr:
        from .voice.asr import ensure_asr_model

        _p("ASR model ready:", ensure_asr_model(settings, _p))


def cmd_new(args):
    ps = ProjectSettings(
        topic=args.topic, language=args.lang, duration=args.duration, style=args.style, brand=args.brand,
        narration=NarrationSettings(provider=args.tts, voice=args.voice, speed=args.speed, tone=args.tone),
        audience=args.audience or "", angle=args.angle or "", music_mood=args.music,
    )
    p = store.create(ps)
    _p(p.id)


def _stage(name):
    def run(args):
        from .pipeline import run_stage

        out = run_stage(args.project, name, store, settings, _p, lambda x: None)
        if name == "qc":
            sys.exit(0 if out.passed else 2)
    return run


def cmd_import(kind):
    def run(args):
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if kind == "research":
            from .research.pipeline import import_research

            r = import_research(args.project, store, data, method=args.method, refetch=not args.no_refetch, log=_p)
            store.set_stage(args.project, "research", "done" if r.sufficiency.enough else "needs_review", r.sufficiency.reason)
            _p(f"Imported {len(r.claims)} claims / {len(r.sources)} sources -> {store.dir(args.project) / 'research.md'}")
        elif kind == "script":
            from .pipeline import import_script

            s = import_script(args.project, data, store, written_by=args.by)
            for i in s.issues:
                _p(f"[{i.severity}] {i.beat_id or ''} {i.message}")
        elif kind == "storyboard":
            from .pipeline import import_storyboard

            sb = import_storyboard(args.project, data, store, planned_by=args.by)
            issues = store.read_json(args.project, "storyboard_issues.json") or []
            for i in issues:
                _p(f"[{i['severity']}] {i.get('beat_id') or ''} {i['message']}")
            _p(f"{len(sb.scenes)} scenes saved")
    return run


def cmd_approve(args):
    if args.what == "research":
        r = store.research(args.project)
        if r is None:
            sys.exit("no research")
        if not r.sufficiency.enough:
            sys.exit(f"Research is insufficient: {r.sufficiency.reason}")
        from .models import now_iso

        r.approved, r.approved_at = True, now_iso()
        store.save("research", args.project, r)
        _p("research approved")
    else:
        from .script.writer import approve_script

        approve_script(args.project, store)
        _p("script approved")


def cmd_produce(args):
    from .pipeline import produce

    out = produce(args.project, store, settings, _p)
    sys.exit(0 if getattr(out, "passed", True) else 2)


def cmd_make(args):
    """Fully automatic run (needs ANTHROPIC_API_KEY): every gate is auto-approved only if it has no errors."""
    from .models import now_iso
    from .pipeline import produce, run_stage
    from .script.writer import approve_script

    cmd_new(args)
    pid = store.list()[0].id
    r = run_stage(pid, "research", store, settings, _p)
    if not r.sufficiency.enough:
        sys.exit(f"Stopped: research insufficient - {r.sufficiency.reason}")
    r.approved, r.approved_at = True, now_iso()
    store.save("research", pid, r)
    run_stage(pid, "script", store, settings, _p)
    approve_script(pid, store)
    run_stage(pid, "storyboard", store, settings, _p)
    out = produce(pid, store, settings, _p)
    _p(f"Project: {pid}\nVideo: {store.dir(pid) / 'output/reel.mp4'}\n{out.summary}")


def cmd_preview(args):
    from .render.pipeline import render_scene_preview

    _p(render_scene_preview(args.project, args.scene, store, settings, _p))


def cmd_stills(args):
    from .render.pipeline import render_storyboard_stills

    for p in render_storyboard_stills(args.project, store, settings, _p):
        _p(p)


def cmd_status(args):
    p = store.project(args.project)
    _p(json.dumps(p.model_dump(), indent=2))


def cmd_list(args):
    for p in store.list():
        _p(f"{p.id:50} {'COMPLETE' if p.complete else '':9} {p.settings.topic}")


def cmd_serve(args):
    import uvicorn

    uvicorn.run("reelforge.server.app:app", host=args.host, port=args.port, reload=False, log_level="info")


def cmd_doctor(args):
    _p(json.dumps(settings.capabilities(), indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="reelforge", description="Research-first Instagram Reel production")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("setup-models", help="download local TTS (and optional ASR) models")
    a.add_argument("--asr", action="store_true", help="also download the offline English ASR model (~460 MB) for QC")
    a.set_defaults(fn=cmd_setup_models)

    def project_args(a):
        a.add_argument("topic")
        a.add_argument("--lang", default="en")
        a.add_argument("--duration", type=int, default=45)
        a.add_argument("--style", default="documentary")
        a.add_argument("--brand", default="default")
        a.add_argument("--tts", default="kokoro")
        a.add_argument("--voice", default="af_heart")
        a.add_argument("--speed", type=float, default=1.0)
        a.add_argument("--tone", default="auto")
        a.add_argument("--music", default="auto")
        a.add_argument("--audience", default="")
        a.add_argument("--angle", default="")

    a = sub.add_parser("new", help="create a project")
    project_args(a)
    a.set_defaults(fn=cmd_new)
    a = sub.add_parser("make", help="topic -> finished reel automatically (needs ANTHROPIC_API_KEY)")
    project_args(a)
    a.set_defaults(fn=cmd_make)

    for name in ("research", "verify_sources", "script", "storyboard", "voice", "assets", "render", "package", "qc"):
        a = sub.add_parser(name.replace("_", "-"), help=f"run the {name} stage")
        a.add_argument("project")
        a.set_defaults(fn=_stage(name))

    for kind in ("research", "script", "storyboard"):
        a = sub.add_parser(f"import-{kind}", help=f"import {kind} JSON (Claude Code mode / manual)")
        a.add_argument("project")
        a.add_argument("file")
        a.add_argument("--by", default="claude_code")
        a.add_argument("--method", default="claude_code: WebSearch + WebFetch; quotes captured verbatim")
        a.add_argument("--no-refetch", action="store_true")
        a.set_defaults(fn=cmd_import(kind))

    a = sub.add_parser("approve", help="approve research or script")
    a.add_argument("what", choices=["research", "script"])
    a.add_argument("project")
    a.set_defaults(fn=cmd_approve)
    a = sub.add_parser("produce", help="voice -> assets -> render -> package -> QC")
    a.add_argument("project")
    a.set_defaults(fn=cmd_produce)
    a = sub.add_parser("preview", help="low-res preview of one scene")
    a.add_argument("project")
    a.add_argument("scene")
    a.set_defaults(fn=cmd_preview)
    a = sub.add_parser("stills", help="storyboard stills for every scene")
    a.add_argument("project")
    a.set_defaults(fn=cmd_stills)
    a = sub.add_parser("status")
    a.add_argument("project")
    a.set_defaults(fn=cmd_status)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("doctor", help="show which integrations are configured").set_defaults(fn=cmd_doctor)
    a = sub.add_parser("serve", help="start the web app")
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--port", type=int, default=8000)
    a.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
    settings.ensure_dirs()
    args.fn(args)


if __name__ == "__main__":
    main()
