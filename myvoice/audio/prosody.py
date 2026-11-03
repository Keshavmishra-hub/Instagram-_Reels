"""Prosody and voice measurements using Praat's algorithms (praat-parselmouth).

Pitch: autocorrelation method, two passes. The first pass uses a wide 50–700 Hz search; the second
uses a speaker-adaptive range (0.75 × Q1 … 1.5 × Q3, or 2.5 × Q3 for expressive deliveries), the
procedure of De Looze & Hirst (2008), which suppresses octave errors.

Voice quality (jitter, shimmer, HNR) is only meaningful on sustained vowels; for connected speech
only the harmonics-to-noise ratio is reported, averaged over voiced frames.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .vad import FRAME, SpeechMap


def parselmouth_available() -> bool:
    try:
        import parselmouth  # noqa: F401

        return True
    except Exception:
        return False


def _speech_mask_for_times(times: np.ndarray, sm: SpeechMap) -> np.ndarray:
    fi = np.clip((times / FRAME).astype(int), 0, len(sm.speech) - 1)
    return sm.speech[fi]


def pitch_track(audio: np.ndarray, sr: int, sm: SpeechMap, expressive: bool = False) -> Optional[dict]:
    try:
        import parselmouth
    except Exception:
        return None
    if sm.speech_seconds < 0.25:
        return None
    snd = parselmouth.Sound(audio.astype(np.float64), sampling_frequency=float(sr))
    p1 = snd.to_pitch_ac(time_step=0.01, pitch_floor=50.0, pitch_ceiling=700.0)
    f1 = p1.selected_array["frequency"]
    t1 = p1.xs()
    v1 = f1[(f1 > 0) & _speech_mask_for_times(t1, sm)]
    if v1.size < 10:
        return {"voiced_frames": int(v1.size), "voiced_fraction": round(v1.size * 0.01 / max(sm.speech_seconds, 1e-6), 3)}
    q1, q3 = np.percentile(v1, [25, 75])
    floor = float(max(40.0, 0.75 * q1))
    ceiling = float(min(1100.0, (2.5 if expressive else 1.5) * q3))
    p2 = snd.to_pitch_ac(time_step=0.01, pitch_floor=floor, pitch_ceiling=ceiling)
    f = p2.selected_array["frequency"]
    t = p2.xs()
    mask = (f > 0) & _speech_mask_for_times(t, sm)
    v = f[mask]
    if v.size < 10:
        return {"voiced_frames": int(v.size), "voiced_fraction": round(v.size * 0.01 / max(sm.speech_seconds, 1e-6), 3)}
    med = float(np.median(v))
    st = 12.0 * np.log2(v / med)
    p5, p95 = np.percentile(v, [5, 95])
    # compact contour for display: (time, Hz) every 20 ms where voiced
    keep = np.where(mask)[0][::2][:600]
    contour = [[round(float(t[i]), 2), round(float(f[i]), 1)] for i in keep]
    return {
        "median_hz": round(med, 1),
        "mean_hz": round(float(v.mean()), 1),
        "p5_hz": round(float(p5), 1),
        "p95_hz": round(float(p95), 1),
        "range_st": round(float(12.0 * np.log2(p95 / p5)), 2),
        "sd_st": round(float(st.std()), 2),
        "voiced_frames": int(v.size),
        "voiced_fraction": round(min(1.0, v.size * 0.01 / max(sm.speech_seconds, 1e-6)), 3),
        "search_floor_hz": round(floor, 1),
        "search_ceiling_hz": round(ceiling, 1),
        "contour": contour,
        "_voiced_times": t[mask],
    }


def harmonicity(audio: np.ndarray, sr: int, floor_hz: float = 75.0) -> Optional[float]:
    try:
        import parselmouth
    except Exception:
        return None
    snd = parselmouth.Sound(audio.astype(np.float64), sampling_frequency=float(sr))
    h = snd.to_harmonicity_cc(time_step=0.01, minimum_pitch=max(40.0, floor_hz), silence_threshold=0.1, periods_per_window=1.0)
    vals = h.values[0]
    vals = vals[vals > -100]  # Praat marks unvoiced frames with -200 dB
    return round(float(vals.mean()), 2) if vals.size >= 10 else None


def sustained_vowel_quality(audio: np.ndarray, sr: int, sm: SpeechMap, floor_hz: float, ceiling_hz: float) -> dict:
    """Jitter (local), shimmer (local) and HNR on the steady middle of a sustained vowel."""
    try:
        import parselmouth
        from parselmouth.praat import call
    except Exception:
        return {}
    if not sm.segments:
        return {}
    a, b = max(sm.segments, key=lambda s: s[1] - s[0])
    if b - a < 1.0:
        return {"note": "vowel shorter than 1 s"}
    a, b = a + 0.25 * (b - a), b - 0.25 * (b - a)  # steady middle half
    seg = audio[int(a * sr):int(b * sr)].astype(np.float64)
    snd = parselmouth.Sound(seg, sampling_frequency=float(sr))
    pp = call(snd, "To PointProcess (periodic, cc)", floor_hz, ceiling_hz)
    out = {"window_s": round(b - a, 2)}
    try:
        out["jitter_local_pct"] = round(100.0 * call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3), 3)
        out["shimmer_local_pct"] = round(100.0 * call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6), 3)
    except Exception:  # pragma: no cover - Praat raises on undefined measures
        pass
    hnr = harmonicity(seg.astype(np.float32), sr, floor_hz)
    if hnr is not None:
        out["hnr_db"] = hnr
    return out


def breaths(sm: SpeechMap, voiced_times: Optional[np.ndarray]) -> int:
    """Audible breaths: >=150 ms stretches inside pauses that are clearly above the room noise but
    unvoiced. A count, not a classification of individual events."""
    if len(sm.segments) < 2:
        return 0
    voiced = np.zeros(len(sm.speech), dtype=bool)
    if voiced_times is not None and len(voiced_times):
        voiced[np.clip((voiced_times / FRAME).astype(int), 0, len(voiced) - 1)] = True
    count = 0
    for (_a0, a1), (b0, _b1) in zip(sm.segments[:-1], sm.segments[1:]):
        i0, i1 = int(a1 / FRAME), int(b0 / FRAME)
        if i1 - i0 < 15:
            continue
        lvl = sm.frame_db[i0:i1]
        hot = (lvl > sm.noise_floor_db + 8.0) & ~voiced[i0:i1]
        run = best = 0
        for h in hot:
            run = run + 1 if h else 0
            best = max(best, run)
        if best >= 15:
            count += 1
    return count


def speaking_rate(syllables: int, words: int, sm: SpeechMap) -> dict:
    if not sm.segments or syllables <= 0:
        return {}
    phonation = sm.speech_seconds
    span = sm.segments[-1][1] - sm.segments[0][0]
    out = {
        "syllables": syllables,
        "words": words,
        "articulation_rate": round(syllables / phonation, 2) if phonation > 0.2 else None,  # syllables / s, pauses excluded
        "speech_rate": round(syllables / span, 2) if span > 0.2 else None,  # syllables / s, pauses included
        "wpm": round(words / (span / 60.0), 1) if span > 0.5 and words else None,
    }
    return out


def pause_stats(analysis: dict) -> dict:
    pauses = analysis.get("pauses") or []
    span = analysis.get("speech_span") or 0.0
    return {
        "count": len(pauses),
        "per_minute": round(len(pauses) / (span / 60.0), 1) if span > 3 else None,
        "mean_s": round(float(np.mean(pauses)), 3) if pauses else None,
        "max_s": round(float(max(pauses)), 3) if pauses else None,
        "total_s": round(float(sum(pauses)), 3),
    }
