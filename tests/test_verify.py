from reelforge.models import Claim, Evidence, Research, Source
from reelforge.research.verify import claim_status, extract_numbers, norm_text, numbers_supported, verify_data, verify_quote

SNAP = norm_text("The Seed Vault opened in February 2008 and has capacity to store 4.5 million varieties of crops.")


def test_extract_numbers_handles_formats():
    vals = extract_numbers("1,301,000 samples, about 1.3 million, 13 lakh, 2.5 crore, 45%, −18°C, in 2008")
    for v in (1301000, 1.3e6, 2.5e7, 45, -18, 2008):
        assert v in vals


def test_numbers_supported_tolerance_depends_on_hedge():
    assert numbers_supported("about 1.3 million samples", ["holds 1,301,000 samples"])[0]
    assert not numbers_supported("1.4 million samples", ["holds 1,301,000 samples"])[0]


def test_quote_exact_fuzzy_and_changed_number():
    assert verify_quote("has capacity to store 4.5 million varieties of crops", SNAP)[0] == "exact"
    assert verify_quote("has the capacity to store 4.5 million varieties of crop", SNAP)[0] == "fuzzy"
    # same sentence, different number -> must be rejected even though text similarity is very high
    assert verify_quote("has capacity to store 5.5 million varieties of crops", SNAP)[0] == "not_found"


CSV = "country,year,iso_code,solar\nIndia,2025,IND,195.99\nChina,2025,CHN,1174.96\nWorld,2025,,2500\nAsia (EI),2025,OWID_ASI,1500\nUnited States,2025,USA,388.82\n"


def test_data_value_and_rank():
    v, q = verify_data({"type": "value", "filters": {"country": "India", "year": "2025"}, "column": "solar"}, CSV, "t1")
    assert v == "exact" and "195.99" in q
    v, q = verify_data({"type": "rank", "group": {"year": "2025"}, "column": "solar", "entity_column": "country", "entity": "India",
                        "exclude_if": {"iso_code": ["", "OWID_*"]}, "top": 3}, CSV, "t2")
    assert v == "exact" and "India ranks #3" in q and "World" not in q
    v, _ = verify_data({"type": "value", "filters": {"country": "India", "year": "2025"}, "column": "solar", "expected": 200}, CSV, "t3")
    assert v == "not_found"


def _research(*sources):
    return Research(topic="t", sources=list(sources))


def test_status_rules():
    gov = Source(id="S1", url="https://pib.gov.in/x", tier="government", primary=True)
    news1 = Source(id="S2", url="https://www.thehindu.com/a", tier="news")
    news2 = Source(id="S3", url="https://indianexpress.com/b", tier="news")
    wiki = Source(id="S4", url="https://en.wikipedia.org/wiki/X", tier="reference")
    r = _research(gov, news1, news2, wiki)
    ok = "exact"
    c = Claim(id="C1", statement="Output was 247.87 million tonnes.", evidence=[Evidence(source_id="S1", quote="247.87 million tonnes", verification=ok)])
    assert claim_status(c, r)[0] == "verified"  # primary official source
    c = Claim(id="C2", statement="x", evidence=[Evidence(source_id="S2", quote="q", verification=ok), Evidence(source_id="S3", quote="q", verification=ok)])
    assert claim_status(c, r)[0] == "verified"  # two independent domains
    c = Claim(id="C3", statement="x", evidence=[Evidence(source_id="S2", quote="q", verification=ok)])
    assert claim_status(c, r)[0] == "single_source"
    c = Claim(id="C4", statement="x", evidence=[Evidence(source_id="S4", quote="q", verification=ok)])
    assert claim_status(c, r)[0] == "single_source"  # encyclopaedia only
    c = Claim(id="C5", statement="x", certainty="disputed", evidence=[Evidence(source_id="S2", quote="q", verification=ok), Evidence(source_id="S3", quote="q", verification=ok)])
    assert claim_status(c, r)[0] == "conflicting"
    c = Claim(id="C6", statement="It was 300 tonnes.", evidence=[Evidence(source_id="S1", quote="It was 247 tonnes", verification=ok)])
    assert claim_status(c, r)[0] == "unverified"  # number not backed by the quote
    c = Claim(id="C7", statement="x", evidence=[Evidence(source_id="S1", quote="q", verification="not_found")])
    assert claim_status(c, r)[0] == "unverified"
