"""Copyright-safe media sources. Every candidate carries its licence and attribution.

- Pexels    (PEXELS_API_KEY)  - Pexels License: free use, no attribution required (we credit anyway)
- Pixabay   (PIXABAY_API_KEY) - Pixabay Content License: free use, no attribution required (we credit anyway)
- Wikimedia Commons (no key)  - only Public Domain / CC0 / CC BY / CC BY-SA files are accepted; attribution kept
- NASA Image & Video Library (no key) - generally not copyrighted; "NASA" credit kept, no endorsement implied
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Optional

import requests

from ..config import Settings, settings as default_settings


@dataclass
class Candidate:
    provider: str
    provider_id: str
    kind: str  # video | image
    page_url: str
    download_url: str
    width: int
    height: int
    duration: float = 0.0
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = ""
    author_url: str = ""
    license: str = ""
    license_url: str = ""
    attribution_required: bool = False
    thumb_url: str = ""
    documentary: bool = False  # depicts the specific real subject (e.g. Wikimedia/NASA photo of the place)
    score: float = 0.0


class ProviderError(RuntimeError):
    pass


def _get(url: str, s: Settings, **kw) -> dict:
    headers = kw.pop("headers", {})
    headers.setdefault("User-Agent", s.user_agent)
    try:
        r = requests.get(url, headers=headers, timeout=s.http_timeout, **kw)
    except requests.exceptions.ProxyError as e:
        raise ProviderError(f"network policy blocked {url.split('/')[2]}: {e}") from e
    except requests.exceptions.RequestException as e:
        raise ProviderError(str(e)) from e
    if r.status_code != 200:
        raise ProviderError(f"HTTP {r.status_code} from {url.split('/')[2]}")
    return r.json()


def pexels_videos(query: str, s: Settings = default_settings, n: int = 12) -> list[Candidate]:
    if not s.pexels_api_key:
        return []
    data = _get("https://api.pexels.com/videos/search", s, params={"query": query, "orientation": "portrait", "per_page": n, "size": "medium"},
                headers={"Authorization": s.pexels_api_key})
    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
        if not files:
            continue
        # pick the smallest file that is still >= 1080 px on the short side, else the largest
        files.sort(key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
        good = [f for f in files if min(f.get("width") or 0, f.get("height") or 0) >= 1080]
        f = good[0] if good else files[-1]
        slug = re.sub(r"https://www.pexels.com/video/|/$", "", v.get("url", "")).replace("-", " ")
        out.append(Candidate(
            provider="pexels", provider_id=str(v["id"]), kind="video", page_url=v.get("url", ""), download_url=f["link"],
            width=f.get("width") or v.get("width", 0), height=f.get("height") or v.get("height", 0), duration=float(v.get("duration") or 0),
            title=slug, tags=[w for w in slug.split() if not w.isdigit()], author=(v.get("user") or {}).get("name", ""),
            author_url=(v.get("user") or {}).get("url", ""), license="Pexels License", license_url="https://www.pexels.com/license/",
            thumb_url=v.get("image", ""),
        ))
    return out


def pexels_photos(query: str, s: Settings = default_settings, n: int = 12) -> list[Candidate]:
    if not s.pexels_api_key:
        return []
    data = _get("https://api.pexels.com/v1/search", s, params={"query": query, "orientation": "portrait", "per_page": n},
                headers={"Authorization": s.pexels_api_key})
    out = []
    for p in data.get("photos", []):
        src = p.get("src") or {}
        out.append(Candidate(
            provider="pexels", provider_id=str(p["id"]), kind="image", page_url=p.get("url", ""), download_url=src.get("large2x") or src.get("original", ""),
            width=p.get("width", 0), height=p.get("height", 0), title=p.get("alt", ""), description=p.get("alt", ""),
            tags=(p.get("alt") or "").lower().split(), author=p.get("photographer", ""), author_url=p.get("photographer_url", ""),
            license="Pexels License", license_url="https://www.pexels.com/license/", thumb_url=src.get("medium", ""),
        ))
    return out


def pixabay_videos(query: str, s: Settings = default_settings, n: int = 15) -> list[Candidate]:
    if not s.pixabay_api_key:
        return []
    data = _get("https://pixabay.com/api/videos/", s, params={"key": s.pixabay_api_key, "q": query[:100], "safesearch": "true", "per_page": n})
    out = []
    for h in data.get("hits", []):
        vids = h.get("videos") or {}
        v = vids.get("large") if (vids.get("large") or {}).get("url") else vids.get("medium") or {}
        if not v.get("url"):
            continue
        out.append(Candidate(
            provider="pixabay", provider_id=str(h["id"]), kind="video", page_url=h.get("pageURL", ""), download_url=v["url"],
            width=v.get("width", 0), height=v.get("height", 0), duration=float(h.get("duration") or 0), title=h.get("tags", ""),
            tags=[t.strip() for t in (h.get("tags") or "").split(",")], author=h.get("user", ""),
            author_url=f"https://pixabay.com/users/{h.get('user', '')}-{h.get('user_id', '')}/", license="Pixabay Content License",
            license_url="https://pixabay.com/service/license-summary/", thumb_url=v.get("thumbnail", ""),
        ))
    return out


def pixabay_photos(query: str, s: Settings = default_settings, n: int = 15) -> list[Candidate]:
    if not s.pixabay_api_key:
        return []
    data = _get("https://pixabay.com/api/", s, params={"key": s.pixabay_api_key, "q": query[:100], "image_type": "photo", "orientation": "vertical", "safesearch": "true", "per_page": n})
    return [Candidate(
        provider="pixabay", provider_id=str(h["id"]), kind="image", page_url=h.get("pageURL", ""), download_url=h.get("largeImageURL", ""),
        width=h.get("imageWidth", 0), height=h.get("imageHeight", 0), title=h.get("tags", ""), tags=[t.strip() for t in (h.get("tags") or "").split(",")],
        author=h.get("user", ""), author_url=f"https://pixabay.com/users/{h.get('user', '')}-{h.get('user_id', '')}/",
        license="Pixabay Content License", license_url="https://pixabay.com/service/license-summary/", thumb_url=h.get("previewURL", ""),
    ) for h in data.get("hits", []) if h.get("largeImageURL")]


_OK_LICENSES = re.compile(r"^(public domain|pd|cc0|cc[- ]by(?:[- ]sa)?(?:[- ][\d.]+)?)", re.I)


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def wikimedia_photos(query: str, s: Settings = default_settings, n: int = 20) -> list[Candidate]:
    if not s.enable_wikimedia:
        return []
    data = _get("https://commons.wikimedia.org/w/api.php", s, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600,
    })
    out = []
    for page in (data.get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
        if not _OK_LICENSES.match(lic) or "nc" in lic.lower() or "nd" in lic.lower():
            continue
        if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        title = page.get("title", "").removeprefix("File:")
        out.append(Candidate(
            provider="wikimedia", provider_id=str(page.get("pageid")), kind="image", page_url=info.get("descriptionurl", ""),
            download_url=info.get("thumburl") or info.get("url", ""), width=info.get("thumbwidth") or info.get("width", 0),
            height=info.get("thumbheight") or info.get("height", 0), title=title,
            description=_strip_html((meta.get("ImageDescription") or {}).get("value", ""))[:400],
            tags=re.findall(r"[a-z]+", title.lower()), author=_strip_html((meta.get("Artist") or {}).get("value", ""))[:120],
            license=lic, license_url=(meta.get("LicenseUrl") or {}).get("value", ""),
            attribution_required=(meta.get("AttributionRequired") or {}).get("value", "false") == "true" or lic.lower().startswith("cc by"),
            documentary=True,
        ))
    return out


def nasa_media(query: str, s: Settings = default_settings, n: int = 12, media_type: str = "image") -> list[Candidate]:
    if not s.enable_nasa:
        return []
    data = _get("https://images-api.nasa.gov/search", s, params={"q": query, "media_type": media_type, "page_size": n})
    out = []
    for item in ((data.get("collection") or {}).get("items") or [])[:n]:
        d = (item.get("data") or [{}])[0]
        nid = d.get("nasa_id")
        if not nid:
            continue
        try:
            assets = _get(f"https://images-api.nasa.gov/asset/{nid}", s)
        except ProviderError:
            continue
        hrefs = [x.get("href", "") for x in (assets.get("collection") or {}).get("items", [])]
        if media_type == "image":
            pick = next((h for h in hrefs if "~large" in h and h.endswith(".jpg")), None) or next((h for h in hrefs if h.endswith(".jpg")), None)
        else:
            pick = next((h for h in hrefs if "~mobile" in h and h.endswith(".mp4")), None) or next((h for h in hrefs if h.endswith(".mp4")), None)
        if not pick:
            continue
        out.append(Candidate(
            provider="nasa", provider_id=nid, kind="image" if media_type == "image" else "video", page_url=f"https://images.nasa.gov/details/{nid}",
            download_url=pick.replace("http://", "https://"), width=0, height=0, title=d.get("title", ""),
            description=(d.get("description") or "")[:400], tags=[k.lower() for k in (d.get("keywords") or [])],
            author=f"NASA{(' / ' + d.get('center')) if d.get('center') else ''}", license="NASA media usage guidelines (generally not copyrighted)",
            license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/", documentary=True,
        ))
    return out


def search_all(query: str, prefer: str, s: Settings = default_settings, errors: Optional[list[str]] = None) -> list[Candidate]:
    funcs = []
    if prefer in ("video", "any"):
        funcs += [pexels_videos, pixabay_videos]
    if prefer in ("photo", "any"):
        funcs += [pexels_photos, pixabay_photos, wikimedia_photos]
    if prefer == "photo":
        funcs.append(nasa_media)
    out: list[Candidate] = []
    for f in funcs:
        try:
            out += f(query, s)
        except ProviderError as e:
            if errors is not None:
                errors.append(f"{f.__name__}: {e}")
    return out
