"""Turn project data (storyboard + timeline + assets + research) into Remotion input props."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ..brand import load_brand
from ..config import Settings, settings as default_settings
from ..models import Asset, Research, Scene, Storyboard, Timeline
from ..storage import ProjectStore
from ..voice.narration import scene_timings

ICON_DIR_REL = Path("node_modules/lucide-static/icons")


def icon_svg(name: str, s: Settings = default_settings) -> Optional[str]:
    name = re.sub(r"[^a-z0-9-]", "", (name or "").lower())
    p = s.renderer_dir / ICON_DIR_REL / f"{name}.svg"
    return p.read_text(encoding="utf-8") if p.exists() else None


def available_icons(s: Settings = default_settings) -> list[str]:
    d = s.renderer_dir / ICON_DIR_REL
    return sorted(p.stem for p in d.glob("*.svg")) if d.exists() else []


def short_source(research: Optional[Research], sid: str) -> Optional[str]:
    if not research:
        return None
    src = research.source(sid)
    if not src:
        return None
    name = src.publisher or urlparse(src.url).netloc.replace("www.", "")
    year = ""
    if src.published:
        m = re.search(r"(19|20)\d{2}", src.published)
        year = f" ({m.group(0)})" if m else ""
    return f"{name}{year}"


def authenticity_label(asset: Optional[Asset], scene: Scene) -> Optional[str]:
    if asset is None:
        return "AI-generated illustration" if scene.visual.authenticity == "ai_generated" else None
    if asset.authenticity == "ai_generated":
        return "AI-generated illustration"
    who = f"{asset.author} / {asset.provider.capitalize()}" if asset.author else asset.provider.capitalize()
    if asset.authenticity == "documentary":
        lic = f" · {asset.license}" if asset.license else ""
        return f"{'Photo' if asset.kind == 'image' else 'Footage'}: {who}{lic}"
    kind = "footage" if asset.kind == "video" else "image"
    return f"Representative {kind} · {who}"


def media_dict(asset: Optional[Asset], scene_duration: float) -> Optional[dict]:
    if asset is None or not asset.file:
        return None
    m = {
        "src": asset.file,
        "type": asset.kind,
        "width": asset.width,
        "height": asset.height,
        "duration": asset.duration,
        "credit": asset.attribution,
    }
    if asset.kind == "video" and asset.duration and asset.duration < scene_duration:
        ratio = asset.duration / scene_duration
        if ratio >= 0.6:
            m["playbackRate"] = round(ratio, 3)  # gentle slow-motion instead of looping
    return m


def build_props(pid: str, store: ProjectStore, s: Settings = default_settings, preview_scenes: Optional[list[str]] = None) -> dict:
    project = store.project(pid)
    script = store.script(pid)
    sb: Storyboard = store.storyboard(pid)
    tl: Timeline = store.timeline(pid)
    research = store.research(pid)
    lib = store.assets(pid)
    if not (script and sb and tl):
        raise RuntimeError("Script, storyboard and voice-over are required before rendering")
    brand = load_brand(project.settings.brand, project.settings.language)
    times = {t.scene_id: t for t in scene_timings(sb, tl)}
    beat_words: dict[str, list[int]] = {}
    for i, w in enumerate(tl.words):
        beat_words.setdefault(w.beat_id, []).append(i)
    section_of = {b.id: b.section for b in script.beats}

    scenes = []
    for sc in sb.scenes:
        t = times.get(sc.id)
        if not t:
            continue
        dur = t.end - t.start
        gidx = [i for b in sc.beat_ids for i in beat_words.get(b, [])]
        params = dict(sc.visual.params)
        if sc.visual.kind == "icon":
            names = params.get("icons") or ([params.get("icon")] if params.get("icon") else [])
            svgs = [x for x in (icon_svg(n, s) for n in names) if x]
            if not svgs:
                svgs = [icon_svg("sparkles", s) or ""]
            params["icons_svg"] = svgs
        if sc.visual.kind in ("kinetic", "title") and not params.get("text"):
            beat = script.beat(sc.beat_ids[0]) if sc.beat_ids else None
            params["text"] = (beat.on_screen_text if beat and beat.on_screen_text else (beat.text if beat else ""))
        if sc.visual.kind == "comparison" and gidx:
            for side in ("left", "right"):
                part = params.get(side)
                if isinstance(part, dict) and part.get("at_word") is not None:
                    k = max(0, min(len(gidx) - 1, int(part["at_word"])))
                    params[side] = {**part, "at": round(tl.words[gidx[k]].start, 3)}
        overlays = []
        for o in sc.overlays:
            at = t.start + 0.2
            if o.at_word is not None and gidx:
                k = max(0, min(len(gidx) - 1, o.at_word))
                at = tl.words[gidx[k]].start
            overlays.append({"kind": o.kind, "text": o.text, "at": round(at, 3), "position": o.position})
        main_asset = lib.get(sc.visual.asset_id)
        bg_asset = lib.get(sc.background.asset_id) if sc.background else None
        label = authenticity_label(main_asset if sc.visual.kind in ("footage", "photo") else bg_asset, sc) if (main_asset or bg_asset or sc.visual.authenticity == "ai_generated") else None
        sources = [x for x in (short_source(research, sid) for sid in sc.source_ids) if x]
        scenes.append({
            "id": sc.id,
            "start": t.start,
            "end": t.end,
            "kind": sc.visual.kind if (sc.visual.kind not in ("footage", "photo") or main_asset) else "kinetic",
            "params": params if (sc.visual.kind not in ("footage", "photo") or main_asset) else {**params, "text": params.get("headline") or (script.beat(sc.beat_ids[0]).on_screen_text if sc.beat_ids and script.beat(sc.beat_ids[0]) else "") or ""},
            "media": media_dict(main_asset, dur) if sc.visual.kind in ("footage", "photo") else None,
            "background": media_dict(bg_asset, dur),
            "overlays": overlays,
            "transition": sc.transition,
            "subtitle_position": sc.subtitle_position,
            "label": label,
            "sources": list(dict.fromkeys(sources)),
            "words": gidx,
            "section": section_of.get(sc.beat_ids[0], "story") if sc.beat_ids else "story",
        })
    if preview_scenes:
        scenes = [x for x in scenes if x["id"] in preview_scenes]
    return {
        "fps": 30,
        "width": 1080,
        "height": 1920,
        "duration": tl.duration,
        "title": script.title,
        "brand": brand,
        "scenes": scenes,
        "words": [{"text": w.text, "start": w.start, "end": w.end, "beat": w.beat_id, "emphasis": w.emphasis} for w in tl.words],
        "cues": [{"start": c.start, "end": c.end, "words": c.word_indices} for c in tl.cues],
        "assetsBase": "",
        "endCard": {"question": script.cta_question or "", "sourcesNote": "Sources in caption"},
        "showSubtitles": True,
    }


def cover_props(pid: str, store: ProjectStore, reel_props: dict) -> dict:
    sb = store.storyboard(pid)
    script = store.script(pid)
    lib = store.assets(pid)
    cover = sb.cover if sb and sb.cover else None
    headline = cover.headline if cover else (script.title if script else "")
    scene_id = cover.scene_id if cover and cover.scene_id else None
    scene = next((x for x in reel_props["scenes"] if x["id"] == scene_id), None)
    if scene is None:
        # prefer the most visual scene: footage/photo, then map, then stat
        for kind in ("footage", "photo", "map", "stat", "chart"):
            scene = next((x for x in reel_props["scenes"] if x["kind"] == kind), None)
            if scene:
                break
    background = scene.get("media") if scene and scene.get("media") else None
    return {
        "brand": reel_props["brand"],
        "headline": headline,
        "highlight": cover.highlight if cover else "",
        "kicker": cover.kicker if cover else "",
        "background": background,
        "scene": None if background else scene,
        "assetsBase": "",
    }
