# MY VOICE — Personal AI Voice Studio

A guided recording studio that runs in your browser and captures your voice systematically — English,
Hindi and Hinglish; neutral, emotional and narration styles; every speech sound — checks every take,
and builds a documented, exportable dataset for cloning **your own voice**.

```bash
pip install -r requirements-voice.txt     # or: ./setup.sh --voice
python -m myvoice serve                   # → http://127.0.0.1:8100
```

Open the link, enter your name, allow the microphone, and the first prompt is on screen. Press **Space**
(or the red button), read it, and stop — or just stop talking: the take ends by itself after a short
silence. The studio scores the take, tells you what (if anything) is wrong, and you approve or re-record.
After approval it moves to the next exercise. You never invent sentences and never upload files.

---

## 1. How a session works

1. **Warm-up** (once per session, about a minute): 5 s of room tone (noise measurement), one hand clap
   (room echo), a microphone check sentence, your consent statement (once, ever), and two *consistency
   anchors* — sentences you repeat every session so natural variation can be measured over days.
2. **Identity first**: until about 80 % of Module A's core exercises are approved, the studio stays in
   Module A (normal, slow, fast, soft, projected and whisper-like voice; questions, statements,
   exclamations; breathing; sustained vowels; a pitch glide).
3. **Adaptive**: after that, each next exercise is the one that best fills what your *approved*
   recordings still lack — minutes per language, phonemes and sound pairs, emotions, narration genres —
   with a reason shown under the prompt ("Hindi needs more minutes", "Sounds still needed: /θ/ …").
   You can also choose a module and go through it in order.
4. **Every take** is saved immediately (lossless) and analysed in under a second; the speech-recognition
   read-check follows a few seconds later in the background.
5. **Review**: score ring, verdict (*Great take* / *Usable — your call* / *Re-record recommended*), the
   reasons and fixes, a waveform with detected speech shaded and problems marked, playback, and the
   measurements. **Enter** approves and moves on; **R** re-records (the old take is kept as *rejected*,
   restorable); **N** skips (the take stays in the review queue).
6. **Breaks and resuming**: *Break* pauses the session with a timer. Closing the browser is fine; the
   next visit within two hours continues the same session, later visits start a new one. Progress is
   stored on disk, not in the browser.

Keyboard: Space record/stop · Enter approve & next · R re-record · P play · K pause/resume · N skip ·
B back · X reject · T Roman transliteration · +/− text size · ? help.

---

## 2. Architecture

```
Browser (vanilla JS ES modules, no build step, no CDN)
  getUserMedia (echoCancellation/noiseSuppression/autoGainControl = false)
  → AudioWorklet: raw float32 PCM at the device rate, 1 s pre-roll ring buffer
  → end-of-speech detector (adaptive noise floor + hysteresis) → auto-stop
  → 32-bit float WAV upload (IndexedDB outbox if the server is unreachable)
        │
        ▼
FastAPI server (python -m myvoice serve, 127.0.0.1 only by default)
  Studio service ── store ── myvoice_data/recordings/<category>/<exercise>__<take>.wav (24-bit PCM)
     │                       + .json sidecar (exercise snapshot, analysis, quality, read-check, capture)
     ├─ analysis   WebRTC VAD + energy gate, levels/SNR, clipping, dropouts, clicks, bandwidth,
     │             hum, Praat pitch/HNR/jitter/shimmer, speaking rate, pauses, breaths, clap T60
     ├─ quality    issues → score → verdict, with plain-language reasons
     ├─ ASR worker faster-whisper (local), script-independent read-check
     ├─ curriculum 593 exercises (YAML) + number generators + adaptive planner
     ├─ coverage   phoneme/diphone counts (eSpeak NG for English, rule-based Devanagari G2P),
     │             language minutes, emotions, genres, consistency → milestones
     ├─ analytics  aggregates of stored measurements
     └─ export     8 profiles (master archive, zero-shot reference pack, ElevenLabs, LJSpeech,
                   F5-TTS/IndicF5, XTTS, Azure, JSONL manifest)
```

