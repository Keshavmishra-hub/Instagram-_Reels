"""Generated exercises for numbers, dates, times, money, percentages, phone-style digit strings and
simple maths. Each exercise is fully determined by its id (I-GEN-<kind>-<lang>-<seed>), so a generated
exercise can always be shown again (e.g. to re-record it). Phone-style numbers are fictional: they
start with 0-5, which no Indian mobile number does."""

from __future__ import annotations

import random
import re
from typing import Optional

from ..models import Exercise, Take
from ..text.devanagari import hindi_number

KINDS = ["amount", "date", "time", "money", "percent", "phone", "year", "maths"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
ID_RE = re.compile(r"^I-GEN-([a-z]+)-(en|hi)-(\d{1,9})$")


def _en(n: int, to: str = "cardinal") -> str:
    from num2words import num2words

    try:
        return num2words(n, to=to, lang="en_IN" if to == "cardinal" else "en").replace(",", "").replace("-", " ")
    except Exception:
        return num2words(n, to=to, lang="en").replace(",", "").replace("-", " ")


def _hi_year(y: int) -> str:
    if 1100 <= y <= 1999:
        h, r = divmod(y, 100)
        return f"{hindi_number(h)} सौ" + (f" {hindi_number(r)}" if r else "")
    return hindi_number(y)


def _en_year(y: int) -> str:
    from num2words import num2words

    return num2words(y, to="year", lang="en").replace(",", "").replace("-", " ")


def _indian_grouping(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def _hi_time(h: int, m: int) -> str:
    """Hindi clock time with सवा / साढ़े / पौने / डेढ़ / ढाई."""
    nxt = h % 12 + 1
    if m == 0:
        return f"{hindi_number(h)} बजे"
    if m == 15:
        return f"सवा {hindi_number(h)} बजे"
    if m == 30:
        return {1: "डेढ़ बजे", 2: "ढाई बजे"}.get(h, f"साढ़े {hindi_number(h)} बजे")
    if m == 45:
        return f"पौने {hindi_number(nxt)} बजे"
    return f"{hindi_number(h)} बजकर {hindi_number(m)} मिनट"


def generate(kind: str, lang: str, seed: int) -> Exercise:
    r = random.Random(f"{kind}-{lang}-{seed}")
    eid = f"I-GEN-{kind}-{lang}-{seed}"
    instruction = "Read the figures naturally, the way you would say them in a video."
    text = spoken = ""
    if kind == "amount":
        n = r.choice([r.randint(101, 999), r.randint(1001, 99999), r.randint(100000, 9999999), r.randint(10000000, 999999999)])
        text = _indian_grouping(n)
        spoken = _en(n) if lang == "en" else hindi_number(n)
        instruction = "Read this number in full, using lakh and crore where they apply."
    elif kind == "date":
        d, mth, y = r.randint(1, 28), r.randint(1, 12), r.choice([r.randint(1850, 1999), r.randint(2000, 2035)])
        if lang == "en":
            text = f"{d} {MONTHS_EN[mth - 1]} {y}"
            spoken = f"{_en(d, 'ordinal')} {MONTHS_EN[mth - 1]} {_en_year(y)}"
        else:
            text = f"{d} {MONTHS_HI[mth - 1]} {y}"
            spoken = f"{hindi_number(d)} {MONTHS_HI[mth - 1]} {_hi_year(y)}"
        instruction = "Read the date the way you would say it aloud."
    elif kind == "time":
        h, m = r.randint(1, 12), r.choice([0, 15, 30, 45, r.randint(1, 59)])
        if lang == "en":
            period = r.choice(["AM", "PM"])
            text = f"{h}:{m:02d} {period}"
            spoken = f"{_en(h)} {('o clock' if m == 0 else ('oh ' + _en(m) if m < 10 else _en(m)))} {' '.join(period)}"
        else:
            part = r.choice(["सुबह", "दोपहर", "शाम", "रात"])
            text = f"{part} {h}:{m:02d}"
            spoken = f"{part} {_hi_time(h, m)}"
            instruction = "Say the time the everyday Hindi way (सवा, साढ़े, पौने…)."
    elif kind == "money":
        n = r.choice([r.randint(10, 999), r.randint(1000, 99999), r.randint(100000, 9999999)])
        text = f"₹{_indian_grouping(n)}"
        spoken = f"{_en(n)} rupees" if lang == "en" else f"{hindi_number(n)} रुपये"
    elif kind == "percent":
        whole = r.randint(1, 99)
        half = r.random() < 0.3
        text = f"{whole}{'.5' if half else ''}%"
        if lang == "en":
            spoken = f"{_en(whole)}{' point five' if half else ''} percent"
        else:
            spoken = (f"साढ़े {hindi_number(whole)}" if half else hindi_number(whole)) + " प्रतिशत"
    elif kind == "phone":
        digits = str(r.randint(0, 5)) + "".join(str(r.randint(0, 9)) for _ in range(9))
        text = f"{digits[:5]} {digits[5:]}"
        spoken = " ".join(_en(int(c)) for c in digits) if lang == "en" else " ".join(hindi_number(int(c)) for c in digits)
        instruction = "A fictional phone-style number. Read it digit by digit" + (" (say 'zero' for 0)." if lang == "en" else " in Hindi.")
    elif kind == "year":
        y = r.choice([r.randint(1500, 1999), r.randint(2000, 2099)])
        text = str(y)
        spoken = _en_year(y) if lang == "en" else _hi_year(y)
        instruction = "Read the year the way it is normally said."
    else:  # maths
        a, b = r.randint(2, 99), r.randint(2, 20)
        op = r.choice(["+", "−", "×"])
        res = a + b if op == "+" else a - b if op == "−" else a * b
        text = f"{a} {op} {b} = {res}"
        if lang == "en":
            word = {"+": "plus", "−": "minus", "×": "times"}[op]
            spoken = f"{_en(a)} {word} {_en(b)} equals {_en(res)}"
        else:
            word = {"+": "जमा", "−": "घटा", "×": "गुणा"}[op]
            spoken = f"{hindi_number(a)} {word} {hindi_number(b)} बराबर {hindi_number(res)}"
        instruction = "Read the calculation aloud."
    return Exercise(
        id=eid, module="I", section="I-GEN", section_title="Generated numbers", category="numbers_special", kind="sentence",
        lang=lang, text=text, spoken=spoken, instruction=instruction + (" (Read in English.)" if lang == "en" else " (हिंदी में पढ़िए।)"),
        style="neutral", core=False, source="generated", order=100000 + seed,
    )


def from_id(eid: str) -> Optional[Exercise]:
    m = ID_RE.match(eid or "")
    if not m or m.group(1) not in KINDS:
        return None
    return generate(m.group(1), m.group(2), int(m.group(3)))


def next_generated(takes: list[Take], max_total: int = 400) -> Optional[Exercise]:
    """Rotate kinds and languages, avoiding ids that already have a take."""
    used = {t.exercise_id for t in takes if t.exercise_id.startswith("I-GEN-")}
    if len(used) >= max_total:
        return None
    k = len(used)
    for i in range(k, k + 200):
        kind = KINDS[i % len(KINDS)]
        lang = "en" if (i // len(KINDS)) % 2 == 0 else "hi"
        eid = f"I-GEN-{kind}-{lang}-{i}"
        if eid not in used:
            return generate(kind, lang, i)
    return None
