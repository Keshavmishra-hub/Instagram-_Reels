"""Voice analytics: aggregates of measurements stored with each take (nothing is estimated here).
Uses approved takes; while nothing is approved yet, pending takes are used and flagged as such."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Optional

import numpy as np

from .models import EMOTIONS, STYLES

SPEECH_KINDS = {"sentence", "paragraph", "word_list", "dialogue", "prompt"}
LANG_NAMES = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}
PACE_NAMES = {"slow": "Slow", "normal": "Normal", "fast": "Fast"}


def _q(vals: list[float]) -> Optional[dict]:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    a = np.asarray(vals, dtype=float)
    return {"lo": round(float(np.percentile(a, 25)), 2), "mid": round(float(np.median(a)), 2), "hi": round(float(np.percentile(a, 75)), 2), "n": len(vals)}


def _rows(groups: dict, names: dict, key: str) -> list[dict]:
    out = []
    for g, takes in groups.items():
        q = _q([_get(t, key) for t in takes])
        if q:
            out.append({"id": g, "label": names.get(g, g), **q})
    return out


def _get(t, key: str):
    an = t.analysis or {}
    if key == "f0":
        return (an.get("pitch") or {}).get("median_hz")
    if key == "rate":
        return (an.get("rate") or {}).get("articulation_rate")
    if key == "pauses_pm":
        return (an.get("pause_stats") or {}).get("per_minute")
    if key == "pause_mean":
        return (an.get("pause_stats") or {}).get("mean_s")
    return an.get(key)


def build(st) -> dict:
    takes = [t for t in st.store.takes() if not t.trashed]
    approved = [t for t in takes if t.status == "approved"]
    basis = "approved"
    pool = approved
    if not pool:
        pool = [t for t in takes if t.status == "pending"]
        basis = "pending"
    speech = [t for t in pool if t.kind in SPEECH_KINDS and (t.analysis or {}).get("speech_seconds", 0) > 0.5]
    sessions = {s.id: s for s in st.store.sessions()}
    out: dict = {"basis": basis, "n_takes": len(pool), "n_speech": len(speech)}

    # ------------------------------------------------------------------ pitch
    frames: list[float] = []
    for t in speech:
        frames += [p[1] for p in ((t.analysis.get("pitch") or {}).get("contour") or [])]
    hist = []
    if frames:
        lo = max(50, int(np.floor(np.percentile(frames, 1) / 10) * 10))
        hi = int(np.ceil(np.percentile(frames, 99) / 10) * 10)
        step = max(5, int(np.ceil((hi - lo) / 30 / 5) * 5))
        edges = list(range(lo, hi + step, step))
        counts, _ = np.histogram(frames, bins=edges)
        hist = [{"x0": edges[i], "x1": edges[i + 1], "count": int(c)} for i, c in enumerate(counts)]
    medians = [_get(t, "f0") for t in speech if _get(t, "f0")]
    by_emotion = defaultdict(list)
    by_lang = defaultdict(list)
    for t in speech:
        by_emotion[t.emotion].append(t)
        if t.lang in LANG_NAMES:
            by_lang[t.lang].append(t)
    out["pitch"] = {
        "hist": hist, "frames": len(frames),
        "median_hz": round(float(median(medians)), 1) if medians else None,
        "p5_hz": round(float(np.percentile(frames, 5)), 1) if frames else None,
        "p95_hz": round(float(np.percentile(frames, 95)), 1) if frames else None,
        "range_st": round(float(12 * np.log2(np.percentile(frames, 95) / np.percentile(frames, 5))), 1) if len(frames) > 20 else None,
        "by_emotion": sorted(_rows(by_emotion, EMOTIONS, "f0"), key=lambda r: r["mid"]),
        "by_lang": _rows(by_lang, LANG_NAMES, "f0"),
    }

    # ------------------------------------------------------------------ rate + pauses
    read = [t for t in speech if t.kind != "prompt"]
    by_pace = defaultdict(list)
    for t in read:
        by_pace[t.pace].append(t)
    pace_rows = [r for p in ("slow", "normal", "fast") for r in _rows({p: by_pace[p]}, PACE_NAMES, "rate") if by_pace[p]]
    by_style = defaultdict(list)
    for t in speech:
        by_style[t.style].append(t)
    pause_rows = []
    for sname, ts in by_style.items():
        vals = [_get(t, "pauses_pm") for t in ts if _get(t, "pauses_pm") is not None]
        means = [_get(t, "pause_mean") for t in ts if _get(t, "pause_mean") is not None]
        if vals:
            pause_rows.append({"id": sname, "label": STYLES.get(sname, sname), "per_minute": round(float(np.mean(vals)), 1),
                               "mean_s": round(float(np.mean(means)), 2) if means else None, "n": len(vals)})
    pause_rows.sort(key=lambda r: -r["per_minute"])
    out["rate"] = {"by_pace": pace_rows, "by_lang": _rows({k: v for k, v in by_lang.items()}, LANG_NAMES, "rate"),
                   "spontaneous": _q([_get(t, "rate") for t in speech if t.kind == "prompt"])}
    out["pauses"] = {"by_style": pause_rows[:12],
                     "breaths_per_min": round(float(np.mean([t.analysis.get("breaths", 0) / max(1e-6, t.analysis.get("speech_span", 0) / 60) for t in speech if t.analysis.get("speech_span", 0) > 5])), 1)
                     if any(t.analysis.get("speech_span", 0) > 5 for t in speech) else None}

    # ------------------------------------------------------------------ read-check
    checked = [t for t in pool if t.asr and t.asr.status == "done" and t.asr.match and t.asr.match.verdict != "unchecked"]
    read_rows = []
    for lang, name in LANG_NAMES.items():
        cs = [t.asr.match.coverage for t in checked if t.lang == lang]
        if cs:
            read_rows.append({"id": lang, "label": name, "coverage": round(float(np.mean(cs)), 3), "n": len(cs),
                              "partial": sum(1 for t in checked if t.lang == lang and t.asr.match.verdict != "read")})
    missed = Counter()
    for t in checked:
        for i in t.asr.match.missing:
            if i < len(t.asr.match.expected_words):
                missed[t.asr.match.expected_words[i].lower()] += 1
    out["read"] = {"by_lang": read_rows, "checked": len(checked), "often_missed": [{"word": w, "count": c} for w, c in missed.most_common(15) if c >= 2]}

    # ------------------------------------------------------------------ quality
    scores = [t.quality.score for t in pool]
    score_hist = []
    if scores:
        counts, edges = np.histogram(scores, bins=list(range(0, 110, 10)))
        score_hist = [{"x0": int(edges[i]), "x1": int(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)]
    issue_counts: Counter = Counter()
    issue_label: dict[str, str] = {}
    for t in takes:  # all non-trashed takes: where problems come from
        for i in t.quality.issues:
            if i.severity in ("error", "warning"):
                issue_counts[i.code] += 1
                issue_label.setdefault(i.code, i.message)
    sess_rows = []
    for sid in sorted({t.session_id for t in takes}):
        ts = [t for t in takes if t.session_id == sid and t.kind != "silence"]
        s = sessions.get(sid)
        snrs = [t.analysis.get("snr_db") for t in ts if t.analysis.get("snr_db") is not None]
        sess_rows.append({
            "id": sid, "label": (s.started_at[:10] if s else sid[1:9]) + (f" #{sid[-4:]}" if s else ""),
            "snr": round(float(median(snrs)), 1) if snrs else None,
            "noise_floor": s.noise_floor_db if s and s.noise_floor_db is not None else (round(float(median([t.analysis.get("noise_floor_dbfs") for t in ts])), 1) if ts else None),
            "score": round(float(np.mean([t.quality.score for t in ts])), 1) if ts else None, "n": len(ts),
            "device": s.device_label if s else "", "voice_state": s.voice_state if s else "",
            "room_t60": s.room_t60 if s else None, "started_at": s.started_at if s else "",
        })
    out["quality"] = {"score_hist": score_hist, "mean": round(float(np.mean(scores)), 1) if scores else None,
                      "issues": [{"code": c, "label": issue_label[c], "count": n} for c, n in issue_counts.most_common(10)],
                      "sessions": sess_rows}

    # ------------------------------------------------------------------ consistency (anchors + spectrum per session)
    anchors = [t for t in approved if t.module == "J" and t.kind in SPEECH_KINDS]
    cons_sessions = []
    for sid in sorted({t.session_id for t in anchors}):
        ts = [t for t in anchors if t.session_id == sid]
        f0 = [_get(t, "f0") for t in ts if _get(t, "f0")]
        rt = [_get(t, "rate") for t in ts if _get(t, "rate")]
        s = sessions.get(sid)
        cons_sessions.append({"id": sid, "label": s.started_at[:10] if s else sid, "started_at": s.started_at if s else "", "f0": round(float(median(f0)), 1) if f0 else None,
                              "f0_lo": round(min(f0), 1) if f0 else None, "f0_hi": round(max(f0), 1) if f0 else None,
                              "rate": round(float(median(rt)), 2) if rt else None, "n": len(ts)})
    ltas_by_session: dict[str, list] = defaultdict(list)
    for t in [t for t in approved if t.kind in SPEECH_KINDS]:
        v = (t.analysis or {}).get("ltas") or []
        if len(v) == 19:
            ltas_by_session[t.session_id].append(v)
    spectra = {sid: np.mean(np.asarray(v), axis=0) for sid, v in ltas_by_session.items() if len(v) >= 2}
    mic_rows = []
    if len(spectra) >= 2:
        overall = np.mean(np.stack(list(spectra.values())), axis=0)
        for sid in sorted(spectra):
            s = sessions.get(sid)
            mic_rows.append({"id": sid, "label": s.started_at[:10] if s else sid, "started_at": s.started_at if s else "", "distance_db": round(float(np.sqrt(np.mean((spectra[sid] - overall) ** 2))), 2),
                             "device": s.device_label if s else ""})
    out["consistency"] = {"anchor_sessions": cons_sessions, "mic": mic_rows,
                          "f0_spread_st": round(float(12 * np.log2(max(r["f0"] for r in cons_sessions if r["f0"]) / min(r["f0"] for r in cons_sessions if r["f0"]))), 2)
                          if sum(1 for r in cons_sessions if r["f0"]) >= 2 else None}

    # ------------------------------------------------------------------ sustained vowels
    vq = []
    for t in [t for t in takes if t.kind == "sustained" and t.status != "rejected"]:
        q = (t.analysis or {}).get("voice_quality") or {}
        if q:
            vq.append({"id": t.id, "text": t.text.split("(")[0].strip(), "date": t.created_at[:10], "f0": _get(t, "f0"),
                       "jitter": q.get("jitter_local_pct"), "shimmer": q.get("shimmer_local_pct"), "hnr": q.get("hnr_db")})
    out["voice_quality"] = vq
    glides = [t for t in takes if t.kind == "glide" and t.status != "rejected" and (t.analysis.get("pitch") or {}).get("p5_hz")]
    out["range"] = [{"id": t.id, "date": t.created_at[:10], "low_hz": t.analysis["pitch"]["p5_hz"], "high_hz": t.analysis["pitch"]["p95_hz"],
                     "range_st": t.analysis["pitch"].get("range_st")} for t in glides]
    return out
