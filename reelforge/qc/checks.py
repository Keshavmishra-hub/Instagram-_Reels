"""Quality control before export. A reel is only marked complete when no critical check fails."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import soundfile as sf

from ..config import Settings, settings as default_settings
from ..models import QCCheck, QCReport
from ..render.master import loudness, probe
from ..research.fetch import fetch
from ..script.validate import CLICKBAIT, validate_script
from ..storage import ProjectStore
from ..storyboard.planner import validate_storyboard

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skipped"


class QC:
    def __init__(self, pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print, live_sources: bool = True):
        self.pid, self.store, self.s, self.log = pid, store, s, log
        self.d = store.dir(pid)
        self.project = store.project(pid)
        self.research = store.research(pid)
        self.script = store.script(pid)
        self.sb = store.storyboard(pid)
        self.tl = store.timeline(pid)
        self.lib = store.assets(pid)
        self.pkg = store.package(pid)
        self.video = self.d / "output/reel.mp4"
        self.props = store.read_json(pid, "render/props.json") or {}
        self.live_sources = live_sources
        self.checks: list[QCCheck] = []

    def add(self, cid: str, name: str, severity: str, status: str, details: str, **data) -> None:
        self.checks.append(QCCheck(id=cid, name=name, severity=severity, status=status, details=details, data=data))
        self.log(f"QC {status.upper():7} [{severity}] {name}: {details}")

    # ------------------------------------------------------------------ content integrity
    def check_research(self) -> None:
        r = self.research
        if r is None:
            return self.add("research", "Research is sufficient", "critical", FAIL, "No research file.")
        if not r.sufficiency.enough:
            return self.add("research", "Research is sufficient", "critical", FAIL, r.sufficiency.reason or "Research marked insufficient.")
        v = sum(1 for c in r.claims if c.status == "verified")
        single = sum(1 for c in r.claims if c.status == "single_source")
        self.add("research", "Research is sufficient", "critical", PASS,
                 f"{v} claims corroborated by independent/official sources and {single} single-source claims, from {len(r.sources)} sources.")

    def check_claims(self) -> None:
        if not self.script:
            return self.add("claims", "All factual claims are supported", "critical", FAIL, "No script.")
        issues = validate_script(self.script, self.research, self.project.settings.duration)
        if self.sb:
            issues += validate_storyboard(self.sb, self.script, self.research)
        grounding_codes = {"uncited", "unknown_claim", "unverified_claim", "dispute_as_fact", "number_unsupported",
                           "graphic_number_unsupported", "quote_unverified", "map_coords", "beat_coverage"}
        errors = [i for i in issues if i.severity == "error" and i.code in grounding_codes]
        single = [i for i in issues if i.code in ("single_source", "estimate_as_exact")]
        used = {c for b in self.script.beats for c in b.claim_ids}
        single_claims = sorted(c for c in used if self.research and self.research.claim(c) and self.research.claim(c).status == "single_source")
        if errors:
            self.add("claims", "All factual claims are supported", "critical", FAIL, "; ".join(f"{i.beat_id}: {i.message}" for i in errors[:6]), issues=[i.model_dump() for i in errors])
        elif single:
            self.add("claims", "All factual claims are supported", "critical", WARN, "; ".join(f"{i.beat_id}: {i.message}" for i in single[:4]))
        elif single_claims:
            self.add("claims", "All factual claims are supported", "critical", WARN,
                     f"Every factual sentence cites checked claims ({len(used)} used) and every on-screen number is backed, but "
                     f"{len(single_claims)} claim(s) rest on a single source ({', '.join(single_claims)}); the source is attributed in the narration. "
                     "Corroborate with an independent or official source when possible.")
        else:
            self.add("claims", "All factual claims are supported", "critical", PASS, f"Every factual sentence cites verified claims ({len(used)} claims used); all on-screen numbers are backed.")

    def check_sources(self) -> None:
        if not (self.research and self.script):
            return self.add("sources", "Sources are accessible and relevant", "critical", FAIL, "Missing research or script.")
        used_ids = []
        for b in self.script.beats:
            for cid in b.claim_ids:
                c = self.research.claim(cid)
                if c:
                    used_ids += [e.source_id for e in c.evidence if e.verification in ("exact", "fuzzy", "agent_attested")]
        used = [self.research.source(i) for i in dict.fromkeys(used_ids) if self.research.source(i)]
        no_snapshot = [s.id for s in used if s.snapshot_kind == "none" or not s.snapshot_file or not (self.d / s.snapshot_file).exists()]
        attested_only = []
        for b in self.script.beats:
            for cid in b.claim_ids:
                c = self.research.claim(cid)
                if c and c.evidence and all(e.verification in ("agent_attested", "not_found", "unchecked") for e in c.evidence):
                    attested_only.append(cid)
        dead, unreachable, ok = [], [], []
        if self.live_sources:
            for src in used:
                res = fetch(src.url, self.s)
                if res.status and 200 <= res.status < 400:
                    ok.append(src.id)
                elif res.status in (404, 410):
                    dead.append(f"{src.id} (HTTP {res.status})")
                else:
                    unreachable.append(f"{src.id} ({'network policy' if res.blocked_by_network else (res.error or res.status)})")
        if no_snapshot or dead:
            return self.add("sources", "Sources are accessible and relevant", "critical", FAIL,
                            f"Sources without a retrieved copy: {no_snapshot or '-'}; dead links: {dead or '-'}.")
        msgs = [f"{len(used)} cited sources, each with a stored snapshot of the text that was read."]
        status = PASS
        if ok:
            msgs.append(f"Live re-check OK for {len(ok)}.")
        if unreachable:
            status = WARN
            msgs.append(f"Could not re-check from this machine: {', '.join(unreachable[:6])}.")
        if attested_only:
            status = WARN
            msgs.append(f"Claims {', '.join(sorted(set(attested_only)))} are verified against researcher-captured excerpts only; run `python -m reelforge verify-sources {self.pid}` on a networked machine to confirm against full pages.")
        self.add("sources", "Sources are accessible and relevant", "critical", status, " ".join(msgs), used=[s.id for s in used])

    def check_language(self) -> None:
        texts = [b.text for b in (self.script.beats if self.script else [])]
        texts += [str(sc.visual.params.get("text", "")) for sc in (self.sb.scenes if self.sb else [])]
        if self.pkg:
            texts += [self.pkg.caption, self.pkg.title, self.pkg.pinned_comment]
        hits = sorted({p for t in texts for p in CLICKBAIT if p in (t or "").lower()})
        if hits:
            self.add("integrity_language", "No misleading clickbait or hype", "major", WARN, f"Review phrasing: {', '.join(hits)}")
        else:
            self.add("integrity_language", "No misleading clickbait or hype", "major", PASS, "No hype/clickbait phrases found in narration, on-screen text or caption.")

    def check_spelling(self) -> None:
        if not self.script:
            return
        issues = [i for i in validate_script(self.script, self.research, self.project.settings.duration) if i.code in ("spelling", "repeated_word")]
        if self.script.language != "en":
            return self.add("spelling", "Spelling and grammar", "major", SKIP, "Automatic spell-check is available for English; review manually.")
        if issues:
            self.add("spelling", "Spelling and grammar", "major", WARN, "; ".join(i.message for i in issues[:6]))
        else:
            self.add("spelling", "Spelling and grammar", "major", PASS, "No spelling issues or repeated words found in the narration.")

    # ------------------------------------------------------------------ narration + subtitles
    def check_sync_and_narration(self) -> None:
        if not self.tl:
            return self.add("sync", "Narration and subtitles are synchronised", "critical", FAIL, "No timeline.")
        from ..voice.align import match_words, speech_mask
        from ..voice.asr import transcribe

        audio, sr = sf.read(self.d / self.tl.narration_file, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        try:
            asr_words, engine = transcribe(audio, sr, self.project.settings.language, self.s)
        except Exception as e:
            # structural fallback: every subtitle cue must sit on detected speech
            mask = speech_mask(audio, sr)
            bad = 0
            for c in self.tl.cues:
                a, b = int(c.start / 0.01), max(int(c.start / 0.01) + 1, int(min(c.end, self.tl.duration) / 0.01))
                seg = mask[a:b]
                if seg.size and seg.mean() < 0.4:
                    bad += 1
            status = PASS if bad == 0 else (WARN if bad <= 2 else FAIL)
            self.add("sync", "Narration and subtitles are synchronised", "critical", status,
                     f"Structural check only (no speech recogniser: {e}); {bad} of {len(self.tl.cues)} cues off speech.")
            return self.add("narration", "Narration matches the script", "major", SKIP, "Install a speech recogniser to verify pronunciation.")
        # compare at word level; hyphenated display tokens ("terawatt-hours") are split like the recogniser writes them
        parts: list[tuple[int, str]] = []
        for i, w in enumerate(self.tl.words):
            for k, piece in enumerate(re.split(r"(?<=[A-Za-z])-(?=[A-Za-z])", w.text)):
                parts.append((i if k == 0 else -1, piece))
        part_map = match_words([p for _, p in parts], asr_words)
        mapping = [None] * len(self.tl.words)
        for (wi, _), m in zip(parts, part_map):
            if wi >= 0:
                mapping[wi] = m
        script_words = [w.text for w in self.tl.words]
        offsets = [self.tl.words[i].start - asr_words[m].start for i, m in enumerate(mapping) if m is not None]
        matched = len(offsets) / max(1, len(script_words))
        if not offsets:
            return self.add("sync", "Narration and subtitles are synchronised", "critical", FAIL, f"ASR ({engine}) could not match the narration.")
        absd = np.abs(np.array(offsets))
        med, p90 = float(np.median(absd)), float(np.percentile(absd, 90))
        status = PASS if (med <= 0.15 and p90 <= 0.35) else (WARN if p90 <= 0.6 else FAIL)
        self.add("sync", "Narration and subtitles are synchronised", "critical", status,
                 f"Independent ASR ({engine}): median |offset| {med * 1000:.0f} ms, 90th percentile {p90 * 1000:.0f} ms over {len(offsets)} matched words.",
                 median_ms=round(med * 1000), p90_ms=round(p90 * 1000))
        # narration accuracy: unmatched script words (ignoring numbers/symbol tokens the ASR writes differently)
        unmatched = [script_words[i] for i, m in enumerate(mapping) if m is None and not re.search(r"\d|[%°$₹€£]", script_words[i])]
        wer_like = len(unmatched) / max(1, len(script_words))
        status = PASS if wer_like <= 0.08 else (WARN if wer_like <= 0.2 else FAIL)
        hint = f" Words the recogniser did not hear as written (check pronunciation): {', '.join(unmatched[:10])}." if unmatched else ""
        self.add("narration", "Narration matches the script (clear audio, pronunciation)", "major", status,
                 f"{matched * 100:.0f}% of subtitle words matched the recognised speech.{hint}", unmatched=unmatched)
        store_rel = "output/asr_transcript.txt"
        self.store.write_text(self.pid, store_rel, " ".join(w.text for w in asr_words) + "\n")

    def check_subtitles(self) -> None:
        if not self.tl:
            return
        cues = self.tl.cues
        covered = {i for c in cues for i in c.word_indices}
        coverage = len(covered) / max(1, len(self.tl.words))
        long_cues = [c.text for c in cues if len(c.text) > 30]
        fast = [c.text for c in cues if (c.end - c.start) > 0 and len(c.text) / (c.end - c.start) > 25]
        short = [c.text for c in cues if (c.end - c.start) < 0.3]
        hook_text = any(c.start < 3.0 for c in cues)
        problems = []
        if coverage < 0.98:
            problems.append(f"only {coverage * 100:.0f}% of words subtitled")
        if long_cues:
            problems.append(f"{len(long_cues)} long cue(s)")
        if fast:
            problems.append(f"{len(fast)} cue(s) faster than 25 chars/s")
        if short:
            problems.append(f"{len(short)} cue(s) shorter than 0.3 s")
        crit_fail = coverage < 0.9 or not hook_text
        status = FAIL if crit_fail else (WARN if problems else PASS)
        self.add("silent_viewing", "Understandable without sound", "critical", status,
                 (f"Word-by-word captions cover {coverage * 100:.0f}% of the narration; text on screen from {cues[0].start:.1f}s; key numbers highlighted."
                  if cues else "No subtitles.") + (f" Issues: {', '.join(problems)}." if problems else ""))

    def check_audio(self) -> None:
        if not self.video.exists():
            return self.add("audio", "Audio is clear and well balanced", "major", FAIL, "No video file.")
        try:
            ld = loudness(self.video, self.s)
        except Exception as e:
            return self.add("audio", "Audio is clear and well balanced", "major", FAIL, f"Loudness analysis failed: {e}")
        i_lufs, tp = float(ld["input_i"]), float(ld["input_tp"])
        self.add("clipping", "Audio does not clip", "critical", PASS if tp <= 0.0 else FAIL,
                 f"True peak of the encoded file: {tp:.1f} dBTP" + (" (inter-sample clipping on playback)." if tp > 0 else "."))
        notes = [f"Integrated {i_lufs:.1f} LUFS, true peak {tp:.1f} dBTP"]
        status = PASS
        if not (-15.5 <= i_lufs <= -12.5):
            status = WARN
            notes.append("loudness outside -14 ±1.5 LUFS")
        if tp > -0.9:
            status = WARN
            notes.append("true peak above -1 dBTP")
        stem = self.d / "audio/stems/music_ducked.wav"
        if stem.exists():
            v, sr = sf.read(self.d / self.tl.narration_file, dtype="float32")
            m, _ = sf.read(stem, dtype="float32")
            m = m.mean(axis=1) if m.ndim > 1 else m
            n = min(len(v), len(m))
            fr = int(0.05 * sr)
            k = n // fr
            if k > 0:
                vr = np.sqrt((v[: k * fr].reshape(k, fr) ** 2).mean(1) + 1e-12)
                mr = np.sqrt((m[: k * fr].reshape(k, fr) ** 2).mean(1) + 1e-12)
                sp = 20 * np.log10(vr) > 20 * np.log10(vr.max()) - 30
                if sp.any():
                    ratio = float(np.median(20 * np.log10(vr[sp] / mr[sp])))
                    notes.append(f"voice sits {ratio:.0f} dB above the music during speech")
                    if not (11 <= ratio <= 28):
                        status = WARN
                        notes.append("music balance outside the 11-28 dB window")
        # long silences inside the reel (excluding the final tail)
        proc = subprocess.run([self.s.ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(self.video), "-af", "silencedetect=n=-45dB:d=1.6", "-f", "null", "-"],
                              capture_output=True, text=True)
        sil = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
        sil = [x for x in sil if x < (self.tl.duration - 2.0 if self.tl else 1e9)]
        if sil:
            status = WARN
            notes.append(f"silence > 1.6 s at {', '.join(f'{x:.1f}s' for x in sil)}")
        self.add("audio", "Audio is clear and well balanced", "major", status, "; ".join(notes) + ".")

    # ------------------------------------------------------------------ technical
    def check_video_specs(self) -> None:
        if not self.video.exists():
            return self.add("specs", "Technical specs (1080x1920, 30 fps, H.264/AAC MP4)", "critical", FAIL, "No video file.")
        info = probe(self.video, self.s)
        v = next((st for st in info["streams"] if st["codec_type"] == "video"), {})
        a = next((st for st in info["streams"] if st["codec_type"] == "audio"), {})
        problems = []
        if (v.get("width"), v.get("height")) != (1080, 1920):
            problems.append(f"resolution {v.get('width')}x{v.get('height')}")
        if v.get("r_frame_rate") != "30/1" or v.get("avg_frame_rate") not in ("30/1",):
            problems.append(f"frame rate {v.get('r_frame_rate')} / {v.get('avg_frame_rate')}")
        if v.get("codec_name") != "h264":
            problems.append(f"video codec {v.get('codec_name')}")
        if v.get("pix_fmt") != "yuv420p":
            problems.append(f"pixel format {v.get('pix_fmt')}")
        if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000" or a.get("channels") != 2:
            problems.append(f"audio {a.get('codec_name')} {a.get('sample_rate')} Hz {a.get('channels')} ch")
        fmt = info.get("format", {})
        if "mp4" not in fmt.get("format_name", ""):
            problems.append(f"container {fmt.get('format_name')}")
        dur = float(fmt.get("duration", 0))
        if self.tl and abs(dur - self.tl.duration) > 0.5:
            problems.append(f"duration {dur:.2f}s vs narration {self.tl.duration:.2f}s")
        faststart = self._faststart()
        if not faststart:
            problems.append("moov atom not at the start (no faststart)")
        details = (f"{v.get('width')}x{v.get('height')}, {v.get('r_frame_rate')} fps, {v.get('codec_name')} {v.get('profile')} "
                   f"{v.get('pix_fmt')}, {a.get('codec_name')} {a.get('sample_rate')} Hz stereo, {dur:.2f}s, faststart={faststart}")
        self.add("specs", "Technical specs (1080x1920, 30 fps, H.264/AAC MP4)", "critical", FAIL if problems else PASS,
                 details + (f". Problems: {'; '.join(problems)}" if problems else "."))

    def _faststart(self) -> bool:
        with open(self.video, "rb") as f:
            order = []
            while len(order) < 12:
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                size = int.from_bytes(hdr[:4], "big")
                typ = hdr[4:8].decode("latin-1")
                order.append(typ)
                if size == 1:
                    size = int.from_bytes(f.read(8), "big")
                    f.seek(size - 16, 1)
                elif size == 0:
                    break
                else:
                    f.seek(size - 8, 1)
        return "moov" in order and "mdat" in order and order.index("moov") < order.index("mdat")

    def check_decode(self) -> None:
        if not self.video.exists():
            return self.add("decode", "Video plays correctly (full decode)", "critical", FAIL, "No video file.")
        proc = subprocess.run([self.s.ffmpeg_bin, "-v", "error", "-i", str(self.video), "-f", "null", "-"], capture_output=True, text=True)
        cnt = subprocess.run([self.s.ffprobe_bin, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
                              "-of", "csv=p=0", str(self.video)], capture_output=True, text=True)
        frames = int((cnt.stdout.strip() or "0").split(",")[0] or 0)
        expected = round((self.tl.duration if self.tl else 0) * 30)
        errs = proc.stderr.strip()
        ok = proc.returncode == 0 and not errs and abs(frames - expected) <= 2
        self.add("decode", "Video plays correctly (full decode)", "critical", PASS if ok else FAIL,
                 f"Decoded {frames} frames (expected {expected}) with {'no errors' if not errs else 'errors: ' + errs[:300]}.")

    def check_black_frozen(self) -> None:
        if not self.video.exists():
            return
        proc = subprocess.run([self.s.ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(self.video), "-vf",
                               "blackdetect=d=0.2:pix_th=0.02:pic_th=0.97,freezedetect=n=0.002:d=2.5", "-an", "-f", "null", "-"],
                              capture_output=True, text=True)
        black = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", proc.stderr)
        frozen = re.findall(r"freeze_start: ([\d.]+)", proc.stderr)
        if black:
            self.add("black_frames", "No black frames or rendering gaps", "critical", FAIL, f"Black segments at {', '.join(f'{a}-{b}s' for a, b in black)}.")
        elif frozen:
            self.add("black_frames", "No black frames or rendering gaps", "critical", WARN, f"Frozen picture from {', '.join(frozen)}s (check the scene).")
        else:
            self.add("black_frames", "No black frames or rendering gaps", "critical", PASS, "No black or frozen segments detected.")

    def check_assets(self) -> None:
        missing, fallbacks, unlicensed, unlabeled = [], [], [], []
        for sc in (self.sb.scenes if self.sb else []):
            for vis in [sc.visual] + ([sc.background] if sc.background else []):
                if vis.kind in ("footage", "photo"):
                    a = self.lib.get(vis.asset_id)
                    if a is None:
                        fallbacks.append(sc.id)
                        continue
                    if not a.file or not (self.d / a.file).exists():
                        missing.append(f"{sc.id}:{a.id}")
                    if not a.license or (a.provider != "local" and not a.license_url):
                        unlicensed.append(f"{sc.id}:{a.id}")
        for psc in self.props.get("scenes", []):
            if (psc.get("media") or psc.get("background")) and not psc.get("label"):
                unlabeled.append(psc["id"])
        if missing:
            self.add("assets", "No missing assets", "critical", FAIL, f"Missing files: {', '.join(missing)}.")
        else:
            self.add("assets", "No missing assets", "critical", PASS if not fallbacks else WARN,
                     "All referenced media present." + (f" Scenes {', '.join(fallbacks)} use motion graphics because no licensed footage was found." if fallbacks else ""))
        if unlicensed:
            self.add("licensing", "All media is licensed and credited", "critical", FAIL, f"No licence recorded for {', '.join(unlicensed)}.")
        else:
            req = [a for a in self.lib.assets if a.attribution_required]
            credited = (self.d / "output/caption.txt").exists() and all((a.author or "")[:12] in (self.d / "output/caption.txt").read_text(encoding="utf-8") for a in req if a.id in {x.visual.asset_id for x in self.sb.scenes})
            self.add("licensing", "All media is licensed and credited", "critical", PASS if credited or not req else WARN,
                     "Every asset has a recorded licence; score is original; fonts OFL; map data public domain." + ("" if credited or not req else " Add required attributions to the caption."))
        if unlabeled:
            self.add("labels", "Illustrative/AI visuals are labelled", "critical", FAIL, f"Scenes with media but no authenticity label: {', '.join(unlabeled)}.")
        else:
            ai = [p["id"] for p in self.props.get("scenes", []) if (p.get("label") or "").startswith("AI-generated")]
            self.add("labels", "Illustrative/AI visuals are labelled", "critical", PASS,
                     "Stock media carries a 'Representative' label; documentary media carries credits" + (f"; AI visuals labelled in {ai}" if ai else "; no AI-generated visuals used") + ".")

    def check_visual_relevance(self) -> None:
        if not self.sb:
            return
        weak = []
        for sc in self.sb.scenes:
            if not sc.visual.purpose and sc.visual.kind in ("footage", "photo"):
                weak.append(f"{sc.id} (no purpose)")
            a = self.lib.get(sc.visual.asset_id) if sc.visual.kind in ("footage", "photo") else None
            if a and a.relevance < 1.0:
                weak.append(f"{sc.id} ('{a.title[:30]}' relevance {a.relevance:.1f})")
        kinds = [sc.visual.kind for sc in self.sb.scenes]
        variety = len(set(kinds))
        if weak:
            self.add("visual_relevance", "Visuals are relevant to the narration", "major", WARN, f"Review: {', '.join(weak)}.")
        else:
            self.add("visual_relevance", "Visuals are relevant to the narration", "major", PASS,
                     f"Each scene has a stated visual purpose; graphics are generated from the cited claims; {variety} different visual types used.")

    def check_pacing(self) -> None:
        if not (self.tl and self.sb):
            return
        from ..voice.narration import scene_timings

        times = scene_timings(self.sb, self.tl)
        lens = [t.end - t.start for t in times]
        kind_of = {sc.id: sc.visual.kind for sc in self.sb.scenes}
        props_scenes = {p["id"]: p for p in self.props.get("scenes", [])}
        # line charts, timelines, maps and footage keep moving for their whole duration; for the other kinds measure
        # the longest stretch without a new visual event (scene start, word-timed reveal, callout)
        static = []
        for t in times:
            if kind_of.get(t.scene_id) not in ("stat", "kinetic", "icon", "comparison", "quote", "title", "photo"):
                continue
            ps = props_scenes.get(t.scene_id, {})
            events = [t.start] + [o["at"] for o in ps.get("overlays", [])]
            for side in ("left", "right"):
                part = (ps.get("params") or {}).get(side)
                if isinstance(part, dict) and part.get("at") is not None:
                    events.append(float(part["at"]))
            events = sorted(e for e in events if t.start <= e <= t.end) + [t.end]
            static.append(max(b - a for a, b in zip(events, events[1:])))
        first_word = self.tl.words[0].start if self.tl.words else 0
        hook = self.tl.beats[0].end - self.tl.beats[0].start if self.tl.beats else 0
        notes = [f"first word at {first_word:.2f}s", f"hook lasts {hook:.1f}s", f"average shot {np.mean(lens):.1f}s", f"longest {max(lens):.1f}s"]
        status = PASS
        if first_word > 0.6 or hook > 4.5:
            status = WARN
        if static and max(static) > 6.5:
            status = WARN
            notes.append("a mostly static scene runs longer than 6.5 s")
        if max(lens) > 10:
            status = WARN
            notes.append("a scene runs longer than 10 s")
        self.add("pacing", "Hook timing and retention pacing", "major", status, ", ".join(notes) + ".")
        target = self.project.settings.duration
        dur = self.tl.duration
        st = PASS if (target * 0.7 <= dur <= target * 1.25 and dur <= 90) else WARN
        self.add("duration", "Duration fits the target", "major", st, f"{dur:.1f}s for a {target}s target.")

    def check_cover_and_caption(self) -> None:
        cover = self.d / "output/cover.jpg"
        if cover.exists():
            from PIL import Image

            with Image.open(cover) as im:
                size = im.size
            words = len((self.sb.cover.headline if self.sb and self.sb.cover else "").split())
            st = PASS if size == (1080, 1920) and words <= 7 else WARN
            self.add("cover", "Cover image", "major", st, f"{size[0]}x{size[1]}, headline {words} words, readable in the 3:4 grid crop.")
        else:
            self.add("cover", "Cover image", "major", FAIL, "cover.jpg missing.")
        cap = self.d / "output/caption.txt"
        if not cap.exists():
            return self.add("caption", "Caption, hashtags, sources", "major", FAIL, "caption.txt missing (run the package step).")
        text = cap.read_text(encoding="utf-8")
        tags = re.findall(r"(?<!\w)#\w+", text)
        problems = []
        if len(text) > 2200:
            problems.append(f"{len(text)} characters (max 2200)")
        if len(tags) > 5:
            problems.append(f"{len(tags)} hashtags (Instagram allows 5)")
        if "Sources:" not in text:
            problems.append("no sources section")
        self.add("caption", "Caption, hashtags, sources", "major", WARN if problems else PASS,
                 f"{len(text)} characters, {len(tags)} hashtags, sources included." if not problems else "; ".join(problems))

    # ------------------------------------------------------------------ run
    def run(self) -> QCReport:
        for fn in (self.check_research, self.check_claims, self.check_sources, self.check_language, self.check_spelling,
                   self.check_sync_and_narration, self.check_subtitles, self.check_audio, self.check_video_specs, self.check_decode,
                   self.check_black_frozen, self.check_assets, self.check_visual_relevance, self.check_pacing, self.check_cover_and_caption):
            try:
                fn()
            except Exception as e:  # a crashing check is itself a failure
                self.add(fn.__name__, fn.__name__.replace("check_", "").replace("_", " "), "critical", FAIL, f"Check crashed: {e}")
        crit = [c for c in self.checks if c.severity == "critical" and c.status == FAIL]
        warns = [c for c in self.checks if c.status == WARN]
        report = QCReport(video_file="output/reel.mp4", checks=self.checks, passed=not crit)
        report.summary = ("PASSED - ready to publish" if not crit else f"NOT READY - {len(crit)} critical check(s) failed") + (f"; {len(warns)} warning(s) to review." if warns else ".")
        self.store.save("qc", self.pid, report)
        self.store.write_text(self.pid, "output/qc_report.md", qc_markdown(report))
        project = self.store.project(self.pid)
        project.complete = report.passed
        project.complete_reason = report.summary
        self.store.save("project", self.pid, project)
        return report


def qc_markdown(r: QCReport) -> str:
    icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skipped": "SKIP"}
    out = [f"# Quality report", "", f"**{r.summary}**", "", f"Checked: {r.created_at}", "", "| Result | Severity | Check | Details |", "|---|---|---|---|"]
    for c in r.checks:
        out.append(f"| {icon[c.status]} | {c.severity} | {c.name} | {c.details.replace('|', '/')} |")
    return "\n".join(out) + "\n"


def run_qc(pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print, live_sources: bool = True) -> QCReport:
    return QC(pid, store, s, log, live_sources).run()
