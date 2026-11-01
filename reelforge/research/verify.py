"""Mechanical fact verification.

The language model may propose claims, quotes and URLs, but nothing it says is trusted until
this module confirms it against the text we actually retrieved from the source:

1. quote check     - the supporting quote must appear in the source snapshot (exact, or fuzzy
                     >= 92% with every number in the quote present in the matched window)
2. number check    - every number in the claim must be backed by a number in its verified quotes
3. corroboration   - "verified" needs two independent (different registrable domain) sources, or
                     one primary source from a government / intergovernmental / academic /
                     company-official publisher; otherwise "single_source"
4. disputes        - claims marked disputed become "conflicting" and may only be used as disputed
"""

from __future__ import annotations

import csv
import fnmatch
import io
import re
import unicodedata
from pathlib import Path
from typing import Optional

from ..models import Claim, Research
from .credibility import STRONG_TIERS, is_tertiary, registrable_domain
from .fetch import read_snapshot

HEDGES = ("about", "around", "approximately", "roughly", "nearly", "almost", "over", "more than", "less than", "under",
          "up to", "at least", "some", "estimated", "an estimated", "~", "close to", "upwards of")
SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
         "trillion": 1e12, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7}
WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
            "hundred": 100, "dozen": 12, "half": 0.5, "double": 2, "twice": 2, "triple": 3}
_NUM_RE = re.compile(
    r"(?<![\w.])([-−–]?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|[-−–]?\d+(?:\.\d+)?)\s*(%|per\s?cent|percent|°\s?[CF]?)?\s*"
    r"(thousand|million|billion|trillion|lakhs?|lac|crores?|bn|mn|cr|k|m|b)?(?![\w])",
    re.I,
)


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("­", "")
    s = re.sub(r"[“”„‟″]", '"', s)
    s = re.sub(r"[‘’‚‛′`´]", "'", s)
    s = re.sub(r"[‐‑‒–—―−]", "-", s)
    s = re.sub(r"[*_#|>]+", " ", s)  # markdown/table artefacts from page extraction
    s = re.sub(r"\[(\d+|citation needed)\]", " ", s)  # wiki-style reference markers
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def extract_numbers(text: str) -> list[float]:
    vals: list[float] = []
    t = unicodedata.normalize("NFKC", text or "").replace("−", "-").replace("–", "-")
    for m in _NUM_RE.finditer(t):
        raw, unit, scale = m.group(1), (m.group(2) or ""), (m.group(3) or "")
        raw_clean = raw.replace(",", "")
        try:
            v = float(raw_clean)
        except ValueError:
            continue
        if scale:
            sc = scale.lower()
            if sc in ("m", "b", "k") and not unit:
                # single-letter scales are only trusted when glued to the number (e.g. "1.3m")
                if not re.search(re.escape(raw) + r"\s?" + re.escape(scale) + r"\b", t, re.I):
                    sc = ""
            v = v * SCALE.get(sc, 1.0)
        vals.append(v)
    return vals


def _close(a: float, b: float, tol: float) -> bool:
    if a == b:
        return True
    if a == 0 or b == 0:
        return abs(a - b) <= tol
    return abs(a - b) / max(abs(a), abs(b)) <= tol


def numbers_supported(statement: str, quotes: list[str]) -> tuple[bool, list[float]]:
    """Every number in the statement must match a number in at least one quote."""
    hedged = any(h in statement.lower() for h in HEDGES)
    tol = 0.03 if hedged else 0.006
    want = extract_numbers(statement)
    have: list[float] = []
    for q in quotes:
        have += extract_numbers(q)
    # allow sign-insensitive matches (e.g. "minus 18" vs "-18") and percentages vs fractions
    have_ext = have + [abs(x) for x in have] + [x * 100 for x in have if 0 < abs(x) < 1]
    missing = [w for w in want if not any(_close(abs(w), abs(h), tol) for h in have_ext)]
    return (len(missing) == 0), missing


def verify_quote(quote: str, snapshot_norm: str) -> tuple[str, float]:
    q = norm_text(quote)
    if len(q) < 12 or not snapshot_norm:
        return "not_found", 0.0
    if q in snapshot_norm:
        return "exact", 100.0
    try:
        from rapidfuzz import fuzz

        al = fuzz.partial_ratio_alignment(q, snapshot_norm, score_cutoff=88)
    except Exception:
        al = None
    if al is None:
        return "not_found", 0.0
    window = snapshot_norm[al.dest_start: al.dest_end]
    qn = extract_numbers(q)
    wn = extract_numbers(window)
    numbers_ok = all(any(_close(a, b, 0.0001) for b in wn) for a in qn)
    if al.score >= 92 and numbers_ok:
        return "fuzzy", round(al.score, 1)
    return "not_found", round(al.score, 1)


_CSV_CACHE: dict[str, list[dict]] = {}


def _csv_rows(text: str, key: str) -> list[dict]:
    if key not in _CSV_CACHE:
        try:
            _CSV_CACHE[key] = list(csv.DictReader(io.StringIO(text)))
        except csv.Error:
            _CSV_CACHE[key] = []
    return _CSV_CACHE[key]


def _row_match(row: dict, filters: dict) -> bool:
    return all(str(row.get(k, "")).strip() == str(v).strip() for k, v in (filters or {}).items())


def _excluded(row: dict, exclude_if: dict) -> bool:
    for col, patterns in (exclude_if or {}).items():
        val = str(row.get(col, "") or "").strip()
        for pat in patterns if isinstance(patterns, list) else [patterns]:
            if (pat == "" and val == "") or (pat and fnmatch.fnmatchcase(val, pat)):
                return True
    return False


