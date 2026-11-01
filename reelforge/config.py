"""Runtime configuration. Every secret comes from the environment (or a local .env file)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional: load a local .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _find_chrome() -> str:
    """Locate a Chrome/Chromium binary for Remotion. Empty string = let Remotion download its own."""
    explicit = _env("REELFORGE_CHROME")
    if explicit:
        return explicit
    candidates = sorted(Path("/opt/pw-browsers").glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    if candidates:
        return str(candidates[-1])
    return ""


@dataclass
class Settings:
    root: Path = ROOT
    projects_dir: Path = field(default_factory=lambda: Path(_env("REELFORGE_PROJECTS_DIR", str(ROOT / "projects"))))
    models_dir: Path = field(default_factory=lambda: Path(_env("REELFORGE_MODELS_DIR", str(ROOT / "models"))))
    renderer_dir: Path = ROOT / "renderer"
    brands_dir: Path = ROOT / "brands"
    data_dir: Path = ROOT / "data"

    # --- LLM (Claude) -------------------------------------------------------------
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("REELFORGE_MODEL", "claude-opus-5-5"))
    web_search_tool: str = field(default_factory=lambda: _env("REELFORGE_WEB_SEARCH_TOOL", "web_search_20260209"))
    web_fetch_tool: str = field(default_factory=lambda: _env("REELFORGE_WEB_FETCH_TOOL", "web_fetch_20260209"))
    research_max_searches: int = field(default_factory=lambda: int(_env("REELFORGE_MAX_SEARCHES", "10")))
    research_max_fetches: int = field(default_factory=lambda: int(_env("REELFORGE_MAX_FETCHES", "14")))

    # --- Optional search APIs (used when no Claude key, or as extra discovery) ----
    brave_api_key: str = field(default_factory=lambda: _env("BRAVE_API_KEY"))
    tavily_api_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY"))

    # --- Stock media ------------------------------------------------------------------
    pexels_api_key: str = field(default_factory=lambda: _env("PEXELS_API_KEY"))
    pixabay_api_key: str = field(default_factory=lambda: _env("PIXABAY_API_KEY"))
    enable_wikimedia: bool = field(default_factory=lambda: _env("REELFORGE_WIKIMEDIA", "1") != "0")
    enable_nasa: bool = field(default_factory=lambda: _env("REELFORGE_NASA", "1") != "0")

    # --- Text to speech -----------------------------------------------------------------
    elevenlabs_api_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    azure_speech_key: str = field(default_factory=lambda: _env("AZURE_SPEECH_KEY"))
    azure_speech_region: str = field(default_factory=lambda: _env("AZURE_SPEECH_REGION", "centralindia"))

    # --- Rendering ------------------------------------------------------------------------
    chrome_executable: str = field(default_factory=_find_chrome)
    render_concurrency: int = field(default_factory=lambda: int(_env("REELFORGE_RENDER_CONCURRENCY", str(max(1, (os.cpu_count() or 2) - 0)))))
    node_bin: str = field(default_factory=lambda: _env("REELFORGE_NODE", shutil.which("node") or "node"))
    ffmpeg_bin: str = field(default_factory=lambda: _env("REELFORGE_FFMPEG", shutil.which("ffmpeg") or "ffmpeg"))
    ffprobe_bin: str = field(default_factory=lambda: _env("REELFORGE_FFPROBE", shutil.which("ffprobe") or "ffprobe"))

    # --- Networking -------------------------------------------------------------------------
    user_agent: str = field(default_factory=lambda: _env(
        "REELFORGE_USER_AGENT",
        "ReelForge/1.0 (research-verification bot; +https://github.com/) python-requests",
    ))
    http_timeout: float = field(default_factory=lambda: float(_env("REELFORGE_HTTP_TIMEOUT", "25")))

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key) or bool(_env("ANTHROPIC_AUTH_TOKEN"))

    def ensure_dirs(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def capabilities(self) -> dict:
        """What is configured, for the UI and the docs. Never returns secret values."""
        from .voice.kokoro_tts import kokoro_available
        from .voice.asr import asr_available

        return {
            "llm": {"configured": self.has_llm, "model": self.llm_model},
            "search": {
                "claude_web_search": self.has_llm,
                "brave": bool(self.brave_api_key),
                "tavily": bool(self.tavily_api_key),
                "wikipedia": True,
            },
            "stock": {
                "pexels": bool(self.pexels_api_key),
                "pixabay": bool(self.pixabay_api_key),
                "wikimedia": self.enable_wikimedia,
                "nasa": self.enable_nasa,
            },
            "tts": {
                "kokoro": kokoro_available(self),
                "elevenlabs": bool(self.elevenlabs_api_key),
                "openai": bool(self.openai_api_key),
                "azure": bool(self.azure_speech_key),
            },
            "asr": asr_available(self),
            "renderer": {
                "node": bool(shutil.which(self.node_bin) or Path(self.node_bin).exists()),
                "installed": (self.renderer_dir / "node_modules" / "remotion").exists(),
                "chrome": self.chrome_executable or "remotion-managed",
            },
            "ffmpeg": bool(shutil.which(self.ffmpeg_bin) or Path(self.ffmpeg_bin).exists()),
        }


settings = Settings()
