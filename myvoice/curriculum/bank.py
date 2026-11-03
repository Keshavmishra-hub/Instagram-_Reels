"""The exercise bank: built-in YAML modules (curriculum/data/*.yaml) plus imported or generated
exercises in the data folder (exercises/*.yaml|json).

YAML layout:

    module: A
    sections:
      - code: A-NORM                     # stable id prefix; exercises become A-NORM-01, A-NORM-02, ...
        title: Normal conversational voice
        category: voice_identity
        defaults: {lang: en, style: conversational}
        instruction: Speak in your everyday voice.
        exercises:
          - "Plain strings are the text to read."
          - {text: "...", lang: hi, emotion: curiosity, context: "..."}

IDs are positional within a section, so new exercises must be appended at the end of a section
(never inserted or reordered) — recordings refer to exercises by id. An explicit `id:` overrides.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml

from ..config import PACKAGE
from ..models import CATEGORIES, EMOTIONS, LANGUAGES, MODULES, STYLES, Exercise
from ..text import devanagari as dv
from ..text.phonemes import analyse_text

DATA_DIR = PACKAGE / "curriculum" / "data"
SECTION_KEYS = {"kind", "lang", "category", "style", "emotion", "pace", "volume", "instruction", "readcheck", "train",
                "core", "focus", "auto_stop", "min_sec", "max_sec", "repeat", "context"}
# syllables per second (fastest, slowest) considered normal for each pace
RATES = {"slow": (4.6, 2.0), "normal": (6.8, 2.8), "fast": (9.0, 3.8)}
DEFAULT_AUTO_STOP = {"sentence": 1.0, "dialogue": 1.1, "word_list": 1.5, "paragraph": 1.6, "prompt": 2.8,
                     "sustained": 0.7, "glide": 0.8, "silence": 0.0, "clap": 0.0}  # multiples of the user's base silence


@dataclass
class Section:
    code: str
    module: str
    title: str
    category: str
    exercise_ids: list[str] = field(default_factory=list)


@dataclass
class ExerciseInfo:
    """Derived facts about an exercise, computed once."""
    syllables: int
    words: int
    en_phonemes: tuple[str, ...]
    hi_phonemes: tuple[str, ...]
    expected: Optional[tuple[float, float]]  # seconds of speech
    roman: str
    has_devanagari: bool


class BankError(ValueError):
    pass


TEMPLATE_RE = re.compile(r"\{([^{}|]*)\|([^{}|]*)\}")


def render(text: str, forms: str = "", name: str = "") -> str:
    """Fill templates: {रहा|रही} picks the speaker's Hindi verb form (m/f; both shown when unset)
    and {name} becomes the speaker's name."""
    if forms == "m":
        text = TEMPLATE_RE.sub(lambda m: m.group(1), text)
    elif forms == "f":
        text = TEMPLATE_RE.sub(lambda m: m.group(2), text)
    else:
        text = TEMPLATE_RE.sub(lambda m: f"{m.group(1)}/{m.group(2)}", text)
    return text.replace("{name}", name.strip() or "…")


def spoken_text(ex: Exercise, forms: str = "m", name: str = "") -> str:
    return render(ex.spoken or ex.text, forms, name)


def _expected(ex: Exercise, syllables: int, words: int) -> Optional[tuple[float, float]]:
    if ex.kind in ("prompt", "silence", "clap", "sustained", "glide") or syllables == 0:
        return None
    fast, slow = RATES.get(ex.pace, RATES["normal"])
    lo, hi = syllables / fast, syllables / slow
    if ex.kind == "word_list":
        hi += 0.5 * words  # a short pause after each word
    if ex.kind == "paragraph":
        hi *= 1.3
    if ex.emotion in ("dramatic", "suspense", "sadness", "calmness", "inspirational") or ex.style in (
            "cinematic_intro", "movie_narration", "dramatic_opening", "suspense"):
        hi *= 1.4  # deliberate pauses
    return (round(lo, 2), round(hi + 0.6, 2))


