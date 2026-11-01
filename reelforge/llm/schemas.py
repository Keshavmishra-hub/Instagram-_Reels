"""Structured-output schemas for Claude. Kept flat and explicit so they validate strictly."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- research extraction
class XEvidence(BaseModel):
    url: str = Field(description="URL of a page that was actually fetched and read")
    quote: str = Field(description="Verbatim sentence(s) copied exactly from that page that support the claim")


class XClaim(BaseModel):
    statement: str = Field(description="One self-contained factual statement in plain language")
    category: Literal["statistic", "date", "event", "person", "place", "definition", "quote", "process", "other"]
    certainty: Literal["established", "estimate", "disputed", "opinion", "uncertain"]
    as_of: Optional[str] = Field(default=None, description="Date/year the figure refers to, for time-sensitive claims")
    caveats: str = Field(default="", description="Context needed so the claim is not misleading")
    evidence: list[XEvidence]


class XSource(BaseModel):
    url: str
    title: str
    publisher: str
    published: Optional[str] = None
    tier: Literal["government", "intergovernmental", "academic", "company_official", "news", "reference", "industry", "ngo", "other"]
    primary: bool = Field(description="True if this organisation is the original publisher of the information it supports")
    notes: str = ""


class XResearch(BaseModel):
    summary: str
    angles: list[str] = Field(description="Story angles / hooks that are fully supported by the claims")
    uncertainties: list[str] = Field(description="Disputed, outdated or uncertain points the script must handle carefully")
    limitations: list[str]
    sources: list[XSource]
    claims: list[XClaim]
    enough_reliable_information: bool
    sufficiency_reason: str


# ---------------------------------------------------------------- script
class XBeat(BaseModel):
    section: Literal["hook", "context", "story", "payoff", "ending"]
    text: str = Field(description="Narration sentence exactly as it should be spoken and subtitled")
    claim_ids: list[str] = Field(description="IDs of verified claims this sentence relies on; empty only for non-factual lines")
    emphasis: list[str] = Field(description="1-3 key words or numbers from the sentence to highlight on screen")
    on_screen_text: Optional[str] = Field(default=None, description="Optional short headline (max 7 words) for a typography scene")


class XScript(BaseModel):
    title: str = Field(description="Short, accurate reel title (max 8 words), no clickbait")
    hook_type: str
    beats: list[XBeat]
    cta_question: str = Field(description="A natural, relevant question to end on (also used as the final line)")
    integrity_notes: str = Field(description="How estimates, disputes or caveats were handled")


# ---------------------------------------------------------------- storyboard
class XOverlay(BaseModel):
    kind: Literal["stat", "label", "highlight"]
    text: str
    at_word: Optional[int] = Field(default=None, description="0-based index of the word in the scene narration when it appears")
    position: Literal["top", "center", "bottom"] = "top"


class XVisual(BaseModel):
    kind: Literal["footage", "photo", "map", "stat", "chart", "timeline", "kinetic", "comparison", "icon", "quote", "title"]
    purpose: str
    queries: list[str] = Field(description="2-4 concrete stock-footage search queries (for footage/photo, else empty)")
    prefer: Literal["video", "photo", "any"] = "any"
    params_json: str = Field(description="JSON object with the parameters for this visual kind (see instructions)")
    authenticity: Literal["documentary", "representative", "generated_graphic", "ai_generated"]


class XScene(BaseModel):
    beat_ids: list[str]
    visual: XVisual
    background_queries: list[str] = Field(default_factory=list, description="Optional stock queries for a dimmed backdrop behind a graphic")
    overlays: list[XOverlay] = Field(default_factory=list)
    transition: Literal["cut", "fade", "slide_up", "slide_left", "zoom", "whip", "wipe"]
    subtitle_position: Literal["lower", "upper", "center"]
    sfx: Optional[Literal["whoosh", "impact", "riser", "pop"]] = None


class XCover(BaseModel):
    headline: str = Field(description="3-6 word cover headline, accurate")
    highlight: str
    kicker: str
    beat_id: str


class XStoryboard(BaseModel):
    scenes: list[XScene]
    music_mood: Literal["curious", "uplifting", "tense", "epic", "calm"]
    cover: XCover


# ---------------------------------------------------------------- publishing
class XPackage(BaseModel):
    title: str
    caption: str = Field(description="Instagram caption: hook line, 2-4 short paragraphs of value, natural CTA. No hashtags inside.")
    hashtags: list[str] = Field(description="At most 5 relevant hashtags without spaces")
    pinned_comment: str
    cta: str
    alt_text: str = Field(description="Accessibility description of the video (max 300 chars)")
