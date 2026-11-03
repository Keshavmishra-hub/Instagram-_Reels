"""Objective signal measurements for one take. Every number here is computed from the audio; nothing
is estimated from defaults. Results are plain JSON-serialisable values.

Measurements
  levels       peak, overall RMS, active speech level, noise floor, SNR, DC offset
  clipping     flat-topped runs at the take's maximum level (and lower-level flat runs = OS-side clipping)
  dropouts     runs of exact digital silence inside the take (USB / driver / buffer glitches)
  clicks       isolated one-sample discontinuities (digital glitches; not mouth noise)
  silence      leading / trailing silence, internal pauses
  truncation   speech still active at the very start / end of the take
  bandwidth    highest frequency with real content (detects Bluetooth "call mode" and phone-band audio)
  hum          50/60 Hz mains hum and harmonics in the non-speech parts
  ltas         speech spectrum shape in 1/3-octave bands (microphone / position consistency)
  room echo    measured separately from a hand clap in the session warm-up (analyze_clap), because
               blind reverberation estimates from one short sentence are not reliable
"""

from __future__ import annotations

import numpy as np
from scipy.signal import welch

from .io import db, peaks
from .vad import FRAME, SpeechMap, detect_speech, runs

THIRD_OCTAVE_CENTERS = [125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000]


def _clipping(audio: np.ndarray, sr: int) -> dict:
    """Clipping = flat-topped runs of identical samples at a high level.

    A natural waveform peak can sit within 0.1 % of its maximum for several samples, so "close to the
    maximum" is not evidence; identical consecutive values are. With 16-bit converters a natural peak
    repeats a value for at most ~3 samples, so we require 4+ identical samples near full scale,
    2+ at full scale, or 7+ at any high level (clipping before the browser, e.g. OS mic boost)."""
    a = np.abs(audio)
    if a.size < 8:
        return {"events": 0, "samples": 0, "ratio": 0.0, "times": [], "flat_runs": 0}
    same = np.concatenate([[False], np.abs(np.diff(audio)) < 1e-7])  # same[i]: x[i] == x[i-1]
    events: list[float] = []
    clipped = 0
    rules = ((a >= 0.999, 1), (a >= 0.89, 3), (a > 0.25, 6))
    seen = np.zeros(a.size, dtype=bool)
    flat_runs = 0
    for level_mask, min_run in rules:
        for s, e in runs(same & level_mask):
            if e - s >= min_run and not seen[s:e].any():
                seen[max(0, s - 1):e] = True
                events.append((s - 1) / sr)
                clipped += e - s + 1
                if min_run == 6:
                    flat_runs += 1
    merged: list[float] = []
    for t in sorted(events):
        if not merged or t - merged[-1] > 0.01:
            merged.append(t)
    return {"events": len(merged), "samples": int(clipped), "ratio": float(clipped / a.size),
            "times": [round(max(0.0, t), 3) for t in merged[:50]], "flat_runs": flat_runs}


def _dropouts(audio: np.ndarray, sr: int, speech_segments: list[tuple[float, float]]) -> dict:
    zero = np.abs(audio) < 1e-7
    min_len = int(0.003 * sr)
    edge = int(0.1 * sr)
    items = []
    for s, e in runs(zero):
        if e - s < min_len or s < edge or e > len(audio) - int(0.02 * sr):
            continue
        t0, t1 = s / sr, e / sr
        in_speech = any(a - 0.05 <= t0 <= b + 0.05 for a, b in speech_segments)
        items.append({"at": round(t0, 3), "ms": round((t1 - t0) * 1000, 1), "in_speech": in_speech})
    all_zero = bool(zero.mean() > 0.98) if zero.size else True
    return {"count": len(items), "items": items[:30], "all_digital_silence": all_zero}


def _clicks(audio: np.ndarray, sr: int) -> dict:
    """Isolated one-sample discontinuities (digital glitches). The second difference of a click is a
    spike far above both its 10 ms frame's typical value and its immediate neighbourhood."""
    if len(audio) < sr // 10:
        return {"count": 0, "times": []}
    d2 = np.abs(np.diff(audio.astype(np.float64), n=2))  # d2[i] is centred on sample i + 1
    flen = max(16, int(0.01 * sr))
    n = len(d2) // flen
    if n == 0:
        return {"count": 0, "times": []}
    block = d2[: n * flen].reshape(n, flen)
    scale = np.median(block, axis=1) + 1e-6
    cand = np.where(((block / scale[:, None]) > 40.0).reshape(-1) & (block.reshape(-1) > 0.08))[0]
    w = max(2, int(0.0004 * sr))
    out: list[float] = []
    for i in cand:
        t = (i + 1) / sr
        if out and t - out[-1] < 0.005:
            continue
        lo, hi = max(0, i - 8 * w), min(len(d2), i + 8 * w)
        around = np.concatenate([d2[lo:max(lo, i - w)], d2[min(hi, i + w + 1):hi]])
        if around.size and d2[i] > 8.0 * (np.percentile(around, 90) + 1e-6):
            out.append(round(t, 3))
    return {"count": len(out), "times": out[:30]}


