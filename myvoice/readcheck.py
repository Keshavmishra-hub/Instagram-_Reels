"""Did the speaker read the displayed text? Compares the expected words with speech-recognition output
using phonetic keys (see text/keys.py) and a monotonic weighted alignment that also allows one word
to match two (compounds split or joined differently by the recogniser)."""

from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz

from .models import ReadMatch
from .text import devanagari as dv
from .text.keys import split_words, word_keys

STRONG_MODELS = ("large", "medium", "turbo", "distil-large")


def _sim(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    best = 0.0
    for x in a:
        for y in b:
            if x == y:
                return 1.0
            if not x or not y:
                continue
            if x.rstrip("n") == y.rstrip("n") and len(x.rstrip("n")) >= 1:
                best = max(best, 0.9)  # nasalisation dropped/added by the recogniser (हैं / है, में / मे)
                continue
            s = fuzz.ratio(x, y) / 100.0
            short = min(len(x), len(y))
            if short <= 2:
                s = 0.0  # very short keys must match exactly (का / की)
            elif short == 3 and s < 0.8:
                s = 0.0
            best = max(best, s)
    return best


THRESHOLD = 0.7
JOIN_THRESHOLD = 0.85  # one word <-> two words must be a near-exact match


def _english_number_words(n: int, year: bool) -> str:
    try:
        from num2words import num2words

        if year and 1100 <= n <= 2099:
            return num2words(n, to="year", lang="en")
        return num2words(n, lang="en")
    except Exception:
        return str(n)


def hindi_year(n: int) -> str:
    if 1100 <= n <= 1999:
        hundreds, rest = divmod(n, 100)
        return dv.hindi_number(hundreds) + " सौ" + (" " + dv.hindi_number(rest) if rest else "")
    return dv.hindi_number(n)


def _expand_numbers(text: str, lang: str, expected_text: str) -> str:
    """Recognisers write digits; the expected text is in words. Expand each number in the way that
    best matches the expected text (cardinal, year, or digit-by-digit)."""
    exp_keys = " ".join(k for w in split_words(expected_text) for k in word_keys(w)[:1])
    currency = {"₹": ("rupees", "रुपये"), "$": ("dollars", "डॉलर"), "€": ("euros", "यूरो"), "£": ("pounds", "पाउंड")}
    for sym, (en_w, hi_w) in currency.items():  # ₹2,500 is read "two thousand five hundred rupees"
        text = re.sub(re.escape(sym) + r"\s*(\d[\d,.]*)", lambda m: f"{m.group(1)} {en_w if lang == 'en' else hi_w}", text)
    text = text.replace("%", " percent " if lang == "en" else " प्रतिशत ")

    def candidates(digits: str) -> list[str]:
        n = int(digits)
        out = []
        if lang == "en":
            out += [_english_number_words(n, False), _english_number_words(n, True)]
            if len(digits) >= 3:
                out.append(" ".join(_english_number_words(int(d), False) for d in digits))
        else:
            out += [dv.hindi_number(n), hindi_year(n)]
            if len(digits) >= 3:
                out.append(" ".join(dv.hindi_number(int(d)) for d in digits))
        return [c.replace("-", " ").replace(",", " ") for c in out]

    def repl(m: re.Match) -> str:
        digits = m.group(0).replace(",", "")
        if not digits.isdigit() or len(digits) > 12:
            return m.group(0)
        cands = candidates(digits)
        def score(c: str) -> float:
            ck = " ".join(k for w in split_words(c) for k in word_keys(w)[:1])
            return fuzz.partial_ratio(ck, exp_keys) if ck and exp_keys else 0
        return " " + max(cands, key=score) + " "

    return re.sub(r"\d[\d,]*", repl, text)


def align(expected: list[str], hyp: list[str]) -> tuple[set[int], set[int]]:
    """Weighted LCS. Returns (matched expected indexes, matched hypothesis indexes)."""
    n, m = len(expected), len(hyp)
    ek = [word_keys(w) for w in expected]
    hk = [word_keys(w) for w in hyp]
    sim = [[_sim(ek[i], hk[j]) for j in range(m)] for i in range(n)]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple]] = [[()] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best, how = dp[i - 1][j], ("skip_e",)
            if dp[i][j - 1] > best:
                best, how = dp[i][j - 1], ("skip_h",)
            s = sim[i - 1][j - 1]
            if s >= THRESHOLD and dp[i - 1][j - 1] + s > best:
                best, how = dp[i - 1][j - 1] + s, ("match",)
            if j >= 2 and sim[i - 1][j - 1] < 1.0:
                joined = tuple(a + b for a in hk[j - 2] for b in hk[j - 1])
                s2 = _sim(ek[i - 1], joined)
                if s2 >= JOIN_THRESHOLD and dp[i - 1][j - 2] + s2 > best:
                    best, how = dp[i - 1][j - 2] + s2, ("split",)
            if i >= 2 and sim[i - 1][j - 1] < 1.0:
                joined = tuple(a + b for a in ek[i - 2] for b in ek[i - 1])
                s3 = _sim(joined, hk[j - 1])
                if s3 >= JOIN_THRESHOLD and dp[i - 2][j - 1] + 2 * s3 - 0.3 > best:
                    best, how = dp[i - 2][j - 1] + 2 * s3 - 0.3, ("join",)
            dp[i][j], back[i][j] = best, how
    me: set[int] = set()
    mh: set[int] = set()
    i, j = n, m
    while i > 0 and j > 0:
        how = back[i][j][0] if back[i][j] else "skip_e"
        if how == "match":
            me.add(i - 1); mh.add(j - 1); i -= 1; j -= 1
        elif how == "split":
            me.add(i - 1); mh.update({j - 1, j - 2}); i -= 1; j -= 2
        elif how == "join":
            me.update({i - 1, i - 2}); mh.add(j - 1); i -= 2; j -= 1
        elif how == "skip_h":
            j -= 1
        else:
            i -= 1
    return me, mh


def check(expected_text: str, hyp_text: str, lang: str, model: str = "", avg_logprob: Optional[float] = None) -> ReadMatch:
    expected = split_words(expected_text)
    if not expected:
        return ReadMatch(verdict="unchecked")
    num_lang = "en" if lang == "en" else "hi"
    hyp = split_words(_expand_numbers(hyp_text or "", num_lang, expected_text))
    me, mh = align(expected, hyp) if hyp else (set(), set())
    coverage = len(me) / len(expected)
    precision = len(mh) / len(hyp) if hyp else 0.0
    strong = any(s in (model or "") for s in STRONG_MODELS)
    if lang == "en":
        read_at, fail_below = (0.85, 0.5) if strong else (0.8, 0.45)
    else:  # Hindi / Hinglish recognition is weaker: be more forgiving
        read_at, fail_below = (0.75, 0.4) if strong else (0.6, 0.3)
    if avg_logprob is not None and avg_logprob < -1.0:
        fail_below -= 0.15  # an unsure recogniser should not fail a take on its own
    verdict = "read" if coverage >= read_at else ("not_read" if coverage < fail_below else "partial")
    return ReadMatch(
        coverage=round(coverage, 3), precision=round(precision, 3), verdict=verdict,
        expected_words=expected, missing=[i for i in range(len(expected)) if i not in me],
        extra_words=[hyp[j] for j in range(len(hyp)) if j not in mh][:30],
    )
