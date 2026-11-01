import numpy as np

from reelforge.assets.music import compose, write_sfx_track
from reelforge.models import Word
from reelforge.voice.subtitles import build_cues, to_srt


def words():
    t, out = 0.2, []
    for i, w in enumerate("Only two countries made more solar power than India. That's 2025 data from Ember.".split()):
        out.append(Word(text=w, start=t, end=t + 0.3, beat_id="B1" if i < 9 else "B2", index=i))
        t += 0.35
    return out


def test_cues_respect_limits_and_beats():
    cues = build_cues(words(), max_words=3, max_chars=22)
    ws = words()
    for c in cues:
        assert len(c.word_indices) <= 3
        assert len({ws[i].beat_id for i in c.word_indices}) == 1
        assert c.end > c.start
    assert sorted(i for c in cues for i in c.word_indices) == list(range(len(ws)))
    for a, b in zip(cues, cues[1:]):
        assert a.end <= b.start + 1e-9


def test_srt_format():
    srt = to_srt(words())
    assert srt.startswith("1\n00:00:00,200 --> ")


def test_music_exact_length_and_finite(tmp_path):
    audio = compose(6.0, "curious", [(0, 2, "hook"), (2, 6, "story")])
    assert audio.shape == (int(6.05 * 48000), 2) or abs(audio.shape[0] - 6.05 * 48000) <= 1
    assert np.isfinite(audio).all() and np.abs(audio).max() <= 1.0
    p = write_sfx_track(tmp_path / "sfx.wav", 3.0, [(0.5, "whoosh", 0.5), (1.5, "pop", 0.3)])
    assert p.exists()