Why these choices:

| Decision | Reason |
|---|---|
| AudioWorklet raw PCM, not MediaRecorder | MediaRecorder produces lossy Opus/AAC; a voice dataset must be lossless. |
| Browser voice processing off | Echo cancellation, noise suppression and AGC change your timbre and pump levels. What the browser actually applied is recorded and flagged. |
| 24-bit WAV at native rate, untouched | "Preserve original recordings": exports are derived copies; originals never change. |
| Files + JSON sidecars as the source of truth | The dataset is readable without the app, survives crashes (atomic writes), and the index rebuilds from the folder. |
| Python backend | The analysis needs NumPy/SciPy, Praat and Whisper; the existing ReelForge app is Python/FastAPI too. |
| No CDN, no build step | Works offline, nothing third-party loads in the page that has your microphone. |
| Local speech recognition | Your voice never leaves the computer for the read-check. |

---

## 3. The recording assistant: what is checked

All numbers are computed from the audio of the take; nothing is estimated from defaults.

| Check | How | Effect |
|---|---|---|
| Speech present | WebRTC VAD fused with an adaptive energy gate (catches whispers, ignores breaths) | no speech → re-record |
| Mic muted / digital silence | exact-zero signal | error, with how to unmute |
| Clipping | flat-topped runs of identical samples (a natural peak is not clipping) | ≥ 10 events → re-record |
| Level | active speech level, full-band dBFS | far too quiet → re-record; quiet → warning |
| Background noise | noise floor of non-speech frames; SNR | < 20 dB → re-record; < 30 dB → warning |
| Bandwidth | highest frequency with real content | < 5.5 kHz (Bluetooth "call mode") → re-record; < 9 kHz → warning |
| Mains hum | 50/60 Hz harmonic peaks in the pauses | warning |
| Dropouts | runs of digital silence inside speech (USB/driver glitches) | re-record |
| OS noise gate | digital silence between words | warning |
| Digital clicks | isolated one-sample discontinuities | warning |
| Cut off | speech still active at the very start/end | re-record |
| Too short / too long | speech duration vs. the script's syllables at the requested pace | re-record / warning |
| Long pause | > 3 s inside read material | warning |
| Microphone interrupted | browser `mute`/`ended` events during the take | re-record |
| Browser processing on | `track.getSettings()` | warning |
| Pace instruction | articulation rate for slow/fast exercises | information |
| Read-check | Whisper transcript aligned with the displayed words (see below) | not read → re-record; partial → warning, missing words highlighted |
| Room tone | noise floor, hum, sound during silence | warnings |
| Room echo | hand clap → Schroeder integration → T60 | > 0.9 s re-record, > 0.6 s warning |

The **score** starts at 100 and each problem subtracts its penalty. *Re-record recommended* means at
least one error or a score below 50. Nothing is ever discarded automatically: you decide.

**Read-check.** Whisper in Hindi mode often writes English words in Devanagari ("मीटिंग"), digits
instead of words, and splits or joins compounds. Both texts are therefore reduced to script-independent
phonetic keys (Devanagari via the Hindi G2P, Latin via eSpeak + spelling rules, acronyms also as letter
names), numbers in the transcript are expanded the way the exercise says them (cardinal, year, digit by
digit; ₹/%/$), and a weighted monotonic alignment allows one-to-two word matches. Thresholds are more
forgiving for Hindi/Hinglish and with smaller models, and an unsure recogniser never fails a take alone.

**Room echo** is measured from a clap rather than from your sentences because blind reverberation
estimates from one short sentence proved unreliable in testing; the clap method was accurate to within
0.03 s on simulated rooms from 0.15 to 1.2 s.

---

## 4. Curriculum