def verify_data(spec: dict, raw_text: str, key: str) -> tuple[str, str]:
    """Recompute a value or ranking from a CSV snapshot. Returns (verification, rendered evidence)."""
    rows = _csv_rows(raw_text, key)
    col = spec.get("column", "")
    if not rows or col not in rows[0]:
        return "not_found", f"Column {col!r} not found in the dataset snapshot."
    kind = spec.get("type", "value")
    if kind == "value":
        filters = spec.get("filters", {})
        hits = [r for r in rows if _row_match(r, filters)]
        if len(hits) != 1 or not str(hits[0].get(col, "")).strip():
            return "not_found", f"No unique row with a value for {filters}."
        val = hits[0][col].strip()
        if "expected" in spec:
            try:
                if not _close(float(val), float(spec["expected"]), 1e-9):
                    return "not_found", f"Dataset has {val}, not {spec['expected']}."
            except ValueError:
                return "not_found", "Non-numeric value."
        where = ", ".join(f"{k}={v}" for k, v in filters.items())
        return "exact", f"Dataset row [{where}]: {col} = {val}"
    if kind == "rank":
        group, ent_col, ent = spec.get("group", {}), spec.get("entity_column", "country"), spec.get("entity", "")
        cand = []
        for r in rows:
            if not _row_match(r, group) or _excluded(r, spec.get("exclude_if", {})):
                continue
            try:
                cand.append((float(r[col]), r))
            except (TypeError, ValueError):
                continue
        cand.sort(key=lambda x: x[0], reverse=True)
        idx = next((i for i, (_, r) in enumerate(cand) if r.get(ent_col) == ent), None)
        if idx is None:
            return "not_found", f"{ent} not found among ranked rows."
        top = max(int(spec.get("top", idx + 1)), idx + 1)
        listing = "; ".join(f"{i + 1}. {r[ent_col]} = {r[col].strip()}" for i, (_, r) in enumerate(cand[:top]))
        where = ", ".join(f"{k}={v}" for k, v in group.items())
        return "exact", f"Ranking of {len(cand)} entities by {col} [{where}], aggregates excluded: {listing}. {ent} ranks #{idx + 1}."
    return "not_found", f"Unknown data evidence type {kind!r}."


def claim_status(claim: Claim, research: Research) -> tuple[str, str]:
    good = [e for e in claim.evidence if e.verification in ("exact", "fuzzy", "agent_attested")]
    if not good:
        return "unverified", "No supporting quote was found in the retrieved source text."
    ok, missing = numbers_supported(claim.statement, [e.quote for e in good])
    if not ok:
        return "unverified", f"Number(s) {', '.join(f'{m:g}' for m in missing)} in the claim are not in its verified quotes."
    if claim.certainty == "disputed":
        return "conflicting", "Sources disagree or the point is contested; present as disputed or leave out."
    domains: set[str] = set()
    strong_primary = False
    tertiary_only = True
    for e in good:
        src = research.source(e.source_id)
        if not src:
            continue
        if not is_tertiary(src.url):
            tertiary_only = False
            domains.add(registrable_domain(src.final_url or src.url))
        if src.primary and src.tier in STRONG_TIERS:
            strong_primary = True
    if tertiary_only:
        return "single_source", "Only supported by an encyclopaedia (tertiary source); find the primary source."
    if len(domains) >= 2:
        return "verified", f"Corroborated by {len(domains)} independent sources."
    if strong_primary:
        return "verified", "Stated by the primary/official source."
    return "single_source", "Only one independent source; corroborate or attribute it in the script."


def verify_research(research: Research, project_dir: Path) -> dict:
    snaps: dict[str, tuple[str, str, str]] = {}
    for s in research.sources:
        raw = read_snapshot(project_dir, s.snapshot_file)
        snaps[s.id] = (norm_text(raw) if len(raw) < 3_000_000 else "", s.snapshot_kind, raw)
    _CSV_CACHE.clear()
    stats = {"claims": len(research.claims), "verified": 0, "single_source": 0, "conflicting": 0, "unverified": 0}
    for c in research.claims:
        for e in c.evidence:
            snap, kind, raw = snaps.get(e.source_id, ("", "none", ""))
            if e.data:
                if kind != "raw_text":
                    e.verification, e.match_score = "unchecked", 0.0  # needs the full downloaded file
                    continue
                v, rendered = verify_data(e.data, raw, e.source_id)
                e.verification, e.match_score = v, (100.0 if v == "exact" else 0.0)  # type: ignore[assignment]
                if v == "exact":
                    e.quote = rendered
                continue
            v, score = verify_quote(e.quote, snap if snap else norm_text(raw))
            if v in ("exact", "fuzzy") and kind == "agent_excerpt":
                v = "agent_attested"
            e.verification, e.match_score = v, score  # type: ignore[assignment]
        c.numbers = [f"{x:g}" for x in extract_numbers(c.statement)]
        status, note = claim_status(c, research)
        if c.status != "excluded":
            c.status = status  # type: ignore[assignment]
        c.notes = note
        stats[status] = stats.get(status, 0) + 1
    verified = [c for c in research.claims if c.status == "verified"]
    usable = verified + [c for c in research.claims if c.status == "single_source"]
    if len(usable) < 4:
        research.sufficiency.enough = False
        research.sufficiency.reason = (
            f"Only {len(usable)} claim(s) could be checked against retrieved sources. "
            "That is not enough for an accurate reel; add sources or choose a narrower topic."
        )
    elif not verified and "single source" not in research.sufficiency.reason.lower():
        research.sufficiency.reason = (research.sufficiency.reason + " " if research.sufficiency.reason else "") + (
            "All usable claims rest on a single source, so the script must attribute them to that source.")
    return stats


def best_quote(claim: Claim) -> Optional[str]:
    for e in claim.evidence:
        if e.verification in ("exact", "fuzzy", "agent_attested"):
            return e.quote
    return None
