"""Original soundtrack for the MASS ENTHUSIAST intro: score + sound design, mixed and mastered.

    python audio/sound_design.py            # -> audio/stems/*.wav, audio/mass_enthusiast_mix.wav

Every cue is placed from the frame numbers in timeline.py (the same numbers that drive
the animation), so picture and sound stay locked. Key: D (phrygian colour), ~100 BPM.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import timeline as TL  # noqa: E402
from synth import *  # noqa: E402,F401,F403
import synth as S  # noqa: E402

DUR = TL.DURATION_S
N = S.n_of(DUR)
rng = np.random.default_rng(77)


def sec(frame):
    return frame / TL.FPS


def hz(note):
    """Note name like 'D2', 'Eb3' -> frequency."""
    names = {"C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
    n, o = (note[:-1], int(note[-1]))
    return 440.0 * 2 ** ((names[n] + 12 * (o + 1) - 69) / 12)


def L(*xs):
    """Sum mono layers of different lengths."""
    n = max(len(x) for x in xs)
    out = np.zeros(n)
    for x in xs:
        out[:len(x)] += x
    return out


class Bus:
    def __init__(self, name):
        self.name = name
        self.buf = np.zeros((N, 2))

    def add(self, x, t0, gain=1.0, p=0.0):
        if x.ndim == 1:
            x = S.pan(x, p)
        i0 = int(round(t0 * S.SR))
        if i0 < 0:
            x = x[-i0:]
            i0 = 0
        i1 = min(N, i0 + len(x))
        if i1 > i0:
            self.buf[i0:i1] += x[:i1 - i0] * gain


# ----------------------------------------------------------------------------- sound elements
def chain_clink(seed):
    r = np.random.default_rng(seed)
    a = S.metal_hit(1.6, r.uniform(1700, 2600), decay=0.5, rng=r)
    b = S.metal_hit(1.2, r.uniform(2200, 3400), decay=0.3, rng=r)
    d = S.n_of(r.uniform(0.018, 0.045))
    out = a.copy()
    n = min(len(out) - d, len(b))
    out[d:d + n] += 0.55 * b[:n]
    thud = S.lowpass(S.noise(0.08, rng=r), 400) * S.env_exp(0.08, 0.02)
    out[:len(thud)] += 0.4 * thud
    return S.lowpass(out, 9000) * 0.5


def creak(dur, seed):
    r = np.random.default_rng(seed)
    f = 70 + 25 * np.sin(S.tt(dur) * 3.0 + r.random()) + 8 * S.lowpass(S.noise(dur, rng=r), 8)
    x = S.saw(f) * 0.5
    x = S.bandpass(x, 300, 1600)
    return x * S.env_adsr(dur, dur * 0.3, dur * 0.2, 0.7, dur * 0.4) * 0.25


def sub_boom(dur=1.6, f0=95, f1=32, drive=1.6, decay=0.55):
    t = S.tt(dur)
    f = f1 + (f0 - f1) * np.exp(-t / 0.12)
    x = S.sine(f) * S.env_exp(dur, decay, attack=0.003)
    return S.soft_clip(x * 1.2, drive)


def thump(dur=0.5, fc=180):
    return S.lowpass(S.noise(dur), fc, 4) * S.env_exp(dur, 0.08) * 2.0


def crack(dur=0.12):
    return S.highpass(S.noise(dur), 1500) * S.env_exp(dur, 0.018, attack=0.0005)


def whoosh(dur, f0=300, f1=3000, curve=1.0, q=1.6, peak=0.6):
    x = S.noise(dur, "pink")
    fc = S.ramp(dur, f0, f1, curve)
    y = S.bandpass_sweep(x, fc, q=q)
    t = np.linspace(0, 1, len(y))
    env = np.where(t < peak, (t / peak) ** 2, ((1 - t) / (1 - peak)) ** 1.5)
    return y * env * 1.2


def reverse_swell(dur=1.2, bright=6000):
    x = S.highpass(S.noise(dur * 1.6), 400) * S.env_exp(dur * 1.6, dur * 0.45)
    x = S.lowpass(x, bright)
    ir = S.reverb_ir(2.0, 1.6)
    y = S.convolve(x, ir)[:S.n_of(dur)]
    return y[::-1] * 1.4


def cymbal(dur=3.0, decay=1.4):
    x = S.highpass(S.noise(dur), 3500) * S.env_exp(dur, decay, attack=0.002)
    for f in (4200, 5300, 6900, 8700):
        x += 0.15 * S.resonator(S.noise(dur), f, 40) * S.env_exp(dur, decay * 0.8)
    return x * 0.35


def anvil(dur, f0, decay=1.1):
    r = np.random.default_rng(int(f0))
    ratios = (1.0, 2.32, 2.95, 4.08, 5.31, 6.77, 8.4)
    return S.metal_hit(dur, f0, ratios=ratios, decay=decay, bright=1.2, rng=r)


def debris(dur=0.9, density=140, seed=0):
    r = np.random.default_rng(seed)
    out = np.zeros(S.n_of(dur))
    n = r.poisson(density * dur)
    for _ in range(n):
        t0 = r.exponential(dur * 0.25)
        if t0 >= dur - 0.02:
            continue
        g = S.metal_hit(0.05, r.uniform(2500, 7000), decay=0.012, rng=r) * r.uniform(0.05, 0.3)
        i = S.n_of(t0)
        out[i:i + len(g)] += g[:len(out) - i]
    return out * np.exp(-S.tt(dur) / (dur * 0.5))


def sizzle(dur=0.8, density=600, seed=1):
    r = np.random.default_rng(seed)
    x = np.zeros(S.n_of(dur))
    idx = r.integers(0, len(x), int(density * dur))
    x[idx] = r.uniform(-1, 1, len(idx))
    x = S.highpass(x, 3000)
    hiss = S.highpass(S.noise(dur, rng=r), 5000) * 0.15
    return (x + hiss) * S.env_exp(dur, dur * 0.4)


def slam(big=True, seed=0):
    """The title slams: a heavy plate seating into a steel frame."""
    dur = 3.2 if big else 1.0
    f0 = 640 + 70 * seed if big else 1250 + 90 * (seed % 5)
    a = anvil(dur, f0, decay=1.0 if big else 0.35)
    out = np.zeros(S.n_of(dur))
    out += a * (0.55 if big else 0.4)
    if big:
        b = sub_boom(dur, 110, 34, 2.0, 0.6)
        out += b * 1.0
        out[:S.n_of(0.5)] += thump(0.5, 220) * 0.6
        out[:S.n_of(0.12)] += crack(0.12) * 0.7
        out[:S.n_of(0.9)] += debris(0.9, 160, seed) * 0.8
        out[:S.n_of(0.8)] += sizzle(0.8, 800, seed) * 0.35
    else:
        out[:S.n_of(0.3)] += sub_boom(0.3, 150, 60, 1.5, 0.08) * 0.35
        out[:S.n_of(0.12)] += crack(0.12) * 0.35
        out[:S.n_of(0.3)] += sizzle(0.3, 500, seed) * 0.25
    return out


def braam(dur, notes, cutoff_peak=1800, attack=0.05, release=1.2, drive=2.2):
    out = np.zeros(S.n_of(dur))
    for nt in notes:
        out += S.supersaw(hz(nt), dur, voices=7, detune=0.01)
    t = S.tt(dur)
    fc = 120 + cutoff_peak * np.exp(-t / 0.45) * np.clip(t / attack, 0, 1) + 300 * np.exp(-t / 2.5)
    y = S.lowpass_sweep(out / len(notes), fc, q=1.2)
    y = S.soft_clip(y * 2.0, drive)
    env = S.env_adsr(dur, attack, 0.6, 0.55, release)
    return y * env


def pad(dur, notes, fc=700, attack=1.5, release=2.0):
    out = np.zeros(S.n_of(dur))
    for nt in notes:
        out += S.supersaw(hz(nt), dur, voices=5, detune=0.006)
    lfo = 1 + 0.25 * np.sin(2 * np.pi * 0.13 * S.tt(dur))
    y = S.lowpass_sweep(out / len(notes), fc * lfo, q=0.8)
    return y * S.env_adsr(dur, attack, 0.5, 0.85, release)


def pluck(f, dur=1.4, bright=5000):
    t = S.tt(dur)
    x = 0.6 * S.saw(f, dur) + 0.4 * S.sine(f * 2, dur)
    fc = 300 + bright * np.exp(-t / 0.12)
    y = S.lowpass_sweep(x, fc, q=1.4)
    bell = S.metal_hit(dur, f * 4, decay=0.4) * 0.15
    return (y + bell) * S.env_exp(dur, 0.45, attack=0.002)


def taiko(dur=1.2, f0=72):
    t = S.tt(dur)
    f = f0 * (1 + 0.6 * np.exp(-t / 0.03))
    body = S.sine(f) * S.env_exp(dur, 0.32)
    skin = S.bandpass(S.noise(dur), 200, 1200) * S.env_exp(dur, 0.04)
    return S.soft_clip(body * 1.3 + skin * 0.5, 1.3)


def ostinato_note(f, dur=0.28, bright=1.0):
    x = S.supersaw(f, dur, voices=3, detune=0.004)
    t = S.tt(dur)
    fc = 180 + 1400 * bright * np.exp(-t / 0.08)
    y = S.lowpass_sweep(x, fc, q=2.0)
    return S.soft_clip(y * 1.6, 1.4) * S.env_adsr(dur, 0.004, 0.08, 0.6, 0.06)


def riser(dur, f0=180, f1=2400):
    t = S.tt(dur)
    out = np.zeros(len(t))
    for k in range(5):
        f = f0 * 2 ** (k * 0.5) * (f1 / f0) ** (t / dur)
        out += S.saw(f) * (0.6 if k % 2 else 1.0)
    out = S.lowpass_sweep(out / 5, S.ramp(dur, 400, 9000, 2.0), q=1.0)
    nz = S.bandpass_sweep(S.noise(dur, "pink"), S.ramp(dur, 300, 9000, 2.2), q=1.4)
    env = np.linspace(0, 1, len(t)) ** 2.4
    return (out * 0.5 + nz * 0.9) * env


def shimmer(dur):
    t = S.tt(dur)
    x = S.bandpass_sweep(S.noise(dur), S.ramp(dur, 3000, 11000, 1.0), q=6.0)
    gl = np.zeros(len(t))
    for k in range(9):
        f = 2000 + 900 * k
        gl += S.sine(f * (1 + 0.002 * np.sin(t * 7 + k))) * np.exp(-((t - dur * k / 9) / 0.08) ** 2)
    return (x * 0.6 + gl * 0.3) * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5


def clatter(dur, rate=24.0, seed=3):
    """Projector mechanism: a sprocket click train plus motor hum."""
    r = np.random.default_rng(seed)
    out = np.zeros(S.n_of(dur))
    k = 0
    while k / rate < dur:
        i = S.n_of(k / rate + r.normal(0, 0.0015))
        c = S.metal_hit(0.03, r.uniform(1800, 2600), decay=0.006, rng=r) * r.uniform(0.5, 1.0)
        if 0 <= i < len(out):
            out[i:i + len(c)] += c[:len(out) - i]
        k += 1
    t = S.tt(dur)
    hum = sum(S.sine(50 * h, dur) / h for h in (1, 2, 3, 5)) * (1 + 0.3 * np.sin(2 * np.pi * rate * t))
    return out * 0.6 + S.lowpass(hum, 600) * 0.06


def buzz(dur, f=100):
    t = S.tt(dur)
    x = np.sign(np.sin(2 * np.pi * f * t)) * 0.5 + S.noise(dur) * 0.3
    return S.bandpass(x, 150, 4000) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 7 * t)))


def fire(dur, seed=4):
    r = np.random.default_rng(seed)
    roar = S.lowpass(S.noise(dur, "brown", rng=r), 500) * 0.6
    cr = np.zeros(S.n_of(dur))
    n = int(dur * 70)
    for _ in range(n):
        i = r.integers(0, len(cr) - 2000)
        g = S.bandpass(r.standard_normal(400), r.uniform(1500, 5000), 9000) * np.hanning(400) * r.uniform(0.1, 0.8)
        cr[i:i + 400] += g
    return roar + cr * 0.5


def grinder(dur, seed=5):
    r = np.random.default_rng(seed)
    t = S.tt(dur)
    band = S.bandpass(S.noise(dur, rng=r), 2200, 9000) * (0.75 + 0.25 * np.sin(2 * np.pi * 31 * t))
    whine = S.sine(3150 * (1 + 0.004 * np.sin(2 * np.pi * 6 * t)), None) * 0.25
    motor = S.lowpass(S.saw(180 + 4 * np.sin(t * 3), None), 900) * 0.3
    return band + whine + motor + sizzle(dur, 900, seed) * 0.8


def zap_run(dur, seed=6):
    t = S.tt(dur)
    x = S.highpass(S.noise(dur), 1500) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 110 * t)))
    tone = S.saw(S.ramp(dur, 220, 880, 1.5)) * 0.2
    return S.bandpass(x + tone, 400, 9000) * S.env_adsr(dur, 0.03, 0.2, 0.7, 0.2)


def servo(dur):
    t = S.tt(dur)
    f = 200 + 380 * (t / dur) ** 1.4
    x = S.saw(f) * 0.4 + S.saw(f * 1.5) * 0.15
    return S.bandpass(x, 150, 3000) * S.env_adsr(dur, 0.05, 0.2, 0.8, 0.1) * 0.6


# ----------------------------------------------------------------------------- arrangement
def build():
    sfx = Bus("sfx")
    hits = Bus("impacts")
    mus = Bus("music")
    amb = Bus("ambience")
    B, T = TL.BEATS, TL.TITLE

    # ---- 0-12 s: the dark, the chain, the cinema objects ----
    t = S.tt(19.0)
    drone = (S.sine(hz("D1"), 19.0) * 0.22 + S.lowpass(S.supersaw(hz("D2"), 19.0, 5, 0.004), 220) * 0.35
             + S.lowpass(S.supersaw(hz("A2"), 19.0, 5, 0.005), 260) * 0.12)
    air = S.bandpass(S.noise(19.0, "pink"), 180, 900) * (0.25 + 0.15 * np.sin(2 * np.pi * 0.07 * t))
    env = np.clip(t / 5.0, 0, 1) ** 1.5 * np.clip((18.6 - t) / 0.4, 0, 1)
    amb.add(S.stereo(drone * env, delay_ms=11), 0.0, 0.32)
    amb.add(S.stereo(air * env, delay_ms=17), 0.0, 0.18)
    for k, f in enumerate(B["chain_clinks"]):
        sfx.add(chain_clink(10 + k), sec(f), 0.55 + 0.05 * k, p=-0.2 + 0.08 * k)
    for k, a in enumerate((0.9, 2.3, 3.4)):
        sfx.add(creak(1.2, 30 + k), a, 0.35, p=0.15 - 0.15 * k)
    for k in range(3):                                    # heartbeat sub pulses
        t0 = 2.45 + 0.82 * k
        hits.add(sub_boom(0.6, 80, 45, 1.0, 0.12), t0, 0.22 + 0.07 * k)
        hits.add(sub_boom(0.5, 75, 42, 1.0, 0.1), t0 + 0.23, 0.14 + 0.05 * k)
    ring = S.metal_hit(4.0, 420, ratios=(1.0, 2.76, 5.40, 8.93), decay=1.6, bright=0.8)
    sfx.add(ring, sec(B["ring_turn"]) + 0.15, 0.32, p=0.1)
    sfx.add(reverse_swell(0.8), sec(B["reel_cut"]) - 0.8, 0.5)
    hits.add(sub_boom(1.4, 90, 36, 1.4, 0.4), sec(B["reel_cut"]), 0.8)
    sfx.add(S.metal_hit(2.0, 900, decay=0.6), sec(B["reel_cut"]), 0.25, p=0.2)
    # music: low pad enters with the reel
    mus.add(S.stereo(pad(7.4, ["D2", "A2", "E3", "F3"], fc=520, attack=2.5, release=1.2), delay_ms=13),
            sec(B["reel_cut"]), 0.30)
    # reel spin: spoke flutter
    d = sec(TL.SHOT["s02_reel"][1] - TL.SHOT["s02_reel"][0]) + 0.1
    tt_ = S.tt(d)
    flutter = S.bandpass(S.noise(d), 300, 3000) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * (14 + 6 * tt_ / d) * tt_)))
    sfx.add(S.stereo(flutter * S.env_adsr(d, 0.1, 0.2, 0.8, 0.15) * 0.35, delay_ms=7), sec(B["reel_cut"]), 0.6)
    # film gate clatter + the four pull-downs
    a0, a1 = TL.SHOT["s03_film"]
    sfx.add(S.stereo(clatter(sec(a1 - a0 + 1)), delay_ms=5), sec(a0), 0.45)
    for f in B["gate_pulldowns"]:
        sfx.add(L(S.metal_hit(0.5, 1400, decay=0.08), thump(0.2, 300) * 0.4), sec(f), 0.5, p=0.05)
    # projector: motor, ignition, whip-pan, screen
    p0, p1 = TL.SHOT["s04_projector"]
    sfx.add(S.stereo(clatter(sec(p1 - p0 + 1), rate=24, seed=8) * 0.6, delay_ms=4), sec(p0), 0.35)
    ign = sec(B["lamp_ignite"])
    sfx.add(L(thump(0.4, 260) * 1.2, crack(0.12) * 0.5), ign, 0.7)
    sfx.add(buzz(1.1) * S.env_adsr(1.1, 0.01, 0.2, 0.5, 0.4), ign, 0.18, p=-0.2)
    hits.add(sub_boom(1.2, 80, 34, 1.2, 0.35), ign, 0.6)
    sfx.add(S.pan(whoosh(0.45, 400, 5000, 0.8), np.linspace(-0.8, 0.8, S.n_of(0.45))), ign + 0.12, 0.8)
    sfx.add(S.stereo(shimmer(0.8), delay_ms=9), sec(B["screen_on"]) + 0.15, 0.25)
    # ticket fire
    tk0, tk1 = TL.SHOT["s05_ticket"]
    fw = whoosh(0.7, 120, 1400, 0.6, q=0.9, peak=0.25) * 1.3
    sfx.add(fw, sec(B["ticket_ignite"]) - 0.08, 0.7)
    sfx.add(S.stereo(fire(sec(tk1 - tk0 + 8)), delay_ms=12), sec(tk0), 0.33)
    # iris ratchet
    i0, i1 = B["iris_close"]
    n_clicks = 11
    for k in range(n_clicks):
        u = (k / (n_clicks - 1)) ** 0.7
        tc = sec(i0) + u * (sec(i1) - sec(i0))
        sfx.add(S.metal_hit(0.08, 3200 + 160 * k, decay=0.02), tc, 0.22 + 0.02 * k, p=0.1)
    sfx.add(L(S.metal_hit(1.2, 760, decay=0.3) * 0.9, thump(0.3, 240) * 0.6), sec(i1), 0.6)
    # speaker: two bass hits + bead rattle
    for k, f in enumerate(B["bass_hits"]):
        hits.add(sub_boom(1.0, 140, 36, 2.5, 0.28), sec(f), 1.0)
        hits.add(thump(0.3, 160), sec(f), 0.5)
        sfx.add(S.stereo(debris(0.8, 260, 40 + k) * 0.8, delay_ms=6), sec(f) + 0.05, 0.6)

    # ---- 12-18.3 s: the build ----
    bar0 = 12.0
    step = 0.3
    motif = ["D2", "D2", "D3", "D2", "Eb2", "D2", "F2", "D2"]
    for k in range(int((18.3 - bar0) / step)):
        tk = bar0 + k * step
        prog = k / ((18.3 - bar0) / step)
        nt = motif[k % 8]
        mus.add(ostinato_note(hz(nt), 0.28, bright=0.4 + 1.6 * prog), tk, 0.22 + 0.25 * prog, p=-0.15 if k % 2 else 0.15)
    for k in range(14):
        tk = 14.4 + 0.6 * k
        if tk >= 18.25:
            break
        hits.add(taiko(1.0, 70), tk, 0.45 + 0.03 * k, p=0.0)
        if k % 2 == 1:
            hits.add(taiko(0.6, 110) * 0.6, tk + 0.3, 0.25, p=0.3)
    rl0 = sec(B["redline_start"])
    sfx.add(S.pan(zap_run(1.3), np.linspace(-0.7, 0.7, S.n_of(1.3))), rl0, 0.35)
    hits.add(sub_boom(0.9, 100, 38, 1.8, 0.25), 12.0, 0.7)
    sfx.add(crack(0.12), 12.0, 0.5)
    g0, g1 = B["grinder"]
    gd = sec(g1 - g0)
    gr = grinder(gd + 0.2) * S.env_adsr(gd + 0.2, 0.03, 0.2, 0.85, 0.25)
    sfx.add(S.stereo(gr, delay_ms=3), sec(g0), 0.30)
    sp0, face = TL.SHOT["s10_spot"][0], B["spot_face"]
    sfx.add(S.stereo(servo(sec(face - sp0)), delay_ms=4), sec(sp0), 0.4)
    hits.add(L(sub_boom(1.0, 120, 36, 2.0, 0.3), thump(0.4, 250)), sec(face), 0.75)
    sfx.add(S.pan(whoosh(0.6, 200, 6000, 1.2, peak=0.85), np.linspace(0.6, -0.4, S.n_of(0.6))), sec(face) - 0.45, 0.6)
    v0 = sec(TL.SHOT["s11_vortex"][0])
    mus.add(S.stereo(riser(18.3 - v0 + 0.05), delay_ms=9), v0, 0.32)
    for k in range(6):                                   # objects rushing past
        tw = v0 + 0.25 + 0.38 * k
        pp = 0.8 if k % 2 else -0.8
        sfx.add(S.pan(whoosh(0.5, 250, 2500, 1.0, peak=0.55), np.linspace(pp, -pp, S.n_of(0.5))), tw, 0.35)
    for k, f in enumerate(B["vortex_hits"]):
        hits.add(sub_boom(1.0, 110, 36, 2.2, 0.3), sec(f), 0.6 + 0.1 * k)
        hits.add(taiko(0.8, 80), sec(f), 0.5)
        sfx.add(L(S.metal_hit(1.4, 700 + 90 * k, decay=0.4) * 0.6, crack(0.12) * 0.5), sec(f), 0.45)
    # flash, then the suck-back into silence
    fl = sec(B["flash"])
    hits.add(sub_boom(2.5, 130, 30, 2.4, 0.7), fl, 1.0)
    sfx.add(S.stereo(cymbal(2.5, 1.0), delay_ms=8), fl, 0.55)
    hits.add(L(thump(0.5, 240), crack(0.15) * 0.6), fl, 0.8)
    mus.add(S.stereo(braam(1.2, ["D1", "D2", "A2"], release=0.6), delay_ms=10), fl, 0.4)
    sfx.add(reverse_swell(0.5, 9000), 18.92 - 0.5, 0.75)

    # ---- 19-27 s: the title is forged and assembled ----
    slams = [T["slam_M"], T["slam_A"], T["slam_S1"], T["slam_S2"]]
    for k, f in enumerate(slams):
        hits.add(S.stereo(slam(True, k), delay_ms=6), sec(f), 0.95, p=0.0)
        sfx.add(S.pan(whoosh(0.22, 300, 4000, 1.5, peak=0.9), np.linspace(-0.3, 0.1, S.n_of(0.22))), sec(f) - 0.2, 0.55)
    # molten glow under the close-ups: a hissing bed
    sfx.add(S.stereo(S.highpass(S.noise(2.4, "pink"), 2500) * S.env_adsr(2.4, 0.2, 0.5, 0.6, 0.6) * 0.15, delay_ms=9), 19.0, 0.6)
    mus.add(S.stereo(braam(2.2, ["D1", "D2", "A2"], cutoff_peak=1600), delay_ms=10), sec(T["slam_M"]), 0.42)
    mus.add(S.stereo(braam(2.0, ["Eb1", "Eb2", "Bb2"], cutoff_peak=1500), delay_ms=10), sec(T["slam_A"]), 0.30)
    mus.add(S.stereo(braam(2.0, ["F1", "F2", "C3"], cutoff_peak=1500), delay_ms=10), sec(T["slam_S1"]), 0.30)
    mus.add(S.stereo(braam(3.0, ["D1", "D2", "A2", "D3"], cutoff_peak=2200), delay_ms=10), sec(T["slam_S2"]), 0.45)
    # MASS locks: the big one
    ml = sec(T["mass_lock"])
    hits.add(sub_boom(3.0, 120, 30, 2.6, 0.9), ml, 1.0)
    hits.add(S.stereo(anvil(3.5, 520, 1.6) * 0.5, delay_ms=7), ml, 0.7)
    sfx.add(S.stereo(cymbal(3.0, 1.6), delay_ms=11), ml, 0.4)
    mus.add(S.stereo(pad(5.8, ["D2", "A2", "D3", "F3", "A3"], fc=1500, attack=0.05, release=1.5), delay_ms=12), ml, 0.42)
    mus.add(S.stereo(braam(2.0, ["D1", "D2", "F2", "A2"], cutoff_peak=2600), delay_ms=10), ml, 0.5)
    a, b = T["sweep_mass"]
    sfx.add(S.pan(shimmer(sec(b - a) + 0.3), np.linspace(-0.6, 0.6, S.n_of(sec(b - a) + 0.3))), sec(a), 0.4)
    for k, f in enumerate((ml + 0.6, ml + 1.2)):
        hits.add(taiko(1.0, 66), f, 0.45)
    # ENTHUSIAST: each letter flips up and locks - a rising scale, one note per letter
    scale = ["D3", "E3", "F3", "G3", "A3", "Bb3", "C4", "D4", "E4", "F4"]
    for k, f in enumerate(T["enth_slams"]):
        sfx.add(S.pan(whoosh(0.2, 600, 3500, 1.0, peak=0.8), np.linspace(-0.7 + 0.14 * k, -0.6 + 0.14 * k, S.n_of(0.2))),
                sec(f) - 0.26, 0.22)
        hits.add(slam(False, k), sec(f), 0.55, p=-0.7 + 0.155 * k)
        mus.add(pluck(hz(scale[k]), 1.6), sec(f), 0.20 + 0.012 * k, p=-0.5 + 0.11 * k)
    hits.add(sub_boom(2.0, 100, 34, 2.0, 0.6), sec(T["enth_slams"][-1]), 0.65)
    mus.add(S.stereo(braam(2.6, ["D1", "D2", "A2", "D3"], cutoff_peak=2400), delay_ms=10), sec(T["enth_slams"][-1]), 0.38)
    # pull back and the second sweep: the chord opens up
    a, b = T["sweep_all"]
    mus.add(S.stereo(pad(7.0, ["Bb1", "F2", "D3", "F3", "A3"], fc=1800, attack=0.8, release=1.5), delay_ms=12), 25.0, 0.36)
    sfx.add(S.pan(shimmer(sec(b - a) + 0.4), np.linspace(-0.7, 0.7, S.n_of(sec(b - a) + 0.4))), sec(a), 0.5)
    sfx.add(reverse_swell(1.0, 7000), sec(a) - 1.0, 0.35)

    # ---- 27-33 s: hero ----
    mus.add(S.stereo(pad(6.2, ["D2", "A2", "D3", "E3", "F3", "A3"], fc=1300, attack=0.6, release=2.5), delay_ms=12),
            26.6, 0.6)
    hd = S.tt(6.4)
    hero_drone = (S.sine(hz("D1"), 6.4) * 0.25 + S.lowpass(S.supersaw(hz("D2"), 6.4, 5, 0.004), 260) * 0.4)
    amb.add(S.stereo(hero_drone * np.clip(hd / 1.0, 0, 1), delay_ms=11), 26.6, 0.4)
    for k in range(4):                                    # slow pulse under the hold
        hits.add(taiko(1.0, 62) * 0.7, 27.0 + 0.7 * k, 0.25 + 0.05 * k)
    hi = sec(T["hero_impact"])
    mus.add(S.stereo(riser(1.6, 220, 1600) * 0.7, delay_ms=8), hi - 1.6, 0.3)
    sfx.add(reverse_swell(1.1, 8000), hi - 1.1, 0.6)
    hits.add(sub_boom(4.0, 140, 29, 2.8, 1.3), hi, 1.15)
    hits.add(S.stereo(anvil(4.5, 480, 2.4) * 0.55, delay_ms=9), hi, 0.75)
    hits.add(L(thump(0.6, 220), crack(0.15) * 0.6), hi, 0.9)
    sfx.add(S.stereo(cymbal(4.0, 2.2), delay_ms=13), hi, 0.42)
    mus.add(S.stereo(braam(3.2, ["D1", "D2", "A2", "D3"], cutoff_peak=2800, release=2.2), delay_ms=10), hi, 0.55)
    sfx.add(S.pan(shimmer(1.4), np.linspace(-0.6, 0.6, S.n_of(1.4))), hi + 0.05, 0.35)
    # embers / room tone under the title
    rt = S.lowpass(S.noise(14.0, "brown"), 300) * 0.25 + fire(14.0, 9) * 0.05
    amb.add(S.stereo(rt, delay_ms=15), 19.0, 0.35)
    return sfx, hits, mus, amb


def master(buses):
    ir_hall = S.reverb_ir(3.2, 2.6, 0.02, 5000, rng=np.random.default_rng(3))
    ir_room = S.reverb_ir(1.2, 0.7, 0.008, 7000, rng=np.random.default_rng(4))
    sfx, hits, mus, amb = buses
    wet_sends = {
        "sfx": (sfx.buf, ir_room, 0.30, ir_hall, 0.22),
        "impacts": (hits.buf, ir_room, 0.12, ir_hall, 0.30),
        "music": (mus.buf, ir_room, 0.0, ir_hall, 0.35),
        "ambience": (amb.buf, ir_room, 0.0, ir_hall, 0.15),
    }
    stems = {}
    for name, (dry, ir1, s1, ir2, s2) in wet_sends.items():
        x = dry.copy()
        if s1:
            x += S.convolve(dry, ir1) * s1
        if s2:
            x += S.convolve(dry, ir2) * s2
        stems[name] = x
    # gentle ducking of music and ambience under the big impacts
    env = np.abs(hits.buf).max(1)
    env = S.lowpass(env, 8, 1)
    duck = 1.0 - 0.35 * np.clip(env / (env.max() + 1e-9) * 2.0, 0, 1)
    stems["music"] *= duck[:, None]
    stems["ambience"] *= duck[:, None]
    mix = stems["sfx"] * 0.9 + stems["impacts"] * 1.0 + stems["music"] * 0.85 + stems["ambience"] * 0.8
    mix = S.highpass(mix, 28, 2)                   # clean sub-sonic rumble
    gap = np.ones(N)
    g0, g1 = int(18.92 * S.SR), int(19.18 * S.SR)
    gap[g0:g1] = 0.06
    gap = S.lowpass(gap, 60, 1)
    mix *= gap[:, None]
    mix = S.compress(mix, thresh_db=-16, ratio=2.5, attack=0.012, release=0.2)
    # fades: in from silence, out with the picture
    t = np.arange(N) / S.SR
    fade = np.clip(t / 0.05, 0, 1) * np.clip((DUR - t) / 1.2, 0, 1) ** 1.5
    mix *= fade[:, None]
    return mix, stems


def loudness_normalise(mix, target=-14.0):
    """Measure integrated loudness with ffmpeg's EBU R128 meter and apply gain + true-peak limit."""
    import subprocess
    import tempfile
    tmp = tempfile.mktemp(suffix=".wav")
    sf.write(tmp, mix.astype(np.float32), S.SR, subtype="FLOAT")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", tmp, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = r.stderr
    I = float(txt.split("Integrated loudness:")[1].split("I:")[1].split("LUFS")[0])
    gain = 10 ** ((target - I) / 20)
    out = mix * gain
    out = S.limiter(out, ceiling=10 ** (-1.3 / 20))
    os.remove(tmp)
    return out, I


def main():
    os.makedirs(os.path.join(HERE, "stems"), exist_ok=True)
    buses = build()
    mix, stems = master(buses)
    for name, x in stems.items():
        sf.write(os.path.join(HERE, "stems", f"{name}.wav"), (x / max(1.0, np.abs(x).max())).astype(np.float32), S.SR,
                 subtype="PCM_24")
    out, I = loudness_normalise(mix)
    path = os.path.join(HERE, "mass_enthusiast_mix.wav")
    sf.write(path, out.astype(np.float32), S.SR, subtype="PCM_24")
    print(f"pre-normalisation loudness {I:.1f} LUFS -> {path}")


if __name__ == "__main__":
    main()
