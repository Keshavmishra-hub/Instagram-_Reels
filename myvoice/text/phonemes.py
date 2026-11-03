"""Phoneme inventories, per-text phoneme extraction and coverage helpers.

English phonemes come from eSpeak NG (General American model) mapped onto a 39-phoneme inventory;
your recordings will of course carry your own Indian-English realisation of each category, which is
exactly what the clone should learn. Hindi phonemes come from the rule-based Devanagari converter.
"""

from __future__ import annotations

import re
from functools import lru_cache

from . import devanagari as dv
from . import espeak

EN_VOWELS = ["iː", "ɪ", "eɪ", "ɛ", "æ", "ɑː", "ɔː", "oʊ", "ʊ", "uː", "ʌ", "ə", "ɜː", "aɪ", "aʊ", "ɔɪ", "ɪə", "eə", "ʊə"]
EN_CONSONANTS = ["p", "b", "t", "d", "k", "g", "f", "v", "θ", "ð", "s", "z", "ʃ", "ʒ", "h", "tʃ", "dʒ", "m", "n", "ŋ", "l", "r", "w", "j"]
EN_INVENTORY = EN_VOWELS + EN_CONSONANTS

HI_VOWELS = ["ə", "aː", "ɪ", "iː", "ʊ", "uː", "eː", "ɛː", "oː", "ɔː", "ɛ", "ɔ"]
HI_NASAL_VOWELS = ["ə̃", "aː̃", "ɪ̃", "iː̃", "ʊ̃", "uː̃", "eː̃", "ɛː̃", "oː̃"]
HI_CONSONANTS = [
    "k", "kʰ", "g", "gʱ", "ŋ", "tʃ", "tʃʰ", "dʒ", "dʒʱ", "ɲ", "ʈ", "ʈʰ", "ɖ", "ɖʱ", "ɳ", "t̪", "t̪ʰ", "d̪", "d̪ʱ", "n",
    "p", "pʰ", "b", "bʱ", "m", "j", "r", "l", "ʋ", "ʃ", "s", "ɦ", "ɽ", "ɽʱ", "q", "x", "ɣ", "z", "f",
]
HI_INVENTORY = HI_VOWELS + HI_NASAL_VOWELS + HI_CONSONANTS

# Rare in natural Hindi: lower occurrence targets so coverage isn't held hostage by them
HI_RARE = {"ŋ", "ɲ", "ɳ", "ɽʱ", "q", "x", "ɣ", "ɔ", "ɪ̃", "ʊ̃", "uː̃", "ə̃", "gʱ", "dʒʱ", "ʈʰ", "ɖʱ"}
EN_RARE = {"ʒ", "ɔɪ", "ʊə", "eə", "ɪə", "ʊ", "θ"}

PHONEME_LABELS: dict[str, str] = {
    # English
    "iː": "ee (see)", "ɪ": "i (sit)", "eɪ": "ay (day)", "ɛ": "e (bed)", "æ": "a (cat)", "ɑː": "aa (car)",
    "ɔː": "aw (law)", "oʊ": "oh (go)", "ʊ": "u (book)", "uː": "oo (food)", "ʌ": "u (cup)", "ə": "schwa (about)",
    "ɜː": "er (bird)", "aɪ": "ai (my)", "aʊ": "ow (now)", "ɔɪ": "oy (boy)", "ɪə": "ear (here)", "eə": "air (there)",
    "ʊə": "oor (tour)", "θ": "th (think)", "ð": "th (this)", "ʃ": "sh (she)", "ʒ": "zh (measure)", "tʃ": "ch (chair)",
    "dʒ": "j (judge)", "ŋ": "ng (sing)", "h": "h (hat)", "w": "w (wet)", "j": "y (yes)", "r": "r (red)",
    # Hindi
    "aː": "आ", "eː": "ए", "ɛː": "ऐ", "oː": "ओ", "ɔː": "औ", "ɛ": "ऐ-like (कहना)", "ɔ": "ऑ",
    "ə̃": "अँ", "aː̃": "आँ", "ɪ̃": "इँ", "iː̃": "ईं", "ʊ̃": "उँ", "uː̃": "ऊँ", "eː̃": "एँ", "ɛː̃": "ऐं", "oː̃": "ओं",
    "kʰ": "ख", "gʱ": "घ", "tʃʰ": "छ", "dʒʱ": "झ", "ɲ": "ञ", "ʈ": "ट", "ʈʰ": "ठ", "ɖ": "ड", "ɖʱ": "ढ", "ɳ": "ण",
    "t̪": "त", "t̪ʰ": "थ", "d̪": "द", "d̪ʱ": "ध", "pʰ": "फ", "bʱ": "भ", "ʋ": "व", "ɦ": "ह", "ɽ": "ड़", "ɽʱ": "ढ़",
    "q": "क़", "x": "ख़", "ɣ": "ग़", "z": "ज़", "f": "फ़",
}

