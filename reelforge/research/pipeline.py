"""Research stage: discover -> read -> extract claims -> verify mechanically -> report."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urldefrag, urlparse

from ..config import Settings, settings as default_settings
from ..languages import get_language
from ..models import Claim, Evidence, Research, Source, Sufficiency, now_iso
from ..storage import ProjectStore
from ..styles import get_style
from .credibility import classify, hostname
from .fetch import fetch, read_snapshot, save_snapshot
from .report import research_markdown
from .verify import verify_research


def normalize_url(url: str) -> str:
    url = urldefrag(url.strip())[0]
    p = urlparse(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return f"{host}{path}{'?' + p.query if p.query else ''}"


def _tier(llm_tier: str, url: str) -> str:
    domain_tier = classify(url)
    # deterministic domain classification wins; the model may only fill in tiers we cannot infer
    return domain_tier if domain_tier != "other" else (llm_tier or "other")


def refresh_snapshots(research: Research, project_dir: Path, s: Settings = default_settings, log: Callable[[str], None] = print) -> dict:
    """Independently fetch every source; store a raw snapshot when it succeeds."""
    stats = {"ok": 0, "blocked": 0, "dead": 0, "failed": 0}
    for src in research.sources:
        res = fetch(src.url, s)
        src.last_check = now_iso()
        if res.ok:
            existing = read_snapshot(project_dir, src.snapshot_file) if src.snapshot_kind == "raw_text" else ""
            combined = res.text if not existing or existing in res.text else res.text + "\n\n" + existing
            rel, sha = save_snapshot(project_dir, src.id, src.url, combined, "raw_text",
                                     header=f"URL: {src.url}\nFINAL-URL: {res.final_url}\nHTTP: {res.status}\nRETRIEVED: {src.last_check}\nSNAPSHOT-KIND: raw_text (fetched by ReelForge)\n")
            src.snapshot_file, src.snapshot_sha256, src.snapshot_kind = rel, sha, "raw_text"
            src.http_status, src.final_url = res.status, res.final_url
            src.title = src.title or res.title
            src.notes = (src.notes + " ").strip() if "fetched by app" in src.notes else (src.notes + " [fetched by app]").strip()
            stats["ok"] += 1
        elif res.blocked_by_network:
            stats["blocked"] += 1
            src.notes = (src.notes + " [app could not re-fetch: network policy]").strip() if "network policy" not in src.notes else src.notes
        elif res.status in (404, 410):
            stats["dead"] += 1
            src.http_status = res.status
            src.notes = (src.notes + f" [HTTP {res.status} on re-check]").strip()
        else:
            stats["failed"] += 1
            src.http_status = res.status
    log(f"Source re-check: {stats}")
    return stats


def run_auto_research(pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print) -> Research:
    from ..llm.client import Claude
    from ..llm.prompts import EXTRACT_SYSTEM, RESEARCH_PROMPT, RESEARCH_SYSTEM
    from ..llm.schemas import XResearch

    project = store.project(pid)
    ps = project.settings
    style = get_style(ps.style)
    claude = Claude(s)
    log("Researching with Claude (web search + web fetch) ...")
    run = claude.research(
        RESEARCH_SYSTEM,
        RESEARCH_PROMPT.format(
            topic=ps.topic, language=get_language(ps.language).name, style_name=style.name, style_desc=style.description,
            audience=ps.audience or "general Instagram audience", angle=ps.angle or "(none)", today=date.today().isoformat(),
            duration=ps.duration,
        ),
        effort="high", log=log,
    )
    store.write_text(pid, "sources/_research_memo.md", run.text)
    log(f"Read {len(run.fetched)} pages after {len(run.searches)} searches. Extracting claims ...")
    docs = []
    for i, d in enumerate(run.fetched, 1):
        text = d.text
        if len(text) > 60000:  # keep the extraction prompt bounded; verification still uses the full text
            text = text[:60000] + "\n[... truncated for extraction ...]"
        docs.append(f"<document index='{i}' url='{d.url}' title='{d.title}'>\n{text}\n</document>")
    prompt = (
        f"Topic: {ps.topic}\n\nResearch memo:\n{run.text}\n\nFetched pages (the only allowed evidence):\n" + "\n\n".join(docs)
    )
    x = claude.structured(EXTRACT_SYSTEM, prompt, XResearch, effort="high", max_tokens=64000)
    research = Research(topic=ps.topic, language=ps.language, method="claude_api: web_search + web_fetch, claims verified against retrieved page text")
    research.summary, research.angles = x.summary, x.angles
    research.uncertainties, research.limitations = x.uncertainties, x.limitations
    research.sufficiency = Sufficiency(enough=x.enough_reliable_information, reason=x.sufficiency_reason)

    d = store.dir(pid)
    fetched = {normalize_url(f.url): f for f in run.fetched}
    url_to_sid: dict[str, str] = {}

    def add_source(url: str, title: str = "", publisher: str = "", published=None, tier: str = "other", primary: bool = False, notes: str = "") -> Optional[str]:
        key = normalize_url(url)
        if key in url_to_sid:
            return url_to_sid[key]
        doc = fetched.get(key)
        if doc is None:
            return None  # never read -> cannot be a source
        sid = f"S{len(research.sources) + 1}"
        rel, sha = save_snapshot(d, sid, url, doc.text, "raw_text",
                                 header=f"URL: {url}\nRETRIEVED: {doc.retrieved_at or now_iso()}\nSNAPSHOT-KIND: raw_text (Anthropic web_fetch)\n")
        research.sources.append(Source(
            id=sid, url=url, title=title or doc.title, publisher=publisher or hostname(url), domain=hostname(url),
            tier=_tier(tier, url), primary=primary, published=published, accessed_at=doc.retrieved_at or now_iso(),
            access_method="anthropic_web_fetch", http_status=200, snapshot_file=rel, snapshot_sha256=sha, snapshot_kind="raw_text", notes=notes,
        ))
        url_to_sid[key] = sid
        return sid

    for xs in x.sources:
        add_source(xs.url, xs.title, xs.publisher, xs.published, xs.tier, xs.primary, xs.notes)
    for i, xc in enumerate(x.claims, 1):
        ev = []
        for e in xc.evidence:
            sid = url_to_sid.get(normalize_url(e.url)) or add_source(e.url)
            if sid:
                ev.append(Evidence(source_id=sid, quote=e.quote))
        research.claims.append(Claim(
            id=f"C{i}", statement=xc.statement, category=xc.category, certainty=xc.certainty,
            as_of=xc.as_of, caveats=xc.caveats, evidence=ev,
        ))
    refresh_snapshots(research, d, s, log)
    stats = verify_research(research, d)
    log(f"Verification: {stats}")
    if usage := run.usage:
        store.write_json(pid, "sources/_usage.json", usage)
    save_research(pid, store, research)
    return research


def import_research(pid: str, store: ProjectStore, data: dict, method: str = "claude_code: WebSearch + WebFetch",
                    s: Settings = default_settings, log: Callable[[str], None] = print, refetch: bool = True) -> Research:
    """Import research prepared outside the app (Claude Code mode or a human researcher).

    Each source must carry `excerpt`: verbatim text as read. Quotes are checked against it and, when the app can
    reach the page, against a fresh raw snapshot as well.
    """
    project = store.project(pid)
    d = store.dir(pid)
    research = Research(topic=project.settings.topic, language=project.settings.language, method=method)
    research.summary = data.get("summary", "")
    research.angles = list(data.get("angles", []))
    research.uncertainties = list(data.get("uncertainties", []))
    research.limitations = list(data.get("limitations", []))
    suff = data.get("sufficiency") or {}
    research.sufficiency = Sufficiency(enough=bool(suff.get("enough", True)), reason=str(suff.get("reason", "")))
    id_map: dict[str, str] = {}
    for i, src in enumerate(data.get("sources", []), 1):
        sid = f"S{i}"
        id_map[str(src.get("id", sid))] = sid
        url = src["url"]
        excerpt = src.get("excerpt", "")
        rel = sha = None
        if excerpt:
            rel, sha = save_snapshot(d, sid, url, excerpt, "agent_excerpt",
                                     header=f"URL: {url}\nACCESSED: {src.get('accessed_at', now_iso())}\nSNAPSHOT-KIND: agent_excerpt (verbatim passages captured by the researcher; not a full page copy)\n")
        research.sources.append(Source(
            id=sid, url=url, title=src.get("title", ""), publisher=src.get("publisher", hostname(url)), domain=hostname(url),
            tier=_tier(src.get("tier", "other"), url), primary=bool(src.get("primary", False)), published=src.get("published"),
            accessed_at=src.get("accessed_at", now_iso()), access_method=src.get("access_method", "claude_code_webfetch"),
            http_status=src.get("http_status", 200), snapshot_file=rel, snapshot_sha256=sha,
            snapshot_kind="agent_excerpt" if excerpt else "none", notes=src.get("notes", ""),
        ))
    for i, c in enumerate(data.get("claims", []), 1):
        ev = [Evidence(source_id=id_map.get(str(e["source_id"]), str(e["source_id"])), quote=e.get("quote", ""), data=e.get("data"))
              for e in c.get("evidence", [])]
        research.claims.append(Claim(
            id=f"C{i}", statement=c["statement"], category=c.get("category", "other"), certainty=c.get("certainty", "established"),
            as_of=c.get("as_of"), caveats=c.get("caveats", ""), evidence=ev,
        ))
    if refetch:
        refresh_snapshots(research, d, s, log)
    stats = verify_research(research, d)
    log(f"Verification: {stats}")
    save_research(pid, store, research)
    return research


def add_manual_source(pid: str, store: ProjectStore, url: str, s: Settings = default_settings) -> Source:
    research = store.research(pid) or Research(topic=store.project(pid).settings.topic, method="manual")
    d = store.dir(pid)
    res = fetch(url, s)
    if not res.ok:
        raise RuntimeError(f"Could not fetch {url}: {res.error or res.status}. Sources must be accessible to be cited.")
    sid = f"S{max([int(x.id[1:]) for x in research.sources] + [0]) + 1}"
    rel, sha = save_snapshot(d, sid, url, res.text, "raw_text")
    src = Source(id=sid, url=url, final_url=res.final_url, title=res.title, publisher=hostname(url), domain=hostname(url),
                 tier=classify(url), access_method="app_fetch", http_status=res.status, snapshot_file=rel, snapshot_sha256=sha,
                 snapshot_kind="raw_text")
    research.sources.append(src)
    save_research(pid, store, research)
    return src


def add_manual_claim(pid: str, store: ProjectStore, statement: str, source_id: str, quote: str, certainty: str = "established",
                     as_of: Optional[str] = None, caveats: str = "") -> Claim:
    research = store.research(pid)
    if research is None or research.source(source_id) is None:
        raise ValueError("Add the source first")
    cid = f"C{max([int(x.id[1:]) for x in research.claims] + [0]) + 1}"
    claim = Claim(id=cid, statement=statement, certainty=certainty, as_of=as_of, caveats=caveats,
                  evidence=[Evidence(source_id=source_id, quote=quote)])
    research.claims.append(claim)
    verify_research(research, store.dir(pid))
    save_research(pid, store, research)
    return research.claim(cid)  # type: ignore[return-value]


def save_research(pid: str, store: ProjectStore, research: Research) -> None:
    store.save("research", pid, research)
    store.write_text(pid, "research.md", research_markdown(research))
