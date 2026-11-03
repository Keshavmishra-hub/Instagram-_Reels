"""Data model: exercises (what to say), takes (recordings + analysis), sessions and the speaker profile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------------
# Controlled vocabularies
# --------------------------------------------------------------------------------------------

# Dataset organisation (folders under recordings/)
CATEGORIES: dict[str, str] = {
    "voice_identity": "Voice identity",
    "english_phonetics": "English phonetics",
    "hindi_phonetics": "Hindi phonetics",
    "hinglish": "Hinglish",
    "conversational": "Conversational speech",
    "emotional": "Emotional speech",
    "professional_narration": "Professional narration",
    "cinematic_narration": "Cinematic narration",
    "documentary_narration": "Documentary narration",
    "numbers_special": "Numbers and special vocabulary",
    "consistency": "Voice consistency tests",
    "room_tone": "Room tone (noise reference)",
    "consent": "Consent & ownership statement",
}

MODULES: dict[str, dict[str, str]] = {
    "S": {"title": "Session setup", "summary": "Microphone check, room tone and your consent statement."},
    "A": {"title": "Basic Voice Identity", "summary": "Your natural voice: pace, loudness, breath, questions, statements and exclamations."},
    "B": {"title": "Phonetic Coverage", "summary": "Every English and Hindi speech sound: vowels, consonants, aspiration, retroflex, nasals, clusters, minimal pairs."},
    "C": {"title": "English Language", "summary": "Everyday to academic English, storytelling, technical explanation and long-form narration."},
    "D": {"title": "Hindi Language", "summary": "Everyday, formal, news, documentary and emotional Hindi in natural Indian usage."},
    "E": {"title": "Hinglish", "summary": "Natural Hindi–English code-switching for Indian Instagram content."},
    "F": {"title": "Emotional Voice", "summary": "Seventeen emotional deliveries, each with a situation to act from."},
    "G": {"title": "Instagram & Cinematic Narration", "summary": "Hooks, cinematic intros, documentary voice-overs, explainers, promos and powerful endings."},
    "H": {"title": "Natural Conversation", "summary": "Prepared conversational scripts and spontaneous speech from a displayed topic."},
    "I": {"title": "Numbers & Special Vocabulary", "summary": "Numbers, dates, time, currency, percentages, maths, science, business and farm terms, acronyms."},
    "J": {"title": "Voice Consistency", "summary": "Anchor sentences repeated across sessions to measure natural variation."},
}

EMOTIONS: dict[str, str] = {
    "neutral": "Neutral",
    "happiness": "Happiness",
    "excitement": "Excitement",
    "confidence": "Confidence",
    "authority": "Authority",
    "seriousness": "Seriousness",
    "curiosity": "Curiosity",
    "surprise": "Surprise",
    "sadness": "Sadness",
    "empathy": "Empathy",
    "motivation": "Motivation",
    "determination": "Determination",
    "suspense": "Suspense",
    "humour": "Humour",
    "calmness": "Calmness",
    "urgency": "Urgency",
    "dramatic": "Dramatic storytelling",
    "inspirational": "Inspirational narration",
}

STYLES: dict[str, str] = {
    "neutral": "Neutral reading",
    "conversational": "Conversational",
    "formal": "Formal",
    "professional": "Professional",
    "business": "Business",
    "academic": "Academic",
    "technical": "Technical explanation",
    "storytelling": "Storytelling",
    "narration": "Long-form narration",
    "news": "News",
    "documentary": "Documentary voice-over",
    "cinematic_intro": "Cinematic introduction",
    "movie_narration": "Movie-style narration",
    "reel_hook": "Instagram Reel hook",
    "motivational": "Motivational",
    "historical": "Historical storytelling",
    "business_explainer": "Business explainer",
    "educational": "Educational",
    "travel": "Travel",
    "agriculture": "Agriculture",
    "personal_branding": "Personal branding",
    "promotional": "Promotional",
    "dramatic_opening": "Dramatic opening",
    "suspense": "Suspense-building",
    "conclusion": "Powerful conclusion",
    "interview": "Interview answer",
    "opinion": "Giving an opinion",
    "instructional": "Giving instructions",
    "spontaneous": "Spontaneous speech",
    "analysis": "Voice analysis task",
}

LANGUAGES: dict[str, str] = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish", "none": "No speech"}

Kind = Literal["sentence", "paragraph", "word_list", "dialogue", "prompt", "sustained", "glide", "silence", "clap"]
Lang = Literal["en", "hi", "hinglish", "none"]
Pace = Literal["slow", "normal", "fast"]
Volume = Literal["normal", "soft", "loud", "whisper"]
TakeStatus = Literal["pending", "approved", "rejected"]


class Exercise(BaseModel):
    id: str
    module: str
    section: str
    section_title: str = ""
    category: str
    kind: Kind = "sentence"
    lang: Lang = "en"
    text: str = ""  # what is displayed (and read)
    spoken: str = ""  # expected spoken words when they differ from `text` (numbers, symbols)
    roman: str = ""  # optional hand-written romanisation (otherwise generated)
    instruction: str = ""  # one-line direction shown above the text
    context: str = ""  # situation to act from (emotional / narration exercises)
    cue: str = ""  # what the other person just said (conversation exercises)
    hints: list[str] = Field(default_factory=list)  # talking points for spontaneous prompts
    emotion: str = "neutral"
    style: str = "neutral"
    pace: Pace = "normal"
    volume: Volume = "normal"
    focus: list[str] = Field(default_factory=list)  # phonetic / linguistic focus labels
    core: bool = True  # part of the core curriculum (otherwise extended pool used by the adaptive planner)
    train: bool = True  # include in training exports by default
    readcheck: bool = True  # compare speech recognition output with the text
    min_sec: Optional[float] = None
    max_sec: Optional[float] = None
    auto_stop: Optional[float] = None  # seconds of silence that end the take; 0 = off; None = default for kind
    repeat: Literal["", "per_session"] = ""
    order: int = 0  # position in the bank (stable ordering)
    source: str = "bank"  # bank | generated | imported


class Issue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    hint: str = ""
    at: Optional[float] = None  # seconds into the take, when the issue is localised
    penalty: float = 0.0


class Quality(BaseModel):
    score: int = 0
    grade: str = ""  # Excellent | Good | Fair | Poor
    verdict: Literal["good", "usable", "rerecord"] = "usable"
    summary: str = ""
    issues: list[Issue] = Field(default_factory=list)


class AudioInfo(BaseModel):
    file: str  # path relative to the data directory
    sample_rate: int
    channels: int = 1
    subtype: str = "PCM_24"
    duration: float
    bytes: int = 0
    sha256: str = ""


class CaptureInfo(BaseModel):
    device_label: str = ""
    device_id: str = ""  # browser-scoped, hashed device id
    user_agent: str = ""
    context_sample_rate: int = 0
    constraints_applied: dict[str, Any] = Field(default_factory=dict)
    preroll_sec: float = 0.0
    auto_stopped: bool = False
    paused_at: list[float] = Field(default_factory=list)  # splice points (seconds) where the take was paused
    track_events: list[dict[str, Any]] = Field(default_factory=list)  # mute/unmute/ended reported by the browser
    client_version: str = ""


class ReadMatch(BaseModel):
    coverage: float = 0.0  # fraction of expected words found in the recognised speech
    precision: float = 0.0  # fraction of recognised words that match expected words
    missing: list[int] = Field(default_factory=list)  # indexes into expected_words
    expected_words: list[str] = Field(default_factory=list)
    extra_words: list[str] = Field(default_factory=list)
    verdict: Literal["read", "partial", "not_read", "unchecked"] = "unchecked"


class ASRResult(BaseModel):
    status: Literal["pending", "running", "done", "unavailable", "skipped", "error"] = "pending"
    engine: str = ""
    model: str = ""
    language: str = ""
    text: str = ""
    words: list[dict[str, Any]] = Field(default_factory=list)
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None
    seconds: float = 0.0
    error: str = ""
    match: Optional[ReadMatch] = None


class Take(BaseModel):
    id: str
    exercise_id: str
    session_id: str
    attempt: int = 1
    created_at: str = Field(default_factory=now_iso)
    status: TakeStatus = "pending"
    status_reason: str = ""
    status_at: str = ""
    # snapshot of the exercise at recording time
    module: str = ""
    section: str = ""
    category: str = ""
    kind: str = "sentence"
    lang: str = "en"
    emotion: str = "neutral"
    style: str = "neutral"
    pace: str = "normal"
    volume: str = "normal"
    text: str = ""
    spoken: str = ""
    train: bool = True
    # what was actually said (used for training exports)
    transcript: str = ""
    transcript_source: Literal["prompt", "asr", "user", "none"] = "prompt"
    transcript_reviewed: bool = False
    audio: AudioInfo
    capture: CaptureInfo = Field(default_factory=CaptureInfo)
    analysis: dict[str, Any] = Field(default_factory=dict)
    quality: Quality = Field(default_factory=Quality)
    asr: ASRResult = Field(default_factory=ASRResult)
    notes: str = ""
    trashed: bool = False


class Session(BaseModel):
    id: str
    started_at: str = Field(default_factory=now_iso)
    last_active_at: str = Field(default_factory=now_iso)
    ended_at: str = ""
    device_label: str = ""
    device_id: str = ""
    user_agent: str = ""
    sample_rate: int = 0
    constraints_applied: dict[str, Any] = Field(default_factory=dict)
    voice_state: Literal["", "fresh", "normal", "tired", "hoarse"] = ""
    note: str = ""
    room_tone_take: str = ""
    noise_floor_db: Optional[float] = None
    room_t60: Optional[float] = None  # reverberation time from the warm-up hand clap
    skipped: list[str] = Field(default_factory=list)  # exercises skipped in this session
    paused_seconds: float = 0.0
    mode: str = "adaptive"  # adaptive | module:<X>


class Preferences(BaseModel):
    text_scale: float = 1.0
    show_roman: bool = True
    preroll_ms: int = 500
    auto_stop: bool = True
    auto_stop_sec: float = 1.8  # base silence for sentences; paragraphs and prompts scale it up
    auto_advance: bool = True  # move to the next exercise after approving
    theme: Literal["system", "dark", "light"] = "system"
    warmup: bool = True  # room tone + anchor sentences at the start of each session


class Profile(BaseModel):
    speaker_name: str = ""
    speaker_id: str = "me"
    hindi_forms: Literal["", "m", "f"] = ""  # first-person Hindi verb agreement: कर रहा हूँ (m) / कर रही हूँ (f)
    created_at: str = Field(default_factory=now_iso)
    consent_given: bool = False
    consent_at: str = ""
    clone_backend: str = "undecided"
    asr_model: str = ""  # overrides the default Whisper size when set
    preferences: Preferences = Field(default_factory=Preferences)
