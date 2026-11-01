"""Speech recognition used for (a) aligning TTS audio that has no native timings and
(b) independently checking narration/subtitle sync and pronunciation in QC.

Engines, in order of preference:
  1. faster-whisper   (pip install faster-whisper; multilingual; model auto-downloads)
  2. sherpa-onnx      (pip install sherpa-onnx; offline models from GitHub releases;
                       English Parakeet-TDT by default: `python -m reelforge setup-models --asr`)
"""

from __future__ import annotations

import functools
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from ..config import Settings, settings as default_settings

PARAKEET = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
PARAKEET_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{PARAKEET}.tar.bz2"
_lock = threading.Lock()


@dataclass
class ASRWord:
    text: str
    start: float
    end: float


def _sherpa_dir(s: Settings) -> Path:
    return s.models_dir / "asr" / PARAKEET


def asr_available(s: Settings = default_settings) -> dict:
    out = {"faster_whisper": False, "sherpa_onnx": False, "engine": None}
    try:
        import faster_whisper  # noqa: F401

        out["faster_whisper"] = True
    except Exception:
        pass
    try:
        import sherpa_onnx  # noqa: F401

        out["sherpa_onnx"] = (_sherpa_dir(s) / "tokens.txt").exists()
    except Exception:
        pass
    if os.environ.get("REELFORGE_ASR", "").strip() in ("sherpa", "sherpa-onnx") and out["sherpa_onnx"]:
        out["engine"] = "sherpa-onnx"
    elif out["faster_whisper"]:
        out["engine"] = "faster-whisper"
    elif out["sherpa_onnx"]:
        out["engine"] = "sherpa-onnx"
    return out


def ensure_asr_model(s: Settings = default_settings, log=print) -> bool:
    d = _sherpa_dir(s)
    if (d / "tokens.txt").exists():
        return True
    import tarfile

    import requests

    d.parent.mkdir(parents=True, exist_ok=True)
    tmp = d.parent / f"{PARAKEET}.tar.bz2"
    log("Downloading Parakeet-TDT ASR model (~460 MB) ...")
    with requests.get(PARAKEET_URL, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    with tarfile.open(tmp) as tf:
        tf.extractall(d.parent, filter="data")
    tmp.unlink(missing_ok=True)
    return (d / "tokens.txt").exists()


def _resample(audio: np.ndarray, sr: int, target: int = 16000) -> np.ndarray:
    if sr == target:
        return audio.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr, target)
    return resample_poly(audio, target // g, sr // g).astype(np.float32)


@functools.lru_cache(maxsize=1)
def _sherpa_recognizer(model_dir: str):
    import sherpa_onnx

    d = Path(model_dir)
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(d / "encoder.int8.onnx"),
        decoder=str(d / "decoder.int8.onnx"),
        joiner=str(d / "joiner.int8.onnx"),
        tokens=str(d / "tokens.txt"),
        num_threads=max(1, (os.cpu_count() or 2)),
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
    )


def _sherpa_transcribe(audio16: np.ndarray, s: Settings) -> list[ASRWord]:
    rec = _sherpa_recognizer(str(_sherpa_dir(s)))
    words: list[ASRWord] = []
    # Parakeet handles long inputs, but chunk at ~25 s on silences to bound memory
    for offset, chunk in _chunks_on_silence(audio16, 16000, max_len=25.0):
        stream = rec.create_stream()
        stream.accept_waveform(16000, chunk)
        rec.decode_stream(stream)
        res = stream.result
        toks = list(res.tokens)
        ts = list(res.timestamps)
        durs = list(getattr(res, "durations", []) or [])
        chunk_end = len(chunk) / 16000
        cur_text, cur_start, cur_end = "", None, 0.0
        for i, tok in enumerate(toks):
            t0 = ts[i] if i < len(ts) else cur_end
            t1 = t0 + (durs[i] if i < len(durs) and durs[i] > 0 else 0.08)
            if i + 1 < len(ts):
                t1 = min(max(t1, t0 + 0.04), ts[i + 1]) if durs else ts[i + 1]
            else:
                t1 = min(max(t1, t0 + 0.08), chunk_end)
            starts_word = tok.startswith("▁") or tok.startswith(" ") or cur_start is None
            piece = tok.replace("▁", "").strip()
            if starts_word and cur_text:
                words.append(ASRWord(cur_text, offset + cur_start, offset + cur_end))
                cur_text, cur_start = "", None
            if cur_start is None:
                cur_start = t0
            cur_text += piece
            cur_end = t1
        if cur_text and cur_start is not None:
            words.append(ASRWord(cur_text, offset + cur_start, offset + cur_end))
    return [w for w in words if w.text]


def _chunks_on_silence(audio: np.ndarray, sr: int, max_len: float = 25.0):
    n = len(audio)
    if n <= max_len * sr:
        yield 0.0, audio
        return
    frame = int(0.02 * sr)
    pos = 0
    while pos < n:
        end = min(n, pos + int(max_len * sr))
        if end < n:
            # cut at the quietest 20 ms frame in the last 5 seconds of the window
            lo = max(pos + frame, end - 5 * sr)
            seg = audio[lo:end]
            k = len(seg) // frame
            if k > 0:
                rms = np.sqrt((seg[: k * frame].reshape(k, frame) ** 2).mean(axis=1))
                end = lo + int(np.argmin(rms)) * frame + frame // 2
        yield pos / sr, audio[pos:end]
        pos = end


@functools.lru_cache(maxsize=2)
def _whisper_model(name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type="int8")


def _whisper_transcribe(audio16: np.ndarray, language: str) -> list[ASRWord]:
    model = _whisper_model(os.environ.get("REELFORGE_WHISPER_MODEL", "small"))
    segments, _info = model.transcribe(audio16, language=language or None, word_timestamps=True, vad_filter=False, beam_size=5)
    out = []
    for seg in segments:
        for w in seg.words or []:
            out.append(ASRWord(w.word.strip(), float(w.start), float(w.end)))
    return out


def transcribe(audio: np.ndarray, sr: int, language: str = "en", s: Settings = default_settings) -> tuple[list[ASRWord], str]:
    """Returns (words, engine name). Raises RuntimeError when no ASR engine is available."""
    info = asr_available(s)
    audio16 = _resample(np.asarray(audio, dtype=np.float32), sr, 16000)
    with _lock:
        if info["engine"] == "faster-whisper":
            return _whisper_transcribe(audio16, language), "faster-whisper"
        if info["engine"] == "sherpa-onnx" and language == "en":
            return _sherpa_transcribe(audio16, s), "sherpa-onnx/parakeet-tdt"
    raise RuntimeError("No speech recogniser available for language %r (install faster-whisper, or run setup-models --asr for English)" % language)


def norm_word(w: str) -> str:
    w = w.lower().replace("’", "'")
    w = re.sub(r"[^\w\u0900-\u0DFF']+", "", w, flags=re.UNICODE)  # keep Indic vowel signs
    return w.strip("'")
