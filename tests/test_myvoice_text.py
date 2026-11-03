import pytest

from myvoice.readcheck import check
from myvoice.text.devanagari import hindi_number, romanize, syllable_count, word_phonemes
from myvoice.text.keys import split_words, word_keys


@pytest.mark.parametrize("word,expected", [
    ("कमला", "k ə m l aː"), ("समझना", "s ə m ə dʒʱ n aː"), ("बदलना", "b ə d̪ ə l n aː"), ("सरकार", "s ə r k aː r"),
    ("लड़का", "l ə ɽ k aː"), ("सड़क", "s ə ɽ ə k"), ("अपना", "ə p n aː"), ("आदमी", "aː d̪ m iː"),
    ("कहना", "k ɛ ɦ n aː"), ("शहर", "ʃ ɛ ɦ ɛ r"), ("हम", "ɦ ə m"), ("हवा", "ɦ ə ʋ aː"), ("बहुत", "b ə ɦ ʊ t̪"),
    ("ज्ञान", "g j aː n"), ("संबंध", "s ə m b ə n d̪ʱ"), ("ठंडा", "ʈʰ ə ɳ ɖ aː"), ("में", "m eː̃"), ("नहीं", "n ə ɦ iː̃"),
    ("उन्होंने", "ʊ n ɦ oː̃ n eː"), ("ज़रूर", "z ə r uː r"), ("फ़ायदा", "f aː j d̪ aː"), ("पढ़ाई", "p ə ɽʱ aː iː"),
    ("मित्र", "m ɪ t̪ r ə"), ("दोस्त", "d̪ oː s t̪"), ("सत्य", "s ə t̪ j ə"), ("दुःख", "d̪ ʊ kʰ"), ("अतः", "ə t̪ ə ɦ"),
    ("जगत्", "dʒ ə g ə t̪"), ("डॉक्टर", "ɖ ɔ k ʈ ə r"),
])
def test_hindi_g2p(word, expected):
    assert " ".join(word_phonemes(word)) == expected


@pytest.mark.parametrize("text,expected", [
    ("आज की meeting में हम marketing strategy discuss करेंगे। ठीक है?", "Aaj ki meeting mein ham marketing strategy discuss karenge. Theek hai?"),
    ("अच्छा", "Accha"), ("लिए", "Liye"), ("चाहिए", "Chaahiye"), ("मैंने", "Maine"), ("लड़का", "Ladka"), ("वह", "Woh"),
    ("नहीं", "Nahin"), ("हूँ", "Hoon"), ("पानी", "Paani"), ("तीन", "Teen"),
])
def test_romanize_casual(text, expected):
    assert romanize(text) == expected


def test_romanize_iast_and_passthrough():
    assert romanize("ठंडा", "iast") == "Ṭhaṇḍā"
    assert romanize("Plain English stays.") == "Plain English stays."


def test_syllables_and_numbers():
    assert syllable_count("आज की मीटिंग में हम बात करेंगे") == 10
    assert hindi_number(0) == "शून्य"
    assert hindi_number(47) == "सैंतालीस"
    assert hindi_number(2026) == "दो हज़ार छब्बीस"
    assert hindi_number(150000) == "एक लाख पचास हज़ार"
    assert hindi_number(25000000) == "दो करोड़ पचास लाख"


def test_keys_cross_script():
    assert set(word_keys("मीटिंग")) & {"miting"}
    assert any(k.startswith("mitin") for k in word_keys("meeting"))
    assert "jiesti" in word_keys("GST") and "jiesti" in word_keys("जीएसटी")
    assert split_words("भारत के किसान। Hello, world!") == ["भारत", "के", "किसान", "Hello", "world"]


@pytest.mark.parametrize("lang,expected,heard,verdict", [
    ("en", "The quick brown fox jumps over the lazy dog near the river bank.", "The quick brown fox jumps over the lazy dog near the riverbank.", "read"),
    ("en", "The quick brown fox jumps over the lazy dog near the river bank.", "The quick brown fox jumps.", "not_read"),
    ("en", "The quick brown fox jumps over the lazy dog near the river bank.", "I went to the market yesterday to buy vegetables.", "not_read"),
    ("hi", "भारत के किसान आज भी मानसून की राह देखते हैं।", "भारत के किसान आज भी मानसून की राह देखते है", "read"),
    ("hinglish", "आज की meeting में हम marketing strategy discuss करेंगे।", "आज की मीटिंग में हम मार्केटिंग स्ट्रैटेजी डिस्कस करेंगे", "read"),
    ("hinglish", "आज की meeting में हम marketing strategy discuss करेंगे।", "aaj ki meeting mein hum marketing strategy discuss karenge", "read"),
    ("hinglish", "हमें GST और ROI दोनों पर ध्यान देना होगा।", "हमें जीएसटी और आरओआई दोनों पर ध्यान देना होगा", "read"),
    ("en", "In twenty twenty-six, prices rose by fifteen percent to two thousand five hundred rupees.", "In 2026, prices rose by 15% to ₹2,500.", "read"),
    ("hi", "उन्नीस सौ सैंतालीस में भारत आज़ाद हुआ।", "1947 में भारत आजाद हुआ", "read"),
    ("en", "Please call nine eight seven six five four three two one zero.", "Please call 9876543210.", "read"),
    ("hinglish", "Weekend पर हम सब लोग मिलकर एक road trip plan कर रहे हैं।", "वीकेंड पर हम सब लोग मिल कर एक रोड ट्रिप प्लान कर रहे हैं", "read"),
])
def test_readcheck(lang, expected, heard, verdict):
    m = check(expected, heard, lang, model="large-v3-turbo")
    assert m.verdict == verdict, (m.coverage, [m.expected_words[i] for i in m.missing])


def test_readcheck_reports_missing_words():
    m = check("One two three four five six seven eight", "one two three four", "en", model="large-v3")
    assert [m.expected_words[i] for i in m.missing] == ["five", "six", "seven", "eight"]
    assert m.coverage == 0.5
