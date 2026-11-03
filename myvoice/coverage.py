"""Dataset coverage and readiness.

Completeness is measured on what the APPROVED recordings actually contain (minutes per language,
phoneme and diphone counts from their transcripts, emotions, narration genres, consistency across
sessions, quality), never on how many exercises were completed.

Milestones map to cloning strategies:
  reference    enough excellent clips for zero-shot / instant cloning (ElevenLabs IVC, IndicF5,
               Chatterbox, F5-style models): a few clean 6-15 s clips per language and style
  finetune     the minimum for professional cloning / fine-tuning (ElevenLabs PVC asks >= 30 min)
  professional broad, consistent coverage (2 h+, all sounds, emotions and genres)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

from .curriculum.bank import ExerciseBank
from .models import EMOTIONS, MODULES, STYLES, Take
from .text.phonemes import EN_INVENTORY, EN_RARE, HI_INVENTORY, HI_RARE, PHONEME_LABELS, analyse_text, diphones

GENRES = ["cinematic_intro", "movie_narration", "documentary", "reel_hook", "motivational", "historical", "business_explainer",
          "educational", "travel", "agriculture", "personal_branding", "promotional", "dramatic_opening", "suspense", "conclusion"]
EMOTION_KEYS = [e for e in EMOTIONS if e != "neutral"]
TRAIN_LANGS = ("en", "hi", "hinglish")


def usable_seconds(t: Take) -> float:
    """Length after trimming excess silence (what an export would contain)."""
    span = t.analysis.get("speech_span") or 0.0
    if span <= 0:
        return 0.0
    return min(t.audio.duration, span + 0.5)


def _day(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).date().isoformat()
    except (TypeError, ValueError):
        return ""


class Coverage:
    def __init__(self, bank: ExerciseBank, takes: list[Take], sessions: list):
        self.bank = bank
        self.all_takes = [t for t in takes if not t.trashed]
        self.approved = [t for t in self.all_takes if t.status == "approved"]
        self.training = [t for t in self.approved if t.train and t.lang in TRAIN_LANGS]
        self.sessions = sessions
        self._compute()

    # -------------------------------------------------------------------------------------------
    def _phonemes_for(self, t: Take) -> tuple[tuple[str, ...], tuple[str, ...]]:
        ex = self.bank.get(t.exercise_id)
        if t.transcript_source == "prompt" and ex is not None and not ex.cue and "{" not in ex.text:
            info = self.bank.derived(ex)
            return info.en_phonemes, info.hi_phonemes
        a = analyse_text(t.transcript or t.spoken or t.text)
        return a["en"], a["hi"]

    def _compute(self) -> None:
        self.lang_seconds: dict[str, float] = defaultdict(float)
        self.category_seconds: dict[str, float] = defaultdict(float)
        self.emotion_counts: Counter = Counter()
        self.style_counts: Counter = Counter()
        self.en_counts: Counter = Counter()
        self.hi_counts: Counter = Counter()
        self.en_di: set = set()
        self.hi_di: set = set()
        self.module_done: dict[str, set] = defaultdict(set)
        for t in self.approved:
            self.module_done[t.module].add(t.exercise_id)
        for t in self.training:
            sec = usable_seconds(t)
            self.lang_seconds[t.lang] += sec
            self.category_seconds[t.category] += sec
            if t.emotion != "neutral":
                self.emotion_counts[t.emotion] += 1
            self.style_counts[t.style] += 1
            en, hi = self._phonemes_for(t)
            self.en_counts.update(en)
            self.hi_counts.update(hi)
            self.en_di.update(diphones(en))
            self.hi_di.update(diphones(hi))
        # diphones present anywhere in the curriculum = the universe we can measure against
        self.en_di_universe: set = set()
        self.hi_di_universe: set = set()
        for ex in self.bank.exercises:
            if not ex.train:
                continue
            info = self.bank.derived(ex)
            self.en_di_universe.update(diphones(info.en_phonemes))
            self.hi_di_universe.update(diphones(info.hi_phonemes))
        self.approved_seconds = sum(self.lang_seconds.values())
        self.recorded_seconds = sum(t.audio.duration for t in self.all_takes)
        scores = [t.quality.score for t in self.approved if t.quality]
        self.mean_score = round(sum(scores) / len(scores), 1) if scores else None
        # consistency anchors: sessions and days in which each anchor was approved
        self.anchor_sessions: dict[str, set] = defaultdict(set)
        self.anchor_days: dict[str, set] = defaultdict(set)
        for t in self.approved:
            if t.module == "J":
                self.anchor_sessions[t.exercise_id].add(t.session_id)
                self.anchor_days[t.exercise_id].add(_day(t.created_at))

    # -------------------------------------------------------------------------------------------
    def phoneme_progress(self, lang: str, common: int, rare: int) -> float:
        inv, counts, rare_set = (EN_INVENTORY, self.en_counts, EN_RARE) if lang == "en" else (HI_INVENTORY, self.hi_counts, HI_RARE)
        vals = [min(1.0, counts.get(p, 0) / (rare if p in rare_set else common)) for p in inv]
        return sum(vals) / len(vals)

    def diphone_ratio(self, lang: str) -> float:
        got, uni = (self.en_di, self.en_di_universe) if lang == "en" else (self.hi_di, self.hi_di_universe)
        return len(got & uni) / len(uni) if uni else 0.0

    def excellent_reference_clips(self, lang: str) -> int:
        n = 0
        for t in self.training:
            if t.lang == lang and t.emotion == "neutral" and t.quality.score >= 85 and 6.0 <= usable_seconds(t) <= 15.0:
                n += 1
        return n

    def consistency_days(self) -> int:
        days = set()
        for d in self.anchor_days.values():
            days |= d
        return len(days)

    def consistency_sessions(self) -> int:
        s = set()
        for v in self.anchor_sessions.values():
            s |= v
        return len(s)

    def _checks(self) -> list[dict]:
        mins = lambda s: s / 60.0  # noqa: E731
        a_core = [e for e in self.bank.exercises if e.module == "A" and e.core and e.train]
        a_done = sum(1 for e in a_core if e.id in self.module_done["A"])
        setup = {
            "room_tone": any(t.module == "S" and t.kind == "silence" for t in self.all_takes),
            "consent": any(t.category == "consent" and t.status == "approved" for t in self.all_takes),
        }
        emo_cov = lambda k: sum(1 for e in EMOTION_KEYS if self.emotion_counts.get(e, 0) >= k)  # noqa: E731
        genre_cov = lambda k: sum(1 for g in GENRES if self.style_counts.get(g, 0) >= k)  # noqa: E731
        spont = sum(usable_seconds(t) for t in self.training if t.kind == "prompt")
        c = []

        def add(milestone, cid, label, value, target, fmt="{:.0f}"):
            c.append({"milestone": milestone, "id": cid, "label": label, "value": round(float(value), 3), "target": target,
                      "progress": round(min(1.0, float(value) / target) if target else 1.0, 3), "display": fmt.format(value) + " / " + fmt.format(target)})

        add("setup", "room_tone", "Room tone recorded", 1 if setup["room_tone"] else 0, 1)
        add("setup", "consent", "Consent statement approved", 1 if setup["consent"] else 0, 1)
        add("identity", "a_core", "Module A core exercises approved", a_done, max(1, round(0.8 * len(a_core))))
        add("identity", "minutes", "Approved minutes", mins(self.approved_seconds), 5, "{:.1f}")
        for lang, name in (("en", "English"), ("hi", "Hindi"), ("hinglish", "Hinglish")):
            add("reference", f"ref_{lang}", f"Excellent 6–15 s neutral clips · {name}", self.excellent_reference_clips(lang), 3)
        add("reference", "ref_narration", "Narration-style takes", sum(self.style_counts.get(s, 0) for s in ("narration", "documentary", "storytelling")), 3)
        add("finetune", "minutes", "Approved minutes", mins(self.approved_seconds), 30, "{:.1f}")
        for lang, name in (("en", "English"), ("hi", "Hindi"), ("hinglish", "Hinglish")):
            add("finetune", f"min_{lang}", f"{name} minutes", mins(self.lang_seconds.get(lang, 0.0)), 8, "{:.1f}")
        add("finetune", "ph_en", "English phonemes (each ≥10, rare ≥3)", 100 * self.phoneme_progress("en", 10, 3), 100, "{:.0f}%")
        add("finetune", "ph_hi", "Hindi phonemes (each ≥10, rare ≥3)", 100 * self.phoneme_progress("hi", 10, 3), 100, "{:.0f}%")
        add("finetune", "di_en", "English diphone coverage", 100 * self.diphone_ratio("en"), 50, "{:.0f}%")
        add("finetune", "di_hi", "Hindi diphone coverage", 100 * self.diphone_ratio("hi"), 50, "{:.0f}%")
        add("finetune", "emotions", "Emotions with ≥3 takes", emo_cov(3), 9)
        add("finetune", "sessions", "Recording sessions", len([s for s in self.sessions if s]), 2)
        add("professional", "minutes", "Approved minutes", mins(self.approved_seconds), 120, "{:.0f}")
        for lang, name in (("en", "English"), ("hi", "Hindi"), ("hinglish", "Hinglish")):
            add("professional", f"min_{lang}", f"{name} minutes", mins(self.lang_seconds.get(lang, 0.0)), 30, "{:.0f}")
        add("professional", "ph_en", "English phonemes (each ≥25, rare ≥6)", 100 * self.phoneme_progress("en", 25, 6), 100, "{:.0f}%")
        add("professional", "ph_hi", "Hindi phonemes (each ≥25, rare ≥6)", 100 * self.phoneme_progress("hi", 25, 6), 100, "{:.0f}%")
        add("professional", "di_en", "English diphone coverage", 100 * self.diphone_ratio("en"), 75, "{:.0f}%")
        add("professional", "di_hi", "Hindi diphone coverage", 100 * self.diphone_ratio("hi"), 75, "{:.0f}%")
        add("professional", "emotions", "Emotions with ≥6 takes", emo_cov(6), len(EMOTION_KEYS))
        add("professional", "genres", "Narration genres with ≥4 takes", genre_cov(4), len(GENRES))
        add("professional", "spontaneous", "Spontaneous speech minutes", mins(spont), 8, "{:.1f}")
        add("professional", "consistency_sessions", "Sessions with anchor sentences", self.consistency_sessions(), 4)
        add("professional", "consistency_days", "Different days with anchor sentences", self.consistency_days(), 3)
        add("professional", "quality", "Average approved quality score", self.mean_score or 0, 80)
        return c

    def milestones(self) -> tuple[list[dict], float]:
        checks = self._checks()
        order = [("setup", "Studio set up"), ("identity", "Voice identity captured"), ("reference", "Reference-ready (zero-shot cloning)"),
                 ("finetune", "Fine-tune ready (minimum)"), ("professional", "Professional dataset")]
        out = []
        for mid, title in order:
            cs = [c for c in checks if c["milestone"] == mid]
            out.append({"id": mid, "title": title, "checks": cs, "done": all(c["progress"] >= 1.0 for c in cs),
                        "progress": round(sum(c["progress"] for c in cs) / len(cs), 3) if cs else 1.0})
        pro = [c for c in checks if c["milestone"] == "professional"]
        completeness = round(100 * sum(c["progress"] for c in pro) / len(pro), 1)
        return out, completeness

    def summary(self) -> dict:
        ms, completeness = self.milestones()
        stage = next((m for m in ms if not m["done"]), None)
        modules = []
        for mid, meta in MODULES.items():
            exs = [e for e in self.bank.exercises if e.module == mid]
            core = [e for e in exs if e.core]
            done = self.module_done.get(mid, set())
            pending = {t.exercise_id for t in self.all_takes if t.module == mid and t.status == "pending"}
            modules.append({
                "id": mid, "title": meta["title"], "summary": meta["summary"],
                "total": len(exs), "core": len(core),
                "approved": len([e for e in exs if e.id in done]),
                "core_approved": len([e for e in core if e.id in done]),
                "pending": len([e for e in exs if e.id in pending]),
                "seconds": round(sum(usable_seconds(t) for t in self.approved if t.module == mid), 1),
            })

        def ph_rows(lang):
            inv, counts, rare = (EN_INVENTORY, self.en_counts, EN_RARE) if lang == "en" else (HI_INVENTORY, self.hi_counts, HI_RARE)
            return [{"p": p, "label": PHONEME_LABELS.get(p, p), "count": counts.get(p, 0), "rare": p in rare} for p in inv]

        status_counts = Counter(t.status for t in self.all_takes)
        return {
            "completeness": completeness,
            "stage": stage["title"] if stage else "Complete",
            "stage_id": stage["id"] if stage else "complete",
            "milestones": ms,
            "totals": {
                "approved_seconds": round(self.approved_seconds, 1),
                "recorded_seconds": round(self.recorded_seconds, 1),
                "takes": len(self.all_takes),
                "approved": status_counts.get("approved", 0),
                "pending": status_counts.get("pending", 0),
                "rejected": status_counts.get("rejected", 0),
                "sessions": len(self.sessions),
                "mean_score": self.mean_score,
                "exercises_total": len(self.bank.exercises),
                "exercises_done": sum(len(v) for v in self.module_done.values()),
            },
            "languages": {l: round(self.lang_seconds.get(l, 0.0), 1) for l in TRAIN_LANGS},
            "categories": {k: round(v, 1) for k, v in self.category_seconds.items()},
            "emotions": [{"id": e, "label": EMOTIONS[e], "count": self.emotion_counts.get(e, 0)} for e in EMOTION_KEYS],
            "genres": [{"id": g, "label": STYLES[g], "count": self.style_counts.get(g, 0)} for g in GENRES],
            "styles": {k: v for k, v in self.style_counts.items()},
            "phonemes": {"en": ph_rows("en"), "hi": ph_rows("hi"),
                         "en_progress": round(self.phoneme_progress("en", 25, 6), 3), "hi_progress": round(self.phoneme_progress("hi", 25, 6), 3),
                         "en_diphones": [len(self.en_di & self.en_di_universe), len(self.en_di_universe)],
                         "hi_diphones": [len(self.hi_di & self.hi_di_universe), len(self.hi_di_universe)]},
            "modules": modules,
        }


def needs(cov: Coverage) -> dict:
    """Per-dimension need weights (0 = saturated, 1 = nothing yet) for the adaptive planner, aimed at
    the next unmet milestone and then the professional targets."""
    ms, _ = cov.milestones()
    nxt = next((m["id"] for m in ms if not m["done"]), "professional")
    lang_target = {"setup": 300, "identity": 300, "reference": 240, "finetune": 480}.get(nxt, 1800)
    emo_target = 3 if nxt in ("setup", "identity", "reference", "finetune") else 6
    ph_common, ph_rare = (10, 3) if nxt in ("setup", "identity", "reference", "finetune") else (25, 6)
    out = {
        "stage": nxt,
        "lang": {l: max(0.0, 1.0 - cov.lang_seconds.get(l, 0.0) / lang_target) for l in TRAIN_LANGS},
        "emotion": {e: max(0.0, 1.0 - cov.emotion_counts.get(e, 0) / emo_target) for e in EMOTION_KEYS},
        "genre": {g: max(0.0, 1.0 - cov.style_counts.get(g, 0) / 4) for g in GENRES},
        "en_ph": {p: max(0.0, 1.0 - cov.en_counts.get(p, 0) / (ph_rare if p in EN_RARE else ph_common)) for p in EN_INVENTORY},
        "hi_ph": {p: max(0.0, 1.0 - cov.hi_counts.get(p, 0) / (ph_rare if p in HI_RARE else ph_common)) for p in HI_INVENTORY},
        "en_di": cov.en_di,
        "hi_di": cov.hi_di,
    }
    return out
