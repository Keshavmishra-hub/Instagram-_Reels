"""Application core shared by the web server and the CLI."""

from __future__ import annotations

import hashlib
import threading
from typing import Optional

from . import __version__
from .analysis import analyze_take, quality_context, rate_from_coverage, reassess, update_rate_from_text
from .asr import ASREngine, ASRWorker
from .audio.io import decode_upload, read_audio
from .audio.prosody import parselmouth_available
from .audio.quality import READ_KINDS
from .config import Settings, settings as default_settings
from .coverage import Coverage
from .curriculum.bank import ExerciseBank, render
from .curriculum.planner import Pick, plan_next
from .models import ASRResult, AudioInfo, CaptureInfo, Profile, Session, Take, now_iso
from .readcheck import check as read_check
from .store import DatasetStore
from .text import espeak


class StudioError(ValueError):
    pass


class Studio:
    def __init__(self, s: Optional[Settings] = None, asr_enabled: Optional[bool] = None):
        self.s = s or default_settings
        self.s.ensure_dirs()
        self.store = DatasetStore(self.s.data_dir)
        self.bank = ExerciseBank(extra_dirs=[self.s.exercises_dir])
        profile = self.store.profile()
        enabled = asr_enabled if asr_enabled is not None else self.s.asr_engine != "off"
        self.asr = ASREngine(profile.asr_model or self.s.asr_model, threads=self.s.asr_threads, enabled=enabled)
        self.worker = ASRWorker(self._asr_job)
        self._lock = threading.RLock()
        for t in self.store.takes():
            if t.asr.status in ("pending", "running"):
                self.worker.submit(t.id)

    # ------------------------------------------------------------------ profile & capabilities
    def profile(self) -> Profile:
        return self.store.profile()

    def save_profile(self, data: dict) -> Profile:
        p = self.store.profile()
        merged = p.model_dump()
        prefs = {**merged["preferences"], **(data.pop("preferences", None) or {})}
        merged.update({k: v for k, v in data.items() if k in Profile.model_fields and k not in ("created_at",)})
        merged["preferences"] = prefs
        if data.get("consent_given") and not p.consent_given:
            merged["consent_at"] = now_iso()
        new = Profile.model_validate(merged)
        self.store.save_profile(new)
        if new.asr_model and new.asr_model != self.asr.model_name:
            self.asr.set_model(new.asr_model)
        return new

    def capabilities(self) -> dict:
        return {
            "version": __version__,
            "asr": self.asr.status(),
            "espeak": espeak.status(),
            "praat": parselmouth_available(),
            "webrtcvad": _has("webrtcvad"),
            "ffmpeg": bool(self.s.ffmpeg_bin),
            "data_dir": str(self.s.data_dir.resolve()),
            "bank_errors": self.bank.errors,
            "load_errors": self.store.load_errors,
        }

    # ------------------------------------------------------------------ exercises
    def exercise_public(self, eid: str) -> dict:
        ex = self.bank.get(eid)
        if ex is None:
            raise StudioError(f"unknown exercise {eid}")
        p = self.profile()
        d = self.bank.public(ex, p.preferences.auto_stop_sec, p.hindi_forms, p.speaker_name)
        takes = self.store.takes_for_exercise(eid)
        d["takes"] = {"approved": sum(t.status == "approved" for t in takes), "pending": sum(t.status == "pending" for t in takes),
                      "rejected": sum(t.status == "rejected" for t in takes), "last": takes[-1].id if takes else None}
        return d

    # ------------------------------------------------------------------ sessions
    def start_session(self, meta: dict) -> Session:
        active = self.store.active_session(self.s.session_idle_hours)
        if active and not meta.get("new"):
            return active
        if active:
            self.store.update_session(active.id, lambda s: setattr(s, "ended_at", now_iso()))
        sess = Session(
            id=self.store.new_session_id(), device_label=str(meta.get("device_label", ""))[:200],
            device_id=str(meta.get("device_id", ""))[:80], user_agent=str(meta.get("user_agent", ""))[:300],
            sample_rate=int(meta.get("sample_rate") or 0), constraints_applied=meta.get("constraints_applied") or {},
            voice_state=meta.get("voice_state", "") if meta.get("voice_state") in ("", "fresh", "normal", "tired", "hoarse") else "",
            note=str(meta.get("note", ""))[:500],
        )
        self.store.save_session(sess)
        self.store.log("session.started", session=sess.id, device=sess.device_label)
        return sess

    def update_session(self, sid: str, data: dict) -> Session:
        if not self.store.get_session(sid):
            raise StudioError("unknown session")

        def m(s: Session) -> None:
            for k in ("voice_state", "note", "mode"):
                if k in data:
                    setattr(s, k, data[k])
            if "paused_seconds" in data:
                s.paused_seconds = float(s.paused_seconds) + max(0.0, float(data["paused_seconds"]))
            if data.get("skip"):
                if data["skip"] not in s.skipped:
                    s.skipped.append(str(data["skip"]))
            if data.get("end"):
                s.ended_at = now_iso()
            if any(k in data for k in ("device_label", "sample_rate", "constraints_applied")):
                s.device_label = str(data.get("device_label", s.device_label))[:200]
                s.sample_rate = int(data.get("sample_rate") or s.sample_rate)
                s.constraints_applied = data.get("constraints_applied") or s.constraints_applied
            s.last_active_at = now_iso()

        return self.store.update_session(sid, m)

    # ------------------------------------------------------------------ planning
    def next(self, session_id: str = "", mode: str = "adaptive", exclude: tuple = ()) -> Pick:
        sess = self.store.get_session(session_id) if session_id else None
        p = self.profile()
        return plan_next(self.bank, self.store.takes(), self.store.sessions(), sess, warmup=p.preferences.warmup,
                         mode=mode or "adaptive", speaker_name=p.speaker_name, exclude=exclude)

    def coverage(self) -> Coverage:
        return Coverage(self.bank, self.store.takes(), self.store.sessions())

    # ------------------------------------------------------------------ takes
    def save_take(self, data: bytes, meta: dict) -> Take:
        if len(data) > self.s.max_upload_mb * 1024 * 1024:
            raise StudioError("upload too large")
        ex = self.bank.get(str(meta.get("exercise_id", "")))
        if ex is None:
            raise StudioError("unknown exercise")
        sess = self.store.get_session(str(meta.get("session_id", "")))
        if sess is None:
            sess = self.start_session({})
        audio, sr, _info = decode_upload(data, self.s.ffmpeg_bin)
        dur = len(audio) / sr
        if dur > self.s.max_take_seconds:
            raise StudioError(f"take longer than {self.s.max_take_seconds:.0f} s")
        if dur < 0.2:
            raise StudioError("take too short")
        p = self.profile()
        text = render(ex.text, p.hindi_forms or "m", p.speaker_name)
        spoken = render(ex.spoken, p.hindi_forms or "m", p.speaker_name) if ex.spoken else ""
        info = self.bank.derived(ex)
        cap = CaptureInfo(
            device_label=str(meta.get("device_label", ""))[:200],
            device_id=hashlib.sha256(str(meta.get("device_id", "")).encode()).hexdigest()[:16] if meta.get("device_id") else "",
            user_agent=str(meta.get("user_agent", ""))[:300], context_sample_rate=int(meta.get("context_sample_rate") or sr),
            constraints_applied={k: v for k, v in (meta.get("constraints_applied") or {}).items() if isinstance(v, (bool, int, float, str))},
            preroll_sec=float(meta.get("preroll_sec") or 0.0), auto_stopped=bool(meta.get("auto_stopped")),
            paused_at=[float(x) for x in (meta.get("paused_at") or [])][:50],
            track_events=[e for e in (meta.get("track_events") or []) if isinstance(e, dict)][:50],
            client_version=str(meta.get("client_version", ""))[:40],
        )
        transcript, tsrc = (spoken or text, "prompt") if ex.kind in READ_KINDS else ("", "none")
        take = Take(
            id=self.store.new_take_id(), exercise_id=ex.id, session_id=sess.id, attempt=self.store.next_attempt(ex.id),
            module=ex.module, section=ex.section, category=ex.category, kind=ex.kind, lang=ex.lang, emotion=ex.emotion,
            style=ex.style, pace=ex.pace, volume=ex.volume, text=text, spoken=spoken, train=ex.train,
            transcript=transcript, transcript_source=tsrc,
            audio=AudioInfo(file="", sample_rate=sr, duration=round(dur, 3)), capture=cap,
        )
        ctx = quality_context(take, info.expected, ex.min_sec)
        ctx.update(syllables=info.syllables, words=info.words)
        take.analysis = analyze_take(audio, sr, ctx)
        take.quality = reassess(take, info.expected, ex.min_sec)
        wants_asr = (ex.readcheck and ex.kind in READ_KINDS) or ex.kind == "prompt"
        if wants_asr and self.asr.enabled and self.asr.installed():
            take.asr = ASRResult(status="pending", model=self.asr.model_name)
        elif wants_asr:
            take.asr = ASRResult(status="unavailable", error="speech recognition not installed" if self.asr.enabled else "speech recognition turned off")
        else:
            take.asr = ASRResult(status="skipped")
        take = self.store.save_new_take(take, audio, sr)
        replaces = str(meta.get("replaces") or "")
        prev = self.store.get_take(replaces) if replaces else None
        if prev and prev.exercise_id == ex.id and prev.status == "pending":
            self.store.set_status(prev.id, "rejected", f"re-recorded as {take.id}")
        if ex.kind == "clap" and ex.module == "S":
            t60 = (take.analysis.get("room") or {}).get("t60")
            self.store.update_session(sess.id, lambda s: setattr(s, "room_t60", t60))
        if ex.kind == "silence" and ex.module == "S":
            floor = take.analysis.get("noise_floor_dbfs")
            self.store.update_session(sess.id, lambda s: (setattr(s, "room_tone_take", take.id), setattr(s, "noise_floor_db", floor)))
        self.store.touch_session(sess.id)
        if take.asr.status == "pending":
            self.worker.submit(take.id)
        return take

    def _asr_job(self, take_id: str) -> None:
        take = self.store.get_take(take_id)
        if take is None or take.trashed:
            return
        ex = self.bank.get(take.exercise_id)
        loading = "" if self.asr.loaded else f"Loading the speech model {self.asr.model_name} (the first time it is downloaded once, 0.5–3 GB)…"
        self.store.update_take(take_id, lambda t: (setattr(t.asr, "status", "running"), setattr(t.asr, "error", loading)))
        try:
            audio, sr = read_audio(self.store.audio_path(take))
            res = self.asr.transcribe(audio, sr, take.lang)
        except Exception as e:
            err = str(e)[:300]
            self.store.update_take(take_id, lambda t: (setattr(t.asr, "status", "error"), setattr(t.asr, "error", err)))
            return
        match = None
        if ex is not None and ex.readcheck and take.kind in READ_KINDS:
            match = read_check(take.spoken or take.text, res["text"], take.lang, self.asr.model_name, res["avg_logprob"])
        expected = self.bank.derived(ex).expected if ex else None
        min_sec = ex.min_sec if ex else None

        def m(t: Take) -> None:
            t.asr = ASRResult(status="done", engine="faster-whisper", model=self.asr.model_name, language=res["language"],
                              text=res["text"], words=res["words"], avg_logprob=res["avg_logprob"],
                              no_speech_prob=res["no_speech_prob"], seconds=res["seconds"], match=match)
            if t.kind == "prompt" and not t.transcript_reviewed:
                t.transcript = res["text"]
                t.transcript_source = "asr"
                update_rate_from_text(t.analysis, res["text"], t.analysis.get("segments") or [])
            elif match is not None and ex is not None:
                info = self.bank.derived(ex)
                rate_from_coverage(t.analysis, info.syllables, info.words, match.coverage)
            t.quality = reassess(t, expected, min_sec)

        self.store.update_take(take_id, m)

    def recheck(self, take_id: str) -> Take:
        take = self.store.get_take(take_id)
        if take is None:
            raise StudioError("unknown take")
        if not (self.asr.enabled and self.asr.installed()):
            raise StudioError("speech recognition is not available")
        take = self.store.update_take(take_id, lambda t: setattr(t, "asr", ASRResult(status="pending", model=self.asr.model_name)))
        self.worker.submit(take_id)
        return take

    def set_status(self, take_id: str, status: str, reason: str = "") -> Take:
        if status not in ("pending", "approved", "rejected"):
            raise StudioError("invalid status")
        take = self.store.get_take(take_id)
        if take is None:
            raise StudioError("unknown take")
        if status == "approved" and take.kind == "prompt" and not take.transcript.strip():
            raise StudioError("add or confirm the transcript before approving this spontaneous take")
        return self.store.set_status(take_id, status, reason)

    def edit_transcript(self, take_id: str, text: str) -> Take:
        take = self.store.get_take(take_id)
        if take is None:
            raise StudioError("unknown take")
        text = text.strip()[:5000]
        ex = self.bank.get(take.exercise_id)

        def m(t: Take) -> None:
            t.transcript = text
            t.transcript_source = "user"
            t.transcript_reviewed = True
            update_rate_from_text(t.analysis, text, t.analysis.get("segments") or [])
            t.quality = reassess(t, self.bank.derived(ex).expected if ex else None, ex.min_sec if ex else None)

        take = self.store.update_take(take_id, m)
        self.store.log("take.transcript", take=take_id)
        return take


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False
