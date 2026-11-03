"""Shared helpers for the MY VOICE tests: real (synthetic) speech from eSpeak NG, rooms, WAV bytes."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

SR = 48000
MIC_CHECK = "Hello, this is my microphone check. I am sitting comfortably, about a hand's width from the mic."


def speech(text: str = MIC_CHECK, voice: str = "en-us", sr: int = SR, lead: float = 0.6, tail: float = 0.9,
           noise_db: float = -70.0, gain: float = 0.5, seed: int = 0) -> np.ndarray:
    from myvoice.audio.io import resample
    from myvoice.text import espeak

    if not espeak.available():
        pytest.skip("eSpeak NG not available")
    a, sr0 = espeak.synthesize(text, voice)
    a = resample(a, sr0, sr)
    a = a * (gain / max(1e-6, float(np.abs(a).max())))
    x = np.concatenate([np.zeros(int(lead * sr), np.float32), a, np.zeros(int(tail * sr), np.float32)])
    rng = np.random.default_rng(seed)
    return (x + rng.normal(0, 10 ** (noise_db / 20), x.shape)).astype(np.float32)


def clap_in_room(t60: float, sr: int = SR, seed: int = 3) -> np.ndarray:
    from scipy.signal import fftconvolve

    rng = np.random.default_rng(seed)
    t = np.arange(int(t60 * 2 * sr)) / sr
    ir = rng.normal(0, 1, len(t)) * np.exp(-6.9 * t / t60)
    clap = rng.normal(0, 1, int(0.006 * sr)) * np.hanning(int(0.006 * sr))
    x = np.concatenate([np.zeros(int(0.5 * sr)), fftconvolve(clap, ir), np.zeros(int(0.5 * sr))])
    x = x / np.abs(x).max() * 0.6 + rng.normal(0, 10 ** (-72 / 20), len(x))
    return x[: int(3.5 * sr)].astype(np.float32)


def wav_bytes(x: np.ndarray, sr: int = SR, subtype: str = "FLOAT") -> bytes:
    buf = io.BytesIO()
    sf.write(buf, x, sr, subtype=subtype, format="WAV")
    return buf.getvalue()
