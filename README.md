# ReelForge — research-first Instagram Reel studio

ReelForge turns a topic into a finished, fact-checked Instagram Reel:

```
Topic → Research → Fact verification → Script → Storyboard → Voice-over → Visuals
      → Subtitles → Edit / render → Quality check → Instagram-ready MP4 + cover + caption + sources
```

It is built around one rule: **never sacrifice truth for virality**. A language model may *propose* facts, but
nothing reaches the script until the app has checked it against the text it actually downloaded from the source.
Every on-screen number must trace back to a verified claim, every source is snapshotted, and a reel is only marked
complete when no critical quality check fails.

| | |
|---|---|
| Output | 1080 × 1920, 30 fps CFR, H.264 High / yuv420p, AAC-LC 48 kHz stereo, MP4 with faststart, −14 LUFS |
| Narration | Local neural TTS (Kokoro-82M, free) with **exact word timings**, or Azure / ElevenLabs / OpenAI voices |
| Visuals | Pexels, Pixabay, Wikimedia Commons, NASA (licence + attribution tracked) and generated motion graphics: animated globe maps, charts, counters, timelines, comparisons, kinetic type |
| Subtitles | Word-synchronised, keyword highlighting, safe-zone placement; SRT/VTT export |
| Music | Original score composed per reel (no licensing issues) with side-chain ducking, or your own licensed track |
| QC | 22 automatic checks incl. independent speech recognition for sync, full decode, black frames, loudness, licensing |

---

## Quick start

Requirements: Python 3.10+, Node.js 18+, FFmpeg. macOS or Linux (Windows: WSL2).

```bash
git clone <this repo> && cd Instagram-_Reels
./setup.sh            # Python venv, Remotion renderer, local voice model (~350 MB)
./setup.sh --asr      # optional: + offline speech recogniser for the sync/pronunciation QC (~460 MB)
. .venv/bin/activate
python -m reelforge serve          # → http://127.0.0.1:8000
```

`python -m reelforge doctor` shows which integrations are active.

## Three ways to drive it

The research, script and storyboard steps need a capable language model. Pick whichever suits you — all three
produce the same files and go through the same mechanical verification.

1. **Claude API (fully automatic).** Put `ANTHROPIC_API_KEY` in `.env`. Research uses Claude's server-side
   `web_search` and `web_fetch` tools; the text of every page Claude reads comes back to the app and is stored as a
   source snapshot. Then `python -m reelforge make "your topic" --style agriculture --duration 45` runs everything,
   or use the web studio and approve each step. Typical cost on Claude Opus 5.5: roughly US$1 per reel
   (set `REELFORGE_MODEL=claude-sonnet-5-5` to roughly halve it).
2. **Claude Code (no API key).** Open Claude Code in this folder. The project ships skills in `.claude/skills/`:
   `/reel-make <topic>`, or step by step `/reel-research <project-id>`, `/reel-script <project-id>`,
   `/reel-storyboard <project-id>`. Claude Code researches with its own web tools, writes JSON in the app's format and
   imports it with `python -m reelforge import-…`; the app re-downloads every source and verifies every quote.
3. **Manual.** In the Research tab add source URLs (the app downloads them; inaccessible sources are refused) and
   claims with verbatim quotes; write the script in the Script tab. The storyboard has a rule-based planner.

## API keys (all optional)

