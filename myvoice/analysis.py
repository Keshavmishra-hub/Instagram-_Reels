"""Analyse one take: signal measurements + prosody, then the quality verdict."""

from __future__ import annotations

from typing import Optional

import numpy as np

from .audio.analysis import analyze_clap, analyze_signal
from .audio.prosody import breaths, harmonicity, pause_stats, pitch_track, speaking_rate, sustained_vowel_quality
from .audio.quality import assess
from .models import Quality, ReadMatch, Take
from .text.phonemes import analyse_text

EXPRESSIVE_STYLES = {"cinematic_intro", "movie_narration", "dramatic_opening", "suspense", "motivational", "promotional", "reel_hook"}


def analyze_take(audio: np.ndarray, sr: int, ctx: dict) -> dict:
    an, sm = analyze_signal(audio, sr)
    kind = ctx.get("kind", "sentence")
    if kind == "clap":
        an["room"] = analyze_clap(audio, sr)
        return an
    if kind == "silence":
        return an
    expressive = ctx.get("emotion", "neutral") != "neutral" or ctx.get("style") in EXPRESSIVE_STYLES or kind == "glide"
    pt = pitch_track(audio, sr, sm, expressive=expressive)
    voiced_times = None
    if pt:
        voiced_times = pt.pop("_voiced_times", None)
        an["pitch"] = pt
    if sm.speech_seconds >= 1.0 and kind != "sustained":
        floor = (pt or {}).get("search_floor_hz", 75.0) if pt else 75.0
        an["hnr_db"] = harmonicity(audio, sr, floor)
    if kind == "sustained" and pt and pt.get("median_hz"):
        an["voice_quality"] = sustained_vowel_quality(audio, sr, sm, pt["search_floor_hz"], pt["search_ceiling_hz"])
    an["breaths"] = breaths(sm, voiced_times)
    expected = ctx.get("expected")
    complete = not expected or sm.speech_seconds >= 0.6 * expected[0]
    if ctx.get("syllables") and complete:  # a rate from the script is only valid if the script was read
        an["rate"] = speaking_rate(int(ctx["syllables"]), int(ctx.get("words") or 0), sm)
    an["pause_stats"] = pause_stats(an)
    return an


def rate_from_coverage(an: dict, syllables: int, words: int, coverage: float) -> None:
    """After the read-check: scale script syllables by the fraction of words actually heard."""
    segs = an.get("segments") or []
    if not segs or not syllables or coverage <= 0:
        return
    phonation = sum(b - a for a, b in segs)
    span = segs[-1][1] - segs[0][0]
    syl, wd = syllables * coverage, words * coverage
    an["rate"] = {"syllables": round(syl), "words": round(wd),
                  "articulation_rate": round(syl / phonation, 2) if phonation > 0.2 else None,
                  "speech_rate": round(syl / span, 2) if span > 0.2 else None,
                  "wpm": round(wd / (span / 60.0), 1) if span > 0.5 else None, "from": "read-check"}


def update_rate_from_text(an: dict, text: str, sm_segments: list) -> None:
    """Recompute speaking rate from a transcript (spontaneous takes, edited transcripts)."""
    a = analyse_text(text)
    if not a["syllables"] or not sm_segments:
        return
    phonation = sum(b - x for x, b in sm_segments)
    span = sm_segments[-1][1] - sm_segments[0][0]
    an["rate"] = {
        "syllables": a["syllables"], "words": a["words"],
        "articulation_rate": round(a["syllables"] / phonation, 2) if phonation > 0.2 else None,
        "speech_rate": round(a["syllables"] / span, 2) if span > 0.2 else None,
        "wpm": round(a["words"] / (span / 60.0), 1) if span > 0.5 else None,
        "from": "transcript",
    }


def quality_context(take: Take, expected: Optional[tuple], min_sec: Optional[float]) -> dict:
    return {
        "kind": take.kind, "volume": take.volume, "pace": take.pace, "emotion": take.emotion, "style": take.style,
        "expected": expected, "min_sec": min_sec,
        "track_events": take.capture.track_events, "constraints_applied": take.capture.constraints_applied,
        "paused_at": take.capture.paused_at,
    }


def reassess(take: Take, expected: Optional[tuple], min_sec: Optional[float]) -> Quality:
    match: Optional[ReadMatch] = take.asr.match if take.asr and take.asr.status == "done" else None
    asr = {"avg_logprob": take.asr.avg_logprob} if take.asr and take.asr.status == "done" else None
    return assess(take.analysis, quality_context(take, expected, min_sec), match, asr)
