"""Local dataset storage. Files are the source of truth:

myvoice_data/
  profile.json                      speaker profile + preferences
  recordings/<category>/<exercise>__<take>.wav    original audio (lossless PCM, native sample rate)
  recordings/<category>/<exercise>__<take>.json   sidecar metadata (exercise snapshot, analysis, status)
  sessions/<session>.json           one file per recording session
  trash/<category>/...              deleted takes (restorable until the trash is emptied)
  exercises/*.yaml|json             imported / generated exercises
  exports/<timestamp>_<profile>/    dataset exports (+ .zip)
  activity.log                      append-only JSON lines: every status change, deletion and export

An in-memory index is rebuilt from the sidecars at start-up, so the folder can be backed up, moved or
inspected with ordinary tools.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
import soundfile as sf

from .models import Profile, Session, Take, now_iso

TAKE_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
SESSION_ID_RE = re.compile(r"^S\d{8}-\d{4}-[0-9a-f]{4}$")
EXERCISE_ID_RE = re.compile(r"^[A-Z0-9][A-Za-z0-9_-]{1,63}$")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{secrets.token_hex(3)}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


class DatasetStore:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        for sub in ("recordings", "sessions", "trash", "exports", "exercises", "cache"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:  # pragma: no cover
            pass
        self._lock = threading.RLock()
        self._takes: dict[str, Take] = {}
        self._sessions: dict[str, Session] = {}
        self.load_errors: list[str] = []
        self.rebuild()

    # ------------------------------------------------------------------ index
    def rebuild(self) -> None:
        with self._lock:
            self._takes.clear()
            self._sessions.clear()
            self.load_errors = []
            for folder in ("recordings", "trash"):
                for p in sorted((self.root / folder).glob("*/*.json")):
                    try:
                        t = Take.model_validate_json(p.read_text(encoding="utf-8"))
                        self._takes[t.id] = t
                    except Exception as e:  # keep going; report in doctor / UI
                        self.load_errors.append(f"{p.relative_to(self.root)}: {e}")
            for p in sorted((self.root / "sessions").glob("*.json")):
                try:
                    s = Session.model_validate_json(p.read_text(encoding="utf-8"))
                    self._sessions[s.id] = s
                except Exception as e:
                    self.load_errors.append(f"{p.relative_to(self.root)}: {e}")

    # ------------------------------------------------------------------ activity log
    def log(self, event: str, **fields) -> None:
        line = json.dumps({"at": now_iso(), "event": event, **fields}, ensure_ascii=False)
        with self._lock, open(self.root / "activity.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_log(self, tail: int = 200) -> list[dict]:
        p = self.root / "activity.log"
        if not p.exists():
            return []
        out = []
        for line in p.read_text(encoding="utf-8").splitlines()[-tail:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    # ------------------------------------------------------------------ takes
    @staticmethod
    def new_take_id() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)

    def _sidecar(self, take: Take) -> Path:
        return (self.root / take.audio.file).with_suffix(".json")

    def audio_path(self, take: Take) -> Path:
        p = (self.root / take.audio.file).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("audio path escapes the data directory")
        return p

    def _write_sidecar(self, take: Take) -> None:
        _atomic_write_text(self._sidecar(take), take.model_dump_json(indent=2))

    def save_new_take(self, take: Take, audio: np.ndarray, sample_rate: int) -> Take:
        """Write the original audio (24-bit PCM WAV, untouched sample rate) and its sidecar."""
        if not TAKE_ID_RE.match(take.id):
            raise ValueError("invalid take id")
        rel = Path("recordings") / take.category / f"{take.exercise_id}__{take.id}.wav"
        wav = self.root / rel
        wav.parent.mkdir(parents=True, exist_ok=True)
        tmp = wav.with_name(wav.name + ".part")
        sf.write(tmp, np.clip(audio, -1.0, 1.0), sample_rate, subtype="PCM_24", format="WAV")
        os.replace(tmp, wav)
        take.audio.file = rel.as_posix()
        take.audio.sample_rate = int(sample_rate)
        take.audio.subtype = "PCM_24"
        take.audio.bytes = wav.stat().st_size
        take.audio.sha256 = sha256_file(wav)
        with self._lock:
            self._write_sidecar(take)
            self._takes[take.id] = take
        self.log("take.saved", take=take.id, exercise=take.exercise_id, session=take.session_id,
                 seconds=round(take.audio.duration, 2), file=take.audio.file)
        return take

    def get_take(self, take_id: str) -> Optional[Take]:
        if not TAKE_ID_RE.match(take_id or ""):
            return None
        return self._takes.get(take_id)

    def takes(self, include_trashed: bool = False) -> list[Take]:
        with self._lock:
            items = list(self._takes.values())
        if not include_trashed:
            items = [t for t in items if not t.trashed]
        return sorted(items, key=lambda t: t.id)

    def takes_for_exercise(self, exercise_id: str, include_trashed: bool = False) -> list[Take]:
        return [t for t in self.takes(include_trashed) if t.exercise_id == exercise_id]

    def next_attempt(self, exercise_id: str) -> int:
        return len(self.takes_for_exercise(exercise_id, include_trashed=True)) + 1

    def update_take(self, take_id: str, mutate: Callable[[Take], None]) -> Take:
        with self._lock:
            take = self._takes.get(take_id)
            if take is None:
                raise KeyError(take_id)
            updated = take.model_copy(deep=True)
            mutate(updated)
            self._write_sidecar(updated)
            self._takes[take_id] = updated
            return updated

    def set_status(self, take_id: str, status: str, reason: str = "") -> Take:
        def m(t: Take) -> None:
            t.status = status  # type: ignore[assignment]
            t.status_reason = reason
            t.status_at = now_iso()

        take = self.update_take(take_id, m)
        self.log("take.status", take=take_id, status=status, reason=reason)
        return take

    def _move_take_files(self, take: Take, dest_folder: str) -> str:
        src_wav = self.root / take.audio.file
        rel = Path(dest_folder) / take.category / src_wav.name
        dst_wav = self.root / rel
        dst_wav.parent.mkdir(parents=True, exist_ok=True)
        src_json = src_wav.with_suffix(".json")
        if src_wav.exists():
            shutil.move(str(src_wav), str(dst_wav))
        if src_json.exists():
            shutil.move(str(src_json), str(dst_wav.with_suffix(".json")))
        return rel.as_posix()

    def trash_take(self, take_id: str) -> Take:
        with self._lock:
            take = self._takes[take_id]
            if take.trashed:
                return take
            new_rel = self._move_take_files(take, "trash")
            take = take.model_copy(deep=True)
            take.audio.file = new_rel
            take.trashed = True
            self._write_sidecar(take)
            self._takes[take_id] = take
        self.log("take.trashed", take=take_id, file=new_rel)
        return take

    def restore_take(self, take_id: str) -> Take:
        with self._lock:
            take = self._takes[take_id]
            if not take.trashed:
                return take
            new_rel = self._move_take_files(take, "recordings")
            take = take.model_copy(deep=True)
            take.audio.file = new_rel
            take.trashed = False
            self._write_sidecar(take)
            self._takes[take_id] = take
        self.log("take.restored", take=take_id, file=new_rel)
        return take

    def purge_trash(self) -> int:
        """Permanently delete everything in the trash (explicit user action only)."""
        with self._lock:
            victims = [t for t in self._takes.values() if t.trashed]
            for t in victims:
                wav = self.root / t.audio.file
                for p in (wav, wav.with_suffix(".json")):
                    try:
                        p.unlink()
                    except FileNotFoundError:
                        pass
                del self._takes[t.id]
        self.log("trash.emptied", count=len(victims), takes=[t.id for t in victims])
        return len(victims)

    # ------------------------------------------------------------------ sessions
    @staticmethod
    def new_session_id() -> str:
        return "S" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)

    def save_session(self, s: Session) -> Session:
        if not SESSION_ID_RE.match(s.id):
            raise ValueError("invalid session id")
        with self._lock:
            _atomic_write_text(self.root / "sessions" / f"{s.id}.json", s.model_dump_json(indent=2))
            self._sessions[s.id] = s
        return s

    def get_session(self, sid: str) -> Optional[Session]:
        if not SESSION_ID_RE.match(sid or ""):
            return None
        return self._sessions.get(sid)

    def sessions(self) -> list[Session]:
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.started_at)

    def update_session(self, sid: str, mutate: Callable[[Session], None]) -> Session:
        with self._lock:
            s = self._sessions[sid].model_copy(deep=True)
            mutate(s)
            return self.save_session(s)

    def active_session(self, idle_hours: float = 2.0) -> Optional[Session]:
        """The most recent session that has not been ended and was active within `idle_hours`."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=idle_hours)
        for s in reversed(self.sessions()):
            last = _parse_iso(s.last_active_at)
            if not s.ended_at and last and last >= cutoff:
                return s
        return None

    def touch_session(self, sid: str) -> None:
        if sid in self._sessions:
            self.update_session(sid, lambda s: setattr(s, "last_active_at", now_iso()))

    # ------------------------------------------------------------------ profile
    def profile(self) -> Profile:
        p = self.root / "profile.json"
        if p.exists():
            try:
                return Profile.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception as e:
                self.load_errors.append(f"profile.json: {e}")
        return Profile()

    def save_profile(self, profile: Profile) -> Profile:
        with self._lock:
            _atomic_write_text(self.root / "profile.json", profile.model_dump_json(indent=2))
        return profile

    # ------------------------------------------------------------------ misc
    def disk_usage(self) -> dict:
        def size(paths: Iterable[Path]) -> int:
            return sum(p.stat().st_size for p in paths if p.is_file())

        return {
            "recordings_bytes": size((self.root / "recordings").rglob("*")),
            "trash_bytes": size((self.root / "trash").rglob("*")),
            "exports_bytes": size((self.root / "exports").rglob("*")),
            "path": str(self.root.resolve()),
        }
