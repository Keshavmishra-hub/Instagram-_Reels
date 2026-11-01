"""Human-readable research file (research.md)."""

from __future__ import annotations

from ..models import Research

STATUS_LABEL = {
    "verified": "VERIFIED",
    "single_source": "SINGLE SOURCE - attribute or corroborate",
    "conflicting": "DISPUTED - do not state as fact",
    "unverified": "UNVERIFIED - do not use",
    "excluded": "EXCLUDED by editor",
}


def research_markdown(r: Research) -> str:
    out = [f"# Research: {r.topic}", ""]
    out += [f"- Compiled: {r.created_at}", f"- Method: {r.method}", f"- Language: {r.language}"]
    verified = sum(1 for c in r.claims if c.status == "verified")
    out += [f"- Claims: {len(r.claims)} total, {verified} verified", f"- Sources: {len(r.sources)}", ""]
    out += ["## Sufficiency", "", ("Enough reliable information: **yes**" if r.sufficiency.enough else "Enough reliable information: **NO**"), "", r.sufficiency.reason or "", ""]
    if r.summary:
        out += ["## Summary", "", r.summary, ""]
    if r.angles:
        out += ["## Story angles supported by the evidence", ""] + [f"- {a}" for a in r.angles] + [""]
    out += ["## Claims", ""]
    for status in ("verified", "single_source", "conflicting", "unverified", "excluded"):
        group = [c for c in r.claims if c.status == status]
        if not group:
            continue
        out += [f"### {STATUS_LABEL[status]} ({len(group)})", ""]
        for c in group:
            meta = [c.category, c.certainty]
            if c.as_of:
                meta.append(f"as of {c.as_of}")
            out.append(f"**{c.id}.** {c.statement}  ")
            out.append(f"_{' · '.join(meta)}_  ")
            if c.caveats:
                out.append(f"Caveat: {c.caveats}  ")
            for e in c.evidence:
                src = r.source(e.source_id)
                where = f"[{src.publisher or src.domain}]({src.url})" if src else e.source_id
                out.append(f"- {e.source_id} {where} - quote check: **{e.verification}**" + (f" ({e.match_score:.0f}%)" if e.verification == "fuzzy" else ""))
                out.append(f"  > {e.quote}")
            if c.notes:
                out.append(f"- Assessment: {c.notes}")
            out.append("")
    if r.uncertainties:
        out += ["## Disputed, outdated or uncertain points", ""] + [f"- {u}" for u in r.uncertainties] + [""]
    out += ["## Sources", "", "| ID | Publisher | Title | Tier | Primary | Accessed | Access | Snapshot |", "|---|---|---|---|---|---|---|---|"]
    for s in r.sources:
        title = (s.title or "").replace("|", "/")[:90]
        out.append(f"| {s.id} | {s.publisher} | [{title or s.url}]({s.url}) | {s.tier} | {'yes' if s.primary else 'no'} | {s.accessed_at[:10]} | {s.access_method} | {s.snapshot_kind} |")
    out.append("")
    if r.limitations:
        out += ["## Limitations", ""] + [f"- {x}" for x in r.limitations] + [""]
    out += [
        "## How to read this file",
        "",
        "- `exact` / `fuzzy`: the quote was found in text retrieved from the source (fuzzy = minor formatting differences, numbers identical).",
        "- `agent_attested`: the quote matches passages captured by the researcher (Claude Code WebFetch); the app could not independently re-download the page. Run `python -m reelforge verify-sources <project>` on a networked machine to upgrade it.",
        "- `not_found`: the quote could not be located; the claim cannot be used.",
        "",
    ]
    return "\n".join(out)
