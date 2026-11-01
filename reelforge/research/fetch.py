"""Fetch a source page ourselves and store a plain-text snapshot (the audit trail)."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from ..config import Settings, settings as default_settings


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: Optional[int]
    title: str
    text: str
    error: str = ""
    blocked_by_network: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and len(self.text) > 200


def _extract_html(html: str, url: str) -> tuple[str, str]:
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    text = ""
    try:
        import trafilatura

        text = trafilatura.extract(html, url=url, include_tables=True, include_comments=False, favor_recall=True) or ""
    except Exception:
        text = ""
    if len(text) < 400:  # fall back to a full-text dump so quotes in tables/figures are still found
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml") if _has_lxml() else BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        full = soup.get_text("\n")
        full = re.sub(r"\n\s*\n+", "\n\n", full)
        if len(full) > len(text):
            text = full
    return title, text.strip()


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401

        return True
    except Exception:
        return False


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:120])
    except Exception:
        return ""


def fetch(url: str, s: Settings = default_settings) -> FetchResult:
    headers = {
        "User-Agent": s.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en;q=0.9,*;q=0.5",
    }
    try:
        r = requests.get(url, headers=headers, timeout=s.http_timeout, allow_redirects=True)
    except requests.exceptions.ProxyError as e:
        return FetchResult(url, url, None, "", "", f"network policy blocked the request: {e}", blocked_by_network=True)
    except requests.exceptions.RequestException as e:
        return FetchResult(url, url, None, "", "", str(e))
    ctype = r.headers.get("content-type", "").lower()
    path = url.lower().split("?")[0]
    if "pdf" in ctype or path.endswith(".pdf"):
        text = _extract_pdf(r.content)
        title = url.rsplit("/", 1)[-1]
    elif any(t in ctype for t in ("text/plain", "text/csv", "application/json", "text/markdown")) or path.endswith((".csv", ".tsv", ".json", ".md", ".txt")):
        # data files and plain text are stored byte-faithfully (no HTML extraction)
        r.encoding = r.encoding or "utf-8"
        text = r.text
        title = url.rsplit("/", 1)[-1]
    else:
        r.encoding = r.encoding or r.apparent_encoding
        title, text = _extract_html(r.text, r.url)
    return FetchResult(url, r.url, r.status_code, title, text, "" if r.ok else f"HTTP {r.status_code}")


def save_snapshot(project_dir: Path, source_id: str, url: str, text: str, kind: str = "raw_text", header: str = "") -> tuple[str, str]:
    """Write the snapshot file; returns (relative path, sha256)."""
    rel = f"sources/{source_id}.txt"
    p = project_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    banner = header or f"URL: {url}\nSNAPSHOT-KIND: {kind}\n"
    body = banner + "\n" + text
    p.write_text(body, encoding="utf-8")
    return rel, hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_snapshot(project_dir: Path, rel: Optional[str]) -> str:
    if not rel:
        return ""
    p = project_dir / rel
    if not p.exists():
        return ""
    raw = p.read_text(encoding="utf-8")
    # strip the banner (first blank line separates it)
    parts = raw.split("\n\n", 1)
    return parts[1] if len(parts) == 2 else raw
