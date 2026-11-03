"""Small DSP toolkit for the sound design (numpy/scipy only, 48 kHz float32).

Everything here is synthesis from first principles - oscillators, filters, modal
resonators, convolution reverb, dynamics - so the soundtrack is 100% original.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import signal

SR = 48000
RNG = np.random.default_rng(1234)


def n_of(dur):
    return int(round(dur * SR))


def tt(dur):
    return np.arange(n_of(dur), dtype=np.float64) / SR


# ----------------------------------------------------------------------------- sources
def noise(dur, color="white", rng=None):
    rng = rng or RNG
    n = n_of(dur)
    w = rng.standard_normal(n)
    if color == "white":
        return w
    f = np.fft.rfftfreq(n, 1 / SR)
    spec = np.fft.rfft(w)
    f[0] = f[1]
    if color == "pink":
        spec /= np.sqrt(f)
    elif color == "brown":
        spec /= f
    out = np.fft.irfft(spec, n)
    return out / (np.std(out) + 1e-12)


def phase(freq, dur=None):
    if np.isscalar(freq):
        return 2 * np.pi * freq * tt(dur)
    return 2 * np.pi * np.cumsum(freq) / SR


def sine(freq, dur=None, ph0=0.0):
    return np.sin(phase(freq, dur) + ph0)


def saw(freq, dur=None, ph0=0.0):
    """PolyBLEP band-limited sawtooth."""
    if np.isscalar(freq):
        freq = np.full(n_of(dur), float(freq))
    inc = freq / SR
    p = (np.cumsum(inc) + ph0) % 1.0
    y = 2 * p - 1
    dt = np.maximum(inc, 1e-9)
    m1 = p < dt
    x = p[m1] / dt[m1]
    y[m1] -= x + x - x * x - 1
    m2 = p > 1 - dt
    x = (p[m2] - 1) / dt[m2]
    y[m2] -= x * x + x + x + 1
    return y


def supersaw(freq, dur, voices=7, detune=0.012, rng=None):
    rng = rng or RNG
    out = np.zeros(n_of(dur))
    for k in range(voices):
        d = 1 + detune * (k - (voices - 1) / 2) / ((voices - 1) / 2 + 1e-9)
        out += saw(freq * d, dur, ph0=rng.random())
    return out / voices


# ----------------------------------------------------------------------------- envelopes
def env_exp(dur, decay, attack=0.002):
    t = tt(dur)
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    return a * np.exp(-t / decay)


def env_adsr(dur, a, d, s, r):
    t = tt(dur)
    e = np.where(t < a, t / max(a, 1e-6), 1.0)
    e = np.where((t >= a) & (t < a + d), 1 - (1 - s) * (t - a) / max(d, 1e-6), e)
    e = np.where(t >= a + d, s, e)
    rel = dur - r
    e = np.where(t > rel, e * np.clip((dur - t) / max(r, 1e-6), 0, 1), e)
    return e


def ramp(dur, a, b, curve=1.0):
    x = np.linspace(0, 1, n_of(dur))
    return a + (b - a) * x ** curve


# ----------------------------------------------------------------------------- filters
def _sos(kind, fc, order=2, fc2=None):
    nyq = SR / 2
    if kind == "band":
        return signal.butter(order, [max(fc, 10) / nyq, min(fc2, nyq * 0.98) / nyq], "band", output="sos")
    return signal.butter(order, min(max(fc, 10), nyq * 0.98) / nyq, kind, output="sos")


def lowpass(x, fc, order=2):
    return signal.sosfilt(_sos("low", fc, order), x, axis=0)


def highpass(x, fc, order=2):
    return signal.sosfilt(_sos("high", fc, order), x, axis=0)


def bandpass(x, f1, f2, order=2):
    return signal.sosfilt(_sos("band", f1, order, f2), x, axis=0)


def resonator(x, f, q=30.0):
    b, a = signal.iirpeak(min(f, SR / 2 * 0.95), q, SR)
    return signal.lfilter(b, a, x)


def lowpass_sweep(x, fc, q=0.9, block=128):
    """Time-varying resonant low-pass (biquad updated per block)."""
    fc = np.broadcast_to(np.asarray(fc, np.float64), x.shape[:1]) if np.ndim(fc) else np.full(len(x), fc)
    y = np.zeros_like(x)
    zi = np.zeros(2)
    for i in range(0, len(x), block):
        f = min(max(fc[i], 20.0), SR * 0.45)
        w0 = 2 * math.pi * f / SR
        alpha = math.sin(w0) / (2 * q)
        cw = math.cos(w0)
        b = np.array([(1 - cw) / 2, 1 - cw, (1 - cw) / 2])
        a = np.array([1 + alpha, -2 * cw, 1 - alpha])
        y[i:i + block], zi = signal.lfilter(b / a[0], a / a[0], x[i:i + block], zi=zi)
    return y


def bandpass_sweep(x, fc, q=2.0, block=128):
    fc = np.broadcast_to(np.asarray(fc, np.float64), x.shape[:1]) if np.ndim(fc) else np.full(len(x), fc)
    y = np.zeros_like(x)
    zi = np.zeros(2)
    for i in range(0, len(x), block):
        f = min(max(fc[i], 30.0), SR * 0.45)
        w0 = 2 * math.pi * f / SR
        alpha = math.sin(w0) / (2 * q)
        cw = math.cos(w0)
        b = np.array([alpha, 0.0, -alpha])
        a = np.array([1 + alpha, -2 * cw, 1 - alpha])
        y[i:i + block], zi = signal.lfilter(b / a[0], a / a[0], x[i:i + block], zi=zi)
    return y


# ----------------------------------------------------------------------------- resonant bodies
def modal(dur, freqs, decays, amps, exc=None, rng=None):
    """Sum of exponentially decaying sinusoids (struck metal)."""
    rng = rng or RNG
    t = tt(dur)
    out = np.zeros_like(t)
    for f, d, a in zip(freqs, decays, amps):
        if f >= SR / 2 * 0.95:
            continue
        out += a * np.sin(2 * np.pi * f * t + rng.random() * 6.28) * np.exp(-t / d)
    if exc is not None:
        out = signal.fftconvolve(out, exc)[:len(t)]
    return out


def metal_hit(dur, f0, ratios=(1.0, 1.59, 2.14, 2.83, 3.61, 4.95, 6.24), decay=0.35, bright=1.0, rng=None):
    rng = rng or RNG
    freqs = [f0 * r * (1 + 0.01 * rng.standard_normal()) for r in ratios]
    decays = [decay * (1.0 / (1 + 0.5 * k)) * rng.uniform(0.7, 1.3) for k in range(len(ratios))]
    amps = [(1.0 / (1 + k)) ** (1.2 / bright) * rng.uniform(0.5, 1.0) for k in range(len(ratios))]
    body = modal(dur, freqs, decays, amps, rng=rng)
    click = highpass(noise(0.006, rng=rng), 2000) * np.hanning(n_of(0.006))
    body[:len(click)] += click * 0.6
    return body


# ----------------------------------------------------------------------------- dynamics / space
def soft_clip(x, drive=1.0):
    return np.tanh(x * drive) / np.tanh(drive)


def pan(x, p):
    """Equal-power pan, p in [-1, 1]; p may be an array."""
    a = (np.asarray(p) + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


def stereo(x, width=0.0, delay_ms=0.0):
    if x.ndim == 2:
        return x
    d = int(delay_ms * SR / 1000)
    l, r = x.copy(), x.copy()
    if d > 0:
        r = np.concatenate([np.zeros(d), x[:-d]])
    return np.stack([l, r], 1) * 0.7071


def reverb_ir(dur=2.5, decay=0.9, predelay=0.012, damp=6000.0, rng=None, early=True):
    rng = rng or RNG
    n = n_of(dur)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for c in range(2):
        nz = rng.standard_normal(n)
        lo = lowpass(nz, damp * 0.35)
        hi = nz - lo
        env = np.exp(-t * 6.9 / decay)
        env_hi = np.exp(-t * 6.9 / (decay * 0.45))
        ir[:, c] = lo * env + hi * env_hi * 0.6
    pd = n_of(predelay)
    ir = np.concatenate([np.zeros((pd, 2)), ir])[:n]
    if early:
        for k in range(14):
            d = n_of(rng.uniform(0.004, 0.08))
            if d < n:
                ir[d, :] += rng.uniform(-0.5, 0.5, 2) * (1 - k / 14)
    ir /= np.sqrt((ir ** 2).sum(0)).max() + 1e-9
    return ir


def convolve(x, ir):
    if x.ndim == 1:
        x = np.stack([x, x], 1) * 0.7071
    out = np.zeros((len(x) + len(ir) - 1, 2))
    for c in range(2):
        out[:, c] = signal.fftconvolve(x[:, c], ir[:, c])
    return out[:len(x)]


def true_peak(x, os_factor=4):
    from scipy.signal import resample_poly
    return max(np.abs(resample_poly(x[:, c], os_factor, 1)).max() for c in range(x.shape[1]))


def limiter(x, ceiling=0.89, release=0.08, lookahead=0.005):
    """Look-ahead brick-wall limiter: the gain reaches its target before the peak arrives."""
    peak = np.abs(x).max(1)
    la = n_of(lookahead)
    padded = np.concatenate([peak, np.zeros(la)])
    win = np.lib.stride_tricks.sliding_window_view(padded, la + 1).max(1)[:len(peak)]
    gain_t = np.minimum(1.0, ceiling / np.maximum(win, 1e-9))
    # release: let the gain recover slowly (one-pole on the way up, instant on the way down)
    gr = math.exp(-1 / (release * SR))
    g = np.empty_like(gain_t)
    cur = 1.0
    for i in range(len(gain_t)):
        tgt = gain_t[i]
        cur = tgt if tgt < cur else tgt + (cur - tgt) * gr
        g[i] = cur
    # smooth the attack across the look-ahead window so the gain change itself is clean
    k = np.hanning(la * 2 + 1)
    k /= k.sum()
    g = np.minimum(g, np.convolve(g, k, mode="same"))
    out = x * g[:, None]
    tp = true_peak(out)
    if tp > ceiling:
        out *= ceiling / tp
    return out


def compress(x, thresh_db=-18.0, ratio=3.0, attack=0.01, release=0.15, makeup_db=0.0):
    lvl = np.sqrt(signal.sosfilt(_sos("low", 30, 1), (x ** 2).mean(1)) + 1e-12)
    db = 20 * np.log10(lvl + 1e-12)
    over = np.maximum(db - thresh_db, 0)
    gr_db = over * (1 - 1 / ratio)
    # smooth the gain reduction
    a = math.exp(-1 / (attack * SR))
    r = math.exp(-1 / (release * SR))
    sm = signal.lfilter([1 - r], [1, -r], gr_db)
    sm = np.maximum(sm, signal.lfilter([1 - a], [1, -a], gr_db))
    g = 10 ** ((makeup_db - sm) / 20)
    return x * g[:, None]
