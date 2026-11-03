"""Minimal ctypes binding to the eSpeak NG library (bundled by the `espeakng-loader` wheel, which
ReelForge's Kokoro dependency already installs; a system libespeak-ng also works).

Used for English grapheme-to-phoneme conversion (phoneme coverage, syllable counts, read-check keys).
`synthesize` exists only so the test-suite can generate real speech without network access; the
studio never plays synthetic speech to you (it could bias your natural pronunciation).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import functools
import threading
from typing import Optional

import numpy as np

_lock = threading.Lock()
_lib = None
_sr = 0
_init_error: Optional[str] = None
_SYNTH_CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
_chunks: list[np.ndarray] = []


@_SYNTH_CB
def _on_audio(wav, n, _events):  # pragma: no cover - exercised through synthesize()
    if n > 0:
        _chunks.append(np.ctypeslib.as_array(wav, shape=(n,)).copy())
    return 0


def _load():
    global _lib, _sr, _init_error
    if _lib is not None or _init_error is not None:
        return _lib
    path = data = None
    try:
        import espeakng_loader

        path = espeakng_loader.get_library_path()
        data = espeakng_loader.get_data_path()
    except Exception:
        path = ctypes.util.find_library("espeak-ng")
    if not path:
        _init_error = "eSpeak NG not found (pip install espeakng-loader)"
        return None
    try:
        lib = ctypes.CDLL(path)
        sr = lib.espeak_Initialize(0x02, 0, data.encode() if data else None, 0)  # AUDIO_OUTPUT_SYNCHRONOUS
        if sr <= 0:
            raise RuntimeError("espeak_Initialize failed")
        lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
        lib.espeak_TextToPhonemes.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_int, ctypes.c_int]
        lib.espeak_SetSynthCallback(_on_audio)
        _lib, _sr = lib, sr
    except Exception as e:  # pragma: no cover - depends on the platform
        _init_error = f"eSpeak NG failed to load: {e}"
    return _lib


def available() -> bool:
    with _lock:
        return _load() is not None


def status() -> dict:
    with _lock:
        _load()
    return {"available": _lib is not None, "error": _init_error or ""}


@functools.lru_cache(maxsize=8192)
def phonemize(text: str, voice: str = "en-us") -> tuple[tuple[str, ...], ...]:
    """IPA phonemes per word, stress marks removed: (("h","ə","l","oʊ"), ("w","ɜː","l","d"))."""
    with _lock:
        lib = _load()
        if lib is None:
            raise RuntimeError(_init_error or "eSpeak NG unavailable")
        lib.espeak_SetVoiceByName(voice.encode())
        ptr = ctypes.pointer(ctypes.c_char_p(text.encode("utf-8")))
        parts = []
        while ptr.contents.value is not None:
            r = lib.espeak_TextToPhonemes(ptr, 1, ord("_") << 8 | 0x02)  # UTF-8 in, IPA out, "_" separated
            if r:
                parts.append(r.decode("utf-8", errors="ignore"))
    words = []
    for w in " ".join(parts).split():
        phs = tuple(p.replace("ˈ", "").replace("ˌ", "") for p in w.split("_"))
        phs = tuple(p for p in phs if p)
        if phs:
            words.append(phs)
    return tuple(words)


def synthesize(text: str, voice: str = "en-us", rate: int = 160) -> tuple[np.ndarray, int]:
    with _lock:
        lib = _load()
        if lib is None:
            raise RuntimeError(_init_error or "eSpeak NG unavailable")
        _chunks.clear()
        lib.espeak_SetVoiceByName(voice.encode())
        lib.espeak_SetParameter(1, rate, 0)  # espeakRATE
        b = text.encode("utf-8")
        lib.espeak_Synth(ctypes.c_char_p(b), ctypes.c_size_t(len(b) + 1), 0, 1, 0, 1, None, None)
        lib.espeak_Synchronize()
        audio = np.concatenate(_chunks).astype(np.float32) / 32768.0 if _chunks else np.zeros(0, np.float32)
        _chunks.clear()
        return audio, _sr
