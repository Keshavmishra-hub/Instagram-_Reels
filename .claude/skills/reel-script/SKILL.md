---
name: reel-script
description: Write the narration script for a ReelForge project from its verified claims and import it for validation. Use when the user asks to write/rewrite a reel script or runs /reel-script <project-id>.
---

# Write a ReelForge script (Claude Code mode)

Argument: project id. Read `projects/<id>/project.json` (duration, style, language, audience, angle) and
`projects/<id>/research.json` (claims with status). Style guidance lives in `reelforge/styles.py`.

## Structure (each beat = one spoken sentence, 6-18 words)
- `hook` (one beat, max ~12 words, lands in the first 1-3 s): a surprising verified fact, sharp question,
  unusual comparison or compelling statement. No "Hello everyone", no "In this video".
- `context`: what it is and why it matters, fast.
- `story`: logical sequence of verified details; concrete numbers, examples, comparisons; no repetition.
- `payoff`: the most interesting fact; it must fulfil the hook's promise.
- `ending`: memorable close with needed context, then a natural question (also put it in `cta_question`).

Target ~2.4 spoken words per second of duration (45 s -> ~95-105 words).

## Integrity
- Cite claim IDs on every factual beat. Use only `verified` claims as plain fact. A `single_source` claim needs
  attribution somewhere in the script ("according to ...", "data from ..."). Never state `conflicting` or
  `unverified` claims as fact.
- Numbers must match the claims (or be rounded with "about"/"more than"). Keep units and years. Write numbers as
  digits. Estimates must sound like estimates. Keep context that a statistic needs (e.g. what still dominates).
- No clickbait, no hype, no invented quotes.

## Output
Write `projects/<id>/inputs/script.json`:
```json
{"title": "...", "hook_type": "...", "cta_question": "...",
 "beats": [{"section": "hook", "text": "...", "claim_ids": ["C1"], "emphasis": ["two"], "on_screen_text": "optional <= 7 words"}]}
```
Then run `python -m reelforge import-script <id> projects/<id>/inputs/script.json` and fix every `[error]`
it prints (re-run until clean). Report warnings to the user. Approval is the user's decision
(UI Script tab or `python -m reelforge approve script <id>`).
