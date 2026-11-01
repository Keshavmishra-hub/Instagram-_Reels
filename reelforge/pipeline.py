"""Stage orchestration + background jobs (used by both the CLI and the web UI)."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .config import Settings, settings as default_settings
from .models import Beat, CoverSpec, Overlay, ProjectSettings, Scene, Script, Storyboard, Visual
from .storage import ProjectStore, store as default_store


class NeedsInput(RuntimeError):
    """The stage cannot run automatically (e.g. no API key) - the user must provide input."""


# ---------------------------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------------------------

def stage_research(pid: str, store: ProjectStore, s: Settings, log: Callable[[str], None], progress: Callable[[float], None]) -> Any:
    if not s.has_llm:
        raise NeedsInput("No ANTHROPIC_API_KEY. Use Claude Code mode (`/reel-research` in Claude Code) or add sources and claims manually.")
    from .research.pipeline import run_auto_research

    r = run_auto_research(pid, store, s, log)
    if not r.sufficiency.enough:
        store.set_stage(pid, "research", "needs_review", r.sufficiency.reason)
        return r
    return r


def stage_verify_sources(pid, store, s, log, progress):
    from .research.pipeline import refresh_snapshots, save_research
    from .research.verify import verify_research

    r = store.research(pid)
    if r is None:
        raise RuntimeError("No research to verify")
    refresh_snapshots(r, store.dir(pid), s, log)
    stats = verify_research(r, store.dir(pid))
    save_research(pid, store, r)
    log(f"Re-verified: {stats}")
    return r


def stage_script(pid, store, s, log, progress):
    if not s.has_llm:
        raise NeedsInput("No ANTHROPIC_API_KEY. Write the script in the editor, or use Claude Code (`/reel-script`).")
    r = store.research(pid)
    if r is None or not r.approved:
        raise NeedsInput("Review and approve the research first.")
    from .script.writer import write_script

    return write_script(pid, store, s, log)


def stage_storyboard(pid, store, s, log, progress):
    script = store.script(pid)
    if script is None or not script.approved:
        raise NeedsInput("Approve the script first.")
    from .storyboard.planner import plan_storyboard

    return plan_storyboard(pid, store, s, log)


def stage_voice(pid, store, s, log, progress):
    script = store.script(pid)
    if script is None or not script.approved:
        raise NeedsInput("Approve the script first.")
    from .voice.narration import synthesize_script

    return synthesize_script(pid, store, s, log)


def stage_assets(pid, store, s, log, progress):
    if store.storyboard(pid) is None:
        raise NeedsInput("Create the storyboard first.")
    from .assets.select import gather_assets

    rep = gather_assets(pid, store, s, log)
    if rep["errors"]:
        log(f"Media provider notes: {rep['errors'][:4]}")
    return rep


def stage_render(pid, store, s, log, progress):
    from .render.pipeline import render_reel

    return render_reel(pid, store, s, log, progress)


def stage_package(pid, store, s, log, progress):
    from .publish.instagram import build_package

    return build_package(pid, store, s, log)


def stage_qc(pid, store, s, log, progress):
    from .qc.checks import run_qc

    rep = run_qc(pid, store, s, log)
    log(rep.summary)
    return rep


STAGES: dict[str, Callable] = {
    "research": stage_research,
    "verify_sources": stage_verify_sources,
    "script": stage_script,
    "storyboard": stage_storyboard,
    "voice": stage_voice,
    "assets": stage_assets,
    "render": stage_render,
    "package": stage_package,
    "qc": stage_qc,
}
STATUS_KEY = {"verify_sources": "research"}


def run_stage(pid: str, stage: str, store: ProjectStore = default_store, s: Settings = default_settings,
              log: Callable[[str], None] = print, progress: Callable[[float], None] = lambda p: None) -> Any:
    key = STATUS_KEY.get(stage, stage)
    store.set_stage(pid, key, "running")

    def _log(msg: str) -> None:
        store.log(pid, f"[{stage}] {msg}")
        log(msg)

    try:
        out = STAGES[stage](pid, store, s, _log, progress)
    except NeedsInput as e:
        store.set_stage(pid, key, "needs_review", str(e))
        raise
    except Exception as e:
        store.set_stage(pid, key, "failed", str(e)[:500])
        raise
    project = store.project(pid)
    if project.stages.get(key) and project.stages[key].status == "running":
        msg = ""
        if stage == "qc":
            msg = out.summary
        store.set_stage(pid, key, "done" if not (stage == "qc" and not out.passed) else "needs_review", msg)
    if stage in ("research", "script", "voice", "assets"):
        store.invalidate_downstream(pid, key)
    elif stage == "storyboard":
        store.invalidate_downstream(pid, "voice")  # a new plan does not change the narration
    return out


PRODUCTION = ["voice", "assets", "render", "package", "qc"]


def produce(pid: str, store: ProjectStore = default_store, s: Settings = default_settings, log: Callable[[str], None] = print,
            progress: Callable[[float], None] = lambda p: None, stages: Optional[list[str]] = None) -> Any:
    stages = stages or PRODUCTION
    out = None
    weights = {"voice": 0.1, "assets": 0.1, "render": 0.6, "package": 0.05, "qc": 0.15}
    done = 0.0
    for st in stages:
        w = weights.get(st, 0.1)
        out = run_stage(pid, st, store, s, log, lambda p, d=done, w=w: progress(d + w * p))
        done += w
        progress(done)
    return out


# ---------------------------------------------------------------------------------------------
# Imports (Claude Code mode / hand-written)
# ---------------------------------------------------------------------------------------------

def import_script(pid: str, data: dict, store: ProjectStore = default_store, written_by: str = "manual") -> Script:
    from .script.writer import save_script

    project = store.project(pid)
    prev = store.script(pid)
    beats = []
    for i, b in enumerate(data.get("beats", []), 1):
        beats.append(Beat(id=b.get("id") or f"B{i}", section=b.get("section", "story"), text=b["text"].strip(),
                          claim_ids=list(b.get("claim_ids", [])), emphasis=list(b.get("emphasis", [])),
                          on_screen_text=b.get("on_screen_text"), spoken=b.get("spoken")))
    script = Script(title=data.get("title", project.settings.topic), hook_type=data.get("hook_type", ""), style=project.settings.style,
                    language=project.settings.language, beats=beats, cta_question=data.get("cta_question", ""),
                    version=(prev.version + 1) if prev else 1, written_by=written_by)
    save_script(pid, store, script)
    store.set_stage(pid, "script", "done", f"{len(beats)} beats ({written_by})")
    store.invalidate_downstream(pid, "script")
    return store.script(pid)  # type: ignore[return-value]


def import_storyboard(pid: str, data: dict, store: ProjectStore = default_store, planned_by: str = "manual") -> Storyboard:
    from .storyboard.planner import save_storyboard

    script = store.script(pid)
    research = store.research(pid)
    scenes = []
    for i, sc in enumerate(data.get("scenes", []), 1):
        v = sc["visual"]
        vis = Visual(kind=v["kind"], purpose=v.get("purpose", ""), queries=v.get("queries", []), prefer=v.get("prefer", "any"),
                     params=v.get("params", {}), authenticity=v.get("authenticity", "generated_graphic"))
        bgq = sc.get("background_queries") or []
        bg = Visual(kind="footage", queries=bgq, prefer="video", authenticity="representative") if bgq else None
        src_ids = sorted({e.source_id for b in sc["beat_ids"] for cid in (script.beat(b).claim_ids if script and script.beat(b) else [])
                          if research and research.claim(cid) for e in research.claim(cid).evidence
                          if e.verification in ("exact", "fuzzy", "agent_attested")})
        scenes.append(Scene(id=sc.get("id") or f"SC{i}", beat_ids=sc["beat_ids"], visual=vis, background=bg,
                            overlays=[Overlay(**o) for o in sc.get("overlays", [])], transition=sc.get("transition", "fade"),
                            subtitle_position=sc.get("subtitle_position", "lower"), source_ids=sc.get("source_ids", src_ids), sfx=sc.get("sfx")))
    cov = data.get("cover") or {}
    beat_to_scene = {b: s_.id for s_ in scenes for b in s_.beat_ids}
    cover = CoverSpec(headline=cov.get("headline", script.title if script else ""), highlight=cov.get("highlight", ""),
                      kicker=cov.get("kicker", ""), scene_id=cov.get("scene_id") or beat_to_scene.get(cov.get("beat_id", "")))
    prev = store.storyboard(pid)
    sb = Storyboard(scenes=scenes, music_mood=data.get("music_mood", "curious"), cover=cover, version=(prev.version + 1) if prev else 1, planned_by=planned_by)
    issues = save_storyboard(pid, store, sb)
    store.set_stage(pid, "storyboard", "done" if not any(i.severity == "error" for i in issues) else "needs_review",
                    f"{len(scenes)} scenes ({planned_by})" + (f"; {len(issues)} issue(s)" if issues else ""))
    store.invalidate_downstream(pid, "voice")
    return sb


# ---------------------------------------------------------------------------------------------
# Background jobs for the web UI
# ---------------------------------------------------------------------------------------------

@dataclass
class Job:
    id: str
    pid: str
    stage: str
    status: str = "queued"  # queued | running | done | failed | needs_input
    progress: float = 0.0
    logs: list[str] = field(default_factory=list)
    error: str = ""
    started: float = field(default_factory=time.time)
    finished: Optional[float] = None


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._project_busy: dict[str, str] = {}

    def start(self, pid: str, stage: str, fn: Callable[[Callable[[str], None], Callable[[float], None]], Any]) -> Job:
        with self._lock:
            busy = self._project_busy.get(pid)
            if busy and self.jobs[busy].status in ("queued", "running"):
                raise RuntimeError(f"Project is busy with '{self.jobs[busy].stage}'")
            job = Job(id=uuid.uuid4().hex[:10], pid=pid, stage=stage)
            self.jobs[job.id] = job
            self._project_busy[pid] = job.id

        def log(m: str) -> None:
            job.logs.append(m)
            job.logs[:] = job.logs[-400:]

        def prog(p: float) -> None:
            job.progress = max(job.progress, min(1.0, float(p)))

        def runner():
            job.status = "running"
            try:
                fn(log, prog)
                job.status = "done"
                job.progress = 1.0
            except NeedsInput as e:
                job.status, job.error = "needs_input", str(e)
            except Exception as e:
                job.status, job.error = "failed", str(e)
                log(traceback.format_exc()[-1500:])
            finally:
                job.finished = time.time()

        threading.Thread(target=runner, daemon=True).start()
        return job

    def get(self, jid: str) -> Optional[Job]:
        return self.jobs.get(jid)

    def for_project(self, pid: str) -> Optional[Job]:
        jid = self._project_busy.get(pid)
        return self.jobs.get(jid) if jid else None


jobs = JobManager()


def new_project(ps: ProjectSettings, store: ProjectStore = default_store):
    return store.create(ps)
