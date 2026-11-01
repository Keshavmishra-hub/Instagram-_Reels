"""Storyboard stage: decide what the viewer sees for every sentence."""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from ..config import Settings, settings as default_settings
from ..languages import get_language
from ..models import CoverSpec, Overlay, Research, Scene, Script, ScriptIssue, Storyboard, Visual
from ..research.verify import extract_numbers, numbers_supported
from ..storage import ProjectStore
from ..styles import get_style

USEFUL_ICONS = [
    "sprout", "wheat", "leaf", "tree-pine", "tractor", "milk", "beef", "fish", "apple", "carrot", "droplets", "cloud-rain",
    "sun", "snowflake", "thermometer", "mountain", "globe", "map-pin", "landmark", "building-2", "factory", "warehouse",
    "lock", "vault", "shield-check", "key-round", "scale", "gavel", "banknote", "coins", "piggy-bank", "trending-up",
    "trending-down", "chart-column", "users", "user", "baby", "graduation-cap", "book-open", "flask-conical", "microscope",
    "dna", "atom", "rocket", "satellite", "plane", "ship", "truck", "train-front", "car", "zap", "battery-charging",
    "fuel", "flame", "wind", "waves", "heart-pulse", "stethoscope", "pill", "syringe", "smartphone", "cpu", "wifi",
    "newspaper", "megaphone", "clock", "calendar", "hourglass", "flag", "anchor", "package", "shopping-cart", "store",
    "hand-coins", "handshake", "earth", "seedling", "bird", "bug", "cow", "egg", "grape", "salad", "utensils", "home",
]

STOPWORDS = set("""a an the and or but if of in on at to for from by with about as into than then that this these those is are was
were be been being it its they them their there here what which who whom whose when where why how not no yes do does did
can could should would will just more most less least very so such also only even ever much many each every some any
all both one two three first second new old today now our we you your he she his her i me my""".split())


def _keywords(text: str, k: int = 3) -> list[str]:
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]+", text)]
    out = []
    for w in words:
        if w not in STOPWORDS and len(w) > 3 and w not in out:
            out.append(w)
    return out[:k]


def _first_number_param(text: str) -> Optional[dict]:
    m = re.search(r"([$₹€£])?\s?(-|−)?(\d[\d,]*(?:\.\d+)?)\s*(%|°C|°F)?\s*(thousand|million|billion|trillion|lakh|crore)?", text)
    if not m:
        return None
    raw = m.group(3).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if m.group(2):
        value = -value
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    is_year = decimals == 0 and 1100 <= value <= 2099 and not m.group(4) and not m.group(5)
    return {
        "value": value, "decimals": decimals, "prefix": m.group(1) or "", "suffix": m.group(4) or "",
        "unit": m.group(5) or "", "count": not is_year, "is_year": is_year,
    }


def rule_based_storyboard(script: Script, research: Optional[Research], stock_available: bool) -> Storyboard:
    """Deterministic fallback when no LLM is configured (or as a starting point for manual editing)."""
    scenes: list[Scene] = []
    transitions = ["cut", "whip", "slide_up", "zoom", "fade", "slide_left", "wipe"]
    for i, b in enumerate(script.beats):
        text = b.text
        num = _first_number_param(text)
        kw = _keywords(text) or _keywords(script.title)
        src_ids = sorted({e.source_id for cid in b.claim_ids if research and research.claim(cid) for e in research.claim(cid).evidence})
        if b.section == "hook":
            vis = Visual(kind="kinetic", purpose="Hook typography over atmospheric footage",
                         params={"text": b.on_screen_text or " ".join(text.split()[:7]), "highlight": b.emphasis[:1]})
            bg_q = [" ".join(kw[:2])] if kw else []
            scenes.append(Scene(id=f"SC{i + 1}", beat_ids=[b.id], visual=vis,
                                background=Visual(kind="footage", queries=bg_q, prefer="video", authenticity="representative") if stock_available and bg_q else None,
                                transition="cut", subtitle_position="lower", source_ids=src_ids))
            continue
        if b.section == "ending":
            vis = Visual(kind="kinetic", purpose="Closing question", params={"text": b.on_screen_text or text, "highlight": b.emphasis[:1]})
        elif num and not num["is_year"]:
            label = b.on_screen_text or re.sub(r"\s+", " ", text)
            vis = Visual(kind="stat", purpose="Make the key number unmissable",
                         params={k: v for k, v in num.items() if k != "is_year"} | {"label": label[:80]})
        elif stock_available and kw:
            vis = Visual(kind="footage", purpose="Show the subject", queries=[" ".join(kw[:2]), kw[0]], prefer="video", authenticity="representative")
        else:
            vis = Visual(kind="kinetic", purpose="Typography for the key idea", params={"text": b.on_screen_text or " ".join(text.split()[:7]), "highlight": b.emphasis[:1]})
        scenes.append(Scene(id=f"SC{i + 1}", beat_ids=[b.id], visual=vis, transition=transitions[i % len(transitions)],
                            subtitle_position="lower", source_ids=src_ids))
    words = script.title.split()
    cover = CoverSpec(headline=" ".join(words[:6]), highlight=words[-1] if words else "", kicker="", scene_id=scenes[0].id if scenes else None)
    return Storyboard(scenes=scenes, music_mood="curious", cover=cover, planned_by="rules")