_EN_MAP: dict[str, tuple[str, ...]] = {
    "ɹ": ("r",), "ɾ": ("t",), "ɚ": ("ə", "r"), "əl": ("ə", "l"), "ɪɹ": ("ɪə", "r"), "ɛɹ": ("eə", "r"),
    "ʊɹ": ("ʊə", "r"), "ɑːɹ": ("ɑː", "r"), "ɔːɹ": ("ɔː", "r"), "aɪɚ": ("aɪ", "ə", "r"), "aɪə": ("aɪ", "ə"),
    "aʊɚ": ("aʊ", "ə", "r"), "i": ("iː",), "ᵻ": ("ɪ",), "ɐ": ("ə",), "n̩": ("n",), "l̩": ("l",), "ɡ": ("g",),
    "iə": ("ɪə",), "ʔ": (), "x": ("k",), "ɬ": ("l",), "e": ("eɪ",), "o": ("oʊ",), "oː": ("ɔː",), "ɒ": ("ɑː",),
    "a": ("æ",), "ɑ": ("ɑː",), "ɔ": ("ɔː",), "ɜ": ("ɜː",), "əʊ": ("oʊ",), "eə": ("eə",), "ʊə": ("ʊə",),
}
_EN_VALID = set(EN_INVENTORY)
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")


def _map_en(phs) -> list[str]:
    out: list[str] = []
    for p in phs:
        for q in _EN_MAP.get(p, (p,)):
            if q in _EN_VALID:
                out.append(q)
    return out


@lru_cache(maxsize=8192)
def english_words(text: str) -> tuple[tuple[str, ...], ...]:
    """Canonical English phonemes per word (eSpeak; empty tuple if eSpeak is unavailable)."""
    if not text.strip() or not espeak.available():
        return ()
    return tuple(tuple(_map_en(w)) for w in espeak.phonemize(text))


def english_syllables_heuristic(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    if w.endswith(("ed",)) and not w.endswith(("ted", "ded")) and n > 1:
        n -= 1
    return max(1, n)


def _segments(text: str) -> list[tuple[str, str]]:
    """Split text into runs of ('hi', devanagari text) and ('en', latin text)."""
    out: list[tuple[str, str]] = []
    for tok in dv.tokens(text):
        if dv.is_devanagari_word(tok):
            lang = "hi"
        elif LATIN_WORD_RE.fullmatch(tok) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9'’.-]*", tok):
            lang = "en"
        else:
            continue
        if out and out[-1][0] == lang:
            out[-1] = (lang, out[-1][1] + " " + tok)
        else:
            out.append((lang, tok))
    return out


@lru_cache(maxsize=8192)
def analyse_text(text: str) -> dict:
    """Phoneme sequences per language, syllable and word counts for a (possibly mixed) text."""
    en: list[str] = []
    hi: list[str] = []
    syllables = 0
    words = 0
    en_ok = espeak.available()
    for lang, chunk in _segments(text):
        if lang == "hi":
            for w in dv.text_phonemes(chunk):
                hi.extend(w)
                syllables += sum(1 for p in w if dv.is_vowel(p))
                words += 1
        else:
            latin_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.-]*", chunk)
            words += len(latin_words)
            if en_ok:
                for w in english_words(chunk):
                    en.extend(w)
                    syllables += sum(1 for p in w if p in EN_VOWELS)
            else:
                syllables += sum(english_syllables_heuristic(w) for w in latin_words)
    return {"en": tuple(en), "hi": tuple(hi), "syllables": syllables, "words": words, "en_g2p": en_ok}


def diphones(seq) -> list[tuple[str, str]]:
    return list(zip(seq[:-1], seq[1:]))
