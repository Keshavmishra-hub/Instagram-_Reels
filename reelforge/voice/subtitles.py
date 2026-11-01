"""Subtitle construction.

On-screen captions: short chunks (<= 3 words / 22 chars) that pop in with the narration and
highlight the word being spoken. Exported captions (SRT/VTT) use readable sentence-level cues
(<= 2 lines x 42 chars) for platforms that accept caption files and for accessibility.
"""

from __future__ import annotations

import re

from ..models import SubtitleCue, Word

SENT_END = (".", "!", "?", "…")
CLAUSE_END = (",", ";", ":", "—", "–")


def _disp_len(words: list[Word]) -> int:
    return len(" ".join(w.text for w in words))


def build_cues(words: list[Word], max_words: int = 3, max_chars: int = 22, hold: float = 0.22,
               min_dur: float = 0.45, pause_break: float = 0.32) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    chunk: list[int] = []

    def flush():
        if not chunk:
            return
        ws = [words[i] for i in chunk]
        cues.append(SubtitleCue(start=ws[0].start, end=ws[-1].end + hold, word_indices=list(chunk), text=" ".join(w.text for w in ws)))
        chunk.clear()

    for i, w in enumerate(words):
        if chunk:
            prev = words[chunk[-1]]
            new_beat = w.beat_id != prev.beat_id
            gap = w.start - prev.end
            cand = [words[j] for j in chunk] + [w]
            if (new_beat or len(cand) > max_words or _disp_len(cand) > max_chars or gap > pause_break
                    or prev.text.endswith(SENT_END) or (prev.text.endswith(CLAUSE_END) and len(chunk) >= 1)):
                flush()
        chunk.append(i)
    flush()
    # no overlaps; enforce a minimum display time where there is room
    for k, c in enumerate(cues):
        nxt = cues[k + 1].start if k + 1 < len(cues) else c.end + 10
        c.end = min(c.end, nxt)
        if c.end - c.start < min_dur:
            c.end = min(c.start + min_dur, nxt)
    return cues


def _fmt(t: float, sep: str) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def sentence_cues(words: list[Word], max_chars: int = 84, max_dur: float = 6.0) -> list[tuple[float, float, str]]:
    out = []
    cur: list[Word] = []
    for w in words:
        cur.append(w)
        text = " ".join(x.text for x in cur)
        end_here = w.text.endswith(SENT_END) or (w.text.endswith(CLAUSE_END) and len(text) > 40)
        if end_here or len(text) > max_chars - 8 or (cur[-1].end - cur[0].start) > max_dur:
            out.append((cur[0].start, cur[-1].end + 0.15, text))
            cur = []
    if cur:
        out.append((cur[0].start, cur[-1].end + 0.15, " ".join(x.text for x in cur)))
    # avoid overlaps
    fixed = []
    for i, (a, b, t) in enumerate(out):
        if i + 1 < len(out):
            b = min(b, out[i + 1][0])
        fixed.append((a, b, t))
    return fixed


def _wrap(text: str, width: int = 42) -> str:
    if len(text) <= width:
        return text
    words = text.split()
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, a, b)
    return f"{best[1]}\n{best[2]}" if best else text


def to_srt(words: list[Word]) -> str:
    blocks = []
    for i, (a, b, t) in enumerate(sentence_cues(words), 1):
        blocks.append(f"{i}\n{_fmt(a, ',')} --> {_fmt(b, ',')}\n{_wrap(t)}\n")
    return "\n".join(blocks)


def to_vtt(words: list[Word]) -> str:
    lines = ["WEBVTT", ""]
    for a, b, t in sentence_cues(words):
        lines += [f"{_fmt(a, '.')} --> {_fmt(b, '.')}", _wrap(t), ""]
    return "\n".join(lines)


def is_emphasis(token: str, emphasis: list[str]) -> bool:
    core = re.sub(r"[^\w\u0900-\u0DFF%°₹$€£.\-−]", "", token.lower()).strip(".")  # keep Indic vowel signs
    if not core:
        return False
    for phrase in emphasis:
        parts = [re.sub(r"[^\w\u0900-\u0DFF%°₹$€£.\-−]", "", p.lower()).strip(".") for p in phrase.split()]
        if core in parts:
            return True
    return bool(re.search(r"\d", core))  # numbers are always emphasised
