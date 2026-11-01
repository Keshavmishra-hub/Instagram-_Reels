"""Publishing package: caption, title, hashtags, pinned comment, CTA, alt text, sources and credits."""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlparse

from ..config import Settings, settings as default_settings
from ..models import InstagramPackage, Research, Script
from ..storage import ProjectStore

MAX_CAPTION = 2200
MAX_HASHTAGS = 5  # Instagram caps hashtags at 5 per post/reel (Dec 2025 change)


def used_sources(script: Script, research: Research) -> list:
    ids = []
    for b in script.beats:
        for cid in b.claim_ids:
            c = research.claim(cid)
            if not c:
                continue
            for e in c.evidence:
                if e.verification in ("exact", "fuzzy", "agent_attested") and e.source_id not in ids:
                    ids.append(e.source_id)
    return [research.source(i) for i in ids if research.source(i)]


def _short_url(url: str, limit: int = 100) -> str:
    """Readable but complete reference: drop the scheme and 'www.', never cut inside a path segment."""
    p = urlparse(url)
    host = (p.hostname or "").removeprefix("www.")
    path = p.path.rstrip("/")
    full = host + path + (f"?{p.query}" if p.query else "")
    if len(full) <= limit:
        return full
    out = host
    for seg in path.split("/")[1:]:
        if len(out) + len(seg) + 1 > limit - 2:
            return out + "/…"
        out += "/" + seg
    return out


def sources_block(script: Script, research: Research, limit: int = 8) -> str:
    lines = ["Sources:"]
    for src in used_sources(script, research)[:limit]:
        title = (src.title or "").split(" - ")[0].strip()
        pub = src.publisher or src.domain
        label = pub + (f", {title}" if title and title.lower() != pub.lower() else "")
        lines.append(f"• {label}: {_short_url(src.url)}")
    return "\n".join(lines)


def credits_line(pid: str, store: ProjectStore) -> str:
    lib = store.assets(pid)
    sb = store.storyboard(pid)
    used = {sc.visual.asset_id for sc in sb.scenes} | {sc.background.asset_id for sc in sb.scenes if sc.background}
    req = [a for a in lib.assets if a.id in used and a.attribution_required]
    if not req:
        return ""
    return "Visual credits: " + "; ".join(f"{a.author or 'unknown'} / {a.provider.capitalize()} ({a.license})" for a in req)


def _hashtag(word: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", word)
    return "#" + "".join(p[:1].upper() + p[1:] for p in parts) if parts else ""


STYLE_TAGS = {
    "documentary": "#Documentary", "explainer": "#Explained", "mystery": "#Mystery", "historical": "#History",
    "business": "#Business", "agriculture": "#Agriculture", "science": "#Science", "current_affairs": "#News",
    "facts": "#DidYouKnow", "human_stories": "#RealStories",
}


def template_package(script: Script, research: Research, topic: str, style: str = "") -> InstagramPackage:
    """Deterministic fallback (no LLM): every content beat, grouped by section, so no context is dropped."""
    beats = script.beats
    hook = beats[0].text if beats else script.title
    question = script.cta_question or (beats[-1].text if beats and beats[-1].text.endswith("?") else "")
    paragraphs = []
    for section in ("context", "story", "payoff", "ending"):
        text = " ".join(b.text for b in beats[1:] if b.section == section and b.text != question)
        if text:
            paragraphs.append(text)
    caption = "\n\n".join([hook, *paragraphs] + ([question] if question else []))
    stop = {"the", "and", "of", "in", "a", "an", "to", "for", "how", "why", "what", "is", "are", "on", "with", "its"}
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z]+", topic) if w.lower() not in stop]
    tags = []
    if words:
        tags.append(_hashtag(words[0]))
    if len(words) >= 3:
        tags.append(_hashtag(words[1] + " " + words[2]))  # "solar power" -> #SolarPower
    elif len(words) == 2:
        tags.append(_hashtag(words[1]))
    tags += [STYLE_TAGS.get(style, "#DidYouKnow"), "#DidYouKnow", "#LearnOnInstagram"]
    return InstagramPackage(
        title=script.title, caption=caption, hashtags=list(dict.fromkeys(t for t in tags if t))[:MAX_HASHTAGS],
        pinned_comment=f"Every fact in this reel is sourced - the list is in the caption. {question or 'What should we cover next?'}",
        cta="Save this to come back to the sources later.", cover_headline=script.title,
        alt_text=f"Short educational video about {topic} with narration, data graphics and subtitles.",
    )


