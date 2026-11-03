"""Script-independent phonetic keys for comparing what was displayed with what speech recognition
heard. "meeting", "मीटिंग" and "miting" all reduce to the key "mitin(g)"; retroflex/dental,
aspirated/plain and vowel-length distinctions are folded so that recogniser spelling choices do not
count as reading errors."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from . import devanagari as dv
from . import espeak
from .phonemes import _map_en

COARSE: dict[str, str] = {
    "ə": "a", "aː": "a", "æ": "a", "ʌ": "a", "ɑː": "a", "ɐ": "a",
    "ɪ": "i", "iː": "i", "ɪː": "i",
    "ʊ": "u", "uː": "u",
    "eː": "e", "ɛː": "e", "ɛ": "e", "e": "e", "eɪ": "e",
    "oː": "o", "ɔː": "o", "ɔ": "o", "o": "o", "oʊ": "o",
    "ɜː": "ar", "aɪ": "ai", "aʊ": "au", "ɔɪ": "oi", "ɪə": "ia", "eə": "ea", "ʊə": "ua",
    "k": "k", "kʰ": "k", "q": "k", "x": "k", "g": "g", "gʱ": "g", "ɣ": "g",
    "tʃ": "c", "tʃʰ": "c", "dʒ": "j", "dʒʱ": "j", "z": "j", "ʒ": "j",
    "ʈ": "t", "ʈʰ": "t", "t̪": "t", "t̪ʰ": "t", "t": "t", "θ": "t",
    "ɖ": "d", "ɖʱ": "d", "d̪": "d", "d̪ʱ": "d", "d": "d", "ð": "d", "ɽ": "d", "ɽʱ": "d",
    "n": "n", "ɳ": "n", "ɲ": "n", "ŋ": "n", "m": "m",
    "p": "p", "pʰ": "p", "f": "f", "b": "b", "bʱ": "b",
    "j": "y", "r": "r", "l": "l", "ɭ": "l", "ʋ": "v", "w": "v", "v": "v",
    "ʃ": "s", "s": "s", "ɦ": "h", "h": "h",
}

LETTER_NAMES = {
    "a": "e", "b": "bi", "c": "si", "d": "di", "e": "i", "f": "ef", "g": "ji", "h": "ech", "i": "ai", "j": "je",
    "k": "ke", "l": "el", "m": "em", "n": "en", "o": "o", "p": "pi", "q": "kyu", "r": "ar", "s": "es", "t": "ti",
    "u": "yu", "v": "vi", "w": "dablyu", "x": "eks", "y": "vai", "z": "jed",
}


def _coarse(phs) -> str:
    out = []
    for p in phs:
        b = p.replace("̃", "")
        piece = COARSE.get(b, "")
        out.append(piece + ("n" if b != p and not piece.endswith("n") else ""))
    return _squeeze("".join(out))


def _squeeze(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def orth_key(word: str) -> str:
    """Spelling-based key for Roman-script words (also covers romanised Hindi)."""
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(c for c in w if c.isascii() and c.isalnum())
    if not w:
        return ""
    rules = [
        ("tch", "c"), ("chh", "c"), ("sch", "sk"), ("ch", "c"), ("sh", "s"), ("ph", "f"), ("kh", "k"), ("gh", "g"),
        ("th", "t"), ("dh", "d"), ("bh", "b"), ("jh", "j"), ("ck", "k"), ("qu", "kv"), ("q", "k"), ("x", "ks"),
        ("wh", "v"), ("w", "v"), ("z", "j"), ("tion", "san"), ("sion", "san"),
        ("aa", "a"), ("ee", "i"), ("ea", "i"), ("oo", "u"), ("ou", "au"), ("ai", "e"), ("ei", "e"), ("ay", "e"),
        ("au", "o"), ("ey", "e"), ("ie", "i"),
    ]
    for a, b in rules:
        w = w.replace(a, b)
    w = re.sub(r"c(?=[eiy])", "s", w)
    w = w.replace("c", "c")
    w = re.sub(r"y$", "i", w)
    w = re.sub(r"(?<=[^aeiou])h", "", w)
    return _squeeze(w)


@lru_cache(maxsize=65536)
def word_keys(word: str) -> tuple[str, ...]:
    """All keys of a word (Devanagari: G2P key; Latin: eSpeak key + spelling key + letter names)."""
    word = word.strip()
    if not word:
        return ()
    if dv.is_devanagari_word(word):
        return (_coarse(dv.word_phonemes(word)),)
    keys = []
    if espeak.available():
        try:
            phs = [p for w in espeak.phonemize(word) for p in _map_en(w)]
            if phs:
                keys.append(_coarse(phs))
        except Exception:
            pass
    keys.append(orth_key(word))
    if word.isupper() and 1 < len(word) <= 6 and word.isalpha():  # acronym: also spelled out
        keys.append(_squeeze("".join(LETTER_NAMES[c] for c in word.lower())))
    return tuple(dict.fromkeys(k for k in keys if k))


def split_words(text: str) -> list[str]:
    """Word tokens (punctuation removed) in reading order."""
    out = []
    for t in dv.tokens(text):
        t = t.strip("'’-.")
        if not t:
            continue
        if dv.is_devanagari_word(t) or re.match(r"[A-Za-z0-9]", t):
            out.append(t)
    return out
