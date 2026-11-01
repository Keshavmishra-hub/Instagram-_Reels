from reelforge.models import Beat, Claim, Evidence, Research, Scene, Script, Source, Storyboard, Visual
from reelforge.script.validate import has_errors, validate_script
from reelforge.storyboard.planner import rule_based_storyboard, validate_storyboard


def research():
    s1 = Source(id="S1", url="https://raw.githubusercontent.com/owid/x.csv", publisher="Our World in Data", tier="reference")
    s2 = Source(id="S2", url="https://pib.gov.in/x", publisher="PIB", tier="government", primary=True)
    return Research(topic="t", sources=[s1, s2], claims=[
        Claim(id="C1", statement="Solar was 9.415% of India's electricity in 2025.", status="single_source",
              evidence=[Evidence(source_id="S1", quote="Dataset row [country=India, year=2025]: solar_share_elec = 9.415", verification="exact")]),
        Claim(id="C2", statement="Milk output was 247.87 million tonnes in 2024-25.", status="verified",
              evidence=[Evidence(source_id="S2", quote="247.87 million tonnes in 2024-25", verification="exact")]),
        Claim(id="C3", statement="Something unverified 12.", status="unverified", evidence=[]),
    ])


def codes(issues):
    return {i.code for i in issues}


def test_grounding_errors():
    r = research()
    s = Script(title="t", beats=[
        Beat(id="B1", section="hook", text="Milk output hit 300 million tonnes.", claim_ids=["C2"]),
        Beat(id="B2", section="story", text="India grew 12 times.", claim_ids=["C3"]),
        Beat(id="B3", section="story", text="In 2019 Delhi changed.", claim_ids=[]),
        Beat(id="B4", section="ending", text="What do you think?", claim_ids=[]),
    ])
    c = codes(validate_script(s, r, 45))
    assert {"number_unsupported", "unverified_claim", "uncited"} <= c
    assert has_errors(validate_script(s, r, 45))


def test_single_source_needs_attribution_once():
    r = research()
    beats = [Beat(id="B1", section="hook", text="Solar reached 9.4% in 2025.", claim_ids=["C1"]),
             Beat(id="B2", section="ending", text="Would you switch?", claim_ids=[])]
    assert "single_source" in codes(validate_script(Script(title="t", beats=beats), r, 45))
    beats.insert(1, Beat(id="B1b", section="context", text="That is according to Our World in Data.", claim_ids=["C1"]))
    assert "single_source" not in codes(validate_script(Script(title="t", beats=beats), r, 45))


def test_generic_intro_and_clickbait():
    s = Script(title="t", beats=[Beat(id="B1", section="hook", text="Hello everyone, you won't believe this.", claim_ids=[]),
                                 Beat(id="B2", section="ending", text="Thoughts?", claim_ids=[])])
    c = codes(validate_script(s, None, 45))
    assert "generic_intro" in c and "clickbait" in c


def test_storyboard_rejects_invented_chart_numbers():
    r = research()
    script = Script(title="t", beats=[Beat(id="B1", section="hook", text="Milk output hit 247.87 million tonnes.", claim_ids=["C2"])])
    good = Storyboard(scenes=[Scene(id="SC1", beat_ids=["B1"], visual=Visual(kind="stat", params={"value": 247.87, "unit": "million"}))])
    assert not [i for i in validate_storyboard(good, script, r) if i.severity == "error"]
    bad = Storyboard(scenes=[Scene(id="SC1", beat_ids=["B1"], visual=Visual(kind="chart", params={"data": [{"label": "2010", "value": 121.8}]}))])
    assert "graphic_number_unsupported" in codes(validate_storyboard(bad, script, r))


def test_rule_based_storyboard_covers_beats():
    script = Script(title="Solar in India", beats=[Beat(id="B1", section="hook", text="Only two countries made more."),
                                                  Beat(id="B2", section="story", text="Solar reached 9.4% in 2025."),
                                                  Beat(id="B3", section="ending", text="Would you switch?")])
    sb = rule_based_storyboard(script, None, stock_available=False)
    assert [b for sc in sb.scenes for b in sc.beat_ids] == ["B1", "B2", "B3"]
    assert sb.scenes[1].visual.kind == "stat" and sb.scenes[1].visual.params["value"] == 9.4
    assert not validate_storyboard(sb, script, None) or all(i.code != "beat_coverage" for i in validate_storyboard(sb, script, None))
