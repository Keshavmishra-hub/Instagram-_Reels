---
name: reel-research
description: Research and fact-check a ReelForge project topic with web search, capturing verbatim quotes, then import it into the app. Use when the user asks to research a reel topic or runs /reel-research <project-id>.
---

# Research a ReelForge project (Claude Code mode)

Argument: a project id (folder name under `projects/`). Read `projects/<id>/project.json` for the topic,
language, style, audience and angle.

## Rules (non-negotiable)
- Never invent facts, statistics, dates, names, quotes or sources. Never cite a page you did not open.
- Prefer primary sources: government statistics/publications, intergovernmental organisations,
  peer-reviewed research, official company reports, the organisation that runs the thing described.
  Use established news organisations and reference works for corroboration and context.
- Corroborate every important claim with two independent sources, or the primary/official source.
- Separate established facts from estimates, projections and opinions; record disputes and as-of dates.
- If reliable information is insufficient, say so (`sufficiency.enough = false`) instead of building a story.

## Steps
1. Plan 4-8 search queries; use WebSearch, then open every page you will rely on with WebFetch
   (ask it to "copy verbatim the sentences about ..."). Search snippets are not evidence.
2. If you can also download the page with `curl -sL <url>` (works on a normal network), do it - the
   app will re-download every source anyway and check quotes against the full text.
3. Write `projects/<id>/inputs/research.json` (create the folder) in this format:

```json
{
  "summary": "...", "angles": ["..."], "uncertainties": ["..."], "limitations": ["..."],
  "sufficiency": {"enough": true, "reason": "..."},
  "sources": [
    {"id": "S1", "url": "https://...", "title": "...", "publisher": "...", "published": "2025-11-26",
     "tier": "government|intergovernmental|academic|company_official|news|reference|industry|ngo|other",
     "primary": true, "accessed_at": "2026-11-01T10:00:00Z", "access_method": "claude_code_webfetch",
     "excerpt": "Verbatim passages you read on the page (every quote you use must be inside this text)."}
  ],
  "claims": [
    {"statement": "Plain-language fact with units and year", "category": "statistic|date|event|person|place|definition|quote|process|other",
     "certainty": "established|estimate|disputed|opinion|uncertain", "as_of": "2024-25", "caveats": "...",
     "evidence": [{"source_id": "S1", "quote": "exact sentence copied from the page"}]}
  ]
}
```

   For CSV datasets use tabular evidence instead of a quote - the app recomputes it from the file:
   `{"source_id": "S1", "data": {"type": "value", "filters": {"country": "India", "year": "2025"}, "column": "solar_electricity"}}`
   or a ranking: `{"type": "rank", "group": {"year": "2025"}, "column": "...", "entity_column": "country", "entity": "India", "exclude_if": {"iso_code": ["", "OWID_*"]}, "top": 3}`.

4. Import and verify: `python -m reelforge import-research <id> projects/<id>/inputs/research.json`
   The app downloads each source, checks every quote/number mechanically, and writes
   `projects/<id>/research.md`. Read it. Fix or drop any claim marked `not_found`/`unverified`.
5. Report to the user: counts of verified / single-source / unverified claims, disputes, and whether the
   research is sufficient. Do not approve it yourself unless the user asked you to; they review it in the UI
   (Research tab) or run `python -m reelforge approve research <id>`.
