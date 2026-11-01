"""Voice-over production: per-beat synthesis -> word timings -> narration track -> timeline."""

from __future__ import annotations

import difflib
from math import gcd
from typing import Callable, Optional

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from ..config import Settings, settings as default_settings
from ..models import BeatTiming, Script, SceneTiming, Storyboard, Timeline, Word
from ..storage import ProjectStore
from .align import align
from .normalize import Token, load_lexicon, normalize_tokens
from .providers import _trim_silence, get_provider
from .subtitles import build_cues, is_emphasis

OUT_SR = 48000
LEAD_IN = 0.12
TAIL = 1.4


def _resample(audio: np.ndarray, sr: int, target: int = OUT_SR) -> np.ndarray:
    if sr == target:
        return audio.astype(np.float32)
    g = gcd(sr, target)
    return resample_poly(audio, target // g, sr // g).astype(np.float32)


def _tokens_for_beat(text: str, spoken: Optional[str], language: str, lexicon: dict) -> tuple[list[Token], list[Token]]:
    """Returns (display tokens with spoken words, tokens actually sent to TTS)."""
    display = normalize_tokens(text, language, lexicon)
    if not spoken:
        return display, display
    say = normalize_tokens(spoken, language, lexicon)
    if len(say) == len(display):  # word-by-word respelling: keep exact mapping
        return [Token(d.display, s.spoken) for d, s in zip(display, say)], say
    # otherwise map display tokens onto spoken tokens by fuzzy sequence matching
    a = [t.display.lower().strip(".,!?;:") for t in display]
    b = [" ".join(t.spoken).lower().strip(".,!?;:") for t in say]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    owner = [None] * len(display)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for k in range(i1, i2):
            if tag == "equal":
                owner[k] = [j1 + (k - i1)]
            elif j2 > j1:
                lo = j1 + int((k - i1) * (j2 - j1) / max(1, i2 - i1))
                hi = j1 + int((k - i1 + 1) * (j2 - j1) / max(1, i2 - i1))
                owner[k] = list(range(lo, max(hi, lo + 1)))
    merged = []
    for k, d in enumerate(display):
        idxs = [j for j in (owner[k] or []) if j < len(say)]
        merged.append(Token(d.display, [w for j in idxs for w in say[j].spoken]))
    return merged, say


def _beat_gap(prev_section: str, next_section: str, prev_text: str) -> float:
    if next_section != prev_section:
        return 0.34 if next_section in ("payoff", "ending") else 0.28
    return 0.24 if prev_text.rstrip().endswith((".", "!", "?")) else 0.16


def synthesize_script(
    pid: str,
    store: ProjectStore,
    s: Settings = default_settings,
    log: Callable[[str], None] = print,
    speed_override: Optional[float] = None,
) -> Timeline:
    project = store.project(pid)
    script: Script = store.script(pid)
    if script is None or not script.beats:
        raise RuntimeError("No script to narrate")
    ns = project.settings.narration
    language = project.settings.language
    lexicon = load_lexicon(store.dir(pid) / "lexicon.yaml")
    provider = get_provider(ns.provider, s)
    speed = float(speed_override or ns.speed or 1.0)

    def run(speed: float):
        beats_audio = []
        for beat in script.beats:
            display, say = _tokens_for_beat(beat.text, beat.spoken, language, lexicon)
            log(f"Narrating {beat.id} ({beat.section}) with {ns.provider}/{ns.voice} ...")
            res = provider.synthesize(say, ns.voice, speed, language, ns.tone)
            audio, sr = res.audio, res.sample_rate
            spoken_words = [w for t in say for w in t.spoken]
            if res.word_times is None or len(res.word_times) != len(spoken_words):
                times, method = align(audio, sr, spoken_words, language, s)
            else:
                times, method = res.word_times, res.method
            # trim edge silence, keep times consistent
            trimmed, head = _trim_silence(audio, sr, thresh_db=-50)
            times = [(max(0.0, a - head), max(0.0, b - head)) for a, b in times]
            beats_audio.append((beat, display, trimmed, sr, times, method))
        return beats_audio

    beats_audio = run(speed)
    total_speech = sum(len(x[2]) / x[3] for x in beats_audio)
    target = project.settings.duration
    est_total = total_speech + LEAD_IN + TAIL + 0.25 * len(beats_audio)
    if speed_override is None and est_total > target * 1.12 and speed < 1.12:
        new_speed = round(min(1.12, speed * est_total / (target * 1.06)), 3)
        if new_speed > speed + 0.015:
            log(f"Narration runs {est_total:.1f}s vs {target}s target; re-voicing at speed {new_speed} (max 1.12 keeps it natural).")
            speed = new_speed
            beats_audio = run(speed)

    # ---- assemble ---------------------------------------------------------------------------------
    pieces = [np.zeros(int(LEAD_IN * OUT_SR), dtype=np.float32)]
    t = LEAD_IN
    words: list[Word] = []
    beat_timings: list[BeatTiming] = []
    methods = set()
    audio_dir = store.dir(pid) / "audio"
    audio_dir.mkdir(exist_ok=True)
    for k, (beat, display, audio, sr, times, method) in enumerate(beats_audio):
        methods.add(method)
        rel = f"audio/beat_{beat.id}.wav"
        sf.write(store.dir(pid) / rel, audio, sr, subtype="PCM_16")
        a48 = _resample(audio, sr)
        dur = len(a48) / OUT_SR
        beat_timings.append(BeatTiming(beat_id=beat.id, start=round(t, 3), end=round(t + dur, 3), audio_file=rel))
        # map spoken-word times onto display tokens
        wi = 0
        last_end = 0.0
        for idx, tok in enumerate(display):
            n = len(tok.spoken)
            if n == 0:
                st, en = last_end, last_end
            else:
                seg = times[wi: wi + n] if wi + n <= len(times) else times[wi:] or [(last_end, last_end)]
                st, en = seg[0][0], seg[-1][1]
                wi += n
            last_end = max(last_end, en)
            words.append(Word(
                text=tok.display, start=round(t + st, 3), end=round(t + max(en, st + 0.05), 3),
                beat_id=beat.id, index=idx, emphasis=is_emphasis(tok.display, beat.emphasis),
            ))
        pieces.append(a48)
        t += dur
        if k + 1 < len(beats_audio):
            gap = _beat_gap(beat.section, beats_audio[k + 1][0].section, beat.text)
            pieces.append(np.zeros(int(gap * OUT_SR), dtype=np.float32))
            t += gap
    pieces.append(np.zeros(int(TAIL * OUT_SR), dtype=np.float32))
    narration = np.concatenate(pieces)
    peak = float(np.max(np.abs(narration))) or 1.0
    narration = (narration / peak * 0.89).astype(np.float32)  # -1 dBFS peak; loudness is mastered later
    sf.write(store.dir(pid) / "audio/narration.wav", narration, OUT_SR, subtype="PCM_24")
    duration = len(narration) / OUT_SR

    from ..brand import load_brand

    brand = load_brand(project.settings.brand, language)
    cues = build_cues(words, max_words=int(brand["subtitles"].get("max_words", 3)), max_chars=int(brand["subtitles"].get("max_chars", 22)))
    timeline = Timeline(
        duration=round(duration, 3), narration_file="audio/narration.wav", sample_rate=OUT_SR,
        provider=ns.provider, voice=ns.voice, alignment="+".join(sorted(methods)),
        beats=beat_timings, words=words, cues=cues,
    )
    sb = store.storyboard(pid)
    if sb:
        timeline.scenes = scene_timings(sb, timeline)
    if abs(speed - (ns.speed or 1.0)) > 1e-3:
        project.settings.narration.speed = speed
        store.save("project", pid, project)
    store.save("timeline", pid, timeline)
    log(f"Voice-over ready: {duration:.1f}s, {len(words)} words, timing method: {timeline.alignment}")
    return timeline


def scene_timings(sb: Storyboard, tl: Timeline) -> list[SceneTiming]:
    """Scenes cut ~0.12 s before the first word of their first beat."""
    beat_start = {b.beat_id: b.start for b in tl.beats}
    beat_end = {b.beat_id: b.end for b in tl.beats}
    starts = []
    for sc in sb.scenes:
        bs = [beat_start[b] for b in sc.beat_ids if b in beat_start]
        starts.append(min(bs) if bs else None)
    out: list[SceneTiming] = []
    valid = [(sc, st) for sc, st in zip(sb.scenes, starts) if st is not None]
    for k, (sc, st) in enumerate(valid):
        start = 0.0 if k == 0 else max(0.0, st - 0.12)
        if k + 1 < len(valid):
            end = max(start + 0.5, valid[k + 1][1] - 0.12)
        else:
            end = tl.duration
        out.append(SceneTiming(scene_id=sc.id, start=round(start, 3), end=round(end, 3)))
    _ = beat_end
    return out
