"""Local speech recognition for the read-check (faster-whisper / CTranslate2, runs on the CPU).

Nothing leaves your computer. The model is downloaded once from Hugging Face on first use
(large-v3-turbo ≈ 1.6 GB, small ≈ 0.5 GB) and cached in ~/.cache/huggingface.

Recognition runs in one background thread so recording never waits for it: a take is saved and
scored on its signal immediately; the read-check result is merged in a few seconds later.
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
from typing import Callable, Optional

import numpy as np

from .audio.io import resample

WHISPER_LANG = {"en": "en", "hi": "hi", "hinglish": "hi"}


class ASREngine:
    def __init__(self, model_name: str, threads: int = 4, enabled: bool = True):
        self.model_name = model_name
        self.threads = threads
        self.enabled = enabled
        self.state = "idle"  # idle | loading | ready | error | unavailable | off
        self.error = ""
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def installed() -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def status(self) -> dict:
        if not self.enabled:
            state = "off"
        elif not self.installed():
            state = "unavailable"
        else:
            state = self.state
        return {"engine": "faster-whisper", "installed": self.installed(), "enabled": self.enabled, "model": self.model_name,
                "state": state, "error": self.error,
                "install_hint": "" if self.installed() else "pip install faster-whisper   (then restart the studio)"}

    def set_model(self, name: str) -> None:
        with self._lock:
            if name and name != self.model_name:
                self.model_name = name
                self._model = None
                self.state = "idle"
                self.error = ""

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self.state = "loading"
            try:
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8", cpu_threads=self.threads)
                self.state = "ready"
            except Exception as e:
                self.state = "error"
                self.error = f"could not load Whisper '{self.model_name}': {e}"
                raise
        return self._model

    def transcribe(self, audio: np.ndarray, sr: int, lang: str) -> dict:
        with self._lock:
            model = self._load()
            a16 = resample(audio, sr, 16000)
            t0 = time.time()
            segments, info = model.transcribe(
                a16, language=WHISPER_LANG.get(lang), task="transcribe", beam_size=5, vad_filter=True,
                word_timestamps=True, condition_on_previous_text=False,
            )
            segs = list(segments)
        words, lp, nsp = [], [], []
        for s in segs:
            lp.append((s.avg_logprob, max(1e-3, s.end - s.start)))
            nsp.append(s.no_speech_prob)
            for w in s.words or []:
                words.append({"w": w.word.strip(), "start": round(float(w.start), 2), "end": round(float(w.end), 2),
                              "p": round(float(w.probability), 3)})
        avg_lp = sum(a * d for a, d in lp) / sum(d for _a, d in lp) if lp else None
        return {
            "text": " ".join(s.text.strip() for s in segs).strip(),
            "words": words,
            "avg_logprob": round(avg_lp, 3) if avg_lp is not None else None,
            "no_speech_prob": round(max(nsp), 3) if nsp else None,
            "language": getattr(info, "language", "") or "",
            "seconds": round(time.time() - t0, 2),
        }


class ASRWorker:
    """Single background thread; `job(take_id)` does the work and persists the result."""

    def __init__(self, job: Callable[[str], None]):
        self.q: "queue.Queue[str]" = queue.Queue()
        self.job = job
        self.pending: set[str] = set()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def submit(self, take_id: str) -> None:
        with self._lock:
            if take_id in self.pending:
                return
            self.pending.add(take_id)
        self.q.put(take_id)
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="myvoice-asr", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                tid = self.q.get(timeout=30)
            except queue.Empty:
                return
            try:
                self.job(tid)
            except Exception:  # pragma: no cover - logged, never kills the worker
                traceback.print_exc()
            finally:
                with self._lock:
                    self.pending.discard(tid)

    def wait_idle(self, timeout: float = 60.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                if not self.pending:
                    return True
            time.sleep(0.05)
        return False
