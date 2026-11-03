"""MY VOICE web server: JSON API + single-page studio (static/). Binds to 127.0.0.1 by default.
When served on the network (for recording from a phone) every request needs the access token
printed at start-up, because the recordings are personal biometric data."""

from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import PRODUCT_NAME, __version__
from ..audio.io import read_audio, wav_bytes
from ..models import CATEGORIES, EMOTIONS, LANGUAGES, MODULES, STYLES, Take
from ..studio import Studio, StudioError

STATIC = Path(__file__).parent / "static"
LIST_DROP = ("waveform", "ltas")


def take_json(t: Take, full: bool = True) -> dict:
    d = t.model_dump()
    if not full:
        an = d.get("analysis") or {}
        d["analysis"] = {k: v for k, v in an.items() if k not in LIST_DROP}
        if "pitch" in d["analysis"] and d["analysis"]["pitch"]:
            d["analysis"]["pitch"] = {k: v for k, v in d["analysis"]["pitch"].items() if k != "contour"}
        d["asr"] = {k: v for k, v in d["asr"].items() if k != "words"}
    return d


def create_app(studio: Optional[Studio] = None, token: Optional[str] = None) -> FastAPI:
    st = studio or Studio()
    app = FastAPI(title=PRODUCT_NAME, version=__version__)
    app.state.studio = st
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if token:
            path = request.url.path
            supplied = request.headers.get("x-myvoice-token") or request.cookies.get("myvoice_token") or ""
            if path == "/" and request.query_params.get("token"):
                if hmac.compare_digest(request.query_params["token"], token):
                    resp = RedirectResponse("/")
                    resp.set_cookie("myvoice_token", token, httponly=True, samesite="strict", secure=request.url.scheme == "https")
                    return resp
            if not hmac.compare_digest(supplied, token) and not path.startswith("/static/"):
                if path == "/":
                    return HTMLResponse("<h1>MY VOICE</h1><p>Open the link with the access token printed in the terminal.</p>", status_code=401)
                return JSONResponse({"detail": "access token required"}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    def err(e: Exception, code: int = 400):
        raise HTTPException(code, str(e))

    # ---------------------------------------------------------------- pages & meta
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/state")
    def state() -> dict:
        p = st.profile()
        active = st.store.active_session(st.s.session_idle_hours)
        return {
            "product": PRODUCT_NAME, "version": __version__,
            "profile": p.model_dump(), "capabilities": st.capabilities(),
            "session": active.model_dump() if active else None,
            "vocab": {"modules": MODULES, "emotions": EMOTIONS, "styles": STYLES, "categories": CATEGORIES, "languages": LANGUAGES},
        }

    @app.get("/api/profile")
    def get_profile() -> dict:
        return st.profile().model_dump()

    @app.put("/api/profile")
    def put_profile(body: dict = Body(...)) -> dict:
        try:
            return st.save_profile(body).model_dump()
        except Exception as e:
            err(e)

    # ---------------------------------------------------------------- sessions
    @app.post("/api/sessions")
    def start_session(body: dict = Body(default={})) -> dict:
        return st.start_session(body).model_dump()

    @app.patch("/api/sessions/{sid}")
    def patch_session(sid: str, body: dict = Body(...)) -> dict:
        try:
            return st.update_session(sid, body).model_dump()
        except StudioError as e:
            err(e, 404)

    @app.get("/api/sessions")
    def list_sessions() -> list[dict]:
        takes = st.store.takes()
        out = []
        for s in reversed(st.store.sessions()):
            ts = [t for t in takes if t.session_id == s.id]
            out.append({**s.model_dump(), "takes": len(ts), "approved": sum(t.status == "approved" for t in ts),
                        "seconds": round(sum(t.audio.duration for t in ts), 1)})
        return out

    # ---------------------------------------------------------------- curriculum
    @app.get("/api/next")
    def next_exercise(session: str = "", mode: str = "adaptive", exclude: str = "") -> dict:
        pick = st.next(session, mode, tuple(x for x in exclude.split(",") if x))
        return {"exercise": st.exercise_public(pick.exercise.id) if pick.exercise else None,
                "phase": pick.phase, "reason": pick.reason, "factors": pick.factors}

    @app.get("/api/exercises/{eid}")
    def get_exercise(eid: str) -> dict:
        try:
            return st.exercise_public(eid)
        except StudioError as e:
            err(e, 404)

    @app.get("/api/curriculum")
    def curriculum(module: str = "") -> dict:
        takes = st.store.takes()
        by_ex: dict[str, list] = {}
        for t in takes:
            by_ex.setdefault(t.exercise_id, []).append(t)
        p = st.profile()
        sections = []
        for sec in st.bank.sections.values():
            if module and sec.module != module:
                continue
            items = []
            for eid in sec.exercise_ids:
                ex = st.bank.by_id[eid]
                ts = by_ex.get(eid, [])
                status = ("approved" if any(t.status == "approved" for t in ts) else "pending" if any(t.status == "pending" for t in ts)
                          else "rejected" if ts else "new")
                best = max((t.quality.score for t in ts if t.status != "rejected"), default=None)
                items.append({"id": eid, "text": st.bank.public(ex, 1.8, p.hindi_forms, p.speaker_name)["text"][:160], "lang": ex.lang,
                              "kind": ex.kind, "emotion": ex.emotion, "style": ex.style, "core": ex.core, "status": status,
                              "takes": len(ts), "best": best})
            sections.append({"code": sec.code, "module": sec.module, "title": sec.title, "category": sec.category, "items": items})
        return {"modules": st.coverage().summary()["modules"], "sections": sections, "bank_errors": st.bank.errors}

    @app.post("/api/exercises/import")
    def import_exercises(body: dict = Body(...)) -> dict:
        """Add exercises (same structure as the built-in YAML) — used by the Claude Code skill."""
        from ..curriculum.bank import ExerciseBank

        name = "".join(c for c in str(body.get("name") or "imported") if c.isalnum() or c in "-_")[:40] or "imported"
        doc = body.get("doc") or body
        path = st.s.exercises_dir / f"{name}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            bank = ExerciseBank(extra_dirs=[st.s.exercises_dir])
        except Exception as e:
            path.unlink(missing_ok=True)
            err(e)
        if bank.errors:
            path.unlink(missing_ok=True)
            err(ValueError("; ".join(bank.errors)))
        added = len(bank.exercises) - len(st.bank.exercises)
        st.bank = bank
        st.store.log("exercises.imported", file=path.name, added=added)
        return {"added": added, "total": len(bank.exercises)}

    # ---------------------------------------------------------------- takes
    @app.post("/api/takes")
    async def upload_take(audio: UploadFile = File(...), meta: str = Form(...)) -> dict:
        try:
            m = json.loads(meta)
        except json.JSONDecodeError:
            err(ValueError("meta must be JSON"))
        data = await audio.read()
        try:
            take = st.save_take(data, m)
        except StudioError as e:
            err(e)
        except ValueError as e:
            err(e)
        return take_json(take)

    @app.get("/api/takes")
    def list_takes(status: str = "", module: str = "", lang: str = "", category: str = "", verdict: str = "", session: str = "",
                   exercise: str = "", q: str = "", trashed: bool = False, limit: int = 500, offset: int = 0) -> dict:
        items = [t for t in st.store.takes(include_trashed=trashed) if t.trashed == trashed]
        if status:
            items = [t for t in items if t.status in status.split(",")]
        if module:
            items = [t for t in items if t.module in module.split(",")]
        if lang:
            items = [t for t in items if t.lang in lang.split(",")]
        if category:
            items = [t for t in items if t.category in category.split(",")]
        if verdict:
            items = [t for t in items if t.quality.verdict in verdict.split(",")]
        if session:
            items = [t for t in items if t.session_id == session]
        if exercise:
            items = [t for t in items if t.exercise_id == exercise]
        if q:
            ql = q.lower()
            items = [t for t in items if ql in t.text.lower() or ql in t.transcript.lower() or ql in t.exercise_id.lower()]
        items.sort(key=lambda t: t.id, reverse=True)
        total = len(items)
        return {"total": total, "items": [take_json(t, full=False) for t in items[offset:offset + max(1, min(limit, 2000))]]}

    @app.get("/api/takes/{tid}")
    def get_take(tid: str) -> dict:
        t = st.store.get_take(tid)
        if t is None:
            err(ValueError("take not found"), 404)
        return take_json(t)

    @app.patch("/api/takes/{tid}")
    def patch_take(tid: str, body: dict = Body(...)) -> dict:
        try:
            if "transcript" in body:
                st.edit_transcript(tid, str(body["transcript"]))
            if "notes" in body:
                st.store.update_take(tid, lambda t: setattr(t, "notes", str(body["notes"])[:2000]))
            if "status" in body:
                st.set_status(tid, str(body["status"]), str(body.get("reason", ""))[:200])
        except (StudioError, KeyError) as e:
            err(e)
        return take_json(st.store.get_take(tid))

    @app.post("/api/takes/bulk")
    def bulk(body: dict = Body(...)) -> dict:
        ids = [str(i) for i in body.get("ids") or []][:5000]
        action = body.get("action")
        done, failed = [], []
        for tid in ids:
            try:
                if action in ("approved", "rejected", "pending"):
                    st.set_status(tid, action, "bulk")
                elif action == "trash":
                    st.store.trash_take(tid)
                elif action == "restore":
                    st.store.restore_take(tid)
                else:
                    raise StudioError("unknown action")
                done.append(tid)
            except Exception as e:
                failed.append({"id": tid, "error": str(e)})
        return {"done": done, "failed": failed}

    @app.post("/api/takes/{tid}/recheck")
    def recheck(tid: str) -> dict:
        try:
            return take_json(st.recheck(tid))
        except StudioError as e:
            err(e)

    @app.post("/api/takes/{tid}/trash")
    def trash(tid: str) -> dict:
        if not st.store.get_take(tid):
            err(ValueError("take not found"), 404)
        return take_json(st.store.trash_take(tid))

    @app.post("/api/takes/{tid}/restore")
    def restore(tid: str) -> dict:
        if not st.store.get_take(tid):
            err(ValueError("take not found"), 404)
        return take_json(st.store.restore_take(tid))

    @app.post("/api/trash/empty")
    def empty_trash(body: dict = Body(default={})) -> dict:
        if body.get("confirm") != "DELETE":
            err(ValueError('send {"confirm": "DELETE"} to permanently delete the trash'))
        return {"deleted": st.store.purge_trash()}

    @app.get("/api/takes/{tid}/audio")
    def take_audio(tid: str, variant: str = "preview", download: bool = False):
        t = st.store.get_take(tid)
        if t is None:
            err(ValueError("take not found"), 404)
        path = st.store.audio_path(t)
        if not path.exists():
            err(ValueError("audio file missing"), 404)
        name = path.name
        if variant == "original":
            return FileResponse(path, media_type="audio/wav", filename=name if download else None)
        audio, sr = read_audio(path)  # 16-bit copy for maximum browser compatibility
        headers = {"Content-Disposition": f'attachment; filename="{name}"'} if download else {}
        return Response(wav_bytes(audio, sr), media_type="audio/wav", headers=headers)

    # ---------------------------------------------------------------- dashboard data
    @app.get("/api/coverage")
    def coverage() -> dict:
        cov = st.coverage()
        out = cov.summary()
        pick = st.next(st.store.active_session(st.s.session_idle_hours).id if st.store.active_session(st.s.session_idle_hours) else "")
        out["next"] = {"phase": pick.phase, "reason": pick.reason, "factors": pick.factors,
                       "exercise": pick.exercise.id if pick.exercise else None}
        out["disk"] = st.store.disk_usage()
        return out

    @app.get("/api/analytics")
    def analytics() -> dict:
        from ..analytics import build

        return build(st)

    @app.get("/api/log")
    def activity(tail: int = 200) -> list[dict]:
        return st.store.read_log(tail)

    # ---------------------------------------------------------------- exports
    @app.get("/api/exports")
    def exports() -> dict:
        from ..export import PROFILES, list_exports

        return {"profiles": PROFILES, "exports": list_exports(st)}

    @app.post("/api/exports")
    def create_export(body: dict = Body(...)) -> dict:
        from ..export import run_export

        try:
            return run_export(st, str(body.get("profile", "")), body.get("options") or {})
        except ValueError as e:
            err(e)

    @app.get("/api/exports/{name}/download")
    def download_export(name: str):
        from ..export import export_zip_path

        try:
            p = export_zip_path(st, name)
        except ValueError as e:
            err(e, 404)
        return FileResponse(p, media_type="application/zip", filename=p.name)

    return app
