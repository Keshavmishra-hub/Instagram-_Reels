"""Text normalisation for narration.

The subtitle shows what the script says ("In 1947, output rose 4.5%"), while the TTS engine
must hear what a narrator would say ("In nineteen forty seven, output rose four point five
percent"). We keep a one-to-many mapping display-token -> spoken words so word timings coming
back from the TTS/aligner can be mapped onto the subtitle tokens exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

try:
    from num2words import num2words
except Exception:  # pragma: no cover
    num2words = None  # type: ignore

PUNCT_TRAIL = ".,!?;:…\"'”’)]}»"
PUNCT_LEAD = "\"'“‘([{«"

UNITS = {
    "km": "kilometres", "kms": "kilometres", "km²": "square kilometres", "km2": "square kilometres", "sq km": "square kilometres",
    "m": "metres", "cm": "centimetres", "mm": "millimetres", "kg": "kilograms", "g": "grams", "mg": "milligrams",
    "ha": "hectares", "l": "litres", "ml": "millilitres", "mt": "million tonnes", "kmph": "kilometres per hour",
    "km/h": "kilometres per hour", "mph": "miles per hour", "°c": "degrees Celsius", "°f": "degrees Fahrenheit",
    "c": "degrees Celsius", "gw": "gigawatts", "mw": "megawatts", "kw": "kilowatts", "kwh": "kilowatt hours",
    "gb": "gigabytes", "tb": "terabytes", "mb": "megabytes", "ft": "feet", "sq": "square",
}
SCALE_WORDS = {"thousand", "million", "billion", "trillion", "lakh", "lakhs", "crore", "crores"}
CURRENCY = {"$": "dollars", "₹": "rupees", "€": "euros", "£": "pounds", "¥": "yen", "rs": "rupees", "rs.": "rupees", "inr": "rupees", "usd": "dollars"}
COUNT_NOUNS = {
    "people", "farmers", "years", "tonnes", "tons", "seeds", "samples", "species", "villages", "acres", "hectares",
    "metres", "meters", "kilometres", "kilometers", "km", "kg", "litres", "liters", "times", "cases", "days", "hours",
    "units", "companies", "workers", "families", "students", "deaths", "cattle", "cows", "animals", "trees", "plants",
    "items", "varieties", "crops", "boxes", "steps", "feet", "miles", "members", "employees", "dollars", "rupees",
    "crore", "lakh", "votes", "seats", "copies", "pages", "words",
}
SYMBOLS = {"&": "and", "+": "plus", "=": "equals", "@": "at", "#": "number", "~": "about", "≈": "about"}
LETTER_NAMES = {c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}

_DEFAULT_LEXICON = Path(__file__).resolve().parents[2] / "data" / "lexicon.yaml"


@dataclass
class Token:
    display: str  # exactly as shown in subtitles
    spoken: list[str] = field(default_factory=list)  # words sent to TTS (may be empty for pure symbols)


def load_lexicon(extra: Optional[Path] = None) -> dict[str, str]:
    """word -> spoken respelling. Case-sensitive keys for acronyms, lower-case keys match any case."""
    lex: dict[str, str] = {}
    for p in [_DEFAULT_LEXICON, extra]:
        if p and Path(p).exists():
            data = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
            for k, v in (data.get("words") or {}).items():
                lex[str(k)] = str(v)
    return lex


def _clean_words(text: str) -> list[str]:
    text = text.replace(",", " ").replace("-", " ").replace("  ", " ")
    return [w for w in text.split() if w]


def _n2w(value: float | int, mode: str = "cardinal", indian: bool = False) -> list[str]:
    if num2words is None:
        return [str(value)]
    lang = "en_IN" if indian else "en"
    try:
        if mode == "year":
            words = num2words(int(value), to="year")
            words = words.replace(" and ", " ").replace("oh-", "oh ")
        elif mode == "ordinal":
            words = num2words(int(value), to="ordinal", lang=lang)
        else:
            words = num2words(value, lang=lang)
            if not indian:
                words = words.replace(" and ", " ")
    except Exception:
        return [str(value)]
    return _clean_words(words)


def _parse_number(s: str) -> tuple[Optional[float], bool, bool]:
    """Return (value, is_integer, indian_grouping)."""
    indian = bool(re.fullmatch(r"\d{1,2}(,\d{2})+,\d{3}(\.\d+)?", s))
    raw = s.replace(",", "")
    try:
        v = float(raw)
    except ValueError:
        return None, False, False
    return v, "." not in raw, indian


def _speak_number(num: str, next_word: str = "", prev_word: str = "") -> list[str]:
    value, is_int, indian = _parse_number(num)
    if value is None:
        return [num]
    nxt = next_word.lower().strip(PUNCT_TRAIL)
    if is_int and "," not in num and 1100 <= value <= 2099 and nxt not in COUNT_NOUNS and nxt not in UNITS and nxt not in SCALE_WORDS:
        return _n2w(int(value), "year")
    if is_int:
        return _n2w(int(value), indian=indian)
    # decimals: read digits after the point individually ("four point five", "zero point two five")
    return _n2w(value, indian=indian)


TOKEN_RE = re.compile(
    r"""^(?P<lead>[\"'“‘(\[{«]*)
        (?P<cur>[$₹€£¥])?
        (?P<neg>[−\-–])?
        (?P<num>\d+(?:,\d+)*(?:\.\d+)?)
        (?P<suffix>%|°[CF]|°|st|nd|rd|th|s|x|km²|km|kg|ha|mm|cm|m|k|K|M|B|bn|cr|GW|MW|kW|kWh)?
        (?P<range>[–\-](?P<num2>\d+(?:,\d+)*(?:\.\d+)?))?
        (?P<trail>[.,!?;:…\"'”’)\]}»]*)$""",
    re.X,
)


def normalize_tokens(text: str, language: str = "en", lexicon: Optional[dict[str, str]] = None) -> list[Token]:
    """Split display text into tokens and attach the spoken words for each."""
    lexicon = lexicon or {}
    lower_lex = {k.lower(): v for k, v in lexicon.items() if not k.isupper()}
    raw_tokens = text.split()
    tokens: list[Token] = []
    english = language == "en"
    i = 0
    while i < len(raw_tokens):
        disp = raw_tokens[i]
        nxt = raw_tokens[i + 1] if i + 1 < len(raw_tokens) else ""
        prev = raw_tokens[i - 1] if i > 0 else ""
        core = disp.strip(PUNCT_LEAD).rstrip(PUNCT_TRAIL)
        trail = disp[len(disp.rstrip(PUNCT_TRAIL)):]
        spoken: list[str] = []

        # 1) explicit lexicon entries (case-sensitive acronyms first, then case-insensitive)
        if core in lexicon:
            spoken = lexicon[core].split()
        elif core.lower() in lower_lex:
            spoken = lower_lex[core.lower()].split()
        elif english and (m := TOKEN_RE.match(disp)):
            cur, neg, num, suffix, num2 = m.group("cur"), m.group("neg"), m.group("num"), m.group("suffix"), m.group("num2")
            words: list[str] = []
            if neg:
                words.append("minus")
            sfx = (suffix or "")
            if sfx in ("st", "nd", "rd", "th") and num.replace(",", "").isdigit():
                words += _n2w(int(num.replace(",", "")), "ordinal")
            elif sfx == "s" and re.fullmatch(r"\d{4}", num):  # 1990s
                base = _n2w(int(num), "year")
                last = base[-1]
                base[-1] = (last[:-1] + "ies") if last.endswith("y") else (last + "s")
                words += base
            else:
                words += _speak_number(num, nxt, prev)
                if sfx == "%":
                    words.append("percent")
                elif sfx in ("°C",):
                    words += ["degrees", "Celsius"]
                elif sfx in ("°F",):
                    words += ["degrees", "Fahrenheit"]
                elif sfx == "°":
                    words.append("degrees")
                elif sfx in ("k", "K"):
                    words.append("thousand")
                elif sfx in ("M",):
                    words.append("million")
                elif sfx in ("B", "bn"):
                    words.append("billion")
                elif sfx == "cr":
                    words.append("crore")
                elif sfx == "x":
                    words.append("times")
                elif sfx.lower() in UNITS:
                    words += UNITS[sfx.lower()].split()
            if num2:
                words.append("to")
                words += _speak_number(num2, nxt, prev)
            if cur:
                # currency word goes after any scale word that follows ("$4.5 billion" -> "... billion dollars")
                nxt_core = nxt.lower().strip(PUNCT_TRAIL)
                if nxt_core in SCALE_WORDS:
                    tokens.append(Token(display=disp, spoken=words))
                    cur_words = [nxt_core] + CURRENCY[cur].split()
                    nxt_trail = nxt[len(nxt.rstrip(PUNCT_TRAIL)):].strip("\"'”’)]}»")
                    if nxt_trail:
                        cur_words[-1] += nxt_trail
                    tokens.append(Token(display=nxt, spoken=cur_words))
                    i += 2
                    continue
                words += CURRENCY[cur].split()
            spoken = words
        elif english and core.isupper() and 2 <= len(core) <= 6 and core.isalpha():
            # Unknown acronym: spell it out unless it reads like a word (has vowels in a pronounceable pattern)
            pronounceable = len(core) >= 4 and re.search(r"[AEIOU]", core[1:]) and not re.search(r"[^AEIOU]{4,}", core)
            spoken = [core.capitalize()] if pronounceable else list(core)
        elif english and core.lower() in UNITS and prev and re.search(r"\d", prev):
            spoken = UNITS[core.lower()].split()
        elif core in SYMBOLS:
            spoken = [SYMBOLS[core]]
        elif english and core.lower() in ("rs", "rs.", "inr"):
            spoken = ["rupees"]
        else:
            cleaned = core.replace("—", " ").replace("–", " ")
            if english and re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z]+)+", cleaned) and cleaned.lower() not in ("co-op", "e-mail"):
                cleaned = cleaned.replace("-", " ")  # "terawatt-hours" -> two spoken words, exact timing per word
            spoken = [w for w in re.split(r"\s+", cleaned) if w]
        if spoken and trail:
            # keep sentence punctuation for prosody
            spoken[-1] = spoken[-1] + trail.strip("\"'”’)]}»")
        spoken = [w for w in spoken if w]
        if not re.search(r"\w", disp) and core not in SYMBOLS and tokens:
            # standalone punctuation (e.g. an em dash) rides along with the previous word on screen
            tokens[-1].display = f"{tokens[-1].display} {disp}"
            if tokens[-1].spoken and disp.strip() in ("—", "–", "-", "…", ";", ":"):
                tokens[-1].spoken[-1] = tokens[-1].spoken[-1].rstrip(",") + ","
            i += 1
            continue
        tokens.append(Token(display=disp, spoken=spoken))
        i += 1
    return tokens


def spoken_text(tokens: list[Token]) -> str:
    return " ".join(w for t in tokens for w in t.spoken)


def count_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1 if word.strip() else 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    return max(1, n)