593 exercises in `myvoice/curriculum/data/*.yaml` (373 in the core pass, the rest an extended pool
the planner draws on). About 34–100 minutes of read speech, plus spontaneous prompts and unlimited
generated numbers/dates/times/money.

| Module | Content |
|---|---|
| S Setup | room tone, clap, mic check, consent (EN + HI) |
| A Voice identity (74) | normal, slow, fast, soft, projected, whisper-like, clear articulation, breathing passages, short/long sentences, questions, statements, exclamations, sustained vowels, pitch glide, counting |
| B Phonetics (140) | every English vowel and consonant, Indian-English contrasts (θ ð, v/w, z, ʒ), clusters, minimal pairs, endings, syllable structures, tongue twisters; Hindi vowels and length, every place of articulation, aspirated/unaspirated pairs, retroflex/dental pairs, anusvara/chandrabindu, nukta sounds and flaps with minimal pairs (राज/राज़), conjuncts, schwa contexts, rare sounds |
| C English (56) | basic, formal, professional, business, academic, conversational, storytelling, technical, long-form narration, complex syntax, numbers/dates/currency/abbreviations |
| D Hindi (56) | everyday, formal, conversational, formal vocabulary, idioms, storytelling, emotional narration, news, documentary, long paragraphs, numbers |
| E Hinglish (59) | Hindi with English words, English with Hindi expressions, business, marketing, agriculture, technology, everyday expressions, code-switching monologues |
| F Emotions (51) | all 17 requested emotions × EN/HI/Hinglish, each with a situation to act from |
| G Instagram & cinematic (71) | all 15 requested genres plus nine complete reel narration scripts |
| H Conversation (41) | replies to a friend's line, explaining to a beginner, interview answers, opinions, questions, disagreement, complex subjects, instructions, 15 spontaneous topics with talking points |
| I Numbers & vocabulary (39 + generated) | 0–100 in English and Hindi (every Hindi number is its own word), lakh/crore, dates, years, times (सवा/साढ़े/पौने), fictional phone-style digits, currency, percentages, maths, science, business abbreviations, farm terms, acronyms |
| J Consistency (6) | anchor sentences, two per session |

Conventions: Hindi is natural Indian Hindi in Devanagari, with a generated Roman line (toggle with T).
Hinglish is written with Hindi words in Devanagari and English words in Latin script, so every word's
language is unambiguous for you and for any future model. First-person Hindi verbs follow the gender you
choose (कर रहा/रही हूँ) — the studio never assumes it. Wherever digits appear, the exact spoken form is
shown and used as the transcript.

**When the bank runs out** for a gap, run `/voice-exercises` in Claude Code (no API key needed): it reads
`python -m myvoice coverage --json`, writes new exercises for the weakest areas and imports them with
`python -m myvoice import-exercises`, which validates every field.

---

## 5. Dataset, approval and storage

```
myvoice_data/                       (git-ignored; chmod 700)
  profile.json                      name, Hindi verb forms, consent, preferences
  recordings/<category>/…wav/.json  voice_identity, english_phonetics, hindi_phonetics, hinglish,
                                    conversational, emotional, professional_narration,
                                    cinematic_narration, documentary_narration, numbers_special,
                                    consistency, room_tone, consent
  sessions/<id>.json                device, sample rate, browser settings, room noise and echo
  trash/                            deleted takes, restorable until you empty the trash
  exercises/                        imported exercises
  exports/                          export folders + ZIPs
  activity.log                      every save, status change, deletion and export
```

Every sidecar stores: recording id, date, language, category, module, exercise id, displayed text,
spoken form, verified transcript and its source (prompt / speech recognition / you), duration, sample
rate, bit depth, SHA-256, quality score and issues, read-check, all measurements, device, browser
processing settings, pause splice points, session id, and status with reason and time.

Takes start as **pending**; only **approved** takes count towards coverage and exports. Re-recording
marks the previous take rejected (kept). Delete moves to the trash; only *Empty trash* (typing DELETE)
removes files. If an upload fails, the take is kept in the browser and retried.

