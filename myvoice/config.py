"""Runtime configuration for MY VOICE. Everything is local; settings come from the environment
(or the repository's .env file) and can be overridden per user in the studio's Settings page."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent

try:  # optional: share the repository's .env with ReelForge
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover - python-dotenv is optional
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def total_ram_gb() -> float:
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
    except (AttributeError, ValueError, OSError):  # Windows / unusual platforms
        return 0.0


def default_asr_model() -> str:
    """Whisper size for the read-check. large-v3-turbo is far better on Hindi and Hinglish than
    'small' but needs ~2 GB of RAM and a ~1.6 GB one-time download."""
    explicit = _env("MYVOICE_ASR_MODEL")
    if explicit:
        return explicit
    return "large-v3-turbo" if total_ram_gb() >= 7.5 else "small"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("MYVOICE_DATA_DIR", str(ROOT / "myvoice_data"))).expanduser())
    # Speech recognition used to check that the displayed text was read ("auto" = faster-whisper if installed)
    asr_engine: str = field(default_factory=lambda: _env("MYVOICE_ASR", "auto"))
    asr_model: str = field(default_factory=default_asr_model)
    asr_threads: int = field(default_factory=lambda: int(_env("MYVOICE_ASR_THREADS", str(max(1, (os.cpu_count() or 2) - 1)))))
    max_upload_mb: int = field(default_factory=lambda: int(_env("MYVOICE_MAX_UPLOAD_MB", "300")))
    max_take_seconds: float = field(default_factory=lambda: float(_env("MYVOICE_MAX_TAKE_SECONDS", "600")))
    session_idle_hours: float = field(default_factory=lambda: float(_env("MYVOICE_SESSION_IDLE_HOURS", "2")))
    ffmpeg_bin: str = field(default_factory=lambda: _env("MYVOICE_FFMPEG", shutil.which("ffmpeg") or ""))

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def trash_dir(self) -> Path:
        return self.data_dir / "trash"

    @property
    def exercises_dir(self) -> Path:
        """User-imported / generated exercises (the built-in bank lives in the package)."""
        return self.data_dir / "exercises"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.recordings_dir, self.sessions_dir, self.exports_dir, self.trash_dir,
                  self.exercises_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:  # recordings are personal biometric data: owner-only access on POSIX systems
            os.chmod(self.data_dir, 0o700)
        except OSError:  # pragma: no cover
            pass


settings = Settings()
