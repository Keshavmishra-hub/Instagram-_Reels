import re
from collections import Counter

import pytest

from myvoice.curriculum.bank import TEMPLATE_RE, ExerciseBank, render
from myvoice.curriculum.generators import KINDS, from_id, generate
from myvoice.models import CATEGORIES, MODULES
from myvoice.text.devanagari import has_devanagari, romanize
from myvoice.text.phonemes import EN_INVENTORY, HI_INVENTORY

LATIN = re.compile(r"[A-Za-z]")


@pytest.fixture(scope="module")
def bank():
    return ExerciseBank()


def test_bank_size_and_ids(bank):
    assert len(bank.exercises) >= 550
    ids = [e.id for e in bank.exercises]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[A-Z][A-Za-z0-9-]+-\d{2}", i) for i in ids)
    assert {e.module for e in bank.exercises} == set(MODULES)
    assert {e.category for e in bank.exercises} == set(CATEGORIES)


def test_scripts_match_languages(bank):
    for e in bank.exercises:
        text = render(e.spoken or e.text, "m", "Name")  # number drills show digits; the language is what is said
        if e.lang == "en":
            assert not has_devanagari(text), e.id
        elif e.lang == "hi":
            assert has_devanagari(text), e.id
        elif e.lang == "hinglish":
            assert has_devanagari(text) and LATIN.search(text), e.id  # Hindi in Devanagari, English in Latin


def test_numbers_have_spoken_forms(bank):
    for e in bank.exercises:
        if e.kind in ("sentence", "paragraph", "word_list", "dialogue") and e.readcheck and re.search(r"\d", e.text):
            assert e.spoken and not re.search(r"\d", e.spoken), e.id


def test_templates_are_well_formed(bank):
    for e in bank.exercises:
        stripped = TEMPLATE_RE.sub("", e.text).replace("{name}", "")
        assert "{" not in stripped and "}" not in stripped and "|" not in stripped, e.id
    assert render("कर {रहा|रही} हूँ", "f") == "कर रही हूँ"
    assert render("कर {रहा|रही} हूँ", "m") == "कर रहा हूँ"
    assert render("कर {रहा|रही} हूँ", "") == "कर रहा/रही हूँ"
    assert render("My name is {name}.", "", "Asha") == "My name is Asha."


def test_romanisation_covers_all_hindi(bank):
    for e in bank.exercises:
        if e.lang in ("hi", "hinglish"):
            r = romanize(render(e.text, "m", "Name"))
            assert not has_devanagari(r), (e.id, r)


def test_every_phoneme_is_in_the_curriculum(bank):
    en, hi = Counter(), Counter()
    for e in bank.exercises:
        if e.train:
            info = bank.derived(e)
            en.update(info.en_phonemes)
            hi.update(info.hi_phonemes)
    if not en:
        pytest.skip("eSpeak NG not available")
    assert all(en[p] >= 20 for p in EN_INVENTORY), {p: en[p] for p in EN_INVENTORY if en[p] < 20}
    assert all(hi[p] >= 7 for p in HI_INVENTORY), {p: hi[p] for p in HI_INVENTORY if hi[p] < 7}


def test_every_emotion_and_genre_is_covered(bank):
    emotions = Counter(e.emotion for e in bank.exercises)
    from myvoice.coverage import EMOTION_KEYS, GENRES

    assert all(emotions[k] >= 3 for k in EMOTION_KEYS)
    styles = Counter(e.style for e in bank.exercises)
    assert all(styles[g] >= 4 for g in GENRES)
    for e in bank.exercises:
        if e.emotion != "neutral" and e.module == "F":
            assert e.context, e.id  # every emotional exercise has a situation to act from


def test_expected_durations_and_auto_stop(bank):
    ex = bank.get("A-SLOW-01")
    info = bank.derived(ex)
    assert info.expected and info.expected[0] < info.expected[1]
    assert bank.public(bank.get("S-ROOM-01"))["fixed_sec"] == 5
    assert bank.public(bank.get("S-CLAP-01"))["fixed_sec"] == 4
    assert bank.public(bank.get("H-SPON-01"), 1.8)["auto_stop_sec"] > bank.public(bank.get("A-NORM-01"), 1.8)["auto_stop_sec"]


@pytest.mark.parametrize("kind", KINDS)
def test_generators_are_deterministic(kind):
    for lang in ("en", "hi"):
        a, b = generate(kind, lang, 42), from_id(f"I-GEN-{kind}-{lang}-42")
        assert a.text == b.text and a.spoken == b.spoken and a.spoken and not re.search(r"\d", a.spoken)


def test_import_rejects_malformed_files(tmp_path):
    (tmp_path / "bad.json").write_text('{"module": "G", "sections": [{"code": "X1-BAD", "category": "nope", "exercises": ["hi"]}]}', encoding="utf-8")
    (tmp_path / "split.yaml").write_text("module: G\nsections:\n  - code: X2-SPLIT\n    category: cinematic_narration\n    exercises:\n"
                                         "      - {text: \"ok\", instruction: one, two}\n", encoding="utf-8")
    b = ExerciseBank(extra_dirs=[tmp_path])
    assert len(b.errors) == 2 and not any(e.section.startswith("X") for e in b.exercises)
    (tmp_path / "bad.json").unlink()
    (tmp_path / "split.yaml").unlink()
    (tmp_path / "good.json").write_text('{"module": "G", "sections": [{"code": "X20261103-T", "category": "cinematic_narration", '
                                        '"defaults": {"lang": "en", "style": "reel_hook"}, "exercises": ["A brand new hook line."]}]}', encoding="utf-8")
    b = ExerciseBank(extra_dirs=[tmp_path])
    assert not b.errors and b.get("X20261103-T-01").source == "imported"
