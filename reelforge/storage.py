"""Per-project folder layout and typed JSON persistence.

projects/<id>/
  project.json        settings + stage status
  research.json/.md   verified research and source list
  sources/            snapshots of every source that was accessed
  script.json/.md     approved script (beats cite claim IDs)
  storyboard.json     scene plan
  audio/              per-beat narration, music, sfx, final mix
  timeline.json       word-level timings, subtitle cues, scene timings
  assets/             downloaded media + assets.json (licences)
  render/             Remotion props, silent render, previews, stills
  output/             reel.mp4, cover.jpg, captions, sources, QC report
  log.txt             human-readable activity log
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from .config import settings
from .models import (
    AssetLibrary,
    InstagramPackage,
    Project,
    ProjectSettings,
    QCReport,
    Research,
    Script,
    StageStatus,
    Storyboard,
    Timeline,
    now_iso,
)

T = TypeVar("T", bound=BaseModel)
_lock = threading.RLock()

ARTIFACTS: dict[str, tuple[str, Type[BaseModel]]] = {
    "project": ("project.json", Project),
    "research": ("research.json", Research),
    "script": ("script.json", Script),
    "storyboard": ("storyboard.json", Storyboard),
    "timeline": ("timeline.json", Timeline),
    "assets": ("assets/assets.json", AssetLibrary),
    "qc": ("output/qc_report.json", QCReport),
    "package": ("output/instagram.json", InstagramPackage),
}

STAGES = ["research", "script", "storyboard", "voice", "assets", "render", "qc", "package"]


def slugify(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    text = text.encode("ascii", "ignore").decode() or "reel"
    return text[:max_len].strip("-") or "reel"


class ProjectStore:
    def __init__(self, base: Optional[Path] = None):
        self.base = Path(base or settings.projects_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------------------
    def dir(self, pid: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", pid):
            raise ValueError(f"invalid project id: {pid!r}")
        return self.base / pid

    def path(self, pid: str, rel: str) -> Path:
        p = (self.dir(pid) / rel).resolve()
        if self.dir(pid).resolve() not in p.parents and p != self.dir(pid).resolve():
            raise ValueError("path escapes project directory")
        return p

    # -- lifecycle -----------------------------------------------------------------------
    def create(self, ps: ProjectSettings, pid: Optional[str] = None) -> Project:
        pid = pid or f"{slugify(ps.topic)}-{secrets.token_hex(3)}"
        d = self.dir(pid)
        for sub in ("sources", "audio", "assets", "render", "output"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        project = Project(id=pid, settings=ps, stages={s: StageStatus() for s in STAGES})
        self.save("project", pid, project)
        self.log(pid, f"Project created for topic: {ps.topic!r}")
        return project

    def exists(self, pid: str) -> bool:
        try:
            return (self.dir(pid) / "project.json").exists()
        except ValueError:
            return False

    def list(self) -> list[Project]:
        out = []
        for p in sorted(self.base.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                out.append(Project.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out

    # -- typed artifacts -----------------------------------------------------------------
    def load(self, kind: str, pid: str) -> Optional[BaseModel]:
        rel, model = ARTIFACTS[kind]
        p = self.path(pid, rel)
        if not p.exists():
            return None
        return model.model_validate_json(p.read_text(encoding="utf-8"))

    def save(self, kind: str, pid: str, obj: BaseModel) -> Path:
        rel, model = ARTIFACTS[kind]
        if not isinstance(obj, model):
            obj = model.model_validate(obj)
        p = self.path(pid, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            if kind == "project":
                obj.updated_at = now_iso()  # type: ignore[attr-defined]
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(obj.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(p)
        return p

    def project(self, pid: str) -> Project:
        p = self.load("project", pid)
        if p is None:
            raise FileNotFoundError(f"project not found: {pid}")
        return p  # type: ignore[return-value]

    def research(self, pid: str) -> Optional[Research]:
        return self.load("research", pid)  # type: ignore[return-value]

    def script(self, pid: str) -> Optional[Script]:
        return self.load("script", pid)  # type: ignore[return-value]

    def storyboard(self, pid: str) -> Optional[Storyboard]:
        return self.load("storyboard", pid)  # type: ignore[return-value]

    def timeline(self, pid: str) -> Optional[Timeline]:
        return self.load("timeline", pid)  # type: ignore[return-value]

    def assets(self, pid: str) -> AssetLibrary:
        return self.load("assets", pid) or AssetLibrary()  # type: ignore[return-value]

    def qc(self, pid: str) -> Optional[QCReport]:
        return self.load("qc", pid)  # type: ignore[return-value]

    def package(self, pid: str) -> Optional[InstagramPackage]:
        return self.load("package", pid)  # type: ignore[return-value]

    # -- text artefacts --------------------------------------------------------------------
    def write_text(self, pid: str, rel: str, text: str) -> Path:
        p = self.path(pid, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def read_json(self, pid: str, rel: str) -> Optional[dict]:
        p = self.path(pid, rel)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def write_json(self, pid: str, rel: str, data) -> Path:
        return self.write_text(pid, rel, json.dumps(data, indent=2, ensure_ascii=False))

    # -- status + log ----------------------------------------------------------------------
    def set_stage(self, pid: str, stage: str, status: str, message: str = "") -> Project:
        with _lock:
            project = self.project(pid)
            project.stages[stage] = StageStatus(status=status, updated_at=now_iso(), message=message)
            if stage in ("research", "script", "storyboard", "voice", "assets", "render") and status in ("running", "done"):
                # anything upstream changed -> the reel is no longer known-good
                project.complete = False
            self.save("project", pid, project)
        self.log(pid, f"[{stage}] {status}{': ' + message if message else ''}")
        return project

    def invalidate_downstream(self, pid: str, stage: str) -> None:
        """Mark stages after `stage` as pending (their outputs are stale)."""
        with _lock:
            project = self.project(pid)
            idx = STAGES.index(stage)
            for s in STAGES[idx + 1:]:
                if project.stages.get(s) and project.stages[s].status != "pending":
                    project.stages[s] = StageStatus(status="pending", updated_at=now_iso(), message=f"stale after {stage} changed")
            project.complete = False
            self.save("project", pid, project)

    def log(self, pid: str, message: str) -> None:
        try:
            with _lock, open(self.dir(pid) / "log.txt", "a", encoding="utf-8") as f:
                f.write(f"{now_iso()}  {message}\n")
        except FileNotFoundError:
            pass

    def read_log(self, pid: str, tail: int = 200) -> list[str]:
        p = self.dir(pid) / "log.txt"
        if not p.exists():
            return []
        return p.read_text(encoding="utf-8").splitlines()[-tail:]


store = ProjectStore()