def plan_storyboard(pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print) -> Storyboard:
    project = store.project(pid)
    script = store.script(pid)
    research = store.research(pid)
    if script is None:
        raise RuntimeError("Write and approve the script first")
    stock = bool(s.pexels_api_key or s.pixabay_api_key or s.enable_wikimedia)
    if not s.has_llm:
        log("No Claude API key: using the rule-based storyboard planner (edit scenes in the UI).")
        sb = rule_based_storyboard(script, research, stock)
    else:
        sb = _llm_storyboard(pid, store, script, research, stock, s, log)
    prev = store.storyboard(pid)
    sb.version = (prev.version + 1) if prev else 1
    save_storyboard(pid, store, sb)
    return sb


def _llm_storyboard(pid, store, script, research, stock, s, log) -> Storyboard:
    from ..llm.client import Claude
    from ..llm.prompts import STORYBOARD_PROMPT, STORYBOARD_SYSTEM
    from ..llm.schemas import XStoryboard

    ps = store.project(pid).settings
    style = get_style(ps.style)
    beats = "\n".join(f"{b.id} | {b.section} | {b.text} | {', '.join(b.claim_ids) or '-'}" for b in script.beats)
    claims = "\n".join(f"{c.id}: {c.statement}" for c in (research.claims if research else []) if c.status in ("verified", "single_source"))
    prompt = STORYBOARD_PROMPT.format(
        style_name=style.name, visual_bias=", ".join(style.visual_bias),
        stock="yes (Pexels/Pixabay/Wikimedia)" if stock else "no - prefer graphics (map, stat, chart, timeline, kinetic, icon)",
        language=get_language(ps.language).name, beats=beats, claims=claims, icons=", ".join(USEFUL_ICONS),
    )
    log("Planning storyboard with Claude ...")
    x = Claude(s).structured(STORYBOARD_SYSTEM, prompt, XStoryboard, effort="medium")
    scenes = []
    for i, xs in enumerate(x.scenes, 1):
        try:
            params = json.loads(xs.visual.params_json or "{}")
            if not isinstance(params, dict):
                params = {}
        except json.JSONDecodeError:
            params = {}
        vis = Visual(kind=xs.visual.kind, purpose=xs.visual.purpose, queries=xs.visual.queries, prefer=xs.visual.prefer,
                     params=params, authenticity=xs.visual.authenticity)
        bg = Visual(kind="footage", queries=xs.background_queries, prefer="video", authenticity="representative") if xs.background_queries and stock else None
        src_ids = sorted({e.source_id for cid in (c for b in xs.beat_ids for c in (script.beat(b).claim_ids if script.beat(b) else []))
                          if research and research.claim(cid) for e in research.claim(cid).evidence})
        scenes.append(Scene(id=f"SC{i}", beat_ids=xs.beat_ids, visual=vis, background=bg,
                            overlays=[Overlay(kind=o.kind, text=o.text, at_word=o.at_word, position=o.position) for o in xs.overlays],
                            transition=xs.transition, subtitle_position=xs.subtitle_position, source_ids=src_ids, sfx=xs.sfx))
    beat_to_scene = {b: sc.id for sc in scenes for b in sc.beat_ids}
    cover = CoverSpec(headline=x.cover.headline, highlight=x.cover.highlight, kicker=x.cover.kicker, scene_id=beat_to_scene.get(x.cover.beat_id))
    return Storyboard(scenes=scenes, music_mood=x.music_mood, cover=cover, planned_by=f"claude_api:{s.llm_model}")