def build_package(pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print) -> InstagramPackage:
    project = store.project(pid)
    script = store.script(pid)
    research = store.research(pid)
    sb = store.storyboard(pid)
    if not (script and research):
        raise RuntimeError("Script and research are required")
    pkg = None
    if s.has_llm:
        try:
            from ..llm.client import Claude
            from ..llm.prompts import PACKAGE_SYSTEM
            from ..llm.schemas import XPackage

            claims = "\n".join(f"{c.id}: {c.statement}" for c in research.claims if c.status == "verified")
            prompt = (f"Topic: {project.settings.topic}\nStyle: {project.settings.style}\nLanguage: {project.settings.language}\n\n"
                      f"Script:\n" + "\n".join(f"- {b.text}" for b in script.beats) + f"\n\nVerified claims:\n{claims}")
            x = Claude(s).structured(PACKAGE_SYSTEM, prompt, XPackage, effort="low", max_tokens=8000)
            pkg = InstagramPackage(title=x.title, caption=x.caption.strip(), hashtags=x.hashtags, pinned_comment=x.pinned_comment,
                                   cta=x.cta, alt_text=x.alt_text)
            log("Caption written with Claude.")
        except Exception as e:
            log(f"Claude caption failed ({e}); using the template.")
    if pkg is None:
        pkg = template_package(script, research, project.settings.topic, project.settings.style)
    pkg.hashtags = [h if h.startswith("#") else "#" + h for h in (re.sub(r"\s+", "", t) for t in pkg.hashtags) if len(h) > 1][:MAX_HASHTAGS]
    pkg.cover_headline = sb.cover.headline if sb and sb.cover else pkg.title
    pkg.sources_text = sources_block(script, research)
    pkg.credits_text = credits_line(pid, store)
    # assemble the final caption: body + sources (+ required credits) + hashtags, within Instagram's limit
    tail = "\n\n" + pkg.sources_text + (f"\n{pkg.credits_text}" if pkg.credits_text else "") + "\n\n" + " ".join(pkg.hashtags)
    body = pkg.caption
    if len(body) + len(tail) > MAX_CAPTION:
        body = body[: MAX_CAPTION - len(tail) - 1].rsplit(" ", 1)[0] + "…"
    full_caption = body + tail
    store.save("package", pid, pkg)
    store.write_text(pid, "output/caption.txt", full_caption + "\n")
    store.write_text(pid, "output/pinned_comment.txt", pkg.pinned_comment + "\n")
    store.write_text(pid, "output/sources.md", sources_markdown(script, research))
    return pkg


def sources_markdown(script: Script, research: Research) -> str:
    out = [f"# Sources for \"{script.title}\"", ""]
    for b in script.beats:
        if not b.claim_ids:
            continue
        out.append(f"**{b.text}**")
        for cid in b.claim_ids:
            c = research.claim(cid)
            if not c:
                continue
            for e in c.evidence:
                if e.verification not in ("exact", "fuzzy", "agent_attested"):
                    continue
                src = research.source(e.source_id)
                if src:
                    out.append(f"- {cid} ({c.status}) - {src.publisher}: [{src.title or src.url}]({src.url}) - accessed {src.accessed_at[:10]}")
                    out.append(f"  > {e.quote}")
        out.append("")
    return "\n".join(out)