---

## 6. Dashboard, analytics and completeness

The dashboard shows completeness, the current milestone and its unmet checks, approved vs. recorded
minutes, quality, language minutes, English and Hindi phoneme grids, diphone coverage, emotions,
narration genres, module progress and sessions. Completeness is computed from approved recordings
against these milestones — finishing exercises alone never completes the dataset:

| Milestone | Meant for | Main targets |
|---|---|---|
| Studio set up | — | room tone, consent statement |
| Voice identity captured | — | 80 % of Module A core, 5 min |
| Reference-ready | zero-shot / instant cloning | 3 excellent 6–15 s neutral clips per language, narration takes |
| Fine-tune ready (minimum) | professional cloning / fine-tuning | 30 min (ElevenLabs PVC minimum), 8 min per language, every phoneme ≥ 10 (rare ≥ 3), 50 % diphones, 9 emotions ×3, 2 sessions |
| Professional dataset | best quality | 120 min, 30 min per language, phonemes ≥ 25 (rare ≥ 6), 75 % diphones, all 17 emotions ×6, all 15 genres ×4, 8 min spontaneous, anchors in 4 sessions over 3 days, average score ≥ 80 |

Voice analytics: pitch distribution and per-emotion/per-language medians (Praat, two-pass speaker-
adaptive range), articulation rate by requested pace, pauses by style, breaths, read-check accuracy by
language and frequently missed words, score distribution and frequent problems, SNR/noise/echo per
session, anchor-sentence pitch across sessions and microphone-spectrum drift, and sustained-vowel
jitter/shimmer/HNR. These are measurements, not judgements; the read-check is not a pronunciation score.

---

## 7. Exports

| Profile | Use | Contents |
|---|---|---|
| master | backup, any future model | original 24-bit WAVs + sidecars, metadata.jsonl/CSV, sessions, coverage, profile |
| reference | IndicF5, F5-TTS, Chatterbox, CosyVoice, ElevenLabs Instant | best 5–15 s clips per language × emotion/style, each with `.txt` transcript |
| elevenlabs | Professional / Instant Voice Clone | per-language files, MP3 192 kbps (WAV without FFmpeg), −20 dB RMS, peaks ≤ −3 dBFS; `ivc_sample` |
| ljspeech | Coqui TTS, Piper, StyleTTS2, VITS | wavs/ + `id|text|normalised` |
| f5tts | F5-TTS / IndicF5 fine-tuning | 24 kHz wavs + `audio_file|text` |
| xtts | XTTS-v2 fine-tuning | train/eval CSVs |
| azure | Azure professional voice | 24 kHz wavs + `transcript.txt` |
| manifest | NeMo/ESPnet/custom | JSONL with language, emotion, style, quality, session |

Training exports contain approved takes only (option: include pending), trimmed to speech with padding,
DC removed, plain gain to a target level (no compression or limiting), polyphase resampling, 16-bit with
dither. Room tone, consent and analysis tasks are excluded from training sets (kept in the master archive).

---

## 8. Choosing the voice-cloning technology (preliminary research, November 2026)

To be decided with your own recordings — a blind listening test with your reference clips beats any
benchmark, and no public benchmark covers Hinglish with all of these systems.

