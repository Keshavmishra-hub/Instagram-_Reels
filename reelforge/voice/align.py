"""Word timing for TTS audio that did not come with timings.

1. ASR alignment: recognise the audio, match recognised words to the known script words
   (sequence alignment), interpolate the few that were not matched.
2. Fallback estimate: split into phrases at punctuation, snap phrase boundaries to detected
   pauses, distribute words inside a phrase by syllable weight.
"""

from __future__ import annotations

import difflib
from typing import Optional

import numpy as np

from ..config import Settings, settings as default_settings
from .asr import ASRWord, norm_word, transcribe
from .normalize import count_syllables


def match_words(script_words: list[str], asr_words: list[ASRWord]) -> list[Optional[int]]:
    """For each script word, the index of the ASR word it matches (or None)."""
    a = [norm_word(w) for w in script_words]
    b = [norm_word(w.text) for w in asr_words]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    mapping: list[Optional[int]] = [None] * len(a)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            mapping[block.a + k] = block.b + k
    # second pass: fuzzy-match within replaced spans of equal length (e.g. "nineteen" vs "19")
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                if difflib.SequenceMatcher(a=a[i1 + k], b=b[j1 + k]).ratio() >= 0.6:
                    mapping[i1 + k] = j1 + k
    return mapping


def _interpolate(words: list[str], known: list[Optional[tuple[float, float]]], total: float) -> list[tuple[float, float]]:
    out: list[Optional[tuple[float, float]]] = list(known)
    n = len(words)
    i = 0
    while i < n:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < n and out[j] is None:
            j += 1
        left = out[i - 1][1] if i > 0 and out[i - 1] else 0.0
        right = out[j][0] if j < n and out[j] else total
        if right < left:
            right = left
        weights = np.array([count_syllables(w) + 0.5 for w in words[i:j]], dtype=float)
        bounds = left + np.concatenate([[0], np.cumsum(weights)]) / weights.sum() * (right - left)
        for k in range(i, j):
            out[k] = (float(bounds[k - i]), float(bounds[k - i + 1]))
        i = j
    return [x if x else (0.0, 0.0) for x in out]


def align_with_asr(audio: np.ndarray, sr: int, words: list[str], language: str, s: Settings = default_settings):
    asr_words, engine = transcribe(audio, sr, language, s)
    mapping = match_words(words, asr_words)
    known = [(asr_words[m].start, asr_words[m].end) if m is not None else None for m in mapping]
    matched = sum(1 for m in mapping if m is not None)
    return _interpolate(words, known, len(audio) / sr), f"asr:{engine}", matched / max(1, len(words))


def speech_mask(audio: np.ndarray, sr: int, frame_s: float = 0.01, thresh_db: float = -38.0) -> np.ndarray:
    frame = max(1, int(frame_s * sr))
    n = len(audio) // frame
    if n == 0:
        return np.zeros(0, dtype=bool)
    rms = np.sqrt((audio[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms / (np.percentile(rms, 98) + 1e-12))
    return db > thresh_db


def estimate(audio: np.ndarray, sr: int, words: list[str]) -> list[tuple[float, float]]:
    """Pause-aware proportional estimate (used when no ASR is installed)."""
    total = len(audio) / sr
    mask = speech_mask(audio, sr)
    if mask.size == 0 or not mask.any():
        return _interpolate(words, [None] * len(words), total)
    voiced = np.where(mask)[0]
    t0, t1 = voiced[0] * 0.01, (voiced[-1] + 1) * 0.01
    # pauses >= 120 ms inside speech
    pauses = []
    run_start = None
    for i in range(voiced[0], voiced[-1] + 1):
        if not mask[i]:
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            if (i - run_start) >= 12:
                pauses.append((run_start * 0.01, i * 0.01))
            run_start = None
    # phrase boundaries after punctuation
    weights = np.array([count_syllables(w) + 0.6 for w in words], dtype=float)
    cum = np.concatenate([[0], np.cumsum(weights)]) / weights.sum()
    phrase_ends = [i for i, w in enumerate(words[:-1]) if w and w[-1] in ",.;:!?…—"]
    known: list[Optional[tuple[float, float]]] = [None] * len(words)
    used = set()
    boundaries = []
    for idx in phrase_ends:
        expect = t0 + cum[idx + 1] * (t1 - t0)
        best = None
        for k, (ps, pe) in enumerate(pauses):
            if k in used:
                continue
            d = abs((ps + pe) / 2 - expect)
            if d < 0.8 and (best is None or d < best[0]):
                best = (d, k)
        if best is not None:
            used.add(best[1])
            boundaries.append((idx, pauses[best[1]]))
    # build segments between snapped boundaries and distribute inside each
    seg_start_word, seg_start_t = 0, t0
    for idx, (ps, pe) in sorted(boundaries):
        _fill(words, known, weights, seg_start_word, idx + 1, seg_start_t, ps)
        seg_start_word, seg_start_t = idx + 1, pe
    _fill(words, known, weights, seg_start_word, len(words), seg_start_t, t1)
    return [k if k else (0.0, 0.0) for k in known]


def _fill(words, known, weights, i, j, a, b):
    if j <= i:
        return
    w = weights[i:j]
    bounds = a + np.concatenate([[0], np.cumsum(w)]) / w.sum() * max(0.0, b - a)
    for k in range(i, j):
        known[k] = (float(bounds[k - i]), float(bounds[k - i + 1]))


def align(audio: np.ndarray, sr: int, words: list[str], language: str, s: Settings = default_settings) -> tuple[list[tuple[float, float]], str]:
    try:
        times, method, ratio = align_with_asr(audio, sr, words, language, s)
        if ratio >= 0.5:
            return times, method
    except Exception:
        pass
    return estimate(audio, sr, words), "estimated"
