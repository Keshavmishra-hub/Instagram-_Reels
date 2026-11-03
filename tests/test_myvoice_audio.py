import numpy as np
import pytest
from scipy.signal import butter, sosfilt

from myvoice.analysis import analyze_take
from myvoice.audio.analysis import analyze_clap
from myvoice.audio.quality import assess
from voice_helpers import SR, clap_in_room, speech

CTX = {"kind": "sentence", "syllables": 28, "words": 19, "expected": (4.1, 12.0)}


def run(x, ctx=CTX):
    an = analyze_take(x, SR, ctx)
    return an, assess(an, ctx)


def codes(q):
    return {i.code for i in q.issues}


def test_clean_speech_is_good_and_measured():
    an, q = run(speech())
    assert q.verdict == "good" and q.score >= 90, q
    assert an["snr_db"] > 40 and -30 < an["speech_level_dbfs"] < -18
    assert 4.0 < an["speech_seconds"] < 7.0
    assert an["leading_silence"] == pytest.approx(0.6, abs=0.12)
    assert 80 < an["pitch"]["median_hz"] < 140  # eSpeak's default voice is ~100 Hz
    assert an["rate"]["articulation_rate"] > 2
    assert an["clipping"]["events"] == 0 and an["dropouts"]["count"] == 0 and an["clicks"]["count"] == 0
    assert len(an["waveform"]) == 600 and len(an["ltas"]) == 19


def test_background_noise_is_flagged():
    an, q = run(speech(noise_db=-49))  # speech ≈ -24 dBFS, white noise -49 dBFS full band -> SNR ≈ 25 dB
    assert 20 < an["snr_db"] < 30 and "noisy" in codes(q) and q.verdict != "good"
    _an, q = run(speech(noise_db=-38))
    assert "noisy_severe" in codes(q) and q.verdict == "rerecord"


def test_clipping_is_flagged():
    _an, q = run(np.clip(speech() * 4, -1, 1))
    assert "clipping_severe" in codes(q) and q.verdict == "rerecord"


def test_natural_peaks_are_not_clipping():
    an, q = run(speech(gain=0.97))  # loud but not clipped
    assert an["clipping"]["events"] == 0 and "clipping_severe" not in codes(q)


def test_dropout_inside_speech():
    x = speech()
    i = int(2.0 * SR)
    x[i:i + int(0.02 * SR)] = 0
    an, q = run(x)
    assert an["dropouts"]["count"] == 1 and "dropout" in codes(q) and q.verdict == "rerecord"


def test_bluetooth_style_narrowband_audio():
    sos = butter(10, 3800, fs=SR, output="sos")
    x = sosfilt(sos, speech(noise_db=-120)).astype(np.float32)
    _an, q = run(x)
    assert "narrowband" in codes(q) and q.verdict == "rerecord"


def test_mains_hum():
    x = speech(noise_db=-75)
    t = np.arange(len(x)) / SR
    x = (x + 0.003 * np.sin(2 * np.pi * 50 * t) + 0.002 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    an, q = run(x)
    assert an["hum"]["detected"] and an["hum"]["base_hz"] == 50 and "hum" in codes(q)


def test_too_quiet_and_cut_off():
    _an, q = run(speech(gain=0.003, noise_db=-80))
    assert "too_quiet_severe" in codes(q)
    x = speech(tail=0.0)
    # cut in the middle of a loud stretch of speech (not inside a pause between words)
    env = np.convolve(np.abs(x), np.ones(480) / 480, mode="same")
    lo, hi = int(len(x) * 0.5), int(len(x) * 0.8)
    cut = lo + int(np.argmax(env[lo:hi]))
    _an, q = run(x[:cut])
    assert "cut_end" in codes(q) and q.verdict == "rerecord"


def test_too_short_for_the_text():
    x = speech(text="Hello there.")
    _an, q = run(x)
    assert "too_short" in codes(q)


def test_digital_clicks():
    x = speech()
    for k in (1.5, 2.7):
        x[int(k * SR)] += 0.6
    an, q = run(x)
    assert an["clicks"]["count"] == 2 and "clicks" in codes(q)


def test_room_tone():
    rng = np.random.default_rng(1)
    quiet = rng.normal(0, 10 ** (-65 / 20), 5 * SR).astype(np.float32)
    an, q = run(quiet, {"kind": "silence"})
    assert q.verdict == "good" and an["noise_floor_dbfs"] == pytest.approx(-65, abs=2)
    noisy = rng.normal(0, 10 ** (-45 / 20), 5 * SR).astype(np.float32)
    _an, q = run(noisy, {"kind": "silence"})
    assert "room_noisy" in codes(q)
    talk = np.concatenate([quiet[: SR], speech()[: 2 * SR], quiet[: SR]])
    _an, q = run(talk, {"kind": "silence"})
    assert "sound_during_silence" in codes(q)


def test_digital_silence_means_muted_mic():
    _an, q = run(np.zeros(3 * SR, np.float32))
    assert codes(q) == {"no_signal"} and q.score == 0


@pytest.mark.parametrize("t60", [0.2, 0.4, 0.7, 1.1])
def test_clap_reverberation_time(t60):
    r = analyze_clap(clap_in_room(t60), SR)
    assert r["t60"] == pytest.approx(t60, rel=0.15)


def test_clap_verdicts():
    an, q = run(clap_in_room(1.1), {"kind": "clap"})
    assert "room_very_echoey" in codes(q) and q.verdict == "rerecord"
    an, q = run(clap_in_room(0.25), {"kind": "clap"})
    assert q.verdict == "good"


def test_browser_processing_and_mic_interruption_flags():
    ctx = {**CTX, "constraints_applied": {"autoGainControl": True}, "track_events": [{"type": "mute", "t": 1.0}]}
    _an, q = run(speech(), ctx)
    assert {"browser_processing", "mic_interrupted"} <= codes(q)


def test_hindi_speech_pitch_and_rate():
    an, q = run(speech("सुबह की ठंडी हवा में खेतों की हरियाली देखकर मन को बहुत सुकून मिलता है।", voice="hi"),
                {"kind": "sentence", "syllables": 24, "words": 14, "expected": (3.5, 9.2)})
    assert q.verdict in ("good", "usable") and an["pitch"]["median_hz"] > 60