def validate_storyboard(sb: Storyboard, script: Script, research: Optional[Research]) -> list[ScriptIssue]:
    """Every beat covered once, in order; graphic numbers backed by the scene's cited claims."""
    issues: list[ScriptIssue] = []
    order = [b.id for b in script.beats]
    covered = [b for sc in sb.scenes for b in sc.beat_ids]
    if covered != [b for b in order if b in covered] or set(covered) != set(order) or len(covered) != len(set(covered)):
        issues.append(ScriptIssue(severity="error", code="beat_coverage", message="Scenes must cover every beat exactly once, in script order."))
    for sc in sb.scenes:
        claim_ids = [cid for b in sc.beat_ids for cid in (script.beat(b).claim_ids if script.beat(b) else [])]
        support: list[str] = []
        if research:
            for cid in claim_ids:
                c = research.claim(cid)
                if c:
                    support.append(c.statement)
                    support += [e.quote for e in c.evidence if e.verification in ("exact", "fuzzy", "agent_attested")]
        support += [script.beat(b).text for b in sc.beat_ids if script.beat(b)]
        p = sc.visual.params
        texts: list[str] = []
        if sc.visual.kind == "stat" and "value" in p:
            texts.append(str(p.get("value")) + (" " + str(p.get("unit")) if p.get("unit") else ""))
        elif sc.visual.kind == "chart":
            texts += [str(d.get("value")) for d in p.get("data", [])]
        elif sc.visual.kind == "timeline":
            texts += [str(e.get("label", "")) + " " + str(e.get("text", "")) for e in p.get("events", [])]
        elif sc.visual.kind == "comparison":
            texts += [str((p.get(k) or {}).get("value", "")) for k in ("left", "right")]
        for o in sc.overlays:
            texts.append(o.text)
        for t in texts:
            if not extract_numbers(t):
                continue
            ok, miss = numbers_supported(t, support)
            if not ok:
                issues.append(ScriptIssue(beat_id=sc.id, severity="error", code="graphic_number_unsupported",
                                          message=f"{sc.id}: on-screen number(s) {', '.join(f'{m:g}' for m in miss)} are not backed by the scene's claims."))
        if sc.visual.kind == "map":
            c = p.get("center") or [0, 0]
            if not (isinstance(c, list) and len(c) == 2 and -180 <= float(c[0]) <= 180 and -90 <= float(c[1]) <= 90):
                issues.append(ScriptIssue(beat_id=sc.id, severity="error", code="map_coords", message=f"{sc.id}: invalid map centre {c}."))
        if sc.visual.kind == "quote":
            q = str(p.get("quote", ""))
            if q and not any(q.lower()[:60] in s.lower() for s in support):
                issues.append(ScriptIssue(beat_id=sc.id, severity="error", code="quote_unverified", message=f"{sc.id}: quote is not found in the verified evidence."))
    return issues


def save_storyboard(pid: str, store: ProjectStore, sb: Storyboard) -> list[ScriptIssue]:
    store.save("storyboard", pid, sb)
    # stills/previews show the previous plan; remove them so the UI never shows a stale frame for a scene id
    render_dir = store.dir(pid) / "render"
    for stale in list(render_dir.glob("stills/*.jpg")) + list(render_dir.glob("preview_*.mp4")):
        stale.unlink(missing_ok=True)
    script = store.script(pid)
    issues = validate_storyboard(sb, script, store.research(pid)) if script else []
    store.write_json(pid, "storyboard_issues.json", [i.model_dump() for i in issues])
    return issues


def regenerate_scene(pid: str, scene_id: str, store: ProjectStore, instruction: str = "", s: Settings = default_settings,
                     log: Callable[[str], None] = print) -> Scene:
    """Re-plan one scene (Claude) - e.g. 'use a map instead' - keeping the rest of the storyboard."""
    from ..llm.client import Claude
    from ..llm.prompts import STORYBOARD_SYSTEM
    from ..llm.schemas import XScene

    sb = store.storyboard(pid)
    script = store.script(pid)
    research = store.research(pid)
    sc = sb.scene(scene_id) if sb else None
    if sc is None:
        raise ValueError(f"unknown scene {scene_id}")
    beats = "\n".join(f"{b} | {script.beat(b).text} | claims: {', '.join(script.beat(b).claim_ids)}" for b in sc.beat_ids if script.beat(b))
    claims = "\n".join(f"{c.id}: {c.statement}" for c in (research.claims if research else []) if c.status in ("verified", "single_source"))
    prompt = (f"Re-plan ONLY this scene. Current plan: {sc.model_dump_json()}\nBeats:\n{beats}\nClaims:\n{claims}\n"
              f"Creator instruction: {instruction or 'make it more visually engaging'}\nIcons: {', '.join(USEFUL_ICONS)}\n"
              f"Keep beat_ids exactly {sc.beat_ids}.")
    x = Claude(s).structured(STORYBOARD_SYSTEM, prompt, XScene, effort="medium")
    try:
        params = json.loads(x.visual.params_json or "{}")
    except json.JSONDecodeError:
        params = {}
    new = Scene(id=sc.id, beat_ids=sc.beat_ids,
                visual=Visual(kind=x.visual.kind, purpose=x.visual.purpose, queries=x.visual.queries, prefer=x.visual.prefer,
                              params=params if isinstance(params, dict) else {}, authenticity=x.visual.authenticity),
                background=Visual(kind="footage", queries=x.background_queries, prefer="video", authenticity="representative") if x.background_queries else None,
                overlays=[Overlay(kind=o.kind, text=o.text, at_word=o.at_word, position=o.position) for o in x.overlays],
                transition=x.transition, subtitle_position=x.subtitle_position, source_ids=sc.source_ids, sfx=x.sfx)
    sb.scenes = [new if s_.id == scene_id else s_ for s_ in sb.scenes]
    save_storyboard(pid, store, sb)
    return new
