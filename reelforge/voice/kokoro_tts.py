"""Local neural narration with Kokoro-82M (Apache-2.0) through kokoro-onnx.

We patch the published ONNX graph so it also returns the duration predictor's output
(the per-phoneme frame counts the model itself used). kokoro-onnx turns those into
phoneme timestamps, which we group into words: subtitles are then timed from the very
durations that produced the audio - no separate alignment step, no drift.
"""

from __future__ import annotations

import functools
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..config import Settings, settings as default_settings
from .normalize import Token

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
SAMPLE_RATE = 24000
_PUNCT = set(".,!?;:…—–-\"'()[]“”‘’«»¡¿")


def model_paths(s: Settings) -> dict[str, Path]:
    d = s.models_dir / "kokoro"
    return {
        "dir": d,
        "model": d / "kokoro-v1.0.onnx",
        "voices": d / "voices-v1.0.bin",
        "timed": d / "kokoro-v1.0-timed.onnx",
    }


def kokoro_available(s: Settings = default_settings) -> dict:
    try:
        import kokoro_onnx  # noqa: F401

        pkg = True
    except Exception:
        pkg = False
    p = model_paths(s)
    return {
        "package": pkg,
        "model": p["model"].exists() and p["voices"].exists(),
        "timed": p["timed"].exists(),
    }


def _download(url: str, dest: Path, log: Callable[[str], None]) -> None:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log(f"Downloading {url.rsplit('/', 1)[-1]} ...")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(dest)


def build_timed_model(src: Path, dst: Path) -> bool:
    """Expose the duration predictor output as a graph output named 'duration'."""
    try:
        import onnx
        from onnx import TensorProto, helper
    except Exception:
        return False
    m = onnx.load(str(src))
    if any(o.name == "duration" for o in m.graph.output):
        onnx.save(m, str(dst))
        return True
    # The duration path is: Sigmoid -> ReduceSum -> Div(speed) -> Round -> Clip(min=1) -> Cast(int64)
    clip_out = None
    for n in m.graph.node:
        if n.op_type == "Clip" and n.input and any(
            p.op_type == "Round" and p.output[0] == n.input[0] for p in m.graph.node
        ):
            clip_out = n.output[0]
            break
    if clip_out is None:
        return False
    cast = next((n for n in m.graph.node if n.op_type == "Cast" and n.input and n.input[0] == clip_out), None)
    src_name, dtype = (cast.output[0], TensorProto.INT64) if cast else (clip_out, TensorProto.FLOAT)
    m.graph.node.append(helper.make_node("Identity", [src_name], ["duration"], name="reelforge_duration"))
    m.graph.output.append(helper.make_tensor_value_info("duration", dtype, ["num_tokens"]))
    onnx.save(m, str(dst))
    return True


def ensure_models(s: Settings = default_settings, log: Callable[[str], None] = print) -> dict:
    p = model_paths(s)
    if not p["model"].exists():
        _download(MODEL_URL, p["model"], log)
    if not p["voices"].exists():
        _download(VOICES_URL, p["voices"], log)
    if not p["timed"].exists():
        log("Building timed Kokoro model (exposes phoneme durations for exact subtitle sync) ...")
        ok = build_timed_model(p["model"], p["timed"])
        log("Timed model ready." if ok else "Could not build timed model; falling back to alignment.")
    return kokoro_available(s)


@dataclass
class SynthResult:
    audio: np.ndarray  # float32 mono
    sample_rate: int
    word_times: Optional[list[tuple[float, float]]]  # one (start, end) per spoken word, or None
    method: str


class KokoroEngine:
    """Thread-safe singleton wrapper around kokoro_onnx.Kokoro."""

    _instance: Optional["KokoroEngine"] = None
    _lock = threading.Lock()

    def __init__(self, s: Settings = default_settings):
        from kokoro_onnx import Kokoro

        p = model_paths(s)
        model = p["timed"] if p["timed"].exists() else p["model"]
        if not model.exists() or not p["voices"].exists():
            raise RuntimeError("Kokoro model files are missing. Run: python -m reelforge setup-models")
        self.kokoro = Kokoro(str(model), str(p["voices"]))
        self.timed = bool(getattr(self.kokoro, "has_timings", False))
        self._run_lock = threading.Lock()

    @classmethod
    def get(cls, s: Settings = default_settings) -> "KokoroEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = KokoroEngine(s)
            return cls._instance

    def voices(self) -> list[str]:
        return self.kokoro.get_voices()

    def _voice(self, spec: str):
        """'af_heart' or a blend 'am_michael:0.6,bm_george:0.4'."""
        if ":" not in spec and "," not in spec:
            return spec
        parts = [x.strip() for x in spec.split(",") if x.strip()]
        style = None
        total = 0.0
        for part in parts:
            name, _, w = part.partition(":")
            w = float(w or 1.0)
            vec = self.kokoro.get_voice_style(name) * w
            style = vec if style is None else style + vec
            total += w
        return style / max(total, 1e-6)

    @functools.lru_cache(maxsize=4096)
    def _phoneme_len(self, word: str, lang: str) -> int:
        ph = self.kokoro.tokenizer.phonemize(word, lang)
        return max(1, len([c for c in ph if c not in _PUNCT and not c.isspace()]))

    def synthesize(self, tokens: list[Token], voice: str, speed: float = 1.0, lang: str = "en-us") -> SynthResult:
        spoken_words = [w for t in tokens for w in t.spoken]
        text = " ".join(spoken_words)
        if not text.strip():
            return SynthResult(np.zeros(int(0.2 * SAMPLE_RATE), dtype=np.float32), SAMPLE_RATE, [], "empty")
        with self._run_lock:
            audio, sr, timings = self.kokoro.create_timed(
                text, voice=self._voice(voice), speed=float(speed), lang=lang,
                trim=True, sentence_pause=0.28, clause_pause=0.12,
            )
        audio = np.asarray(audio, dtype=np.float32)
        if not timings:
            return SynthResult(audio, sr, None, "none")
        return SynthResult(audio, sr, self._word_times(timings, spoken_words, lang), "kokoro-durations")

    def _word_times(self, timings, spoken_words: list[str], lang: str) -> list[tuple[float, float]]:
        # group phoneme timings into space-separated phoneme words
        groups: list[list] = []
        cur: list = []
        for t in timings:
            if t.phoneme == " ":
                if cur:
                    groups.append(cur)
                    cur = []
            else:
                cur.append(t)
        if cur:
            groups.append(cur)
        # drop groups that are only punctuation (they belong to the previous word)
        words_ph = [g for g in groups if any(p.phoneme not in _PUNCT for p in g)]
        if len(words_ph) == len(spoken_words):
            return [(g[0].start, max(x.end for x in g if x.phoneme not in _PUNCT)) for g in words_ph]
        # counts differ (espeak expanded/merged something): distribute by phoneme length
        phones = [t for g in words_ph for t in g if t.phoneme not in _PUNCT]
        if not phones:
            return [(0.0, 0.0)] * len(spoken_words)
        lens = np.array([self._phoneme_len(re.sub(r"[^\w'’-]", "", w) or w, lang) for w in spoken_words], dtype=float)
        bounds = np.concatenate([[0.0], np.cumsum(lens) / lens.sum() * len(phones)])
        out = []
        for i in range(len(spoken_words)):
            a = min(int(round(bounds[i])), len(phones) - 1)
            b = max(a + 1, min(int(round(bounds[i + 1])), len(phones)))
            out.append((phones[a].start, phones[b - 1].end))
        return out