| Option | Type | Hindi / Hinglish | Commercial use | Data needed | Privacy |
|---|---|---|---|---|---|
| ElevenLabs Professional Voice Clone | cloud, paid | Hindi supported; Hinglish anecdotally good with natural mixed training audio | yes on paid plans | ≥ 30 min, ideally 2 h+; live voice verification | audio uploaded |
| ElevenLabs Instant Voice Clone | cloud, paid | same models | yes on paid plans | 1–2 min | audio uploaded |
| Sarvam Bulbul v3 custom voice | cloud | built for Indian languages, smooth Hindi–English switching | check current terms | 30–60 s + consent | audio uploaded |
| Azure personal / professional voice | cloud | Hindi listed | limited access (application + recorded consent) | short sample (personal) / large set (professional) | audio uploaded |
| Chatterbox Multilingual (Resemble AI) | local, open | Hindi in its 23 languages; dedicated Hindi fine-tune | MIT; outputs are watermarked | 5–10 s reference | local |
| IndicF5 (AI4Bharat) | local, open | Hindi-specific, reference clip + transcript | licence reported as MIT by derived projects — verify on the gated model page | 5–15 s reference | local |
| F5-TTS (official weights), XTTS-v2 | local, open | — | **non-commercial** weights (CC-BY-NC / CPML) | — | local |

Points from the research worth keeping in mind:
- ElevenLabs states that more than 30 minutes and ideally 2+ hours of consistent audio gives the best
  professional clone, recommends MP3 at 192 kbps over WAV for uploads, and targets roughly −23 to
  −18 dB RMS with peaks around −3 dB; it also noted that Professional clones were not fully optimised for
  its v3 model during the research preview, so compare its models (v2, v3, v4) for your clone.
- Larger datasets help fine-tuning and professional cloning, not zero-shot models: those need a few
  excellent, representative reference clips (the *reference* export).
- The licence of a fine-tuned model inherits the base model's licence.

**Recommended path.** (1) Record until *Reference-ready* (about 30–45 minutes of studio time). (2)
Export the reference pack and run a blind A/B test: ElevenLabs Instant, Chatterbox Multilingual (local),
IndicF5 (local) and Sarvam, on the same 30-second Hinglish reel script, scoring speaker similarity, Hindi,
Indian English, Hinglish switching, emotion and stability over a 60-second narration. (3) If ElevenLabs
wins, keep recording to *Fine-tune ready* or beyond and upload the ElevenLabs export for a Professional
clone; if a local model wins, keep the reference pack updated per style and consider fine-tuning later.
Paid services are never contacted by the studio itself; uploading is your explicit choice.