| Key | What it enables | Where to get it | Cost |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | automatic research, script, storyboard, captions | console.anthropic.com → API Keys | pay-as-you-go |
| `PEXELS_API_KEY` | stock video + photos | pexels.com/api | free |
| `PIXABAY_API_KEY` | stock video + photos | pixabay.com/api/docs | free |
| — | Wikimedia Commons, NASA images | no key needed | free |
| `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | neural voices incl. Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Punjabi | Azure portal → Speech service | free tier ≈ 0.5M chars/month |
| `ELEVENLABS_API_KEY` | premium voices with built-in word timings | elevenlabs.io → API keys | paid (free tier is non-commercial) |
| `OPENAI_API_KEY` | `gpt-4o-mini-tts` voices | platform.openai.com | low cost |

Copy `.env.example` to `.env` and fill in what you have. Secrets are only read from the environment.

## The studio (web UI)

1. **New reel** — topic, language (15), duration (30–90 s), one of 10 storytelling styles, voice provider/voice/pace/tone,
   brand kit, music mood, audience and angle.
2. **Research** — run research (or import), then review: sufficiency verdict, summary, story angles, every claim with
   its status, evidence quotes and source links, source tiers and snapshots. Exclude claims, add sources/claims,
   re-check sources, then **Approve research**.
3. **Script** — generate or write beats (hook / context / story / payoff / ending), each citing claim IDs. Validation
   runs on save: uncited facts, numbers not in the claims, unverified or disputed claims stated as fact, missing
   attribution for single-source claims, generic intros, clickbait, length, spelling. **Approve script** is blocked
   while errors remain.
4. **Storyboard** — scene cards with the narration, visual type, purpose, stock queries, parameters (JSON), transition,
   media alternatives (swap), per-scene **Regenerate** with an instruction ("use a map instead") and per-scene low-res
   **Preview**. Generate the voice-over, find stock media and render storyboard stills here.
5. **Produce** — one click: voice-over → media → render → caption → QC, with live progress and logs. Upload your own
   licensed footage or music here.
6. **Publish** — player, cover (and 3:4 grid preview), downloads (MP4, cover, SRT/VTT, research, sources, credits, ZIP),
   caption with sources and hashtags, pinned comment, CTA, alt text, and the full QC report.

## Command line

```bash
python -m reelforge new "topic" --style science --duration 45 --lang en --voice af_heart
python -m reelforge research <id>            # Claude API
python -m reelforge import-research <id> file.json   # Claude Code / manual
python -m reelforge verify-sources <id>      # re-download sources, re-check every quote
python -m reelforge approve research <id>
python -m reelforge script <id> | import-script <id> file.json ; approve script <id>
python -m reelforge storyboard <id> | import-storyboard <id> file.json
python -m reelforge stills <id>              # storyboard frames before the full render
python -m reelforge preview <id> SC3         # low-res preview of one scene
python -m reelforge produce <id>             # voice → assets → render → package → qc (exit 2 if QC fails)
python -m reelforge make "topic" ...         # everything, automatic (needs ANTHROPIC_API_KEY)
python -m reelforge serve | list | status <id> | doctor | setup-models [--asr]
```

## How accuracy is enforced

| Safeguard | Mechanism |
|---|---|
| No phantom sources | A URL can only become a source if its content was retrieved (by Claude's `web_fetch` or by the app). Evidence pointing at a page that was never opened is dropped. Each source keeps a text snapshot (`projects/<id>/sources/`) with its SHA-256 and access time. |
| No invented quotes | Every quote must be found in the snapshot: exact, or fuzzy ≥ 92 % **with every number identical** (a quote whose number was changed is rejected even at 98 % similarity). |
| No inflated numbers | Every number in a claim must appear in its verified quotes (±0.6 %, or ±3 % with "about/nearly/more than"). The script validator applies the same test to every sentence, and the storyboard validator to every number shown on screen (charts, counters, comparisons, timelines, callouts). |
| Datasets | CSV evidence is verified by recomputing the value or ranking from the downloaded file (`{"type": "value" | "rank", ...}`). |
| Independent corroboration | `verified` = two independent domains, or one primary government/intergovernmental/academic/company source. Otherwise `single_source` (must be attributed in the narration), `conflicting` (only as a dispute) or `unverified` (unusable). Encyclopaedias alone never verify a claim. |
| Honest framing | Estimates must be hedged, disputes presented as disputes, context kept (the validator and prompts both enforce this); clickbait phrasing is flagged. |
| Insufficient information | If fewer than four claims survive verification the research is marked insufficient and scripting is blocked — the app tells you instead of building a story. |
| Visual honesty | Stock media is labelled on screen ("Representative footage · author / Pexels"); documentary media carries its credit; anything AI-generated is labelled "AI-generated illustration". Charts and maps are generated from the verified numbers. |

## Production details

- **Voice-over** — Kokoro-82M (Apache-2.0) runs locally. ReelForge patches the ONNX graph to expose the duration
  predictor, so every word gets the exact timing the model used to generate it (measured against an independent
  recogniser: median offset ≈ 60–90 ms, i.e. within the recogniser's own 80 ms frame size). Numbers, years, currencies,
  units, lakh/crore and acronyms are normalised for natural reading ("1947" → "nineteen forty seven", "₹2,000 crore" →
  "two thousand crore rupees"); add names to `data/lexicon.yaml` or `projects/<id>/lexicon.yaml`. Narration that runs
  long is re-voiced up to 12 % faster to fit the target. Cloud voices without timings are aligned with speech recognition.
- **Subtitles** — 1–3 words per cue, word-level highlight, numbers and key terms in the accent colour, placed inside
  Instagram's safe area (clear of the top bar, caption area and right-hand buttons).
- **Visual storytelling** — every sentence gets a scene with a stated purpose: real footage/photos with slow camera
  moves and a consistent grade (landscape photos are shown whole on a blurred fill), or motion graphics. Transitions:
  cut, fade, slide, zoom, whip, wipe; whooshes, risers and impacts are synthesised to match.
- **Music** — an original underscore (pads, arpeggio, bass, light percussion) composed for the reel's exact length,
  with intensity following the script (lift at the payoff). Ducked under the voice (≈ 15–20 dB below speech).
- **Mastering** — voice EQ + compression, carved and side-chain-ducked music, two-pass EBU R128 normalisation to
  −14 LUFS, AAC 256 kbps with a closed-loop true-peak check (≤ −1 dBTP after encoding).
- **Render** — Remotion (React) composes 1080 × 1920 frames in headless Chrome; the H.264 stream is muxed without a
  second lossy encode. A 45 s reel renders in ~3–4 minutes on a 4-core CPU.

## Quality control

`python -m reelforge qc <id>` (also run automatically). Critical failures block completion.

| Check | Severity |
|---|---|
| Research sufficient; every factual sentence cites checked claims; on-screen numbers backed | critical |
| Cited sources have stored snapshots; live re-check (dead links fail) | critical |
| Narration ↔ subtitle sync measured by independent speech recognition | critical |
| Understandable without sound (caption coverage, text on screen from the start) | critical |
| 1080 × 1920, 30/1 fps, H.264 yuv420p, AAC 48 kHz stereo, MP4, faststart, duration | critical |
| Full decode without errors, exact frame count | critical |
| No black or frozen segments | critical |
| No missing media; every asset licensed; stock/AI visuals labelled | critical |
| Audio does not clip (true peak of the encoded file) | critical |
| Narration matches script (pronunciation), loudness/balance, no dead air | major |
| No clickbait, spelling, visual relevance, hook timing & pacing, duration, cover, caption/hashtags/sources | major |

## Outputs (`projects/<id>/output/`)

`reel.mp4`, `cover.jpg` (+ `cover_grid_preview.jpg`), `caption.txt` (with sources and ≤ 5 hashtags — Instagram's
limit since Dec 2025), `pinned_comment.txt`, `captions.srt` / `.vtt`, `sources.md`, `credits.txt`, `qc_report.md`,
plus `research.md` and `script.md` in the project folder.

## Styles, languages, brands

- **Styles**: Documentary, Explainer, Mystery & curiosity, Historical storytelling, Business & finance,
  Agriculture & rural economy, Science & technology, Current affairs, Interesting facts, Human stories
  (`reelforge/styles.py` — hooks, voice direction, pacing, music and visual preferences for each).
- **Languages**: English, Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Punjabi, Spanish, French,
  Portuguese, Italian, German. Kokoro covers English, Hindi, Spanish, French, Portuguese and Italian locally; Azure covers
  every Indian language listed. Fonts for each script are bundled.
- **Brand kits**: `brands/*.yaml` (colours, fonts, subtitle style, grade, handle). Two included; add more files for more
  brands — they appear in the UI automatically.

## Sample

`samples/india-solar-surge/` contains a 42.7-second reel produced end-to-end by this pipeline ("India's solar surge,
in numbers": globe map, counters, line and bar charts, comparison; Kokoro narration; original score). Every figure in
it was recomputed by the app from Our World in Data's downloaded energy dataset (Ember data), and QC passed with two
explained warnings. Its README documents exactly how it was made, including the build environment's network limits
(only GitHub-hosted sources and no stock-media APIs were reachable, so the sample is graphics-only and single-source).

## Project layout

```
reelforge/            Python package
  research/           fetch + snapshots, credibility tiers, verification, report, orchestration
  llm/                Claude client (web research, structured outputs), prompts, schemas
  script/ storyboard/ writer + validator, planner + validator
  voice/              normaliser, Kokoro (timed), cloud TTS, ASR, alignment, subtitles, narration assembly
  assets/             stock providers + selection, procedural music and SFX
  render/             Remotion props, renderer bridge, FFmpeg mastering, render stage
  publish/ qc/        Instagram package, quality control
  server/             FastAPI app + single-page studio (static/)
renderer/             Remotion compositions (React/TypeScript), fonts, textures, render CLI
brands/ data/         brand kits, pronunciation lexicon
.claude/skills/       Claude Code mode
tests/                pytest suite
```

## Licences and third-party terms

- **Remotion** is free for individuals and companies with up to 3 employees; larger companies need a Remotion company
  licence (remotion.dev/license).
- Kokoro-82M (Apache-2.0), kokoro-onnx (MIT), Parakeet-TDT via sherpa-onnx (CC-BY-4.0 model, Apache-2.0 runtime).
- Fonts: Anton, Inter, Montserrat, Poppins, Teko, Noto Sans (SIL OFL, licences in `renderer/public/fonts`).
- Icons: Lucide (ISC). Map data: Natural Earth (public domain) via world-atlas.
- Stock media keeps its own licence (Pexels License, Pixabay Content License, CC licences on Wikimedia, NASA media
  guidelines); attributions are written to `credits.txt` and, where required, the caption.
- Synthetic voices: check your TTS provider's terms for commercial use (Kokoro: Apache-2.0; ElevenLabs free tier is
  non-commercial).

## Troubleshooting

- `doctor` shows `renderer.installed: false` → `cd renderer && npm install`.
- Remotion cannot launch Chrome on Linux → install Chrome dependencies or set `REELFORGE_CHROME` to a Chrome/Chromium
  headless shell.
- "No speech recogniser" in QC → `pip install -r requirements-asr.txt && python -m reelforge setup-models --asr`
  (English) or `pip install faster-whisper` (multilingual). Without it QC falls back to a structural sync check.
- A source shows `agent_attested` → the quotes were captured by Claude Code but the app could not download the page;
  run `python -m reelforge verify-sources <id>` on a normal network.

## Limitations

- Factual accuracy is enforced mechanically for quotes and numbers; whether a sentence's *wording* is fair to its
  sources still deserves a human read — that is why research and script approval are manual gates.
- Visual relevance of stock footage is scored from provider metadata (tags/titles), not by looking at the frames.
- Automatic spell-checking is English-only; other languages need a manual proofread.
