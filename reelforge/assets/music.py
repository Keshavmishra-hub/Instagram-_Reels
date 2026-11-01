"""Original, copyright-free background score + sound effects, synthesised per reel.

Why: licensed library music needs per-track licences and online access. A procedurally composed
underscore is ours by construction, follows the script's structure (intensity rises toward the
payoff), and always fits the exact duration. Users can still drop licensed tracks into
`music/` (see README) and the mixer will use them instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

SR = 48000
RNG_SEED = 7

NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
ROMAN = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}


@dataclass(frozen=True)
class Mood:
    key: str
    mode: str
    bpm: float
    progression: tuple[str, ...]
    bars_per_chord: int
    arp_pattern: tuple[int, ...]  # chord-tone indices per 16th (-1 = rest)
    perc: float  # 0..1 percussion level
    brightness: float  # 0..1 filter openness
    kick_pattern: tuple[int, ...]  # 16 steps


MOODS: dict[str, Mood] = {
    "curious": Mood("D", "minor", 96, ("i", "VI", "III", "VII"), 1, (0, -1, 2, -1, 4, -1, 2, 3, 0, -1, 2, -1, 4, 3, 2, -1), 0.55, 0.55,
                    (1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0)),
    "uplifting": Mood("C", "major", 104, ("I", "V", "vi", "IV"), 1, (0, 2, 4, 2, 5, 2, 4, 2, 0, 2, 4, 2, 5, 4, 2, 4), 0.7, 0.75,
                      (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)),
    "tense": Mood("E", "minor", 90, ("i", "VI", "iv", "v"), 1, (0, -1, 0, 3, -1, 0, -1, 4, 0, -1, 0, 3, -1, 4, 2, -1), 0.45, 0.4,
                  (1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0)),
    "epic": Mood("A", "minor", 84, ("i", "VI", "III", "VII"), 2, (0, -1, -1, 2, -1, -1, 4, -1, 5, -1, -1, 4, -1, -1, 2, -1), 0.6, 0.6,
                 (1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0)),
    "calm": Mood("F", "major", 78, ("I", "IV", "vi", "V"), 2, (0, -1, 2, -1, 4, -1, 5, -1, 4, -1, 2, -1, 0, -1, -1, -1), 0.0, 0.45,
                 (0,) * 16),
}


def _midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _chord(mood: Mood, roman: str, octave: int = 3) -> list[int]:
    scale = MAJOR if mood.mode == "major" else MINOR
    deg = ROMAN[roman.lower()]
    root = 12 * (octave + 1) + NOTE[mood.key]
    tones = []
    for k in (0, 2, 4, 6):  # triad + 7th from the scale
        idx = deg + k
        tones.append(root + scale[idx % 7] + 12 * (idx // 7))
    return tones


_TABLE_N = 4096
_SAW = sum(((-1) ** (k + 1)) / k * np.sin(2 * np.pi * k * np.arange(_TABLE_N) / _TABLE_N) for k in range(1, 40)).astype(np.float32)
_SAW /= np.abs(_SAW).max()


def _osc(freq: float, n: int, table=_SAW, phase0: float = 0.0, vibrato: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    f = freq * (1 + vibrato * np.sin(2 * np.pi * 4.8 * t)) if vibrato else freq
    phase = (phase0 + np.cumsum(np.broadcast_to(f, (n,))) / SR) % 1.0
    return table[(phase * _TABLE_N).astype(np.int32)]


def _env(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    si = max(0, n - ai - di - ri)
    e = np.concatenate([
        np.linspace(0, 1, max(1, ai), endpoint=False),
        np.linspace(1, s, max(1, di), endpoint=False),
        np.full(si, s),
        np.linspace(s, 0, max(1, ri)),
    ])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def _lowpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    sos = butter(order, min(cutoff, SR / 2 * 0.95) / (SR / 2), btype="low", output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def _highpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    sos = butter(order, cutoff / (SR / 2), btype="high", output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def _bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    sos = butter(2, [lo / (SR / 2), min(hi, SR / 2 * 0.95) / (SR / 2)], btype="band", output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def _reverb_ir(seconds: float, rng: np.random.Generator) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    decay = np.exp(-6.9 * t / seconds)
    ir = rng.standard_normal((n, 2)).astype(np.float32) * decay[:, None]
    ir = _lowpass(ir, 6000)
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]
    return ir / np.sqrt((ir ** 2).sum(axis=0, keepdims=True))


def _reverb(x: np.ndarray, ir: np.ndarray, wet: float) -> np.ndarray:
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    out = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1).astype(np.float32)
    return x * (1 - wet) + out * wet


def _place(buf: np.ndarray, sig: np.ndarray, at: int, pan: float = 0.0, gain: float = 1.0) -> None:
    at = max(0, int(at))
    if at >= len(buf):
        return
    n = min(len(sig), len(buf) - at)
    l = np.cos((pan + 1) * np.pi / 4)
    r = np.sin((pan + 1) * np.pi / 4)
    if sig.ndim == 1:
        buf[at:at + n, 0] += sig[:n] * gain * l * 1.414
        buf[at:at + n, 1] += sig[:n] * gain * r * 1.414
    else:
        buf[at:at + n] += sig[:n] * gain


def _kick() -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 28)
    ph = np.cumsum(f) / SR
    body = np.sin(2 * np.pi * ph) * np.exp(-t * 9)
    click = _highpass(np.random.default_rng(1).standard_normal(n).astype(np.float32), 2500) * np.exp(-t * 180) * 0.25
    return np.tanh((body + click) * 1.6).astype(np.float32) * 0.8


def _hat(rng) -> np.ndarray:
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return (_highpass(rng.standard_normal(n).astype(np.float32), 7000) * np.exp(-t * 70)).astype(np.float32) * 0.35


def _snap(rng) -> np.ndarray:
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    noise = _bandpass(rng.standard_normal(n).astype(np.float32), 1200, 6000) * np.exp(-t * 22)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.4
    return (noise + tone).astype(np.float32) * 0.45


def _pluck(freq: float, dur: float, bright: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    tri = 2 * np.abs(2 * ((freq * t) % 1.0) - 1) - 1
    sig = (0.6 * tri + 0.4 * np.sin(2 * np.pi * freq * t)) * np.exp(-t * (7 - 3 * bright))
    sig[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    return _lowpass(sig.astype(np.float32), 1800 + 3500 * bright)


def compose(duration: float, mood_key: str = "curious", sections: Optional[list[tuple[float, float, str]]] = None,
            seed: int = RNG_SEED) -> np.ndarray:
    """Return stereo float32 music of exactly `duration` seconds.

    sections: [(start, end, section_name)] from the narration timeline; intensity follows them.
    """
    mood = MOODS.get(mood_key, MOODS["curious"])
    rng = np.random.default_rng(seed)
    total = int((duration + 0.05) * SR)
    buf = np.zeros((total + SR * 4, 2), dtype=np.float32)
    beat = 60.0 / mood.bpm
    step = beat / 4
    bar = beat * 4
    n_bars = int(np.ceil((duration + 2) / bar))

    def intensity(t: float) -> float:
        base = {"hook": 0.75, "context": 0.55, "story": 0.75, "payoff": 1.0, "ending": 0.5}
        if not sections:
            return 0.7
        for a, b, name in sections:
            if a <= t < b:
                return base.get(name, 0.7)
        return 0.45 if t > sections[-1][1] else 0.7

    ir = _reverb_ir(2.6, rng)
    pad_bus = np.zeros_like(buf)
    arp_bus = np.zeros_like(buf)
    bass_bus = np.zeros_like(buf)
    drum_bus = np.zeros_like(buf)

    for b in range(n_bars):
        chord_name = mood.progression[(b // mood.bars_per_chord) % len(mood.progression)]
        tones = _chord(mood, chord_name, 3)
        t_bar = b * bar
        start = int(t_bar * SR)
        inten = intensity(t_bar)
        # pad: chord across octaves, re-triggered per chord change, long release
        if b % mood.bars_per_chord == 0:
            n = int((bar * mood.bars_per_chord + 1.2) * SR)
            pad = np.zeros(n, dtype=np.float32)
            for k, m in enumerate([tones[0] - 12, tones[0], tones[1], tones[2], tones[3] if mood.mode == "minor" else tones[2] + 12]):
                f = _midi_hz(m)
                for det in (-0.07, 0.0, 0.07):
                    pad += _osc(f * 2 ** (det / 12), n, phase0=rng.random(), vibrato=0.0015) * (0.5 if k == 0 else 0.32)
            cutoff = 700 + 2200 * mood.brightness * (0.6 + 0.4 * inten)
            pad = _lowpass(pad, cutoff, 2) * _env(n, 0.9, 0.6, 0.85, 1.1)
            _place(pad_bus, pad * 0.11, start, pan=rng.uniform(-0.15, 0.15))
        # arpeggio (enters when intensity allows)
        if inten >= 0.5:
            arp_tones = [tones[0] + 12, tones[1] + 12, tones[2] + 12, tones[3] + 12, tones[0] + 24, tones[1] + 24]
            for s_idx, ti in enumerate(mood.arp_pattern):
                if ti < 0:
                    continue
                t = t_bar + s_idx * step + rng.normal(0, 0.003)
                vel = (0.7 + 0.3 * (s_idx % 4 == 0)) * (0.55 + 0.45 * inten)
                note = _pluck(_midi_hz(arp_tones[ti % len(arp_tones)]), 0.55, mood.brightness)
                _place(arp_bus, note * 0.12 * vel, int(t * SR), pan=0.35 * np.sin(s_idx * 0.9))
        # bass
        if inten >= 0.55:
            for s_idx in (0, 8) if mood.bpm < 95 else (0, 6, 8, 14):
                t = t_bar + s_idx * step
                n = int(step * 6 * SR)
                f = _midi_hz(tones[0] - 12)
                tt = np.arange(n) / SR
                sig = np.tanh(1.8 * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt))) * _env(n, 0.01, 0.2, 0.6, 0.25)
                _place(bass_bus, sig.astype(np.float32) * 0.16 * inten, int(t * SR))
        # drums
        if mood.perc > 0 and inten >= 0.7:
            for s_idx, hit in enumerate(mood.kick_pattern):
                if hit:
                    _place(drum_bus, _kick() * 0.5 * mood.perc, int((t_bar + s_idx * step) * SR))
            for s_idx in range(0, 16, 2):
                _place(drum_bus, _hat(rng) * (0.5 + 0.5 * (s_idx % 4 == 2)) * mood.perc * 0.6, int((t_bar + s_idx * step + rng.normal(0, 0.002)) * SR),
                       pan=0.25)
            if inten >= 0.9:
                for s_idx in (4, 12):
                    _place(drum_bus, _snap(rng) * mood.perc * 0.5, int((t_bar + s_idx * step) * SR))

    pad_bus = _reverb(pad_bus, ir, 0.35)
    # ping-pong delay on the arp
    d = int(step * 3 * SR)
    echo = np.zeros_like(arp_bus)
    echo[d:, 0] = arp_bus[:-d, 1] * 0.35
    echo[d:, 1] = arp_bus[:-d, 0] * 0.35
    arp_bus = _reverb(arp_bus + _lowpass(echo, 3500), ir, 0.25)
    drum_bus = _reverb(drum_bus, ir, 0.08)
    mix = pad_bus + arp_bus + _lowpass(bass_bus, 900) + drum_bus
    # gentle "air" noise bed
    air = _bandpass(rng.standard_normal((len(mix), 2)).astype(np.float32), 3000, 9000) * 0.004
    mix = (mix + air)[:total]
    # fades: quick fade-in, 2.5 s fade-out ending exactly at the end
    fi = int(0.25 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)[:, None]
    fo = min(int(2.5 * SR), len(mix))
    mix[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    # normalise to a consistent level (~ -18 dBFS RMS), soft-limit peaks
    rms = np.sqrt((mix ** 2).mean() + 1e-12)
    mix = mix * (10 ** (-18 / 20) / rms)
    return np.tanh(mix * 1.2).astype(np.float32) / 1.2


# --------------------------------------------------------------------------------------------
# Sound effects
# --------------------------------------------------------------------------------------------


def whoosh(dur: float = 0.55, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    # time-varying band-pass by blocks
    out = np.zeros(n, dtype=np.float32)
    blocks = 24
    for i in range(blocks):
        a, b = i * n // blocks, (i + 1) * n // blocks
        pos = i / (blocks - 1)
        centre = 250 * (16 ** pos) if pos < 0.6 else 250 * 16 ** 0.6 * (1 - (pos - 0.6))
        lo, hi = max(80, centre * 0.6), min(16000, centre * 1.8)
        seg = _bandpass(noise[max(0, a - 512):b], lo, hi)[-(b - a):]
        out[a:b] = seg
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * np.clip(t * 1.15, 0, 1)) ** 2
    stereo = np.stack([out * env * (1 - 0.6 * t), out * env * (0.4 + 0.6 * t)], axis=1)
    return (stereo / (np.abs(stereo).max() + 1e-9) * 0.5).astype(np.float32)


def impact(seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    f = 38 + 60 * np.exp(-t * 12)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    hit = _bandpass(rng.standard_normal(n).astype(np.float32), 300, 5000) * np.exp(-t * 35) * 0.5
    sig = np.tanh(1.4 * (boom + hit)).astype(np.float32)
    st = _reverb(np.stack([sig, sig], 1), _reverb_ir(1.8, rng), 0.25)
    return (st / (np.abs(st).max() + 1e-9) * 0.55).astype(np.float32)


def riser(dur: float = 1.6, seed: int = 9) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    noise = _highpass(rng.standard_normal(n).astype(np.float32), 1500) * t ** 2
    f = 200 * (8 ** t)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25 * t ** 1.5
    sig = (noise * 0.6 + tone).astype(np.float32)
    sig[-int(0.03 * SR):] *= np.linspace(1, 0, int(0.03 * SR))
    st = np.stack([sig, sig], 1)
    return (st / (np.abs(st).max() + 1e-9) * 0.45).astype(np.float32)


def pop(seed: int = 11) -> np.ndarray:
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * (900 + 500 * np.exp(-t * 60)) * t) * np.exp(-t * 45)
    st = np.stack([sig, sig], 1).astype(np.float32)
    return st * 0.35


SFX = {"whoosh": whoosh, "impact": impact, "riser": riser, "pop": pop}


def write_music(path: Path, duration: float, mood: str, sections=None, seed: int = RNG_SEED) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = compose(duration, mood, sections, seed)
    sf.write(path, audio, SR, subtype="PCM_24")
    meta = {
        "generator": "ReelForge procedural score",
        "mood": mood, "seed": seed, "duration": duration,
        "license": "Original composition generated by this software for this reel; no third-party rights.",
    }
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def write_sfx_track(path: Path, duration: float, events: list[tuple[float, str, float]]) -> Path:
    """events: [(time_seconds, sfx_name, gain)] -> one stereo stem."""
    buf = np.zeros((int((duration + 2) * SR), 2), dtype=np.float32)
    cache: dict[str, np.ndarray] = {}
    for t, name, gain in events:
        if name not in SFX:
            continue
        sig = cache.setdefault(name, SFX[name]())
        at = int(max(0.0, t) * SR)
        if name == "whoosh":
            at = max(0, at - int(0.3 * SR))  # centre the whoosh on the cut
        if name == "riser":
            at = max(0, at - len(sig))  # riser ends on the moment
        _place(buf, sig, at, gain=gain)
    buf = buf[: int(duration * SR)]
    sf.write(path, buf, SR, subtype="PCM_24")
    return path