Sources: [ElevenLabs Professional Voice Cloning](https://elevenlabs.io/docs/product-guides/voices/voice-cloning/professional-voice-cloning),
[ElevenLabs Instant Voice Cloning](https://elevenlabs.io/docs/creative-platform/voices/voice-cloning/instant-voice-cloning),
[Eleven v3 accents post](https://elevenlabs.io/blog/eleven-v3-audio-tags-emulating-accents-with-precision),
[Chatterbox model card](https://huggingface.co/ResembleAI/chatterbox), [Chatterbox Multilingual](https://resemble.ai/learn/models/chatterbox-multilingual),
[IndicF5](https://huggingface.co/ai4bharat/IndicF5), [Hinglish IndicF5 evaluation](https://github.com/harrrshall/hinglish-tts),
[F5-TTS](https://github.com/SWivid/F5-TTS), [Sarvam text-to-speech](https://www.sarvam.ai/text-to-speech),
[Azure personal voice](https://learn.microsoft.com/azure/ai-services/speech-service/personal-voice-overview).

---

## 9. Next step: your voice as the default Instagram narrator

Planned integration with ReelForge (this repository's reel pipeline) once a clone is chosen:
script → narration in **your** voice → your review → word-timed sync with the video → final reel.

- A `myvoice` TTS provider in `reelforge/voice/providers.py` that calls the chosen backend with your
  voice (ElevenLabs voice id, or a local model + reference clip chosen per style from the reference pack).
- It becomes ReelForge's default narration provider. If it is unavailable, narration **fails with a clear
  message**; it never falls back to a generic voice. Another voice is used only when you select it.
- Styles (documentary, reel hook, suspense …) select the matching reference clip or delivery setting;
  the speaker stays you. Word timings come from ReelForge's existing alignment.

---

## 10. Dependencies and costs

| Component | Licence | Cost |
|---|---|---|
| FastAPI, NumPy, SciPy, soundfile, RapidFuzz, PyYAML, num2words | permissive | free |
| praat-parselmouth (Praat) | GPL-3.0 | free |
| webrtcvad-wheels | MIT | free |
| espeakng-loader (eSpeak NG) | GPL-3.0 | free |
| faster-whisper + Whisper model | MIT | free; model download 0.5–3 GB once |
| Inter, Noto Sans Devanagari fonts | SIL OFL | free |

The studio itself uses no paid API and no cloud service. Disk: about 0.5 GB per hour of recordings
(24-bit, 48 kHz mono) plus exports. CPU: analysis takes well under a second per take; the read-check with
large-v3-turbo takes a few seconds per take on a typical laptop and runs in the background (choose
`small` in Settings on slower machines; it is weaker on Hindi).

## 11. Browser and device limitations

- Microphone access requires a secure page: `http://127.0.0.1` / `localhost` on the same computer, or HTTPS.
- Best: Chrome or Edge on a computer. Firefox works. Safari (especially on iPhone/iPad) may ignore the
  request to disable voice processing; the studio detects this and flags the take.
- Bluetooth headsets switch to telephone quality when their microphone is used; the studio detects
  narrow-band audio. Use a wired or USB microphone.
- Phones stop the microphone when the screen locks or the tab goes to the background.
- **Recording from a phone**: `python -m myvoice serve --lan` serves HTTPS with a self-signed certificate
  and prints a link containing a random access token (accept the certificate warning once). Anyone with
  the link on your network can reach the studio while it runs.

## 12. Privacy and security

Local only: the server binds to 127.0.0.1 unless you pass `--lan`, which adds HTTPS and a token (every
request is checked; constant-time comparison). Recordings are stored owner-only. The only network access
is the one-time Whisper model download. Paths are validated against traversal; uploads are size-limited.

## 13. What was verified, and known limitations

Verified in development: 130+ automated tests (Hindi G2P and romanisation, read-check alignment across
scripts, every signal check on synthetic signals with known properties — noise, clipping, dropouts,
narrow-band, hum, clicks, truncation, room tone, clap reverberation at four T60 values — curriculum
validation, storage durability, planner, coverage, the HTTP API, access tokens, and all eight export
profiles) and a browser end-to-end test (`tests/e2e/studio_flow.mjs`) that records complete takes through
the real AudioWorklet recorder in Chromium and visits every page on desktop, mobile and dark mode.

Limitations to know:
- The read-check code was tested with simulated recogniser output; the build environment could not
  download Whisper models, so the first real runs happen on your machine. Speech recognition on Hindi and
  Hinglish is imperfect; treat partial matches as "listen back", not as proof of a mistake.
- English phoneme counts use eSpeak's General American model as a category inventory; your Indian-English
  realisation is what gets recorded (intended), but the counts are categories, not pronunciation scores.
- Breath counts, bandwidth and hum are heuristics with conservative thresholds; check the waveform when
  in doubt.
- Voice-cloning recommendations are from public documentation and reports as of November 2026 and should
  be confirmed with your own listening tests and each provider's current terms.

## 14. Command line

```
python -m myvoice serve [--port 8100] [--lan] [--https]
python -m myvoice doctor                       # component check
python -m myvoice stats                        # milestones and progress
python -m myvoice coverage --json              # full coverage report
python -m myvoice export --list | <profile> [--sample-rate N] [--include-pending]
python -m myvoice import-exercises file.json   # validated import
python -m myvoice rebuild-index                # re-read all sidecars
```
Environment: `MYVOICE_DATA_DIR`, `MYVOICE_ASR=off`, `MYVOICE_ASR_MODEL`, `MYVOICE_ASR_THREADS`,
`MYVOICE_SESSION_IDLE_HOURS`, `MYVOICE_MAX_TAKE_SECONDS`.
