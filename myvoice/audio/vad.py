"""Speech activity detection at 10 ms resolution.

WebRTC's GMM voice-activity detector (webrtcvad-wheels) is fused with an adaptive energy gate:
  * the noise floor is the median level of frames far from any speech candidate;
  * a frame is speech when the VAD fires and the level clears the floor, or when the level is far
    above both the floor and the take's own loud-speech level minus a margin (catches whispers and
    quiet consonants the VAD can miss without counting breaths as speech).
Without webrtcvad, a pure energy gate is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .io import resample

FRAME = 0.01  # seconds per analysis frame
VAD_SR = 16000


@dataclass
class SpeechMap:
    frame_db: np.ndarray  # dBFS per 10 ms frame
    speech: np.ndarray  # bool per frame
    segments: list[tuple[float, float]] = field(default_factory=list)  # seconds
    noise_floor_db: float = -120.0  # in the 0-8 kHz analysis band (used for decisions)
    speech_level_db: float = -120.0  # active speech level, analysis band
    loud_level_db: float = -120.0  # 95th percentile frame level
    engine: str = "energy"
    noise_frames: int = 0
    noise_floor_full_db: float = -120.0  # full-band levels at the original sample rate (reported)
    speech_level_full_db: float = -120.0

    @property
    def speech_seconds(self) -> float:
        return float(sum(b - a for a, b in self.segments))


def frame_db(audio16: np.ndarray, frame_len: int = 160) -> np.ndarray:
    n = len(audio16) // frame_len
    if n == 0:
        return np.full(1, -120.0)
    x = audio16[: n * frame_len].astype(np.float64).reshape(n, frame_len)
    rms = np.sqrt((x * x).mean(axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-6))


def runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of True runs."""
    if flags.size == 0:
        return []
    f = np.concatenate([[False], flags.astype(bool), [False]])
    d = np.diff(f.astype(np.int8))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    return list(zip(starts.tolist(), ends.tolist()))


def fill_gaps(flags: np.ndarray, max_gap: int) -> np.ndarray:
    out = flags.copy()
    r = runs(flags)
    for (a0, a1), (b0, _b1) in zip(r[:-1], r[1:]):
        if b0 - a1 <= max_gap:
            out[a1:b0] = True
    return out


def remove_short(flags: np.ndarray, min_len: int) -> np.ndarray:
    out = flags.copy()
    for a, b in runs(flags):
        if b - a < min_len:
            out[a:b] = False
    return out


def dilate(flags: np.ndarray, width: int) -> np.ndarray:
    if width <= 0 or not flags.any():
        return flags.copy()
    k = np.ones(2 * width + 1)
    return np.convolve(flags.astype(float), k, mode="same") > 0


def _webrtc_flags(audio16: np.ndarray, n_frames: int, aggressiveness: int = 2):
    try:
        import webrtcvad
    except Exception:
        return None
    vad = webrtcvad.Vad(aggressiveness)
    pcm = (np.clip(audio16, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    flen = 480  # 30 ms at 16 kHz
    nb = len(audio16) // flen
    out = np.zeros(n_frames, dtype=bool)
    for i in range(nb):
        try:
            sp = vad.is_speech(pcm[i * flen * 2:(i + 1) * flen * 2], VAD_SR)
        except Exception:
            return None
        if sp:
            out[i * 3:min(n_frames, i * 3 + 3)] = True
    return out


def detect_speech(audio: np.ndarray, sr: int) -> SpeechMap:
    a16 = resample(audio, sr, VAD_SR)
    db = frame_db(a16)
    n = len(db)
    p10 = float(np.percentile(db, 10))
    loud = float(np.percentile(db, 95))
    web = _webrtc_flags(a16, n)

    # 1) rough candidates -> noise floor from frames well away from them
    cand = db > max(p10 + 15.0, loud - 30.0)
    if web is not None:
        cand |= web & (db > p10 + 6.0)
    near = dilate(cand, 20)
    noise = ~near
    if noise.sum() >= 20:
        floor = float(np.median(db[noise]))
    else:
        floor = p10

    # 2) final decision
    if web is not None:
        strong = db > max(floor + 15.0, loud - 25.0)
        weak = db > max(floor + 6.0, loud - 45.0)
        speech = strong | (web & weak)
        engine = "webrtcvad+energy"
    else:
        speech = db > max(floor + 10.0, loud - 35.0)
        engine = "energy"
    if loud - floor < 8.0:  # nothing stands out from the background: no speech
        speech[:] = False
    speech = fill_gaps(speech, 15)  # bridge gaps < 150 ms (stop closures, short dips)
    speech = remove_short(speech, 6)  # ignore blips < 60 ms

    segs = [(a * FRAME, b * FRAME) for a, b in runs(speech)]
    power_mean_db = lambda v: float(10.0 * np.log10(np.mean(10.0 ** (v / 10.0))))  # noqa: E731
    lvl = power_mean_db(db[speech]) if speech.any() else -120.0
    # full-band levels: same frames, original sample rate (what recording guidelines refer to)
    full = frame_db(audio, max(1, int(round(FRAME * sr))))
    m = min(len(full), n)
    full, sp_m, nz_m = full[:m], speech[:m], noise[:m]
    floor_full = float(np.median(full[nz_m])) if nz_m.sum() >= 20 else float(np.percentile(full, 10))
    lvl_full = power_mean_db(full[sp_m]) if sp_m.any() else -120.0
    return SpeechMap(db, speech, segs, round(floor, 2), round(lvl, 2), round(loud, 2), engine, int(noise.sum()),
                     round(floor_full, 2), round(lvl_full, 2))
