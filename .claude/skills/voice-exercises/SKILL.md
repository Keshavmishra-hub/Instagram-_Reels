---
name: voice-exercises
description: Write new recording exercises for MY VOICE (the personal voice studio in myvoice/) aimed at the dataset's current coverage gaps, validate them and import them. Use when the user asks for more voice-training material, or runs /voice-exercises [focus].
---

# Generate targeted exercises for MY VOICE (Claude Code mode)

Optional argument: a focus such as "Hindi suspense narration" or "English consonant clusters". Without one,
work from the coverage report.

## 1. Find the gaps
Run `python -m myvoice coverage --json --compact` (use `.venv/bin/python` if that venv exists). Look at:
- `milestones[].checks` with `progress < 1` (language minutes, phonemes, diphones, emotions, genres, spontaneous minutes)
- `phonemes.en` / `phonemes.hi` rows with low `count` (rare sounds have lower targets)
- `languages`, `emotions`, `genres`, and `next.reason` / `next.factors` (what the planner wanted but may not find)
Also skim the existing bank in `myvoice/curriculum/data/*.yaml` so you do not duplicate sentences.

## 2. Write the exercises
Create `myvoice_data/exercises/new_<topic>.json` (any path is fine) with the bank's structure:

```json
{
  "module": "G",
  "sections": [
    {
      "code": "X20261103-HI-SUSP",
      "title": "More Hindi suspense narration",
      "category": "cinematic_narration",
      "defaults": {"kind": "sentence", "lang": "hi", "style": "suspense", "emotion": "suspense"},
      "instruction": "धीमे और ठहराव के साथ पढ़िए।",
      "exercises": [
        {"text": "...", "context": "A one-line situation to act from."}
      ]
    }
  ]
}
```

Rules (the importer rejects violations; the rest are quality rules you must follow):
- `module`: one of A–J (S and J are reserved). `category`: voice_identity, english_phonetics, hindi_phonetics, hinglish,
  conversational, emotional, professional_narration, cinematic_narration, documentary_narration, numbers_special.
- `code`: unique, starts with `X` + today's date (`X20261103-...`), letters/digits/hyphens. Never reuse or rename a code:
  recordings refer to exercise ids (`<code>-01`, `<code>-02`, ...). Only append to a section.
- `lang`: `en`, `hi` or `hinglish`. Hindi is written in Devanagari. Hinglish: Hindi words in Devanagari, English words
  in Latin script ("आज की meeting में हम plan discuss करेंगे।"). Natural Indian usage, not Sanskritised.
- First-person Hindi verbs agree with the speaker's gender: write both forms as `{रहा|रही}`, `{करता|करती}`,
  `{गया था|गई थी}` (masculine first). Never assume the speaker's gender.
- No digits in `text` unless you add `spoken` with exactly how it is said, in words.
- `emotion` from: happiness, excitement, confidence, authority, seriousness, curiosity, surprise, sadness, empathy,
  motivation, determination, suspense, humour, calmness, urgency, dramatic, inspirational (or neutral).
  Emotional and narration items need a `context` line.
- `style` from the list in `myvoice/models.py` (`STYLES`), e.g. reel_hook, documentary, agriculture, business_explainer.
- `kind`: sentence (6–30 words), paragraph (40–110 words), word_list, dialogue (with a `cue`), or prompt
  (spontaneous; set `"readcheck": false, "min_sec": 25, "hints": [...]`).
- Phonetic targets: put the needed sounds in natural words several times; do not write nonsense.
- Facts must be true and uncontroversial; when unsure, write a story or a generic statement instead.
- Aim for 10–30 exercises per run, spread across the gaps you found.

## 3. Validate and import
Run `python -m myvoice import-exercises <file>`. It rejects the file with a reason if anything is malformed
(fix and retry). Then tell the user how many exercises were added and which gaps they target. A running studio
picks them up after a restart (or immediately through `POST /api/exercises/import`).
