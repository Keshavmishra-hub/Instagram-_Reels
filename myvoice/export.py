"""Dataset exports. Originals are never modified; every export is a new folder (+ ZIP) under
exports/. Training formats contain approved takes marked `train` (no room tone, consent or analysis
tasks), trimmed to speech with padding, DC-free, gain-normalised (plain gain, no compression or
limiting) and resampled with a polyphase filter, 16-bit with TPDF dither."""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import PRODUCT_NAME, __version__
from .audio.io import read_audio, resample, write_wav
from .coverage import Coverage, usable_seconds
from .models import Take

PROFILES: dict[str, dict] = {
    "master": {
        "title": "Master archive (everything, lossless)",
        "summary": "Original 24-bit recordings at their native sample rate, untouched, with complete metadata (JSONL + CSV), sessions, coverage report and your consent statement.",
        "sample_rates": [0], "default_rate": 0, "note": "Keep this as your backup and as the source for any future model.",
    },
    "reference": {
        "title": "Zero-shot reference pack (IndicF5, F5-TTS, Chatterbox, CosyVoice, ElevenLabs Instant)",
        "summary": "Your best 5–15 s clips per language, emotion and style, each with an exact transcript (.txt) — the input zero-shot cloning models need.",
        "sample_rates": [24000, 44100, 48000], "default_rate": 24000, "note": "More audio does not help zero-shot models; clean, representative reference clips do.",
    },
    "elevenlabs": {
        "title": "ElevenLabs Professional / Instant Voice Clone upload",
        "summary": "Approved speech joined into per-language files (MP3 192 kbps as ElevenLabs recommends, WAV if FFmpeg is missing), levels around −20 dB RMS with peaks ≤ −3 dBFS, plus a 1–2 minute Instant-clone sample.",
        "sample_rates": [44100], "default_rate": 44100, "note": "Professional cloning needs at least 30 minutes (ideally 2 h+) and a live voice verification on their site. Paid plan; audio is uploaded to their servers.",
    },
    "ljspeech": {
        "title": "LJSpeech format (Coqui TTS, Piper, StyleTTS2, VITS)",
        "summary": "wavs/ + metadata.csv (id|text|normalised text), mono 16-bit.",
        "sample_rates": [22050, 24000, 44100], "default_rate": 22050, "note": "",
    },
    "f5tts": {
        "title": "F5-TTS / IndicF5 fine-tuning set",
        "summary": "wavs/ at 24 kHz + metadata.csv with the audio_file|text header used by F5-TTS's dataset preparation.",
        "sample_rates": [24000], "default_rate": 24000, "note": "Check model licences: the official F5-TTS base weights are CC-BY-NC (non-commercial), and that restriction carries into fine-tunes.",
    },
    "xtts": {
        "title": "Coqui XTTS-v2 fine-tuning set",
        "summary": "wavs/ at 22.05 kHz + metadata_train.csv / metadata_eval.csv (audio_file|text|speaker_name).",
        "sample_rates": [22050], "default_rate": 22050, "note": "XTTS-v2 weights are under the Coqui Public Model Licence (non-commercial).",
    },
    "azure": {
        "title": "Azure AI Speech custom/professional voice",
        "summary": "24 kHz 16-bit mono WAVs + transcript.txt (file id <tab> text) in Azure's training-data layout.",
        "sample_rates": [24000, 48000], "default_rate": 24000, "note": "Professional voice is a limited-access service: Microsoft requires an application and a recorded consent statement.",
    },
    "manifest": {
        "title": "Generic JSONL manifest (NeMo / ESPnet / custom training)",
        "summary": "wavs/ + manifest.jsonl with audio_filepath, text, duration, language, emotion, style, quality and session for every take.",
        "sample_rates": [16000, 22050, 24000, 44100, 48000], "default_rate": 24000, "note": "",
    },
}

NAME_RE = re.compile(r"^\d{8}-\d{6}_[a-z0-9]+$")
TRAIN_LANGS = ("en", "hi", "hinglish")


