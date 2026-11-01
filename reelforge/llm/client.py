"""Claude API access (official Anthropic Python SDK).

- research(): agentic web research with the server-side web_search + web_fetch tools.
  Every page Claude fetched comes back to us as a document block, so we keep the exact text
  Claude read as a source snapshot.
- structured(): JSON output validated against a Pydantic model (claims, script, storyboard, caption).

Model defaults to claude-opus-5-5 (override with REELFORGE_MODEL). Requests opt into server-side
refusal fallbacks ("fallbacks": "default") so a rare safety-classifier decline is retried on the
recommended fallback model instead of failing the whole step.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Callable, Optional, Type, TypeVar

from pydantic import BaseModel

from ..config import Settings, settings as default_settings

T = TypeVar("T", bound=BaseModel)
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


@dataclass
class FetchedDoc:
    url: str
    title: str
    text: str
    retrieved_at: str = ""


@dataclass
class ResearchRun:
    text: str
    searches: list[str] = field(default_factory=list)
    search_results: list[dict] = field(default_factory=list)  # {url, title, page_age}
    fetched: list[FetchedDoc] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)  # {url, title, cited_text}
    fetch_errors: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def _pdf_text(b64: str) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(base64.b64decode(b64)))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return ""


class Claude:
    def __init__(self, s: Settings = default_settings):
        import anthropic

        if not s.has_llm:
            raise LLMError("ANTHROPIC_API_KEY is not set. Add it to .env, or use Claude Code mode (see README).")
        self.s = s
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=3, timeout=900.0)
        self.model = s.llm_model

    # ------------------------------------------------------------------------------------
    def _check(self, msg) -> None:
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            cat = getattr(details, "category", None) if details else None
            raise LLMError(f"The model declined this request (category: {cat}). Rephrase the topic or angle.")
        if msg.stop_reason == "max_tokens":
            raise LLMError("The model ran out of output tokens; try a shorter duration or fewer sources.")

    def _usage(self, msg, acc: dict) -> None:
        u = getattr(msg, "usage", None)
        if not u:
            return
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            acc[k] = acc.get(k, 0) + (getattr(u, k, 0) or 0)
        stu = getattr(u, "server_tool_use", None)
        if stu is not None:
            acc["web_search_requests"] = acc.get("web_search_requests", 0) + (getattr(stu, "web_search_requests", 0) or 0)
            acc["web_fetch_requests"] = acc.get("web_fetch_requests", 0) + (getattr(stu, "web_fetch_requests", 0) or 0)

    # ------------------------------------------------------------------------------------
    def research(self, system: str, prompt: str, effort: str = "high", log: Callable[[str], None] = print) -> ResearchRun:
        tools = [
            {"type": self.s.web_search_tool, "name": "web_search", "max_uses": self.s.research_max_searches},
            {
                "type": self.s.web_fetch_tool,
                "name": "web_fetch",
                "max_uses": self.s.research_max_fetches,
                "citations": {"enabled": True},
                "max_content_tokens": 40000,
            },
        ]
        messages: list = [{"role": "user", "content": prompt}]
        run = ResearchRun(text="")
        texts: list[str] = []
        for _ in range(8):  # continuation budget for pause_turn
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
                tools=tools,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                msg = stream.get_final_message()
            self._usage(msg, run.usage)
            for block in msg.content:
                t = getattr(block, "type", "")
                if t == "server_tool_use":
                    inp = getattr(block, "input", {}) or {}
                    if block.name == "web_search" and inp.get("query"):
                        run.searches.append(str(inp["query"]))
                        log(f"Searching: {inp['query']}")
                    elif block.name == "web_fetch" and inp.get("url"):
                        log(f"Reading: {inp['url']}")
                elif t == "web_search_tool_result":
                    content = block.content
                    if isinstance(content, list):
                        for r in content:
                            run.search_results.append({"url": r.url, "title": r.title, "page_age": getattr(r, "page_age", None)})
                elif t == "web_fetch_tool_result":
                    content = block.content
                    if getattr(content, "type", "") == "web_fetch_result":
                        doc = content.content
                        src = getattr(doc, "source", None)
                        text = ""
                        if src is not None and getattr(src, "type", "") == "text":
                            text = src.data
                        elif src is not None and getattr(src, "type", "") == "base64":
                            text = _pdf_text(src.data)
                        run.fetched.append(FetchedDoc(url=content.url, title=getattr(doc, "title", "") or "", text=text, retrieved_at=getattr(content, "retrieved_at", "") or ""))
                    else:
                        run.fetch_errors.append({"error": getattr(content, "error_code", "unknown")})
                elif t == "text":
                    texts.append(block.text)
                    for c in getattr(block, "citations", None) or []:
                        url = getattr(c, "url", None)
                        run.citations.append({"url": url, "title": getattr(c, "title", None) or getattr(c, "document_title", None), "cited_text": getattr(c, "cited_text", "")})
            if msg.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": msg.content})
                continue
            self._check(msg)
            break
        run.text = "".join(texts).strip()
        return run

    # ------------------------------------------------------------------------------------
    def structured(self, system: str, prompt: str, model_cls: Type[T], effort: str = "medium", max_tokens: int = 32000) -> T:
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_format=model_cls,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
        self._check(msg)
        parsed = getattr(msg, "parsed_output", None)
        if parsed is None:
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            parsed = model_cls.model_validate_json(text)
        return parsed
