"""Deterministic script checks: grounding, integrity language, structure, length, spelling."""

from __future__ import annotations

import re
from typing import Optional

from ..models import Research, Script, ScriptIssue
from ..research.verify import extract_numbers, numbers_supported

GENERIC_OPENERS = ("hello", "hi guys", "hey guys", "welcome back", "welcome to", "in this video", "today we", "today i", "namaste doston")
CLICKBAIT = (
    "you won't believe", "shocking", "mind-blowing", "mind blowing", "nobody knows", "nobody is talking about",
    "they don't want you to know", "100% true", "will blow your mind", "secret they", "jaw-dropping", "insane",
    "the truth about", "exposed", "destroyed", "never before seen", "the only video you need", "you need to see this",
)
ATTRIBUTION = ("according to", "says", "said", "reported", "reports", "estimates", "estimated", "claims", "per ", "data from",
               "compiled by", "figures from", "published by", "source:")
DISPUTE_WORDS = ("disputed", "debated", "contested", "unclear", "estimates vary", "some say", "may", "might", "possibly", "reportedly")
WPS = {"en": 2.55, "hi": 2.35, "es": 2.6, "fr": 2.5, "pt": 2.5, "it": 2.5, "de": 2.3}


def estimated_seconds(script: Script) -> float:
    words = len(script.full_text().split())
    wps = WPS.get(script.language, 2.4)
    return words / wps + 0.27 * len(script.beats) + 1.6


def _has_factual_content(text: str) -> bool:
    if extract_numbers(text):
        return True
    # capitalised words after the first word suggest names/places
    caps = [w for w in re.findall(r"\b[A-Z][a-zA-Z]+", text)[1:]]
    return len(caps) >= 1


def _spellcheck(script: Script, research: Optional[Research]) -> list[ScriptIssue]:
    if script.language != "en":
        return []
    try:
        from spellchecker import SpellChecker
    except Exception:
        return []
    sp = SpellChecker()
    known: set[str] = set()
    if research:
        blob = " ".join([c.statement for c in research.claims] + [e.quote for c in research.claims for e in c.evidence]
                        + [s.publisher + " " + s.title for s in research.sources])
        known |= {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'’-]+", blob)}
    issues = []
    for b in script.beats:
        for raw in re.findall(r"[A-Za-z][A-Za-z'’-]+", b.text):
            w = raw.lower().strip("'’-")
            if len(w) < 3 or w in known or raw[0].isupper():
                continue
            parts = re.split(r"[-'’]", w)
            if all(p in sp or not p for p in parts):
                continue
            suggestion = sp.correction(w)
            if suggestion and suggestion != w:
                issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="spelling", message=f"Possible misspelling: '{raw}' (did you mean '{suggestion}'?)"))
    return issues


