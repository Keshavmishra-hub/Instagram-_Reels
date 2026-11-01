"""Claude response parsing with a fake client (no network), and the import/verification path."""
from types import SimpleNamespace as NS

import pytest

from reelforge.llm import client as llm


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def _msg(content, stop="end_turn"):
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=10, output_tokens=5, server_tool_use=NS(web_search_requests=1, web_fetch_requests=1)))


def test_research_collects_fetched_pages_and_continues_pause_turn(monkeypatch):
    first = _msg([
        NS(type="server_tool_use", name="web_search", input={"query": "india solar"}),
        NS(type="web_search_tool_result", content=[NS(url="https://a.gov/x", title="A", page_age=None)]),
    ], stop="pause_turn")
    doc = NS(source=NS(type="text", data="Solar reached 9.4 percent."), title="Doc")
    second = _msg([
        NS(type="server_tool_use", name="web_fetch", input={"url": "https://a.gov/x"}),
        NS(type="web_fetch_tool_result", content=NS(type="web_fetch_result", url="https://a.gov/x", retrieved_at="2026-11-01", content=doc)),
        NS(type="text", text="Memo text", citations=[NS(url="https://a.gov/x", title="A", cited_text="9.4 percent")]),
    ])
    calls = []

    class FakeMessages:
        def stream(self, **kw):
            calls.append(kw)
            return FakeStream(first if len(calls) == 1 else second)

    c = llm.Claude.__new__(llm.Claude)
    c.s = NS(web_search_tool="web_search_20260209", web_fetch_tool="web_fetch_20260209", research_max_searches=3, research_max_fetches=3)
    c.model = "claude-opus-5-5"
    c.client = NS(beta=NS(messages=FakeMessages()))
    run = c.research("sys", "prompt", log=lambda m: None)
    assert run.text == "Memo text" and run.searches == ["india solar"]
    assert run.fetched[0].url == "https://a.gov/x" and "9.4 percent" in run.fetched[0].text
    assert len(calls) == 2 and calls[1]["messages"][-1]["role"] == "assistant"  # paused turn re-sent
    assert calls[0]["fallbacks"] == "default" and calls[0]["tools"][0]["type"] == "web_search_20260209"


def test_refusal_raises():
    c = llm.Claude.__new__(llm.Claude)
    with pytest.raises(llm.LLMError):
        c._check(NS(stop_reason="refusal", stop_details=NS(category="cyber")))


def test_auto_research_drops_urls_that_were_never_fetched(store, project, monkeypatch):
    from reelforge.llm import schemas
    from reelforge.research import pipeline as rp

    run = llm.ResearchRun(text="memo", fetched=[llm.FetchedDoc(url="https://www.pib.gov.in/release", title="PIB",
                                                               text="India's milk production reached 247.87 million tonnes in 2024-25.")])
    x = schemas.XResearch(
        summary="s", angles=[], uncertainties=[], limitations=[], enough_reliable_information=True, sufficiency_reason="",
        sources=[schemas.XSource(url="https://www.pib.gov.in/release", title="PIB", publisher="PIB", tier="government", primary=True),
                 schemas.XSource(url="https://never-opened.example.com/a", title="X", publisher="X", tier="news", primary=False)],
        claims=[schemas.XClaim(statement="India's milk production was 247.87 million tonnes in 2024-25.", category="statistic", certainty="established",
                               evidence=[schemas.XEvidence(url="https://www.pib.gov.in/release", quote="milk production reached 247.87 million tonnes in 2024-25"),
                                         schemas.XEvidence(url="https://never-opened.example.com/a", quote="invented")])],
    )

    class FakeClaude:
        def __init__(self, s):
            pass

        def research(self, *a, **k):
            return run

        def structured(self, *a, **k):
            return x

    monkeypatch.setattr(llm, "Claude", FakeClaude)
    monkeypatch.setattr(rp, "fetch", lambda url, s=None: NS(ok=False, blocked_by_network=True, status=None, error="blocked", text="", final_url=url, title=""))
    r = rp.run_auto_research(project.id, store, log=lambda m: None)
    assert [s.url for s in r.sources] == ["https://www.pib.gov.in/release"]  # the unopened URL never becomes a source
    c = r.claims[0]
    assert len(c.evidence) == 1 and c.evidence[0].verification == "exact" and c.status == "verified"


def test_import_marks_excerpt_quotes_as_agent_attested(store, project, monkeypatch):
    from reelforge.research import pipeline as rp

    monkeypatch.setattr(rp, "fetch", lambda url, s=None: NS(ok=False, blocked_by_network=True, status=None, error="blocked", text="", final_url=url, title=""))
    data = {"summary": "s", "sufficiency": {"enough": True, "reason": ""},
            "sources": [{"id": "S1", "url": "https://pib.gov.in/x", "publisher": "PIB", "tier": "government", "primary": True,
                         "excerpt": "Milk production reached 247.87 million tonnes in 2024-25, a growth of 3.58%."}],
            "claims": [{"statement": "Milk production was 247.87 million tonnes in 2024-25.", "evidence": [{"source_id": "S1", "quote": "Milk production reached 247.87 million tonnes in 2024-25"}]},
                       {"statement": "Growth was 9%.", "evidence": [{"source_id": "S1", "quote": "a growth of 9%"}]}]}
    r = rp.import_research(project.id, store, data, log=lambda m: None)
    assert r.claims[0].evidence[0].verification == "agent_attested" and r.claims[0].status == "verified"
    assert r.claims[1].status == "unverified"
    assert (store.dir(project.id) / "research.md").exists()
