"""Hindi (Devanagari) grapheme-to-phoneme conversion and romanisation.

Devanagari is close to phonemic, so a rule-based converter is reliable for the purposes here
(phoneme coverage, syllable counts, a reading aid and script-independent matching):

* aksharas are parsed into consonant clusters + vowel (inherent schwa, matra, or halant);
* nukta letters (क़ ख़ ग़ ज़ फ़ ड़ ढ़ झ़) map to their own phonemes;
* schwa deletion: word-final schwa is dropped (except after a conjunct or in one-akshara words),
  then medial schwas in a V C _ C V context are dropped right to left (Ohala's rule), so
  कमला → kəmlaː, समझना → səmədʒʱnaː, बदलना → bəd̪əlnaː, सरकार → sərkaːr;
* anusvara becomes the homorganic nasal before a stop (संबंध → səmbənd̪ʱ, ठंडा → ʈʰəɳɖaː) and
  nasalises the vowel elsewhere (में → mẽː, नहीं → nəɦĩː); chandrabindu always nasalises;
* /ə/ next to /ɦ/ in a closed context is realised [ɛ] (कहना → kɛɦnaː, शहर → ʃɛɦɛr).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

NUKTA = "़"
VIRAMA = "्"
ANUSVARA = "ं"
CHANDRABINDU = "ँ"
VISARGA = "ः"
AVAGRAHA = "ऽ"
ZW = {"‌", "‍"}

CONSONANTS: dict[str, str] = {
    "क": "k", "ख": "kʰ", "ग": "g", "घ": "gʱ", "ङ": "ŋ",
    "च": "tʃ", "छ": "tʃʰ", "ज": "dʒ", "झ": "dʒʱ", "ञ": "ɲ",
    "ट": "ʈ", "ठ": "ʈʰ", "ड": "ɖ", "ढ": "ɖʱ", "ण": "ɳ",
    "त": "t̪", "थ": "t̪ʰ", "द": "d̪", "ध": "d̪ʱ", "न": "n",
    "प": "p", "फ": "pʰ", "ब": "b", "भ": "bʱ", "म": "m",
    "य": "j", "र": "r", "ल": "l", "व": "ʋ",
    "श": "ʃ", "ष": "ʃ", "स": "s", "ह": "ɦ",
    "ळ": "ɭ", "ऴ": "ɻ", "ऩ": "n", "ऱ": "r",
}
NUKTA_FORMS: dict[str, str] = {
    "क": "q", "ख": "x", "ग": "ɣ", "ज": "z", "फ": "f", "ड": "ɽ", "ढ": "ɽʱ", "झ": "ʒ", "य": "j", "न": "n", "र": "r", "ल": "ɭ",
}
INDEPENDENT_VOWELS: dict[str, str] = {
    "अ": "ə", "आ": "aː", "इ": "ɪ", "ई": "iː", "उ": "ʊ", "ऊ": "uː", "ऋ": "rɪ", "ॠ": "rɪː",
    "ए": "eː", "ऐ": "ɛː", "ओ": "oː", "औ": "ɔː", "ऍ": "æ", "ऑ": "ɔ", "ऎ": "e", "ऒ": "o", "ऌ": "lɪ",
}
MATRAS: dict[str, str] = {
    "ा": "aː", "ि": "ɪ", "ी": "iː", "ु": "ʊ", "ू": "uː", "ृ": "rɪ", "ॄ": "rɪː",
    "े": "eː", "ै": "ɛː", "ो": "oː", "ौ": "ɔː", "ॅ": "æ", "ॉ": "ɔ", "ॆ": "e", "ॊ": "o",
}
VOWELS = {"ə", "aː", "ɪ", "iː", "ʊ", "uː", "eː", "ɛː", "oː", "ɔː", "æ", "ɔ", "e", "o", "ɛ", "ɪː"}

PLACE = {  # for anusvara assimilation
    "k": "ŋ", "kʰ": "ŋ", "g": "ŋ", "gʱ": "ŋ", "q": "ŋ", "x": "ŋ", "ɣ": "ŋ",
    "tʃ": "ɲ", "tʃʰ": "ɲ", "dʒ": "ɲ", "dʒʱ": "ɲ",
    "ʈ": "ɳ", "ʈʰ": "ɳ", "ɖ": "ɳ", "ɖʱ": "ɳ",
    "t̪": "n", "t̪ʰ": "n", "d̪": "n", "d̪ʱ": "n",
    "p": "m", "pʰ": "m", "b": "m", "bʱ": "m",
}  # before nasals, sonorants and fricatives the anusvara nasalises the vowel instead (उन्होंने, संसार)

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
TOKEN_RE = re.compile(r"[ऀ-ॣ०-ॿ‌‍]+|[A-Za-z0-9'’]+(?:[-.][A-Za-z0-9'’]+)*|[^\s]", re.UNICODE)


def has_devanagari(text: str) -> bool:
    return bool(DEVANAGARI_RE.search(text or ""))


_DEVA_LETTER_RE = re.compile(r"[ऄ-हक़-ॡॲ-ॿ]")


def is_devanagari_word(word: str) -> bool:
    """A Devanagari word: only Devanagari characters and at least one letter (not ।, ॥ or digits)."""
    return (bool(word) and all(("ऀ" <= ch <= "ॣ") or ("॰" <= ch <= "ॿ") or ch in ZW for ch in word)
            and bool(_DEVA_LETTER_RE.search(word)))


@dataclass
class Unit:
    cons: list[str] = field(default_factory=list)
    vowel: Optional[str] = None
    inherent: bool = False
    nasal: str = ""  # "" | "anusvara" | "chandrabindu"
    visarga: bool = False


def _parse_word(word: str) -> list[Unit]:
    word = unicodedata.normalize("NFC", word)
    chars = [c for c in word if c not in ZW]
    units: list[Unit] = []
    i = 0
    n = len(chars)
    while i < n:
        c = chars[i]
        if c in CONSONANTS:
            cluster = []
            while i < n and chars[i] in CONSONANTS:
                base = chars[i]
                ph = CONSONANTS[base]
                if i + 1 < n and chars[i + 1] == NUKTA:
                    ph = NUKTA_FORMS.get(base, ph)
                    i += 1
                cluster.append(ph)
                i += 1
                if i < n and chars[i] == VIRAMA:
                    i += 1
                    if i < n and chars[i] in CONSONANTS:
                        continue  # conjunct continues
                    units.append(Unit(cons=cluster, vowel=None))
                    cluster = []
                    break
                break
            if not cluster:
                continue
            u = Unit(cons=cluster)
            if i < n and chars[i] in MATRAS:
                u.vowel = MATRAS[chars[i]]
                i += 1
            else:
                u.vowel = "ə"
                u.inherent = True
            units.append(u)
        elif c in INDEPENDENT_VOWELS:
            units.append(Unit(cons=[], vowel=INDEPENDENT_VOWELS[c]))
            i += 1
        elif c in (ANUSVARA, CHANDRABINDU):
            if units and units[-1].vowel:
                units[-1].nasal = "chandrabindu" if c == CHANDRABINDU else "anusvara"
            i += 1
        elif c == VISARGA:
            if units:
                units[-1].visarga = True
            i += 1
        elif c in MATRAS:  # stray matra (typo): treat as vowel
            units.append(Unit(cons=[], vowel=MATRAS[c]))
            i += 1
        else:
            i += 1  # nukta without base, avagraha, digits, marks
    # ज्ञ is pronounced "gy" in Hindi
    for u in units:
        for k in range(len(u.cons) - 1):
            if u.cons[k] == "dʒ" and u.cons[k + 1] == "ɲ":
                u.cons[k:k + 2] = ["g", "j"]
                break
    # ऋ/ृ produce r + ɪ: fold the r into the consonant cluster
    for u in units:
        if u.vowel in ("rɪ", "rɪː"):
            u.cons = u.cons + ["r"]
            u.vowel = "ɪ" if u.vowel == "rɪ" else "iː"
        elif u.vowel == "lɪ":
            u.cons = u.cons + ["l"]
            u.vowel = "ɪ"
    return units


def _delete_schwas(units: list[Unit]) -> None:
    if len(units) >= 2:
        last = units[-1]
        # after a conjunct the final schwa survives only when it ends in र/य/व (मित्र, सत्य, तत्त्व);
        # दोस्त, शब्द, धर्म, ख़त्म lose it
        keeps = len(last.cons) > 1 and last.cons[-1] in ("r", "j", "ʋ")
        if last.inherent and not keeps and not last.nasal and not last.visarga:
            last.vowel = None
    for i in range(len(units) - 2, 0, -1):
        u = units[i]
        if not (u.inherent and u.vowel == "ə" and len(u.cons) == 1 and not u.nasal):
            continue
        prev, nxt = units[i - 1], units[i + 1]
        if prev.vowel is None:
            continue
        if len(nxt.cons) != 1 or nxt.vowel is None:
            continue
        u.vowel = None


def word_phonemes(word: str) -> list[str]:
    units = _parse_word(word)
    _delete_schwas(units)
    out: list[str] = []
    for idx, u in enumerate(units):
        out.extend(u.cons)
        if u.vowel is None:
            continue
        v = u.vowel
        if u.nasal:
            nxt_cons = None
            if idx + 1 < len(units) and units[idx + 1].cons:
                nxt_cons = units[idx + 1].cons[0]
            if u.nasal == "anusvara" and nxt_cons in PLACE:
                out.append(v)
                out.append(PLACE[nxt_cons])
            else:
                out.append(v + "̃")
        else:
            out.append(v)
        if u.visarga and idx == len(units) - 1:
            out.append("ḥ")  # word-final visarga (अतः); medial visarga (दुःख) is silent in Hindi
    # /ə/ before /ɦ/ is realised [ɛ] when the /ɦ/ is not followed by a full vowel (कहना, पहला, यह);
    # a schwa right after such an /ɦ/ is raised too (शहर ʃɛɦɛr, बहन bɛɦɛn). Initial ह is unaffected (हम, हवा).
    for k, ph in enumerate(out):
        if ph != "ɦ" or k == 0 or out[k - 1] != "ə":
            continue
        after = out[k + 1] if k + 1 < len(out) else None
        if after is not None and is_vowel(after) and after != "ə":
            continue
        out[k - 1] = "ɛ"
        if after == "ə":
            out[k + 1] = "ɛ"
    return ["ɦ" if p == "ḥ" else p for p in out]


def base_vowel(ph: str) -> str:
    return ph.replace("̃", "")


def is_vowel(ph: str) -> bool:
    return base_vowel(ph) in VOWELS


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(unicodedata.normalize("NFC", text or ""))


def text_phonemes(text: str) -> list[list[str]]:
    """Phonemes per Devanagari word (non-Devanagari tokens are skipped)."""
    return [word_phonemes(t) for t in tokens(text) if is_devanagari_word(t)]


def syllable_count(text: str) -> int:
    return sum(1 for w in text_phonemes(text) for p in w if is_vowel(p))


# ------------------------------------------------------------------------------- romanisation

_CASUAL_CONS = {
    "k": "k", "kʰ": "kh", "g": "g", "gʱ": "gh", "ŋ": "n", "tʃ": "ch", "tʃʰ": "chh", "dʒ": "j", "dʒʱ": "jh", "ɲ": "n",
    "ʈ": "t", "ʈʰ": "th", "ɖ": "d", "ɖʱ": "dh", "ɳ": "n", "t̪": "t", "t̪ʰ": "th", "d̪": "d", "d̪ʱ": "dh", "n": "n",
    "p": "p", "pʰ": "ph", "b": "b", "bʱ": "bh", "m": "m", "j": "y", "r": "r", "l": "l", "ʋ": "v",
    "ʃ": "sh", "s": "s", "ɦ": "h", "ɽ": "r", "ɽʱ": "rh", "q": "q", "x": "kh", "ɣ": "gh", "z": "z", "f": "f", "ʒ": "zh",
    "ɭ": "l", "ɻ": "zh",
}
_CASUAL_VOWEL = {"ə": "a", "aː": "aa", "ɪ": "i", "iː": "ee", "ʊ": "u", "uː": "oo", "eː": "e", "ɛː": "ai", "oː": "o",
                 "ɔː": "au", "æ": "ai", "ɔ": "o", "e": "e", "o": "o", "ɛ": "e", "ɪː": "ee"}
_CASUAL_FINAL = {"aː": "a", "iː": "i", "uː": "u"}
_CASUAL_NASAL = {"ə": "an", "aː": "aan", "ɪ": "in", "iː": "een", "ʊ": "un", "uː": "oon", "eː": "ein", "ɛː": "ain",
                 "oː": "on", "ɔː": "aun", "ɛ": "en", "æ": "ain", "ɔ": "on", "e": "en", "o": "on"}
_CASUAL_NASAL_FINAL = {"iː": "in", "aː": "aan", "uː": "oon"}

_IAST_CONS = {
    "k": "k", "kʰ": "kh", "g": "g", "gʱ": "gh", "ŋ": "ṅ", "tʃ": "c", "tʃʰ": "ch", "dʒ": "j", "dʒʱ": "jh", "ɲ": "ñ",
    "ʈ": "ṭ", "ʈʰ": "ṭh", "ɖ": "ḍ", "ɖʱ": "ḍh", "ɳ": "ṇ", "t̪": "t", "t̪ʰ": "th", "d̪": "d", "d̪ʱ": "dh", "n": "n",
    "p": "p", "pʰ": "ph", "b": "b", "bʱ": "bh", "m": "m", "j": "y", "r": "r", "l": "l", "ʋ": "v",
    "ʃ": "ś", "s": "s", "ɦ": "h", "ɽ": "ṛ", "ɽʱ": "ṛh", "q": "q", "x": "x", "ɣ": "ġ", "z": "z", "f": "f", "ʒ": "ž",
    "ɭ": "ḷ", "ɻ": "ḻ",
}
_IAST_VOWEL = {"ə": "a", "aː": "ā", "ɪ": "i", "iː": "ī", "ʊ": "u", "uː": "ū", "eː": "e", "ɛː": "ai", "oː": "o",
               "ɔː": "au", "æ": "æ", "ɔ": "ŏ", "e": "ĕ", "o": "ŏ", "ɛ": "e", "ɪː": "ī"}


# everyday spellings that the rules cannot predict (Urdu-origin व is usually written "w")
_CASUAL_EXCEPTIONS = {
    "वह": "woh", "वो": "wo", "वाला": "wala", "वाली": "wali", "वाले": "wale", "वहाँ": "wahaan", "वहां": "wahaan",
    "वक़्त": "waqt", "वजह": "wajah", "वादा": "waada", "यह": "yeh", "ये": "ye", "वे": "ve",
}
DEVA_WORD_RE = re.compile(r"[ऀ-ॣ॰-ॿ‌‍]+")
_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _roman_word(phs: list[str], style: str) -> str:
    out = []
    last_vowel_idx = max((k for k, p in enumerate(phs) if is_vowel(p)), default=-1)
    k = 0
    while k < len(phs):
        p = phs[k]
        if style == "casual" and p == "tʃ" and k + 1 < len(phs) and phs[k + 1] == "tʃʰ":
            out.append("cch")
            k += 2
            continue
        if is_vowel(p):
            b = base_vowel(p)
            nasal = p != b
            final = k == last_vowel_idx and k == len(phs) - 1 and len(phs) > 1
            if style == "casual":
                if b == "eː" and k > 0 and is_vowel(phs[k - 1]):
                    out.append("y")  # लिए liye, गए gaye, चाहिए chaahiye
                if nasal and k + 1 < len(phs) and phs[k + 1] in ("n", "m"):
                    nasal = False  # मैंने maine, उन्होंने unhone: the following nasal carries it
                if nasal:
                    out.append(_CASUAL_NASAL_FINAL[b] if final and b in _CASUAL_NASAL_FINAL else _CASUAL_NASAL.get(b, "an"))
                else:
                    out.append(_CASUAL_FINAL[b] if final and b in _CASUAL_FINAL else _CASUAL_VOWEL.get(b, "a"))
            else:
                out.append(_IAST_VOWEL.get(b, "a") + ("̃" if nasal else ""))
        else:
            table = _CASUAL_CONS if style == "casual" else _IAST_CONS
            piece = table.get(p, "")
            if style == "casual" and p in ("ɽ", "ɽʱ"):
                piece = "d" if p == "ɽ" else "dh"  # लड़का ladka, पढ़ाई padhai
            out.append(piece)
        k += 1
    return "".join(out)


def romanize(text: str, style: str = "casual") -> str:
    """Romanise the Devanagari words of `text` in place; Latin words, spacing and punctuation are
    kept. style="casual" gives everyday Hinglish spelling ("Aaj ki meeting mein"), "iast" a precise
    transliteration with retroflex dots ("ṭhaṇḍā")."""
    if not has_devanagari(text):
        return text

    def repl(m: re.Match) -> str:
        w = unicodedata.normalize("NFC", m.group(0))
        if style == "casual" and w in _CASUAL_EXCEPTIONS:
            return _CASUAL_EXCEPTIONS[w]
        return _roman_word(word_phonemes(w), style)

    s = DEVA_WORD_RE.sub(repl, unicodedata.normalize("NFC", text))
    s = s.replace("॥", ".").replace("।", ".").translate(_DEVA_DIGITS)
    s = re.sub(r"(^|[.!?]\s+|\n)([a-zāīūṭḍṇśṛ])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


# ------------------------------------------------------------------------------- numbers

_HI_UNITS = [
    "शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानबे", "बानबे", "तिरानबे", "चौरानबे", "पंचानबे", "छियानबे", "सत्तानबे", "अट्ठानबे", "निन्यानबे",
]


def hindi_number(n: int) -> str:
    """Integer -> Hindi words in the Indian system (सौ, हज़ार, लाख, करोड़, अरब)."""
    if n < 0:
        return "माइनस " + hindi_number(-n)
    if n < 100:
        return _HI_UNITS[n]
    parts = []
    for value, name in ((10**9, "अरब"), (10**7, "करोड़"), (10**5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= value:
            q, n = divmod(n, value)
            parts.append(f"{hindi_number(q)} {name}")
    if n:
        parts.append(_HI_UNITS[n])
    return " ".join(parts)
