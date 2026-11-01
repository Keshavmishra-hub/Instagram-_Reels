"""Choose, download and normalise media for each scene; keep alternatives for one-click swaps."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

import requests
from PIL import Image

from ..config import Settings, settings as default_settings
from ..models import Asset, AssetLibrary, Scene, Storyboard
from ..storage import ProjectStore
from .providers import Candidate, search_all

STOP = set("a an the of and or in on at to for with from by is are was were this that these those its it as into over under".split())


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def score(c: Candidate, query: str, scene_secs: float, beat_text: str = "") -> float:
    want = _tokens(query) | _tokens(beat_text)
    have = _tokens(" ".join(c.tags)) | _tokens(c.title) | _tokens(c.description)
    rel = len(want & have) / max(1, len(_tokens(query)))
    sc = 2.0 * min(1.0, rel)
    if c.kind == "video":
        if c.height > c.width:
            sc += 0.6
        if c.duration >= scene_secs:
            sc += 0.4
        elif c.duration >= scene_secs * 0.6:
            sc += 0.2
    else:
        if c.height >= c.width:
            sc += 0.3
    if min(c.width or 0, c.height or 0) >= 1080 or c.provider == "nasa":
        sc += 0.3
    if c.documentary:
        sc += 0.2
    return round(sc, 3)


def _download(url: str, dest: Path, s: Settings) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": s.user_agent}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def normalise_video(src: Path, dest: Path, max_secs: float, s: Settings = default_settings) -> tuple[int, int, float]:
    """H.264 yuv420p 30 fps, no audio, short side >= 1080 when available, trimmed - fast for Remotion to read."""
    vf = "scale='if(gt(iw,ih),-2,min(1080,iw))':'if(gt(iw,ih),min(1920,ih),-2)',fps=30,format=yuv420p"
    subprocess.run([s.ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-t", f"{max_secs:.2f}", "-an",
                    "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart", str(dest)], check=True)
    from ..render.master import probe

    info = probe(dest, s)
    v = next(st for st in info["streams"] if st["codec_type"] == "video")
    return int(v["width"]), int(v["height"]), float(info["format"].get("duration", 0))


def normalise_image(src: Path, dest: Path) -> tuple[int, int]:
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((2160, 2160))
        im.save(dest, "JPEG", quality=92)
        return im.size


def _to_asset(c: Candidate, aid: str, query: str, authenticity: str) -> Asset:
    attribution = f"{'Photo' if c.kind == 'image' else 'Video'}: {c.author or 'unknown'} / {c.provider.capitalize()} ({c.license})"
    return Asset(id=aid, kind=c.kind, provider=c.provider, provider_id=c.provider_id, page_url=c.page_url, download_url=c.download_url,
                 width=c.width, height=c.height, duration=c.duration, title=c.title, description=c.description, tags=c.tags[:20],
                 author=c.author, author_url=c.author_url, license=c.license, license_url=c.license_url,
                 attribution_required=c.attribution_required, attribution=attribution,
                 authenticity="documentary" if (c.documentary and authenticity == "documentary") else "representative",
                 query=query, relevance=c.score)


def fetch_asset(pid: str, store: ProjectStore, asset: Asset, max_secs: float, s: Settings = default_settings) -> Asset:
    d = store.dir(pid) / "assets"
    raw = d / f"raw_{asset.id}{'.mp4' if asset.kind == 'video' else '.img'}"
    _download(asset.download_url, raw, s)
    if asset.kind == "video":
        out = d / f"{asset.id}.mp4"
        asset.width, asset.height, asset.duration = normalise_video(raw, out, max_secs + 1.0, s)
    else:
        out = d / f"{asset.id}.jpg"
        asset.width, asset.height = normalise_image(raw, out)
    raw.unlink(missing_ok=True)
    asset.file = f"assets/{out.name}"
    return asset


def gather_assets(pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print,
                  only_scene: Optional[str] = None) -> dict:
    sb: Storyboard = store.storyboard(pid)
    script = store.script(pid)
    tl = store.timeline(pid)
    lib: AssetLibrary = store.assets(pid)
    durations = {}
    if tl:
        from ..voice.narration import scene_timings

        durations = {t.scene_id: t.end - t.start for t in scene_timings(sb, tl)}
    used = {a.provider_id for a in lib.assets if any(a.id in (sc.visual.asset_id, sc.background.asset_id if sc.background else None) for sc in sb.scenes)}
    report = {"downloaded": 0, "missing": [], "errors": []}
    for sc in sb.scenes:
        if only_scene and sc.id != only_scene:
            continue
        targets: list[tuple[str, object]] = []
        if sc.visual.kind in ("footage", "photo"):
            targets.append(("visual", sc.visual))
        if sc.background is not None:
            targets.append(("background", sc.background))
        for role, vis in targets:
            if vis.asset_id and lib.get(vis.asset_id) and (store.dir(pid) / lib.get(vis.asset_id).file).exists() and not only_scene:
                continue
            secs = durations.get(sc.id, 4.0)
            beat_text = " ".join(script.beat(b).text for b in sc.beat_ids if script and script.beat(b))
            prefer = "photo" if vis.kind == "photo" else vis.prefer
            cands: list[Candidate] = []
            for q in (vis.queries or [])[:3]:
                for c in search_all(q, prefer, s, report["errors"]):
                    c.score = score(c, q, secs, beat_text)
                    c.title = c.title or q
                    cands.append(c)
                if len([c for c in cands if c.score >= 2.0]) >= 4:
                    break
            cands = [c for c in cands if c.provider_id not in used]
            cands.sort(key=lambda c: c.score, reverse=True)
            if not cands:
                report["missing"].append(f"{sc.id}:{role}")
                log(f"{sc.id}: no licensed media found for {vis.queries} - falling back to motion graphics")
                vis.asset_id = None
                continue
            chosen = None
            alternatives = []
            for c in cands[:5]:
                aid = f"A{len(lib.assets) + 1}"
                a = _to_asset(c, aid, c.title, vis.authenticity)
                if chosen is None:
                    try:
                        a = fetch_asset(pid, store, a, secs, s)
                        chosen = a
                        used.add(c.provider_id)
                        report["downloaded"] += 1
                    except Exception as e:  # try the next candidate
                        report["errors"].append(f"{sc.id}: download failed for {c.page_url}: {e}")
                        continue
                lib.assets.append(a)
                alternatives.append(a.id)
            if chosen:
                vis.asset_id = chosen.id
                vis.candidate_ids = alternatives
                log(f"{sc.id} {role}: {chosen.provider} '{chosen.title[:50]}' by {chosen.author or 'unknown'} ({chosen.license})")
            else:
                report["missing"].append(f"{sc.id}:{role}")
    store.save("assets", pid, lib)
    store.save("storyboard", pid, sb)
    store.write_json(pid, "assets/report.json", report)
    return report


def swap_asset(pid: str, store: ProjectStore, scene_id: str, asset_id: str, role: str = "visual", s: Settings = default_settings) -> Asset:
    sb = store.storyboard(pid)
    lib = store.assets(pid)
    sc = sb.scene(scene_id)
    a = lib.get(asset_id)
    if not sc or not a:
        raise ValueError("unknown scene or asset")
    if not a.file or not (store.dir(pid) / a.file).exists():
        tl = store.timeline(pid)
        secs = 6.0
        if tl:
            from ..voice.narration import scene_timings

            secs = next((t.end - t.start for t in scene_timings(sb, tl) if t.scene_id == scene_id), 6.0)
        a = fetch_asset(pid, store, a, secs, s)
        lib.assets = [a if x.id == a.id else x for x in lib.assets]
    target = sc.visual if role == "visual" else sc.background
    if target is None:
        raise ValueError("scene has no background slot")
    target.asset_id = a.id
    store.save("assets", pid, lib)
    store.save("storyboard", pid, sb)
    return a


def add_local_asset(pid: str, store: ProjectStore, path: Path, license: str, author: str, authenticity: str = "documentary",
                    title: str = "", s: Settings = default_settings) -> Asset:
    """User-supplied media (their own footage or properly licensed files)."""
    lib = store.assets(pid)
    aid = f"A{len(lib.assets) + 1}"
    is_video = path.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm", ".mkv")
    out = store.dir(pid) / "assets" / f"{aid}{'.mp4' if is_video else '.jpg'}"
    if is_video:
        w, h, dur = normalise_video(path, out, 60.0, s)
    else:
        (w, h), dur = normalise_image(path, out), 0.0
    a = Asset(id=aid, kind="video" if is_video else "image", provider="local", provider_id=path.name, file=f"assets/{out.name}",
              width=w, height=h, duration=dur, title=title or path.stem, author=author, license=license,
              attribution=f"{author} ({license})", authenticity=authenticity)
    lib.assets.append(a)
    store.save("assets", pid, lib)
    return a