def _export_dir(st, profile: str) -> Path:
    name = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "_" + profile
    d = st.s.exports_dir / name
    d.mkdir(parents=True, exist_ok=False)
    return d


def _process(t: Take, path: Path, target_sr: int, target_db: float = -20.0, ceiling_db: float = -1.0, pad: float = 0.15) -> tuple[np.ndarray, int]:
    audio, sr = read_audio(path)
    segs = t.analysis.get("segments") or []
    if segs:
        a = max(0, int((segs[0][0] - pad) * sr))
        b = min(len(audio), int((segs[-1][1] + pad) * sr))
        audio = audio[a:b]
    audio = audio - float(np.mean(audio)) if audio.size else audio
    lvl = t.analysis.get("speech_level_dbfs")
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if lvl is not None and lvl > -100 and peak > 0:
        gain_db = min(target_db - lvl, ceiling_db - 20 * np.log10(peak))
        audio = audio * (10 ** (gain_db / 20))
    fade = min(len(audio) // 4, int(0.005 * sr))
    if fade > 1:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        audio[:fade] *= ramp
        audio[-fade:] *= ramp[::-1]
    if target_sr and target_sr != sr:
        audio, sr = resample(audio, sr, target_sr), target_sr
    return np.clip(audio, -1.0, 1.0).astype(np.float32), sr


def _text(t: Take) -> str:
    return (t.transcript or t.spoken or t.text).strip().replace("\n", " ")


def _meta_row(t: Take, file: str, seconds: float, sr: int) -> dict:
    return {
        "id": f"{t.exercise_id}__{t.id}", "file": file, "text": _text(t), "displayed_text": t.text, "spoken_form": t.spoken,
        "transcript_source": t.transcript_source, "language": t.lang, "category": t.category, "module": t.module, "exercise_id": t.exercise_id,
        "kind": t.kind, "emotion": t.emotion, "style": t.style, "pace": t.pace, "volume": t.volume, "duration": round(seconds, 3), "sample_rate": sr,
        "quality_score": t.quality.score, "quality_verdict": t.quality.verdict, "snr_db": t.analysis.get("snr_db"),
        "pitch_median_hz": (t.analysis.get("pitch") or {}).get("median_hz"), "status": t.status, "session_id": t.session_id,
        "recorded_at": t.created_at, "device": t.capture.device_label, "original_sha256": t.audio.sha256,
    }


def _write_meta(d: Path, rows: list[dict]) -> None:
    with open(d / "metadata.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if rows:
        with open(d / "metadata_full.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


def _readme(d: Path, profile: str, st, rows: list[dict], warnings: list[str], extra: str = "") -> None:
    p = PROFILES[profile]
    prof = st.profile()
    langs = {l: round(sum(r["duration"] for r in rows if r["language"] == l) / 60, 1) for l in TRAIN_LANGS}
    txt = f"""# {p['title']}

Exported by {PRODUCT_NAME} v{__version__} on {datetime.now(timezone.utc).isoformat(timespec='seconds')}.

Speaker: {prof.speaker_name or '(name not set)'} · consent confirmed in the studio: {'yes, ' + prof.consent_at if prof.consent_given else 'no'}

{p['summary']}

* takes: {len(rows)}
* minutes: {round(sum(r['duration'] for r in rows) / 60, 1)} (English {langs['en']}, Hindi {langs['hi']}, Hinglish {langs['hinglish']})
* language codes: en = English (Indian English), hi = Hindi, hinglish = Hindi-English code-switching
  (Hindi words in Devanagari, English words in Latin script)

{p.get('note') or ''}
{extra}
Every row in metadata.jsonl links back to the original recording by `original_sha256`.
{('Warnings: ' + ' '.join(warnings)) if warnings else ''}
"""
    (d / "README.md").write_text(txt, encoding="utf-8")


def _zip(d: Path) -> Path:
    z = d.with_suffix(".zip")
    with zipfile.ZipFile(z, "w") as zf:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                comp = zipfile.ZIP_STORED if f.suffix in (".wav", ".mp3") else zipfile.ZIP_DEFLATED
                zf.write(f, f"{d.name}/{f.relative_to(d).as_posix()}", compress_type=comp)
    return z


def select_takes(st, include_pending: bool = False, training: bool = True) -> list[Take]:
    statuses = {"approved", "pending"} if include_pending else {"approved"}
    takes = [t for t in st.store.takes() if t.status in statuses and not t.trashed]
    if training:
        takes = [t for t in takes if t.train and t.lang in TRAIN_LANGS and (t.analysis.get("speech_seconds") or 0) > 0.3 and _text(t)]
    return takes


def run_export(st, profile: str, options: dict) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"unknown export profile {profile!r}; choose one of {', '.join(PROFILES)}")
    p = PROFILES[profile]
    sr = int(options.get("sample_rate") or p["default_rate"])
    if p["sample_rates"] and sr not in p["sample_rates"]:
        sr = p["default_rate"]
    include_pending = bool(options.get("include_pending"))
    warnings: list[str] = []
    if include_pending:
        warnings.append("Includes takes you have not reviewed yet.")
    if profile == "master":
        return _export_master(st, include_pending, warnings)
    takes = select_takes(st, include_pending)
    if not takes:
        raise ValueError("No approved training takes yet. Approve some recordings first (or tick “include pending”).")
    unreviewed = [t for t in takes if t.kind == "prompt" and not t.transcript_reviewed]
    if unreviewed:
        warnings.append(f"{len(unreviewed)} spontaneous take(s) use an unreviewed speech-recognition transcript.")
    d = _export_dir(st, profile)
    fn = {"reference": _export_reference, "elevenlabs": _export_elevenlabs}.get(profile, _export_training)
    rows, extra = fn(st, profile, takes, d, sr, warnings)
    _write_meta(d, rows)
    _readme(d, profile, st, rows, warnings, extra)
    summary = {"name": d.name, "profile": profile, "takes": len(rows), "seconds": round(sum(r["duration"] for r in rows), 1),
               "sample_rate": sr, "warnings": warnings, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (d / "export.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    z = _zip(d)
    st.store.log("export.created", name=d.name, profile=profile, takes=len(rows))
    return {**summary, "path": str(d), "zip": str(z), "download": f"/api/exports/{d.name}/download"}


def _export_training(st, profile: str, takes: list[Take], d: Path, sr: int, warnings: list[str]):
    wavs = d / "wavs"
    rows = []
    for t in takes:
        audio, out_sr = _process(t, st.store.audio_path(t), sr)
        name = f"{t.exercise_id}__{t.id}"
        write_wav(wavs / f"{name}.wav", audio, out_sr)
        rows.append(_meta_row(t, f"wavs/{name}.wav", len(audio) / out_sr, out_sr))
    extra = ""
    if profile == "ljspeech":
        with open(d / "metadata.csv", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(f"{r['id']}|{r['text'].replace('|', ' ')}|{(r['spoken_form'] or r['text']).replace('|', ' ')}\n")
        extra = "metadata.csv: `id|transcription|normalised transcription` (numbers already spelled out where the exercise specified how to say them)."
    elif profile == "f5tts":
        with open(d / "metadata.csv", "w", encoding="utf-8") as f:
            f.write("audio_file|text\n")
            for r in rows:
                f.write(f"{r['file']}|{r['text'].replace('|', ' ')}\n")
        extra = "metadata.csv uses F5-TTS's `audio_file|text` header (relative paths). Run its prepare_csv_wavs script on this folder."
    elif profile == "xtts":
        speaker = re.sub(r"\W+", "_", st.profile().speaker_name.strip().lower()) or "me"
        for fname, part in (("metadata_train.csv", [r for i, r in enumerate(rows) if i % 20 != 19]), ("metadata_eval.csv", [r for i, r in enumerate(rows) if i % 20 == 19])):
            with open(d / fname, "w", encoding="utf-8") as f:
                f.write("audio_file|text|speaker_name\n")
                for r in part:
                    f.write(f"{r['file']}|{r['text'].replace('|', ' ')}|{speaker}\n")
        extra = "Every 20th take is held out in metadata_eval.csv."
    elif profile == "azure":
        with open(d / "transcript.txt", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(f"{r['id']}\t{r['text']}\n")
        extra = "transcript.txt: one line per WAV, `file id<TAB>text`. Upload the wavs folder (zipped) and the transcript file; include your recorded consent statement (in the Master archive)."
    elif profile == "manifest":
        with open(d / "manifest.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"audio_filepath": r["file"], "text": r["text"], "duration": r["duration"], "lang": r["language"],
                                    "emotion": r["emotion"], "style": r["style"], "speaker": "me", "quality": r["quality_score"],
                                    "session": r["session_id"]}, ensure_ascii=False) + "\n")
    return rows, extra


def _export_reference(st, profile: str, takes: list[Take], d: Path, sr: int, warnings: list[str]):
    groups: dict[tuple, list[Take]] = {}
    for t in takes:
        sec = usable_seconds(t)
        if not 5.0 <= sec <= 15.5 or t.quality.verdict == "rerecord":
            continue
        if t.asr.match is not None and t.asr.match.verdict != "read":
            continue  # a reference transcript must be exact
        key = (t.lang, t.emotion if t.emotion != "neutral" else t.style)
        groups.setdefault(key, []).append(t)
    rows = []
    index = io.StringIO()
    w = csv.writer(index)
    w.writerow(["language", "group", "file", "transcript", "score", "seconds"])
    for (lang, grp), ts in sorted(groups.items()):
        for t in sorted(ts, key=lambda x: -x.quality.score)[:3]:
            audio, out_sr = _process(t, st.store.audio_path(t), sr, pad=0.1)
            rel = f"{lang}/{grp}/{t.exercise_id}__{t.id}"
            write_wav(d / f"{rel}.wav", audio, out_sr)
            (d / f"{rel}.txt").write_text(_text(t) + "\n", encoding="utf-8")
            rows.append(_meta_row(t, f"{rel}.wav", len(audio) / out_sr, out_sr))
            w.writerow([lang, grp, f"{rel}.wav", _text(t), t.quality.score, round(len(audio) / out_sr, 2)])
    (d / "references.csv").write_text(index.getvalue(), encoding="utf-8")
    if not rows:
        warnings.append("No take met the reference criteria yet (5–15 s, not flagged for re-recording, read-check passed).")
    for lang in TRAIN_LANGS:
        if not any(r["language"] == lang and r["emotion"] == "neutral" for r in rows):
            warnings.append(f"No neutral {lang} reference clip yet.")
    return rows, ("Each folder is language/emotion-or-style. Give a zero-shot model one clip and its .txt transcript; "
                  "choose the clip whose language and delivery match the narration you want. Test several: they differ.")


def _export_elevenlabs(st, profile: str, takes: list[Take], d: Path, sr: int, warnings: list[str]):
    ffmpeg = st.s.ffmpeg_bin
    if not ffmpeg:
        warnings.append("FFmpeg not found: files are WAV instead of the MP3 192 kbps ElevenLabs recommends.")
    gap = np.zeros(int(0.6 * sr), dtype=np.float32)
    rows = []
    total = sum(usable_seconds(t) for t in takes) / 60
    if total < 30:
        warnings.append(f"Only {total:.0f} min of approved speech: Professional Voice Cloning needs at least 30 min (2 h+ recommended). The Instant-clone sample is usable now.")

    def emit(name: str, parts: list[np.ndarray]) -> str:
        audio = np.concatenate(parts) if parts else np.zeros(1, np.float32)
        wav = d / f"{name}.wav"
        write_wav(wav, audio, sr)
        if ffmpeg:
            mp3 = d / f"{name}.mp3"
            r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3)], capture_output=True)
            if r.returncode == 0:
                wav.unlink()
                return mp3.name
            warnings.append(f"MP3 encoding failed for {name}; kept WAV.")
        return wav.name

    for lang in TRAIN_LANGS:
        ts = [t for t in takes if t.lang == lang]
        part, part_len, idx = [], 0.0, 1
        for t in ts:
            audio, _ = _process(t, st.store.audio_path(t), sr, target_db=-20.0, ceiling_db=-3.0)
            part += [audio, gap]
            part_len += len(audio) / sr
            rows.append(_meta_row(t, f"pvc_{lang}_{idx:02d}", len(audio) / sr, sr))
            if part_len >= 600:  # ~10 minute files keep uploads manageable
                fname = emit(f"pvc_{lang}_{idx:02d}", part)
                for r in rows:
                    if r["file"] == f"pvc_{lang}_{idx:02d}":
                        r["file"] = fname
                part, part_len, idx = [], 0.0, idx + 1
        if part:
            fname = emit(f"pvc_{lang}_{idx:02d}", part)
            for r in rows:
                if r["file"] == f"pvc_{lang}_{idx:02d}":
                    r["file"] = fname
    # Instant clone: ~90 s of the best neutral speech, mixing the languages you use
    best = sorted([t for t in takes if t.emotion == "neutral" and t.quality.score >= 80], key=lambda t: -t.quality.score)
    chosen, secs = [], 0.0
    for t in best:
        if secs >= 90:
            break
        chosen.append(t)
        secs += usable_seconds(t)
    if chosen:
        parts = []
        for t in chosen:
            a, _ = _process(t, st.store.audio_path(t), sr, target_db=-20.0, ceiling_db=-3.0)
            parts += [a, gap]
        emit("ivc_sample", parts)
    else:
        warnings.append("No neutral take scored 80+ yet for the Instant-clone sample.")
    return rows, ("Upload the pvc_* files for a Professional Voice Clone (same mic and style throughout is what ElevenLabs asks for), "
                  "or ivc_sample for an Instant Voice Clone. Only upload if you accept their terms; the audio leaves your computer.")


def _export_master(st, include_pending: bool, warnings: list[str]) -> dict:
    statuses = {"approved", "pending"} if include_pending else {"approved"}
    takes = [t for t in st.store.takes() if t.status in statuses]
    consent = [t for t in st.store.takes() if t.category == "consent" and t.status != "rejected"]
    takes = takes + [t for t in consent if t not in takes]
    if not takes:
        raise ValueError("No approved takes yet.")
    d = _export_dir(st, "master")
    rows = []
    for t in takes:
        src = st.store.audio_path(t)
        dst = d / "recordings" / t.category / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        shutil.copy2(src.with_suffix(".json"), dst.with_suffix(".json"))
        rows.append(_meta_row(t, f"recordings/{t.category}/{src.name}", t.audio.duration, t.audio.sample_rate))
    _write_meta(d, rows)
    (d / "sessions.json").write_text(json.dumps([s.model_dump() for s in st.store.sessions()], indent=2, ensure_ascii=False), encoding="utf-8")
    cov = Coverage(st.bank, st.store.takes(), st.store.sessions()).summary()
    (d / "coverage.json").write_text(json.dumps(cov, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "profile.json").write_text(st.profile().model_dump_json(indent=2), encoding="utf-8")
    _readme(d, "master", st, rows, warnings, "Folders follow the dataset categories. Each WAV has its full JSON sidecar (exercise, analysis, quality, read-check, capture settings).")
    summary = {"name": d.name, "profile": "master", "takes": len(rows), "seconds": round(sum(r["duration"] for r in rows), 1), "sample_rate": 0,
               "warnings": warnings, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (d / "export.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    z = _zip(d)
    st.store.log("export.created", name=d.name, profile="master", takes=len(rows))
    return {**summary, "path": str(d), "zip": str(z), "download": f"/api/exports/{d.name}/download"}


def list_exports(st) -> list[dict]:
    out = []
    for f in sorted(st.s.exports_dir.glob("*/export.json"), reverse=True):
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        info["zip"] = f.parent.with_suffix(".zip").exists()
        out.append(info)
    return out


def export_zip_path(st, name: str) -> Path:
    if not NAME_RE.match(name or ""):
        raise ValueError("invalid export name")
    p = st.s.exports_dir / f"{name}.zip"
    if not p.exists():
        raise ValueError("export not found")
    return p
