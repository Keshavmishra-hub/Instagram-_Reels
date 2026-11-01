from reelforge.voice.normalize import load_lexicon, normalize_tokens, spoken_text


def say(text):
    return spoken_text(normalize_tokens(text, "en", load_lexicon()))


def test_years_and_decimals():
    assert say("In 1947, output rose.") == "In nineteen forty seven, output rose."
    assert "twenty twenty five" in say("By 2025 it grew")
    assert say("4.5%") == "four point five percent"


def test_count_noun_is_not_a_year():
    assert say("2000 farmers") == "two thousand farmers"


def test_currency_moves_after_scale_word():
    assert say("It cost $4.5 billion.") == "It cost four point five billion dollars."
    assert say("₹2,000 crore.") == "two thousand crore rupees."


def test_indian_grouping_and_temperature():
    assert say("1,00,000 litres") == "one lakh litres"
    assert say("Stored at −18°C.") == "Stored at minus eighteen degrees Celsius."


def test_acronyms_and_hyphens():
    assert say("The UN and WHO") == "The U N and W H O"
    toks = normalize_tokens("about 7 terawatt-hours", "en", {})
    assert toks[-1].display == "terawatt-hours" and toks[-1].spoken == ["terawatt", "hours"]


def test_standalone_dash_joins_previous_word():
    toks = normalize_tokens("think — and", "en", {})
    assert [t.display for t in toks] == ["think —", "and"]
