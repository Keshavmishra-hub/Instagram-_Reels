# Sample reel: "India's solar surge, in numbers"

Produced end-to-end by ReelForge in its build environment (Claude Code mode: Claude Code did the research,
writing and storyboard; the app did verification, narration, rendering, packaging and QC).

| | |
|---|---|
| Video | `output/reel.mp4` — 42.7 s, 1080 × 1920, 30 fps, H.264 High + AAC 48 kHz stereo, −14.1 LUFS, −1.4 dBTP |
| Cover | `output/cover.jpg` (+ `cover_grid_preview.jpg`, the 3:4 profile-grid crop) |
| Publishing | `output/caption.txt` (with sources + 5 hashtags), `pinned_comment.txt`, `captions.srt/.vtt`, `instagram.json` |
| Research | `research.md` / `research.json`, `output/sources.md`, `source_snapshots/` |
| Script & plan | `script.md` / `script.json`, `storyboard.json`, `timeline.json` (word-level timings) |
| QC | `output/qc_report.md` — **PASSED**, 2 warnings (below) |
| Inputs | `inputs/` — the research/script/storyboard files exactly as Claude Code wrote them |

## How it was made

```bash
python -m reelforge new "India's solar power surge, 2015-2025" --style science --duration 45 --voice af_heart --music uplifting
python -m reelforge import-research <id> samples/india-solar-surge/inputs/research.json
python -m reelforge approve research <id>
python -m reelforge import-script <id> samples/india-solar-surge/inputs/script.json
python -m reelforge approve script <id>
python -m reelforge import-storyboard <id> samples/india-solar-surge/inputs/storyboard.json
python -m reelforge produce <id>        # voice → media → render → caption → QC (≈ 4 min on 4 CPU cores)
```

## Why this topic, and what the evidence is

The build environment's network policy only allowed GitHub-hosted files: news sites, government portals
(pib.gov.in, nddb.coop), Wikipedia, Ember and the stock-media APIs were all blocked — for the app *and* for
Claude Code's own web fetch. The first topic considered (Operation Flood / India's milk production) was dropped
because its primary sources could not be opened, and the integrity rules forbid citing a page that was not read.

Our World in Data publishes its energy dataset (electricity figures from Ember's Yearly Electricity Data 2026 and
the Energy Institute's Statistical Review 2025) on GitHub, so the app could download it and check every figure
itself:

| Claim used | Value in the dataset |
|---|---|
| India's rank in solar generation, 2025 (countries only) | #3 of 90 — China 1174.96 TWh, United States 388.82 TWh, India 195.99 TWh |
| Solar share of India's electricity, 2015 → 2025 | 0.541 % → 9.415 % |
| India's solar generation 2015 / 2017 / 2020 / 2022 / 2025 | 7.09 / 22.36 / 52.91 / 95.92 / 195.99 TWh |
| Coal share / all-renewables share, 2025 | 70.818 % / 24.067 % |

The 9.2 MB dataset snapshot is not committed (SHA-256 `266f2e2baad7975351bc9bb4aa061d22b1da9fe4c47d51d2ac6071e01e171f76`
of `owid-energy-data.csv` as downloaded on 2026-11-01); the codebook and README snapshots are in `source_snapshots/`.
Values for 2018 and 2019 were deliberately not used: the legacy file reports an identical 37.45 TWh for both years,
which looks like a data artefact.

## The two QC warnings

1. **Single source.** All ten claims come from one compiled dataset, so they are `single_source`, not
   independently corroborated. The narration attributes them ("That's 2025 data from Ember, compiled by Our World in
   Data"), every data scene carries a source tag, and the caption lists the files. On a normal network, add Ember's
   own release or a government source and the claims become `verified`.
2. **No stock footage.** Two scenes asked for real solar-farm footage; with the stock APIs blocked they fell back to
   motion graphics, so this sample is graphics-only (globe map, counters, line and bar charts, comparison, icons).
   With `PEXELS_API_KEY`/`PIXABAY_API_KEY` on a normal network those scenes get licensed, labelled footage.

Everything else passed: independent speech recognition put the subtitles within a median 71 ms of the spoken words,
97 % of words were recognised as written, the file decodes to exactly 1280 frames with no black or frozen segments,
and every on-screen number is traced to a verified claim.
