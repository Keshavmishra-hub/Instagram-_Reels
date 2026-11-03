"""Adaptive curriculum: decide what to record next.

1. Session warm-up (once per session): room tone, microphone check, consent (once ever), and two
   consistency anchors (Module J), rotating so every anchor is repeated across sessions.
2. Identity first: until Module A's core is mostly approved, only Module A is offered.
3. Adaptive: every remaining exercise is scored by how much it would fill current gaps: language
   minutes, phonemes and diphones still under target, emotions and narration genres still thin,
   unfinished core exercises. This is greedy coverage selection, the classic method for designing
   TTS recording scripts. A small flow/variety term keeps related exercises together without
   letting one module dominate a session.
4. When the bank cannot fill a gap, number/date/currency exercises are generated; for other gaps
   the studio asks for new material (Curriculum → Need more material).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from ..coverage import GENRES, Coverage, needs
from ..models import EMOTIONS, STYLES, Exercise, Take
from ..text.phonemes import PHONEME_LABELS, diphones
from .bank import ExerciseBank


@dataclass
class Pick:
    exercise: Optional[Exercise]
    phase: str  # warmup | identity | adaptive | module | generated | done
    reason: str
    factors: list[str] = field(default_factory=list)


LANG_NAMES = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}


def _status_by_exercise(takes: list[Take]) -> dict[str, set]:
    st: dict[str, set] = {}
    for t in takes:
        if not t.trashed:
            st.setdefault(t.exercise_id, set()).add(t.status)
    return st


def plan_next(bank: ExerciseBank, takes: list[Take], sessions: list, session, *, warmup: bool = True,
              mode: str = "adaptive", speaker_name: str = "", exclude: tuple = (), cov: Optional[Coverage] = None) -> Pick:
    takes = [t for t in takes if not t.trashed]
    status = _status_by_exercise(takes)
    this_session = [t for t in takes if session is not None and t.session_id == session.id]
    in_session = {t.exercise_id for t in this_session}
    skipped = set(session.skipped if session is not None else []) | set(exclude)

    # ---------------------------------------------------------------- 1. warm-up
    if warmup and session is not None:
        reasons = {"S-ROOM-01": "Measures your room noise before anything else.", "S-CLAP-01": "Measures how echoey your room is.",
                   "S-MIC-01": "Checks level, noise and mic quality for this session."}
        for eid in ("S-ROOM-01", "S-CLAP-01", "S-MIC-01"):
            if eid not in in_session and eid not in skipped and bank.get(eid):
                why = reasons[eid]
                return Pick(bank.get(eid), "warmup", why)
        if speaker_name.strip():
            for eid in ("S-CONSENT-01", "S-CONSENT-02"):
                if bank.get(eid) and not (status.get(eid, set()) & {"approved", "pending"}) and eid not in skipped:
                    return Pick(bank.get(eid), "warmup", "Documents that this voice is yours and recorded by choice (once).")
        anchors = [e for e in bank.exercises if e.module == "J" and e.repeat == "per_session"]
        done_here = [e for e in anchors if e.id in in_session]
        if anchors and len(done_here) < 2:
            sess_count = Counter()
            for t in takes:
                if t.module == "J" and t.status != "rejected":
                    sess_count[(t.exercise_id, t.session_id)] += 1
            per_anchor = Counter(eid for (eid, _sid) in sess_count)
            todo = [e for e in anchors if e.id not in in_session and e.id not in skipped]
            if todo:
                todo.sort(key=lambda e: (per_anchor.get(e.id, 0), e.order))
                pick = todo[0]
                n = per_anchor.get(pick.id, 0)
                return Pick(pick, "warmup", f"Consistency anchor: repeated across sessions to measure natural variation (recorded in {n} session{'s' if n != 1 else ''} so far).")

    cov = cov or Coverage(bank, takes, sessions)

    def available(e: Exercise) -> bool:
        st = status.get(e.id, set())
        return (e.module not in ("S", "J") and e.id not in skipped and not (st & {"approved", "pending"}))

    # ---------------------------------------------------------------- 2. module mode
    if mode.startswith("module:"):
        mid = mode.split(":", 1)[1]
        cands = [e for e in bank.exercises if e.module == mid and available(e)]
        cands.sort(key=lambda e: (not e.core, e.order))
        if not cands:
            return Pick(None, "done", f"Every exercise in this module is recorded or waiting for review. Switch to adaptive mode for what the dataset needs next.")
        e = cands[0]
        return Pick(e, "module", f"Next {'core' if e.core else 'extended'} exercise in {e.section_title}.")

    # ---------------------------------------------------------------- 3. identity gate
    a_core = [e for e in bank.exercises if e.module == "A" and e.core]
    a_done = sum(1 for e in a_core if "approved" in status.get(e.id, set()))
    a_open = [e for e in a_core if available(e)]
    if a_core and a_done < 0.8 * len(a_core) and a_open:
        a_open.sort(key=lambda e: e.order)
        e = a_open[0]
        return Pick(e, "identity", f"Building your voice identity first: {a_done} of {len(a_core)} core Module A exercises approved.",
                    [e.section_title])

    # ---------------------------------------------------------------- 4. adaptive scoring
    nd = needs(cov)
    module_core_left = Counter(e.module for e in bank.exercises if e.core and available(e))
    recent = [t for t in sorted(this_session, key=lambda t: t.id)][-8:]
    last_section = recent[-1].section if recent else ""
    section_run = 0
    for t in reversed(recent):
        if t.section != last_section:
            break
        section_run += 1
    last_module = recent[-1].module if recent else ""
    module_run = 0
    for t in reversed(recent):
        if t.module != last_module:
            break
        module_run += 1

    best = None
    for e in bank.exercises:
        if not available(e) or not e.train:
            continue
        info = bank.derived(e)
        factors: list[tuple[float, str]] = []
        s = 0.0
        if e.core and module_core_left.get(e.module):
            s += 1.6
            factors.append((1.6, f"Core exercise · {e.section_title}"))
        ln = nd["lang"].get(e.lang, 0.0)
        if ln > 0:
            v = 1.6 * ln
            s += v
            factors.append((v, f"{LANG_NAMES.get(e.lang, e.lang)} needs more minutes ({cov.lang_seconds.get(e.lang, 0) / 60:.1f} min so far)"))
        if e.emotion != "neutral":
            v = 1.8 * nd["emotion"].get(e.emotion, 0.0)
            s += v
            if v > 0:
                factors.append((v, f"Emotion: {EMOTIONS[e.emotion]} ({cov.emotion_counts.get(e.emotion, 0)} takes so far)"))
        if e.style in GENRES:
            v = 1.4 * nd["genre"].get(e.style, 0.0)
            s += v
            if v > 0:
                factors.append((v, f"Genre: {STYLES[e.style]} ({cov.style_counts.get(e.style, 0)} takes so far)"))
        gains = []
        for seq, need_key in ((info.en_phonemes, "en_ph"), (info.hi_phonemes, "hi_ph")):
            for p, n in Counter(seq).items():
                w = nd[need_key].get(p, 0.0) * min(n, 3)
                if w > 0:
                    gains.append((w, p))
        g = min(1.5, sum(w for w, _ in gains) / 12.0)
        if g > 0:
            s += 1.3 * g
            top = [p for _w, p in sorted(gains, reverse=True)[:3]]
            factors.append((1.3 * g, "Sounds still needed: " + ", ".join(
                f"/{p}/ {PHONEME_LABELS[p]}" if p in PHONEME_LABELS else f"/{p}/" for p in top)))
        di = set(diphones(info.en_phonemes)) - nd["en_di"] | set(diphones(info.hi_phonemes)) - nd["hi_di"]
        total_di = len(set(diphones(info.en_phonemes)) | set(diphones(info.hi_phonemes)))
        if total_di:
            v = 0.8 * len(di) / total_di
            s += v
            if v > 0.3:
                factors.append((v, f"{len(di)} new sound combinations"))
        if e.kind == "prompt":
            s += 0.25
        if "rejected" in status.get(e.id, set()):
            s -= 0.3
        if e.section == last_section and section_run < 4:
            s += 0.45  # keep related exercises together
        elif e.section == last_section:
            s -= 0.6
        if e.module == last_module and module_run >= 8:
            s -= 0.8  # don't let one module take over a session
        if best is None or s > best[0] + 1e-9:
            best = (s, e, factors)

    if best is not None:
        _s, e, factors = best
        factors.sort(key=lambda f: -f[0])
        reason = factors[0][1] if factors else "Rounds out your dataset."
        return Pick(e, "adaptive", reason, [f[1] for f in factors[:4]])

    # ---------------------------------------------------------------- 5. generated material
    from .generators import next_generated

    gen = next_generated(takes)
    if gen is not None:
        return Pick(gen, "generated", "Fresh numbers, dates and amounts (generated) keep improving how your voice reads figures.")
    return Pick(None, "done", "The built-in curriculum is complete. Check the dashboard for remaining gaps and add new material from the Curriculum page.")