def _spectra(audio: np.ndarray, sr: int, sm: SpeechMap):
    """Mean power spectra (dB) of speech and non-speech frames (accumulated in batches)."""
    nfft = 2048 if sr >= 32000 else 1024
    hop = nfft // 2
    if len(audio) < nfft * 2:
        return None
    win = np.hanning(nfft)
    norm = (win ** 2).sum()
    nfr = 1 + (len(audio) - nfft) // hop
    sp_sum = np.zeros(nfft // 2 + 1)
    ns_sum = np.zeros(nfft // 2 + 1)
    sp_n = ns_n = 0
    for b0 in range(0, nfr, 256):
        ids = np.arange(b0, min(nfr, b0 + 256))
        idx = np.arange(nfft)[None, :] + hop * ids[:, None]
        spec = (np.abs(np.fft.rfft(audio[idx] * win, axis=1)) ** 2) / norm
        centers = (ids * hop + nfft / 2) / sr
        fi = np.clip((centers / FRAME).astype(int), 0, len(sm.speech) - 1)
        mask = sm.speech[fi]
        sp_sum += spec[mask].sum(axis=0)
        ns_sum += spec[~mask].sum(axis=0)
        sp_n += int(mask.sum())
        ns_n += int((~mask).sum())
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    s_db = 10 * np.log10(sp_sum / sp_n + 1e-20) if sp_n >= 3 else None
    n_db = 10 * np.log10(ns_sum / ns_n + 1e-20) if ns_n >= 3 else None
    return freqs, s_db, n_db


def _bandwidth(freqs, s_db) -> dict:
    if s_db is None:
        return {"effective_hz": None}
    k = 9
    sm = np.convolve(s_db, np.ones(k) / k, mode="same")
    usable = freqs <= freqs[-1] * 0.96
    ref = float(np.max(sm[(freqs > 150) & usable]))
    above = np.where(usable & (freqs > 300) & (sm >= ref - 60.0))[0]
    eff = float(freqs[above[-1]]) if above.size else None
    return {"effective_hz": round(eff) if eff else None, "nyquist_hz": round(float(freqs[-1]))}


def _hum(audio: np.ndarray, sr: int, sm: SpeechMap) -> dict:
    """Mains hum in non-speech parts: narrow peaks at 50/60 Hz multiples standing out from neighbours."""
    flen = int(FRAME * sr)
    mask = np.repeat(~sm.speech, flen)[: len(audio)]
    noise = audio[: len(mask)][mask]
    if len(noise) < int(0.4 * sr):
        return {"detected": False, "checked": False}
    nper = min(len(noise), 16384 if sr >= 32000 else 8192)
    f, p = welch(noise.astype(np.float64), fs=sr, nperseg=nper)
    pdb = 10 * np.log10(p + 1e-20)
    best = {"detected": False, "checked": True, "base_hz": None, "prominence_db": 0.0}
    for base in (50, 60):
        proms = []
        for k in range(1, 5):
            fk = base * k
            if fk > f[-1]:
                break
            peak_i = np.where(np.abs(f - fk) <= 1.6)[0]
            neigh = np.where((np.abs(f - fk) > 4) & (np.abs(f - fk) <= 18))[0]
            if peak_i.size and neigh.size:
                proms.append(float(pdb[peak_i].max() - np.median(pdb[neigh])))
        if proms and max(proms) > best["prominence_db"]:
            best.update(base_hz=base, prominence_db=round(max(proms), 1), harmonics_over_10db=sum(p >= 10 for p in proms))
    best["detected"] = bool(best["prominence_db"] >= 15.0 or best.get("harmonics_over_10db", 0) >= 2)
    return best


def analyze_clap(audio: np.ndarray, sr: int) -> dict:
    """Room reverberation time from a hand clap (the classic field method).

    The clap is band-passed to 500 Hz – 4 kHz (the speech-critical range), its energy envelope is
    truncated where it meets the noise floor (Lundeby-style), Schroeder backward-integrated into an
    energy decay curve, and the slope between −5 and −25 dB (T20) is extrapolated to 60 dB.
    Needs >= 30 dB between the clap and the room noise; otherwise no value is reported."""
    from scipy.signal import butter, sosfiltfilt

    if len(audio) < sr // 2:
        return {"t60": None, "reason": "too short"}
    sos = butter(4, [500, min(4000, sr / 2 * 0.9)], btype="band", fs=sr, output="sos")
    y = sosfiltfilt(sos, audio.astype(np.float64))
    hop = max(1, int(0.002 * sr))
    n = len(y) // hop
    env = (y[: n * hop] ** 2).reshape(n, hop).mean(axis=1)
    env_db = 10 * np.log10(env + 1e-20)
    pk = int(np.argmax(env_db))
    before = env_db[: max(1, pk - 25)]
    after = env_db[pk + int(0.8 * (n - pk)):] if n - pk > 100 else np.array([])
    noise_db = float(np.median(np.concatenate([before, after]))) if (before.size + after.size) else float(env_db.min())
    dr = float(env_db[pk] - noise_db)
    out = {"t60": None, "dynamic_range_db": round(dr, 1), "clap_at": round(pk * hop / sr, 3)}
    if dr < 30:
        out["reason"] = "clap not loud enough above the room noise"
        return out
    below = np.where(env_db[pk:] <= noise_db + 3)[0]
    end = pk + (int(below[0]) if below.size else n - pk)
    edc = np.cumsum(env[pk:end][::-1])[::-1]
    edc_db = 10 * np.log10(edc / edc[0] + 1e-20)
    t = np.arange(len(edc_db)) * hop / sr
    sel = np.where((edc_db <= -5) & (edc_db >= -25))[0]
    if len(sel) < 5:
        sel = np.where((edc_db <= -3) & (edc_db >= -15))[0]
    if len(sel) < 5:
        out["reason"] = "decay too short to measure"
        return out
    slope = float(np.polyfit(t[sel], edc_db[sel], 1)[0])
    if slope >= -5:
        out["reason"] = "no clear decay"
        return out
    out["t60"] = round(-60.0 / slope, 2)
    return out


def _ltas(freqs, s_db) -> list[float]:
    if s_db is None:
        return []
    p = 10 ** (s_db / 10)
    bands = []
    for c in THIRD_OCTAVE_CENTERS:
        lo, hi = c / 2 ** (1 / 6), c * 2 ** (1 / 6)
        m = (freqs >= lo) & (freqs < hi)
        bands.append(10 * np.log10(p[m].mean() + 1e-20) if m.any() else -120.0)
    bands = np.array(bands)
    ref = 10 * np.log10(np.mean(10 ** (bands / 10)) + 1e-20)
    return [round(float(v - ref), 2) for v in bands]


def analyze_signal(audio: np.ndarray, sr: int) -> tuple[dict, SpeechMap]:
    duration = len(audio) / sr
    sm = detect_speech(audio, sr)
    segs = sm.segments
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if audio.size else 0.0
    out: dict = {
        "duration": round(duration, 3),
        "sample_rate": sr,
        "peak_dbfs": round(db(peak), 2),
        "rms_dbfs": round(db(rms), 2),
        "dc_offset": round(float(np.mean(audio)), 5) if audio.size else 0.0,
        "noise_floor_dbfs": sm.noise_floor_full_db,
        "speech_level_dbfs": sm.speech_level_full_db,
        "snr_db": round(sm.speech_level_full_db - sm.noise_floor_full_db, 1) if segs else None,
        "vad_engine": sm.engine,
        "speech_seconds": round(sm.speech_seconds, 3),
        "speech_ratio": round(sm.speech_seconds / duration, 3) if duration else 0.0,
        "segments": [[round(a, 2), round(b, 2)] for a, b in segs],
    }
    if segs:
        first, last = segs[0][0], segs[-1][1]
        pauses = [round(b0 - a1, 3) for (_a0, a1), (b0, _b1) in zip(segs[:-1], segs[1:]) if b0 - a1 >= 0.2]
        out.update(
            leading_silence=round(first, 3),
            trailing_silence=round(max(0.0, duration - last), 3),
            speech_span=round(last - first, 3),
            pauses=pauses,
            longest_pause=max(pauses) if pauses else 0.0,
        )
        end_frames = sm.speech[-10:]
        end_level = float(np.mean(sm.frame_db[-5:]))
        out["cut_end"] = bool(end_frames.any() and end_frames[-3:].all() and end_level > sm.noise_floor_db + 15)
        out["cut_start"] = bool(sm.speech[:3].all() and float(np.mean(sm.frame_db[:3])) > sm.noise_floor_db + 15)
    else:
        out.update(leading_silence=round(duration, 3), trailing_silence=0.0, speech_span=0.0, pauses=[],
                   longest_pause=0.0, cut_end=False, cut_start=False)
    out["clipping"] = _clipping(audio, sr)
    out["dropouts"] = _dropouts(audio, sr, segs)
    out["clicks"] = _clicks(audio, sr)
    spectra = _spectra(audio, sr, sm)
    if spectra:
        freqs, s_db, _n_db = spectra
        out["bandwidth"] = _bandwidth(freqs, s_db)
        out["ltas"] = _ltas(freqs, s_db)
    else:
        out["bandwidth"] = {"effective_hz": None}
        out["ltas"] = []
    out["hum"] = _hum(audio, sr, sm)
    out["waveform"] = peaks(audio, 600)
    return out, sm