def validate_script(script: Script, research: Optional[Research], target_seconds: int) -> list[ScriptIssue]:
    issues: list[ScriptIssue] = []
    if not script.beats:
        return [ScriptIssue(severity="error", code="empty", message="The script has no beats.")]
    claims = {c.id: c for c in research.claims} if research else {}

    first = script.beats[0]
    if first.section != "hook":
        issues.append(ScriptIssue(beat_id=first.id, severity="warning", code="hook_missing", message="The first beat should be the hook."))
    if len(first.text.split()) > 16:
        issues.append(ScriptIssue(beat_id=first.id, severity="warning", code="hook_long", message="Hook is long; the first line should land within ~3 seconds (max ~14 words)."))
    if first.text.lower().startswith(GENERIC_OPENERS):
        issues.append(ScriptIssue(beat_id=first.id, severity="error", code="generic_intro", message="Generic introduction; open with the hook itself."))
    if not script.beats[-1].text.strip().endswith("?") and not (script.cta_question or "").strip():
        issues.append(ScriptIssue(beat_id=script.beats[-1].id, severity="warning", code="no_question", message="End with a natural, relevant question."))
    sections = [b.section for b in script.beats]
    if "payoff" not in sections:
        issues.append(ScriptIssue(severity="warning", code="payoff_missing", message="No payoff beat: make sure the hook's promise is delivered."))

    # attribution is established once per publisher (journalistic norm), anywhere in the script
    attributed: set[str] = set()
    if research:
        for b in script.beats:
            if any(w in b.text.lower() for w in ATTRIBUTION):
                for cid in b.claim_ids:
                    c = claims.get(cid)
                    for e in (c.evidence if c else []):
                        src = research.source(e.source_id)
                        if src:
                            attributed.add((src.publisher or src.domain).lower())

    def _publishers(c) -> set[str]:
        out = set()
        for e in c.evidence:
            src = research.source(e.source_id) if research else None
            if src:
                out.add((src.publisher or src.domain).lower())
        return out

    seen_texts: set[str] = set()
    for b in script.beats:
        t = b.text.strip()
        low = t.lower()
        if re.search(r"\b(\w+)\s+\1\b", low):
            issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="repeated_word", message="Repeated word."))
        if low in seen_texts:
            issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="duplicate", message="Duplicate sentence."))
        seen_texts.add(low)
        for phrase in CLICKBAIT:
            if phrase in low:
                issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="clickbait", message=f"Avoid hype/clickbait phrasing: '{phrase}'."))
        if len(t.split()) > 26:
            issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="long_sentence", message="Long sentence; split it for the ear (<= 18 words)."))
        factual = _has_factual_content(t)
        if not b.claim_ids:
            if factual and b.section != "ending":
                issues.append(ScriptIssue(beat_id=b.id, severity="error", code="uncited", message="Factual sentence without a cited claim."))
            continue
        cited = [claims.get(cid) for cid in b.claim_ids]
        missing = [cid for cid, c in zip(b.claim_ids, cited) if c is None]
        if missing:
            issues.append(ScriptIssue(beat_id=b.id, severity="error", code="unknown_claim", message=f"Cites unknown claim(s): {', '.join(missing)}."))
        cited = [c for c in cited if c is not None]
        for c in cited:
            if c.status in ("unverified", "excluded") or not c.use_in_script:
                issues.append(ScriptIssue(beat_id=b.id, severity="error", code="unverified_claim", message=f"{c.id} is {c.status}; it cannot be stated as fact."))
            elif c.status == "conflicting" and not any(w in low for w in DISPUTE_WORDS):
                issues.append(ScriptIssue(beat_id=b.id, severity="error", code="dispute_as_fact", message=f"{c.id} is disputed; present it as disputed or remove it."))
            elif c.status == "single_source" and not any(w in low for w in ATTRIBUTION) and not (_publishers(c) & attributed):
                issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="single_source", message=f"{c.id} rests on one source; attribute it (\"According to ...\") or corroborate it."))
            if c.certainty == "estimate" and not any(w in low for w in ("about", "around", "estimate", "roughly", "nearly", "almost", "approximately", "more than", "over", "some")):
                issues.append(ScriptIssue(beat_id=b.id, severity="warning", code="estimate_as_exact", message=f"{c.id} is an estimate; signal it (\"about\", \"an estimated\")."))
        support = [c.statement for c in cited] + [e.quote for c in cited for e in c.evidence if e.verification in ("exact", "fuzzy", "agent_attested")]
        ok, miss = numbers_supported(t, support)
        if not ok:
            issues.append(ScriptIssue(beat_id=b.id, severity="error", code="number_unsupported",
                                      message=f"Number(s) {', '.join(f'{m:g}' for m in miss)} are not in the cited claims."))
    est = estimated_seconds(script)
    if est > target_seconds * 1.18:
        issues.append(ScriptIssue(severity="warning", code="too_long", message=f"Estimated {est:.0f}s for a {target_seconds}s target; tighten the script."))
    elif est < target_seconds * 0.6:
        issues.append(ScriptIssue(severity="info", code="short", message=f"Estimated {est:.0f}s for a {target_seconds}s target."))
    issues += _spellcheck(script, research)
    return issues


def has_errors(issues: list[ScriptIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
