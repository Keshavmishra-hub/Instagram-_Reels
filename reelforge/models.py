"""Data model shared by every stage. Everything is persisted as JSON inside the project folder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


StyleKey = Literal[
    "documentary",
    "explainer",
    "mystery",
    "historical",
    "business",
    "agriculture",
    "science",
    "current_affairs",
    "facts",
    "human_stories",
]

# ---------------------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------------------


class NarrationSettings(BaseModel):
    provider: str = "kokoro"  # kokoro | elevenlabs | openai | azure
    voice: str = "af_heart"
    speed: float = 1.0  # 0.8 .. 1.25
    tone: str = "auto"  # auto | calm | warm | energetic | serious


class ProjectSettings(BaseModel):
    topic: str
    language: str = "en"
    duration: int = 45  # target seconds (30-90)
    style: StyleKey = "documentary"
    narration: NarrationSettings = Field(default_factory=NarrationSettings)
    brand: str = "default"
    music_mood: str = "auto"  # auto | curious | uplifting | tense | epic | calm | none
    music_level_db: float = -12.0  # gain applied to the (loudness-normalised) music bed before ducking
    audience: str = ""
    angle: str = ""  # optional editorial instruction from the user


StageName = Literal["research", "script", "storyboard", "voice", "assets", "render", "qc", "package"]


class StageStatus(BaseModel):
    status: Literal["pending", "running", "done", "failed", "needs_review"] = "pending"
    updated_at: Optional[str] = None
    message: str = ""


class Project(BaseModel):
    id: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    settings: ProjectSettings
    stages: dict[str, StageStatus] = Field(default_factory=dict)
    complete: bool = False
    complete_reason: str = ""


# ---------------------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------------------

SourceTier = Literal[
    "government",  # ministries, statistics offices, regulators, parliament, courts
    "intergovernmental",  # UN agencies, World Bank, IMF, OECD ...
    "academic",  # peer-reviewed journals, universities, research institutes
    "company_official",  # annual reports, filings, official company pages
    "news",  # established news organisations
    "reference",  # encyclopaedias, museum/archives pages
    "industry",  # industry bodies, credible market research
    "ngo",  # established NGOs / foundations
    "other",
]

AccessMethod = Literal["app_fetch", "anthropic_web_fetch", "claude_code_webfetch", "manual"]


class Source(BaseModel):
    id: str  # S1, S2, ...
    url: str
    final_url: str = ""
    title: str = ""
    publisher: str = ""
    domain: str = ""
    tier: SourceTier = "other"
    primary: bool = False  # the originating organisation of the information it supports
    published: Optional[str] = None
    accessed_at: str = Field(default_factory=now_iso)
    access_method: AccessMethod = "app_fetch"
    http_status: Optional[int] = None
    snapshot_file: Optional[str] = None  # relative to project dir
    snapshot_sha256: Optional[str] = None
    snapshot_kind: Literal["raw_text", "agent_excerpt", "none"] = "none"
    last_check: Optional[str] = None  # last live re-check result: ok | unreachable | dead | blocked
    notes: str = ""


class Evidence(BaseModel):
    source_id: str
    quote: str = ""  # verbatim supporting text copied from the source (rendered automatically for data evidence)
    verification: Literal["exact", "fuzzy", "agent_attested", "not_found", "unchecked"] = "unchecked"
    match_score: float = 0.0
    # Tabular evidence (CSV datasets): the app recomputes the value from the downloaded file.
    #   {"type": "value", "filters": {"country": "India", "year": "2025"}, "column": "solar_electricity"}
    #   {"type": "rank", "group": {"year": "2025"}, "column": "solar_electricity", "entity_column": "country",
    #    "entity": "India", "exclude_if": {"iso_code": ["", "OWID_*"]}, "top": 3}
    data: Optional[dict[str, Any]] = None


class Claim(BaseModel):
    id: str  # C1, C2, ...
    statement: str
    category: Literal["statistic", "date", "event", "person", "place", "definition", "quote", "process", "other"] = "other"
    certainty: Literal["established", "estimate", "disputed", "opinion", "uncertain"] = "established"
    status: Literal["verified", "single_source", "conflicting", "unverified", "excluded"] = "unverified"
    evidence: list[Evidence] = Field(default_factory=list)
    as_of: Optional[str] = None
    caveats: str = ""
    numbers: list[str] = Field(default_factory=list)
    use_in_script: bool = True
    notes: str = ""


class Sufficiency(BaseModel):
    enough: bool = False
    reason: str = ""


class Research(BaseModel):
    topic: str
    language: str = "en"
    created_at: str = Field(default_factory=now_iso)
    method: str = ""
    summary: str = ""
    angles: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    sufficiency: Sufficiency = Field(default_factory=Sufficiency)
    approved: bool = False
    approved_at: Optional[str] = None

    def source(self, sid: str) -> Optional[Source]:
        return next((s for s in self.sources if s.id == sid), None)

    def claim(self, cid: str) -> Optional[Claim]:
        return next((c for c in self.claims if c.id == cid), None)


# ---------------------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------------------

Section = Literal["hook", "context", "story", "payoff", "ending"]


class Beat(BaseModel):
    id: str  # B1, B2, ...
    section: Section
    text: str  # narration exactly as it should appear in subtitles
    claim_ids: list[str] = Field(default_factory=list)
    emphasis: list[str] = Field(default_factory=list)  # words/phrases to highlight
    on_screen_text: Optional[str] = None  # short headline for kinetic text scenes
    spoken: Optional[str] = None  # optional pronunciation override sent to TTS instead of `text`


class ScriptIssue(BaseModel):
    beat_id: Optional[str] = None
    severity: Literal["error", "warning", "info"] = "warning"
    code: str
    message: str


class Script(BaseModel):
    title: str
    hook_type: str = ""
    style: str = "documentary"
    language: str = "en"
    beats: list[Beat] = Field(default_factory=list)
    cta_question: str = ""
    approved: bool = False
    approved_at: Optional[str] = None
    version: int = 1
    issues: list[ScriptIssue] = Field(default_factory=list)
    written_by: str = ""

    def full_text(self) -> str:
        return " ".join(b.text.strip() for b in self.beats)

    def beat(self, bid: str) -> Optional[Beat]:
        return next((b for b in self.beats if b.id == bid), None)


# ---------------------------------------------------------------------------------------
# Storyboard
# ---------------------------------------------------------------------------------------

VisualKind = Literal[
    "footage", "photo", "map", "stat", "chart", "timeline", "kinetic", "comparison", "icon", "quote", "title"
]
Authenticity = Literal["documentary", "representative", "generated_graphic", "ai_generated"]
Transition = Literal["cut", "fade", "slide_up", "slide_left", "zoom", "whip", "wipe"]


class Visual(BaseModel):
    kind: VisualKind
    purpose: str = ""  # why this visual serves the sentence
    queries: list[str] = Field(default_factory=list)  # stock search queries (footage/photo)
    prefer: Literal["video", "photo", "any"] = "any"
    asset_id: Optional[str] = None
    candidate_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)  # kind-specific parameters
    authenticity: Authenticity = "generated_graphic"


class Overlay(BaseModel):
    kind: Literal["stat", "label", "highlight"] = "label"
    text: str
    at_word: Optional[int] = None  # index into the scene's narration words; None = scene start
    position: Literal["top", "center", "bottom"] = "top"


class Scene(BaseModel):
    id: str  # SC1, ...
    beat_ids: list[str]
    visual: Visual
    background: Optional[Visual] = None
    overlays: list[Overlay] = Field(default_factory=list)
    transition: Transition = "fade"
    subtitle_position: Literal["lower", "upper", "center"] = "lower"
    source_ids: list[str] = Field(default_factory=list)
    sfx: Optional[Literal["whoosh", "impact", "riser", "pop"]] = None
    notes: str = ""


class CoverSpec(BaseModel):
    headline: str
    highlight: str = ""  # word(s) of the headline to colour
    kicker: str = ""  # small line above the headline
    scene_id: Optional[str] = None


class Storyboard(BaseModel):
    scenes: list[Scene] = Field(default_factory=list)
    music_mood: str = "curious"
    cover: Optional[CoverSpec] = None
    version: int = 1
    planned_by: str = ""

    def scene(self, sid: str) -> Optional[Scene]:
        return next((s for s in self.scenes if s.id == sid), None)


# ---------------------------------------------------------------------------------------
# Timeline (after voice-over)
# ---------------------------------------------------------------------------------------


class Word(BaseModel):
    text: str
    start: float
    end: float
    beat_id: str
    index: int  # index of the word inside its beat
    emphasis: bool = False


class BeatTiming(BaseModel):
    beat_id: str
    start: float
    end: float
    audio_file: str


class SubtitleCue(BaseModel):
    start: float
    end: float
    word_indices: list[int]  # indices into Timeline.words
    text: str


class SceneTiming(BaseModel):
    scene_id: str
    start: float
    end: float


class Timeline(BaseModel):
    duration: float
    narration_file: str
    sample_rate: int = 48000
    provider: str = ""
    voice: str = ""
    alignment: str = ""  # how word timings were obtained
    beats: list[BeatTiming] = Field(default_factory=list)
    words: list[Word] = Field(default_factory=list)
    cues: list[SubtitleCue] = Field(default_factory=list)
    scenes: list[SceneTiming] = Field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------------------


class Asset(BaseModel):
    id: str
    kind: Literal["video", "image"]
    provider: str  # pexels | pixabay | wikimedia | nasa | local | generated
    provider_id: str = ""
    page_url: str = ""
    download_url: str = ""
    file: str = ""  # relative to project dir
    width: int = 0
    height: int = 0
    duration: float = 0.0
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    author_url: str = ""
    license: str = ""
    license_url: str = ""
    attribution_required: bool = False
    attribution: str = ""
    authenticity: Authenticity = "representative"
    query: str = ""
    relevance: float = 0.0


class AssetLibrary(BaseModel):
    assets: list[Asset] = Field(default_factory=list)

    def get(self, aid: Optional[str]) -> Optional[Asset]:
        if not aid:
            return None
        return next((a for a in self.assets if a.id == aid), None)


# ---------------------------------------------------------------------------------------
# QC + publishing
# ---------------------------------------------------------------------------------------


class QCCheck(BaseModel):
    id: str
    name: str
    severity: Literal["critical", "major", "minor"]
    status: Literal["pass", "warn", "fail", "skipped"]
    details: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class QCReport(BaseModel):
    created_at: str = Field(default_factory=now_iso)
    video_file: str = ""
    checks: list[QCCheck] = Field(default_factory=list)
    passed: bool = False
    summary: str = ""


class InstagramPackage(BaseModel):
    title: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    pinned_comment: str = ""
    cta: str = ""
    cover_headline: str = ""
    alt_text: str = ""
    sources_text: str = ""
    credits_text: str = ""
