"""Turn measurements into a quality score, a verdict and plain-language reasons.

The score starts at 100 and each problem subtracts a penalty. Thresholds follow common voice-dataset
practice (ElevenLabs' cloning guidance targets roughly -23…-18 dB RMS with peaks around -3 dB and a
quiet room; TTS corpora are recorded at >=35-40 dB SNR without clipping or browser processing).
Verdicts:
  good      no warnings or errors and score >= 80
  usable    warnings only (you decide)
  rerecord  any error, or score < 50
"""

from __future__ import annotations

from typing import Optional

from ..models import Issue, Quality, ReadMatch

READ_KINDS = {"sentence", "paragraph", "word_list", "dialogue"}


def _issue(issues: list[Issue], code: str, severity: str, message: str, hint: str = "", penalty: float = 0.0,
           at: Optional[float] = None) -> None:
    issues.append(Issue(code=code, severity=severity, message=message, hint=hint, penalty=round(penalty, 1), at=at))


def assess(an: dict, ctx: dict, match: Optional[ReadMatch] = None, asr: Optional[dict] = None) -> Quality:
    """`an` = analysis dict, `ctx` = exercise context (kind, volume, pace, expected, readcheck, capture...)."""
    issues: list[Issue] = []
    kind = ctx.get("kind", "sentence")
    volume = ctx.get("volume", "normal")
    lvl = an.get("speech_level_dbfs", -120.0)
    floor = an.get("noise_floor_dbfs", -120.0)
    snr = an.get("snr_db")
    speech = an.get("speech_seconds", 0.0)
    dur = an.get("duration", 0.0)

    # ---------------------------------------------------------------- the microphone itself
    if an.get("dropouts", {}).get("all_digital_silence"):
        _issue(issues, "no_signal", "error", "The microphone delivered digital silence.",
               "Check that the mic is not muted (hardware switch, OS privacy setting) and pick the right input device.", 100)
        return _finish(issues, kind)

    events = ctx.get("track_events") or []
    if any(e.get("type") in ("mute", "ended") for e in events):
        _issue(issues, "mic_interrupted", "error", "The browser reported a microphone interruption during this take.",
               "Another app may have taken the mic, or the device disconnected. Record again.", 35)
    applied = ctx.get("constraints_applied") or {}
    processed = [k for k in ("echoCancellation", "noiseSuppression", "autoGainControl") if applied.get(k) is True]
    if processed:
        _issue(issues, "browser_processing", "warning",
               "Your browser kept voice processing on: " + ", ".join(processed) + ".",
               "Processing changes the timbre of your voice. Chrome, Edge and Firefox on a computer honour the studio's request to turn it off.", 8)

    sr = an.get("sample_rate", 48000)
    if sr < 22050:
        _issue(issues, "low_sample_rate", "warning", f"Low sample rate ({sr} Hz).", "Use a microphone/browser that records at 44.1 or 48 kHz.", 10)

    bw = (an.get("bandwidth") or {}).get("effective_hz")
    if bw and speech >= 0.8:
        if bw < 5500:
            _issue(issues, "narrowband", "error", f"Telephone-quality audio: nothing above about {bw / 1000:.1f} kHz.",
                   "This is typical of a Bluetooth headset in call mode. Use a wired or USB microphone.", 35)
        elif bw < 9000 and sr >= 32000:
            _issue(issues, "reduced_bandwidth", "warning", f"Reduced bandwidth: little content above {bw / 1000:.1f} kHz.",
                   "Bluetooth headsets (even in 'HD voice' mode) and some cheap USB mics cut the highs that make a voice sound crisp. A wired mic is better.", 12)

    # ---------------------------------------------------------------- room echo check (hand clap)
    if kind == "clap":
        room = an.get("room") or {}
        t60 = room.get("t60")
        if t60 is None:
            _issue(issues, "clap_unmeasured", "warning", "Could not measure the room: " + (room.get("reason") or "no clear clap") + ".",
                   "Clap once, sharply, at your recording position, then stay silent until the recording stops.", 40)
        elif t60 > 0.9:
            _issue(issues, "room_very_echoey", "error", f"Very echoey room (reverberation time {t60:.2f} s).",
                   "Echo is baked into every take and into the clone. Record in a smaller, furnished room (bedroom, wardrobe of clothes), away from bare walls.", 45)
        elif t60 > 0.6:
            _issue(issues, "room_echoey", "warning", f"Noticeable room echo (reverberation time {t60:.2f} s).",
                   "Soft furnishings, curtains, a rug, or recording facing a wardrobe reduce echo. Keep a hand's width from the mic.", 20)
        elif t60 > 0.4:
            _issue(issues, "room_some_echo", "info", f"Some room echo (reverberation time {t60:.2f} s) — acceptable.", "Under 0.4 s is ideal for voice recording.", 3)
        return _finish(issues, kind)

    # ---------------------------------------------------------------- silence / room tone
    if kind == "silence":
        if speech > 0.4:
            _issue(issues, "sound_during_silence", "warning", "We heard sound while you were meant to be silent.",
                   "Stay still and quiet for the whole room-tone recording.", 25)
        if floor > -40:
            _issue(issues, "room_very_noisy", "error", f"Your room is very noisy ({floor:.0f} dBFS).",
                   "Switch off fans/AC, close windows, move away from traffic, or lower the input gain.", 50)
        elif floor > -50:
            _issue(issues, "room_noisy", "warning", f"Background noise is noticeable ({floor:.0f} dBFS).",
                   "A quieter room improves every recording. Fans and AC are the usual culprits.", 20)
        hum = an.get("hum") or {}
        if hum.get("detected"):
            _issue(issues, "hum", "warning", f"Electrical hum at {hum.get('base_hz')} Hz.",
                   "Move away from chargers/power strips, or try another USB port or cable.", 10)
        return _finish(issues, kind)

    if speech < 0.3:
        _issue(issues, "no_speech", "error", "No speech detected.", "Check the input level meter while speaking, then record again.", 100)
        return _finish(issues, kind)

    # ---------------------------------------------------------------- levels
    clip = an.get("clipping") or {}
    if clip.get("events", 0) >= 10 or clip.get("ratio", 0) >= 0.001:
        _issue(issues, "clipping_severe", "error", f"Heavy clipping ({clip.get('events')} distorted peaks).",
               "Lower the input gain or move a little further from the mic.", 40, at=(clip.get("times") or [None])[0])
    elif clip.get("events", 0) > 0:
        n = clip["events"]
        _issue(issues, "clipping", "warning", f"{n} clipped peak{'s' if n > 1 else ''} (distortion).",
               "Back off slightly from the mic on loud words.", 6 + 3 * n, at=(clip.get("times") or [None])[0])
    elif an.get("peak_dbfs", -100) > -0.5:
        _issue(issues, "hot_peaks", "info", "Peaks are very close to 0 dBFS.", "Leave some headroom: peaks around -6 to -3 dB are ideal.", 2)

    quiet_adj = 10.0 if volume in ("soft", "whisper") else 0.0
    if lvl < -45 - quiet_adj:
        _issue(issues, "too_quiet_severe", "error", f"Far too quiet (speech level {lvl:.0f} dBFS).",
               "Move closer to the mic (a hand-span away) or raise the input gain in your OS sound settings.", 30)
    elif lvl < -36 - quiet_adj:
        _issue(issues, "too_quiet", "warning", f"Quiet recording (speech level {lvl:.0f} dBFS).",
               "Aim for the meter's green zone: move a little closer or raise the input gain.", 10)
    elif lvl > -10 and volume != "loud":
        _issue(issues, "too_loud", "warning", f"Very loud recording (speech level {lvl:.0f} dBFS).", "Lower the input gain a little.", 6)

    if snr is not None:
        if snr < 20:
            _issue(issues, "noisy_severe", "error", f"Too much background noise (SNR {snr:.0f} dB).",
                   "Voice cloning learns the noise too. Find a quieter room, or move closer to the mic.", 35)
        elif snr < 30:
            _issue(issues, "noisy", "warning", f"Audible background noise (SNR {snr:.0f} dB).",
                   "Quieter is better: switch off fans and close the door. 35 dB+ is the target.", 10 + (30 - snr) * 1.2)
        elif snr < 35:
            _issue(issues, "slightly_noisy", "info", f"Slight background noise (SNR {snr:.0f} dB).", "", 3)

    hum = an.get("hum") or {}
    if hum.get("detected"):
        _issue(issues, "hum", "warning", f"Electrical hum at {hum.get('base_hz')} Hz.",
               "Move away from chargers/power strips or try another USB port.", 8)

    # ---------------------------------------------------------------- glitches
    drops = an.get("dropouts") or {}
    in_speech = [d for d in drops.get("items", []) if d.get("in_speech")]
    gated = [d for d in drops.get("items", []) if not d.get("in_speech")]
    if in_speech:
        _issue(issues, "dropout", "error", f"Audio dropout in your speech at {in_speech[0]['at']:.2f} s ({len(in_speech)} total).",
               "A glitch in the mic/USB/driver chain. Close other audio apps and record again.", 30, at=in_speech[0]["at"])
    if len(gated) >= 2:
        _issue(issues, "noise_gate", "warning", "The microphone outputs pure digital silence between words.",
               "An OS 'enhancement' or noise gate is active. Turn off voice effects in your sound settings.", 8, at=gated[0]["at"])
    clicks = an.get("clicks") or {}
    if clicks.get("count", 0) > 0:
        n = clicks["count"]
        _issue(issues, "clicks", "warning", f"{n} digital click{'s' if n > 1 else ''} detected.",
               "Clicks are glitches in the audio chain. Re-record if you can hear them.", min(16, 4 * n), at=(clicks.get("times") or [None])[0])

    # ---------------------------------------------------------------- completeness
    if an.get("cut_end"):
        _issue(issues, "cut_end", "error", "Your speech seems cut off at the end.",
               "Wait a moment after the last word before stopping (or let auto-stop do it).", 30, at=dur)
    if an.get("cut_start"):
        _issue(issues, "cut_start", "error", "Your speech seems cut off at the start.",
               "Press record, then start speaking.", 25, at=0.0)

    expected = ctx.get("expected")  # (min_s, max_s) of speech for read material
    if kind in READ_KINDS and expected:
        lo, hi = expected
        if speech < 0.5 * lo:
            _issue(issues, "too_short", "error", f"Much shorter than expected ({speech:.1f} s of speech; about {lo:.0f}–{hi:.0f} s expected).",
                   "It looks like part of the text was not read. Read the whole text.", 40)
        elif speech < 0.75 * lo:
            _issue(issues, "short", "warning", f"Shorter than expected ({speech:.1f} s of speech; about {lo:.0f}–{hi:.0f} s expected).",
                   "Make sure every word was read.", 12)
        elif speech > 2.2 * hi:
            _issue(issues, "too_long", "warning", f"Much longer than expected ({speech:.1f} s of speech).",
                   "Extra words or long hesitations? Re-record if you went off-script.", 8)
    min_sec = ctx.get("min_sec")
    if kind == "prompt" and min_sec and speech < min_sec:
        _issue(issues, "prompt_short", "warning", f"Only {speech:.0f} s of speech; aim for at least {min_sec:.0f} s.",
               "Keep talking: give an example, a reason, a small story.", 15)
    if kind == "sustained" and speech < 2.0:
        _issue(issues, "vowel_short", "warning", "Hold the vowel steady for at least 3 seconds.", "", 15)

    if kind in READ_KINDS and an.get("longest_pause", 0) > 3.0:
        _issue(issues, "long_pause", "warning", f"A {an['longest_pause']:.1f} s pause in the middle.",
               "Did you lose your place? Fine to keep if it was intentional (dramatic pause).", 5)
    if an.get("leading_silence", 0) > 3.0:
        _issue(issues, "lead_silence", "info", f"{an['leading_silence']:.1f} s of silence before you started.", "Trimmed automatically in exports.", 0)
    if an.get("trailing_silence", 0) > 4.0:
        _issue(issues, "trail_silence", "info", f"{an['trailing_silence']:.1f} s of silence at the end.", "Trimmed automatically in exports.", 0)
    if abs(an.get("dc_offset", 0.0)) > 0.01:
        _issue(issues, "dc_offset", "info", "DC offset in the signal.", "Harmless; removed in exports.", 1)
    if ctx.get("paused_at"):
        _issue(issues, "paused_splice", "info", "This take was paused and resumed.", "The splice point is stored in the metadata.", 2)

    # ---------------------------------------------------------------- delivery vs instruction (informational)
    rate = (an.get("rate") or {}).get("articulation_rate")
    pace = ctx.get("pace", "normal")
    if rate and kind in READ_KINDS:
        if pace == "slow" and rate > 5.2:
            _issue(issues, "pace_fast_for_slow", "info", f"Not much slower than usual ({rate:.1f} syllables/s).", "Slow down and give each word space.", 0)
        elif pace == "fast" and rate < 4.2:
            _issue(issues, "pace_slow_for_fast", "info", f"Quite relaxed for a fast exercise ({rate:.1f} syllables/s).", "Pick up the tempo while staying clear.", 0)

    # ---------------------------------------------------------------- read-check (speech recognition)
    if match is not None and match.verdict != "unchecked":
        miss = [match.expected_words[i] for i in match.missing][:6]
        miss_txt = (" Possibly missed: " + ", ".join(miss) + ("…" if len(match.missing) > 6 else "")) if miss else ""
        if match.verdict == "not_read":
            _issue(issues, "not_read", "error", f"Speech recognition found only {match.coverage:.0%} of the words.{miss_txt}",
                   "Read the displayed text from start to finish.", 45)
        elif match.verdict == "partial":
            _issue(issues, "partial_read", "warning", f"Speech recognition matched {match.coverage:.0%} of the words.{miss_txt}",
                   "Listen back: if you skipped or changed words, re-record. Recognition also makes mistakes, especially in Hindi.", 12)
        if match.precision < 0.65 and match.coverage >= 0.5 and len(match.extra_words) >= 3:
            _issue(issues, "extra_speech", "warning", "Extra words that are not in the text were recognised.",
                   "Fine for natural speech; for read material, stick to the script.", 5)
    if asr and asr.get("avg_logprob") is not None and asr["avg_logprob"] < -1.0 and kind in READ_KINDS:
        _issue(issues, "asr_low_confidence", "info", "Speech recognition was unsure about this take.",
               "Listen back to check clarity; recognition confidence is not a pronunciation score.", 0)

    return _finish(issues, kind)


def _finish(issues: list[Issue], kind: str) -> Quality:
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i.severity], -i.penalty))
    score = max(0, int(round(100 - sum(i.penalty for i in issues))))
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    if errors or score < 50:
        verdict = "rerecord"
    elif not warnings and score >= 80:
        verdict = "good"
    else:
        verdict = "usable"
    grade = "Excellent" if score >= 90 else "Good" if score >= 75 else "Fair" if score >= 50 else "Poor"
    if verdict == "rerecord":
        lead = errors[0].message if errors else "several problems add up"
        summary = f"Re-record recommended: {lead[0].lower() + lead[1:]}"
    elif verdict == "good":
        summary = "Excellent take." if score >= 90 else "Good take."
    else:
        summary = f"Usable, with {len(warnings)} warning{'s' if len(warnings) != 1 else ''}."
    return Quality(score=score, grade=grade, verdict=verdict, summary=summary, issues=issues)
