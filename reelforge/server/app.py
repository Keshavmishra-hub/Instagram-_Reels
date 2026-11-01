"""Web app: FastAPI JSON API + a single-page UI (static/)."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..brand import list_brands
from ..config import settings
from ..languages import KOKORO_VOICE_LABELS, language_options
from ..models import NarrationSettings, ProjectSettings, Research, Script, Storyboard, now_iso
from ..pipeline import NeedsInput, STAGES, import_script, import_storyboard, jobs, produce, run_stage
from ..storage import STAGES as STAGE_ORDER, store
from ..styles import style_options

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="ReelForge", version="1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

DELIVERABLES = {
    "reel": "output/reel.mp4",
    "cover": "output/cover.jpg",
    "cover_grid": "output/cover_grid_preview.jpg",
    "srt": "output/captions.srt",
    "vtt": "output/captions.vtt",
    "caption": "output/caption.txt",
    "pinned": "output/pinned_comment.txt",
    "sources": "output/sources.md",
    "credits": "output/credits.txt",
    "qc": "output/qc_report.md",
    "research": "research.md",
    "research_json": "research.json",
    "script": "script.md",
}


def _need(pid: str) -> None:
    if not store.exists(pid):
        raise HTTPException(404, "project not found")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta")
def meta() -> dict:
    from ..voice.providers import OPENAI_VOICES

    return {
        "styles": style_options(),
        "languages": language_options(),
        "kokoro_voices": KOKORO_VOICE_LABELS,
        "openai_voices": OPENAI_VOICES,
        "brands": list_brands(),
        "capabilities": settings.capabilities(),
        "stages": STAGE_ORDER,
        "music_moods": ["auto", "curious", "uplifting", "tense", "epic", "calm", "none"],
    }


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return [{"id": p.id, "topic": p.settings.topic, "complete": p.complete, "updated_at": p.updated_at,
             "stages": {k: v.status for k, v in p.stages.items()}} for p in store.list()]


@app.post("/api/projects")
def create_project(body: dict = Body(...)) -> dict:
    try:
        ps = ProjectSettings(
            topic=body["topic"].strip(), language=body.get("language", "en"), duration=int(body.get("duration", 45)),
            style=body.get("style", "documentary"), brand=body.get("brand", "default"), music_mood=body.get("music_mood", "auto"),
            audience=body.get("audience", ""), angle=body.get("angle", ""),
            narration=NarrationSettings(**(body.get("narration") or {})),
        )
    except Exception as e:
        raise HTTPException(400, f"invalid settings: {e}")
    if len(ps.topic) < 3:
        raise HTTPException(400, "topic is too short")
    p = store.create(ps)
    return {"id": p.id}


@app.get("/api/projects/{pid}")
def get_project(pid: str) -> dict:
    _need(pid)
    p = store.project(pid)
    tl = store.timeline(pid)
    d = store.dir(pid)
    job = jobs.for_project(pid)
    files = {k: f"/files/{pid}/{rel}" for k, rel in DELIVERABLES.items() if (d / rel).exists()}
    # one image per scene: whichever is newer of the storyboard still and the frame taken from the final render
    best: dict[str, Path] = {}
    for f in list((d / "render/stills").glob("*.jpg")) + list((d / "render/thumbs").glob("*.jpg")):
        if f.stem not in best or f.stat().st_mtime > best[f.stem].stat().st_mtime:
            best[f.stem] = f
    sb_mtime = (d / "storyboard.json").stat().st_mtime if (d / "storyboard.json").exists() else 0
    thumbs = {k: f"/files/{pid}/{f.relative_to(d).as_posix()}?v={int(f.stat().st_mtime)}" for k, f in best.items() if f.stat().st_mtime >= sb_mtime}
    stills: dict[str, str] = {}
    previews = {f.stem.replace("preview_", ""): f"/files/{pid}/render/{f.name}" for f in sorted((d / "render").glob("preview_*.mp4"))}
    return {
        "project": p.model_dump(),
        "research": (store.research(pid).model_dump() if store.research(pid) else None),
        "script": (store.script(pid).model_dump() if store.script(pid) else None),
        "storyboard": (store.storyboard(pid).model_dump() if store.storyboard(pid) else None),
        "storyboard_issues": store.read_json(pid, "storyboard_issues.json") or [],
        "timeline": ({"duration": tl.duration, "alignment": tl.alignment, "voice": tl.voice, "provider": tl.provider,
                      "scenes": [s.model_dump() for s in tl.scenes], "beats": [b.model_dump() for b in tl.beats]} if tl else None),
        "assets": store.assets(pid).model_dump(),
        "qc": (store.qc(pid).model_dump() if store.qc(pid) else None),
        "package": (store.package(pid).model_dump() if store.package(pid) else None),
        "caption_full": (d / "output/caption.txt").read_text(encoding="utf-8") if (d / "output/caption.txt").exists() else "",
        "files": files,
        "narration_url": f"/files/{pid}/audio/narration.wav" if (d / "audio/narration.wav").exists() else None,
        "thumbs": thumbs,
        "stills": stills,
        "previews": previews,
        "job": (vars(job) if job else None),
        "log": store.read_log(pid, 60),
    }


@app.patch("/api/projects/{pid}/settings")
def update_settings(pid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    p = store.project(pid)
    data = p.settings.model_dump()
    for k, v in body.items():
        if k == "narration" and isinstance(v, dict):
            data["narration"].update(v)
        elif k in data and k != "topic":
            data[k] = v
    p.settings = ProjectSettings.model_validate(data)
    store.save("project", pid, p)
    if "narration" in body:
        store.invalidate_downstream(pid, "storyboard")
    return p.settings.model_dump()


# ------------------------------------------------------------------------------------- jobs
@app.post("/api/projects/{pid}/stages/{stage}")
def start_stage(pid: str, stage: str) -> dict:
    _need(pid)
    if stage not in STAGES:
        raise HTTPException(404, "unknown stage")
    try:
        job = jobs.start(pid, stage, lambda log, prog: run_stage(pid, stage, store, settings, log, prog))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"job": job.id}


@app.post("/api/projects/{pid}/produce")
def start_produce(pid: str) -> dict:
    _need(pid)
    script = store.script(pid)
    if not (script and script.approved):
        raise HTTPException(400, "Approve the script first")
    if store.storyboard(pid) is None:
        raise HTTPException(400, "Create the storyboard first")
    try:
        job = jobs.start(pid, "produce", lambda log, prog: produce(pid, store, settings, log, prog))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"job": job.id}


@app.get("/api/jobs/{jid}")
def get_job(jid: str) -> dict:
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    return vars(job)


# ------------------------------------------------------------------------------------- research
@app.post("/api/projects/{pid}/research/approve")
def approve_research(pid: str) -> dict:
    _need(pid)
    r = store.research(pid)
    if r is None:
        raise HTTPException(400, "no research yet")
    if not r.sufficiency.enough:
        raise HTTPException(400, f"Research is not sufficient: {r.sufficiency.reason}")
    r.approved, r.approved_at = True, now_iso()
    store.save("research", pid, r)
    store.set_stage(pid, "research", "done", "approved")
    return {"ok": True}


@app.post("/api/projects/{pid}/research/claims/{cid}")
def update_claim(pid: str, cid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    from ..research.pipeline import save_research

    r = store.research(pid)
    c = r.claim(cid) if r else None
    if not c:
        raise HTTPException(404, "claim not found")
    if "use_in_script" in body:
        c.use_in_script = bool(body["use_in_script"])
    if "caveats" in body:
        c.caveats = str(body["caveats"])
    r.approved = False
    save_research(pid, store, r)
    return c.model_dump()


@app.post("/api/projects/{pid}/research/sources")
def add_source(pid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    from ..research.pipeline import add_manual_source

    try:
        return add_manual_source(pid, store, body["url"], settings).model_dump()
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/projects/{pid}/research/claims")
def add_claim(pid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    from ..research.pipeline import add_manual_claim

    try:
        return add_manual_claim(pid, store, body["statement"], body["source_id"], body["quote"], body.get("certainty", "established"),
                                body.get("as_of"), body.get("caveats", "")).model_dump()
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/projects/{pid}/research/import")
def import_research_api(pid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    from ..research.pipeline import import_research

    r = import_research(pid, store, body, method=body.get("method", "imported"), s=settings)
    store.set_stage(pid, "research", "done" if r.sufficiency.enough else "needs_review", r.sufficiency.reason)
    return {"claims": len(r.claims), "sources": len(r.sources)}


# ------------------------------------------------------------------------------------- script
@app.put("/api/projects/{pid}/script")
def save_script_api(pid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    s = import_script(pid, body, store, written_by=body.get("written_by", "editor"))
    return s.model_dump()


@app.post("/api/projects/{pid}/script/approve")
def approve_script_api(pid: str) -> dict:
    _need(pid)
    from ..script.writer import approve_script

    try:
        approve_script(pid, store)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    store.set_stage(pid, "script", "done", "approved")
    return {"ok": True}


# ------------------------------------------------------------------------------------- storyboard
@app.put("/api/projects/{pid}/storyboard")
def save_storyboard_api(pid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    from ..storyboard.planner import save_storyboard

    sb = Storyboard.model_validate(body)
    issues = save_storyboard(pid, store, sb)
    store.invalidate_downstream(pid, "voice")  # narration is still valid; media, render, QC and caption are not
    return {"issues": [i.model_dump() for i in issues]}


@app.post("/api/projects/{pid}/storyboard/scenes/{sid}/regenerate")
def regenerate_scene_api(pid: str, sid: str, body: dict = Body(default={})) -> dict:
    _need(pid)
    if not settings.has_llm:
        raise HTTPException(400, "Scene regeneration with Claude needs ANTHROPIC_API_KEY; edit the scene manually instead.")
    from ..storyboard.planner import regenerate_scene

    def work(log, prog):
        regenerate_scene(pid, sid, store, body.get("instruction", ""), settings, log)
        from ..assets.select import gather_assets

        gather_assets(pid, store, settings, log, only_scene=sid)

    job = jobs.start(pid, f"regenerate {sid}", work)
    return {"job": job.id}


@app.post("/api/projects/{pid}/storyboard/scenes/{sid}/swap")
def swap_api(pid: str, sid: str, body: dict = Body(...)) -> dict:
    _need(pid)
    from ..assets.select import swap_asset

    try:
        a = swap_asset(pid, store, sid, body["asset_id"], body.get("role", "visual"), settings)
    except Exception as e:
        raise HTTPException(400, str(e))
    return a.model_dump()


@app.post("/api/projects/{pid}/storyboard/scenes/{sid}/preview")
def preview_api(pid: str, sid: str) -> dict:
    _need(pid)
    from ..render.pipeline import render_scene_preview

    job = jobs.start(pid, f"preview {sid}", lambda log, prog: render_scene_preview(pid, sid, store, settings, log))
    return {"job": job.id}


@app.post("/api/projects/{pid}/stills")
def stills_api(pid: str) -> dict:
    _need(pid)
    from ..render.pipeline import render_storyboard_stills

    job = jobs.start(pid, "stills", lambda log, prog: render_storyboard_stills(pid, store, settings, log))
    return {"job": job.id}


@app.post("/api/projects/{pid}/assets/upload")
async def upload_asset(pid: str, file: UploadFile = File(...), license: str = Form(...), author: str = Form(...),
                       authenticity: str = Form("documentary"), scene_id: Optional[str] = Form(None)) -> dict:
    _need(pid)
    from ..assets.select import add_local_asset, swap_asset

    tmp = store.dir(pid) / "assets" / f"upload_{Path(file.filename or 'file').name}"
    with open(tmp, "wb") as f:
        shutil.copyfileobj(file.file, f)
    a = add_local_asset(pid, store, tmp, license=license, author=author, authenticity=authenticity, s=settings)
    tmp.unlink(missing_ok=True)
    if scene_id:
        swap_asset(pid, store, scene_id, a.id, "visual", settings)
    return a.model_dump()


@app.post("/api/projects/{pid}/music")
async def upload_music(pid: str, file: UploadFile = File(...), license: str = Form(...)) -> dict:
    _need(pid)
    suffix = Path(file.filename or "music.mp3").suffix.lower() or ".mp3"
    for old in (store.dir(pid) / "audio").glob("music_override.*"):
        old.unlink()
    dest = store.dir(pid) / "audio" / f"music_override{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    store.write_text(pid, "audio/music_override_license.txt", license)
    return {"ok": True}


# ------------------------------------------------------------------------------------- files
@app.get("/files/{pid}/{path:path}")
def files(pid: str, path: str, download: bool = False):
    _need(pid)
    try:
        p = store.path(pid, path)
    except ValueError:
        raise HTTPException(400, "bad path")
    if not p.exists() or p.is_dir():
        raise HTTPException(404, "file not found")
    return FileResponse(p, filename=p.name if download else None)


@app.get("/api/projects/{pid}/bundle.zip")
def bundle(pid: str):
    _need(pid)
    d = store.dir(pid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in DELIVERABLES.values():
            if (d / rel).exists():
                z.write(d / rel, arcname=Path(rel).name)
        if (d / "sources").exists():
            for f in (d / "sources").glob("*.txt"):
                z.write(f, arcname=f"source_snapshots/{f.name}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{pid}.zip"'})
