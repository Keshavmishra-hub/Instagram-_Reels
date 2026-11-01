---
name: reel-storyboard
description: Plan the visual storyboard (what the viewer sees for each sentence) for a ReelForge project and import it. Use when the user asks for a storyboard or runs /reel-storyboard <project-id>.
---

# Plan a ReelForge storyboard (Claude Code mode)

Argument: project id. Read `projects/<id>/script.json` and `research.json`. It must not look like a slideshow:
every scene needs a visual purpose and motion, the visual should change every ~3-4 s, open on the strongest image.

Scene kinds and params (see `reelforge/llm/prompts.py` STORYBOARD_SYSTEM for the full list):
- `footage` / `photo`: `queries` = 2-4 concrete filmable stock searches; authenticity `representative`
  (or `documentary` only if it shows the exact subject). The app labels these on screen.
- `map`: `{"center":[lon,lat],"zoom":1-40,"highlight":["Country"],"marker":{"lon":..,"lat":..,"label":"..","sublabel":".."},"routes":[[[lon,lat],[lon,lat]]],"title":".."}`
- `stat`: `{"value":9.4,"decimals":1,"prefix":"","suffix":"%","unit":"million","label":"..","sublabel":"..","kicker":".."}`
- `chart`: `{"type":"line"|"bar","title":"..","unit":"..","decimals":0,"highlight":2,"data":[{"label":"2015","value":7.09}]}`
- `timeline`: `{"events":[{"label":"2008","text":".."}]}`; `comparison`: `{"title":"..","left":{"label","value","note"},"right":{...}}`
- `kinetic`: `{"text":"max 7 words","highlight":["word"],"kicker":".."}`; `icon`: `{"icons":["lucide-name"],"label":"..","caption":".."}`
  (icon names: files in `renderer/node_modules/lucide-static/icons/`); `quote`: verbatim quotes from the claims only.

Every number shown on screen must come from the claims cited by that scene's beats - the importer rejects
anything else. Optional per scene: `background_queries`, `overlays` (`{"kind":"stat","text":"..","at_word":N}`),
`transition` (cut|fade|slide_up|slide_left|zoom|whip|wipe), `subtitle_position` (lower|upper|center), `sfx`.

Write `projects/<id>/inputs/storyboard.json`:
```json
{"music_mood": "curious|uplifting|tense|epic|calm",
 "cover": {"headline": "3-6 words", "highlight": "word", "kicker": "..", "beat_id": "B4"},
 "scenes": [{"beat_ids": ["B1"], "transition": "cut", "subtitle_position": "lower",
             "visual": {"kind": "map", "purpose": "..", "authenticity": "generated_graphic", "params": {...}}}]}
```
Run `python -m reelforge import-storyboard <id> projects/<id>/inputs/storyboard.json` and fix all errors.
Then `python -m reelforge voice <id>` and `python -m reelforge stills <id>`; look at the stills in
`projects/<id>/render/stills/` and fix layout problems before the full render.