class ExerciseBank:
    def __init__(self, extra_dirs: Iterable[Path] = ()):
        self.exercises: list[Exercise] = []
        self.by_id: dict[str, Exercise] = {}
        self.sections: dict[str, Section] = {}
        self.info: dict[str, ExerciseInfo] = {}
        self.errors: list[str] = []
        order = 0
        files = sorted(DATA_DIR.glob("*.yaml"))
        for d in extra_dirs:
            if Path(d).exists():
                files += sorted(Path(d).glob("*.yaml")) + sorted(Path(d).glob("*.json"))
        for f in files:
            source = "bank" if f.parent == DATA_DIR else "imported"
            try:
                doc = json.loads(f.read_text(encoding="utf-8")) if f.suffix == ".json" else yaml.safe_load(f.read_text(encoding="utf-8"))
                order = self._load_doc(doc or {}, source, order, f.name)
            except BankError as e:
                if source == "bank":
                    raise
                self.errors.append(f"{f.name}: {e}")
            except Exception as e:  # imported files must not break the studio
                if source == "bank":
                    raise
                self.errors.append(f"{f.name}: {e}")

    # -------------------------------------------------------------------------------------------
    def _load_doc(self, doc: dict, source: str, order: int, fname: str) -> int:
        module = str(doc.get("module", "")).strip()
        if module not in MODULES:
            raise BankError(f"{fname}: unknown module {module!r}")
        for sec in doc.get("sections") or []:
            code = str(sec.get("code", "")).strip()
            if not re.fullmatch(r"[A-Z][A-Za-z0-9-]{1,40}", code):
                raise BankError(f"{fname}: bad section code {code!r}")
            if code in self.sections:
                raise BankError(f"{fname}: duplicate section code {code}")
            title = sec.get("title", code)
            defaults = {k: v for k, v in (sec.get("defaults") or {}).items() if k in SECTION_KEYS}
            for k in SECTION_KEYS:
                if k in sec and k not in defaults:
                    defaults[k] = sec[k]
            category = defaults.get("category") or sec.get("category")
            if category not in CATEGORIES:
                raise BankError(f"{fname}: section {code}: unknown category {category!r}")
            section = Section(code=code, module=module, title=title, category=category)
            self.sections[code] = section
            core_first = sec.get("core_first")  # first N exercises form the core pass; the rest are the extended pool
            for n, item in enumerate(sec.get("exercises") or [], start=1):
                if isinstance(item, str):
                    item = {"text": item}
                if core_first is not None and n > int(core_first) and "core" not in item:
                    item = {**item, "core": False}
                unknown = [k for k in item if k not in Exercise.model_fields or item[k] is None]
                if unknown:  # usually an unquoted YAML value split at a comma or colon
                    raise BankError(f"{fname}: section {code} item {n}: unexpected keys {unknown} (quote values containing ',' or ': ')")
                data = {**defaults, **item}
                data.setdefault("category", category)
                eid = str(item.get("id") or f"{code}-{n:02d}")
                if eid in self.by_id:
                    raise BankError(f"{fname}: duplicate exercise id {eid}")
                order += 1
                ex = Exercise(id=eid, module=module, section=code, section_title=title, order=order, source=source,
                              **{k: v for k, v in data.items() if k in Exercise.model_fields and k not in ("id", "module", "section", "section_title", "order", "source")})
                self._validate(ex, fname)
                self.exercises.append(ex)
                self.by_id[eid] = ex
                section.exercise_ids.append(eid)
        return order

    def _validate(self, ex: Exercise, fname: str) -> None:
        where = f"{fname}: {ex.id}"
        if ex.emotion not in EMOTIONS:
            raise BankError(f"{where}: unknown emotion {ex.emotion!r}")
        if ex.style not in STYLES:
            raise BankError(f"{where}: unknown style {ex.style!r}")
        if ex.lang not in LANGUAGES:
            raise BankError(f"{where}: unknown language {ex.lang!r}")
        if ex.kind not in ("silence", "clap") and not ex.text.strip():
            raise BankError(f"{where}: empty text")
        if ex.kind in ("sentence", "paragraph", "word_list", "dialogue") and ex.readcheck and re.search(r"\d", ex.text) and not ex.spoken:
            raise BankError(f"{where}: text contains digits; add `spoken:` with the words to be said")

    # -------------------------------------------------------------------------------------------
    def get(self, eid: str) -> Optional[Exercise]:
        ex = self.by_id.get(eid)
        if ex is None and eid.startswith("I-GEN-"):
            from .generators import from_id

            ex = from_id(eid)
        return ex

    def derived(self, ex: Exercise) -> ExerciseInfo:
        info = self.info.get(ex.id)
        if info is None:
            spoken = spoken_text(ex, "m", "Name")
            a = analyse_text(spoken) if ex.kind not in ("silence", "clap", "sustained", "glide") else {"en": (), "hi": (), "syllables": 0, "words": 0}
            plain = render(ex.text, "m", "Name")
            roman = ex.roman or (dv.romanize(plain) if dv.has_devanagari(plain) else "")
            info = ExerciseInfo(
                syllables=a["syllables"], words=a["words"], en_phonemes=tuple(a["en"]), hi_phonemes=tuple(a["hi"]),
                expected=_expected(ex, a["syllables"], a["words"]), roman=roman, has_devanagari=dv.has_devanagari(ex.text),
            )
            self.info[ex.id] = info
        return info

    def auto_stop_seconds(self, ex: Exercise, base: float) -> float:
        if ex.auto_stop is not None:
            return float(ex.auto_stop)
        return round(base * DEFAULT_AUTO_STOP.get(ex.kind, 1.0), 2)

    def public(self, ex: Exercise, base_silence: float = 1.8, forms: str = "", name: str = "") -> dict:
        info = self.derived(ex)
        d = ex.model_dump()
        text = render(ex.text, forms, name)
        roman = ex.roman or (dv.romanize(text) if ex.lang in ("hi", "hinglish") and dv.has_devanagari(text) else "")
        d.update(
            text=text,
            spoken=render(ex.spoken, forms, name) if ex.spoken else "",
            cue=render(ex.cue, forms, name),
            templated=bool(TEMPLATE_RE.search(ex.text) or "{name}" in ex.text),
            module_title=MODULES.get(ex.module, {}).get("title", ex.module),
            category_title=CATEGORIES.get(ex.category, ex.category),
            emotion_title=EMOTIONS.get(ex.emotion, ex.emotion),
            style_title=STYLES.get(ex.style, ex.style),
            lang_title=LANGUAGES.get(ex.lang, ex.lang),
            roman=roman,
            expected=list(info.expected) if info.expected else None,
            syllables=info.syllables,
            words=info.words,
            auto_stop_sec=self.auto_stop_seconds(ex, base_silence),
        )
        if ex.kind in ("silence", "clap"):
            d["fixed_sec"] = ex.max_sec or 5.0
        return d

    def module_sections(self, module: str) -> list[Section]:
        return [s for s in self.sections.values() if s.module == module]
