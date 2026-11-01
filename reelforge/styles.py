"""The ten storytelling styles. Each one shapes the script prompt, pacing, music and visual defaults."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    description: str
    hook_patterns: list[str]
    voice_direction: str
    music_mood: str
    pace: float  # TTS speed multiplier suggestion
    visual_bias: list[str]  # preferred visual kinds, in order
    structure_notes: str
    cta_examples: list[str] = field(default_factory=list)


STYLES: dict[str, Style] = {
    "documentary": Style(
        key="documentary",
        name="Documentary",
        description="Measured, cinematic, evidence-led storytelling with a clear narrative arc.",
        hook_patterns=["a striking verified fact framed as a scene", "a 'this place/thing exists' reveal", "a consequence before its cause"],
        voice_direction="calm authority, deliberate pauses before key facts",
        music_mood="curious",
        pace=0.98,
        visual_bias=["footage", "photo", "map", "stat", "timeline"],
        structure_notes="Open on the most cinematic verified fact; build context; let the story unfold chronologically; end on the significance.",
        cta_examples=["What should the world protect next?", "Did you know about this before today?"],
    ),
    "explainer": Style(
        key="explainer",
        name="Explainer",
        description="Answers one clear question step by step, like a smart friend explaining.",
        hook_patterns=["a common question people get wrong", "a surprising 'why' question", "a simple analogy"],
        voice_direction="clear, friendly, confident; slightly quicker pace",
        music_mood="uplifting",
        pace=1.04,
        visual_bias=["kinetic", "chart", "icon", "comparison", "footage"],
        structure_notes="Pose the question; give the minimum context; explain in 2-4 steps; deliver the answer as the payoff.",
        cta_examples=["What should we explain next?", "Which part surprised you most?"],
    ),
    "mystery": Style(
        key="mystery",
        name="Mystery & curiosity",
        description="Builds an open loop and resolves it at the payoff. Curiosity, never deception.",
        hook_patterns=["an unexplained-sounding fact that is genuinely true", "a question the viewer can't answer yet", "a hidden-in-plain-sight reveal"],
        voice_direction="intriguing, slightly lower energy, pauses before reveals",
        music_mood="tense",
        pace=0.97,
        visual_bias=["footage", "map", "kinetic", "photo", "stat"],
        structure_notes="Open a loop in the hook; add clues in order; resolve the loop with a verified answer. Never imply mystery where the facts are settled.",
        cta_examples=["Had you heard of this?", "What other mystery should we solve?"],
    ),
    "historical": Style(
        key="historical",
        name="Historical storytelling",
        description="Brings a historical moment to life with dates, people and consequences.",
        hook_patterns=["a date and a turning point", "a person facing a decision", "then-vs-now contrast"],
        voice_direction="storyteller cadence, warm and grave where needed",
        music_mood="epic",
        pace=0.97,
        visual_bias=["photo", "timeline", "map", "quote", "footage"],
        structure_notes="Anchor every event with a verified date; show cause and effect; connect to today in the payoff.",
        cta_examples=["What historical moment should we cover next?"],
    ),
    "business": Style(
        key="business",
        name="Business & finance",
        description="Numbers-driven story about companies, markets or money, with context for every figure.",
        hook_patterns=["a big number with an unexpected comparison", "a company decision that changed a market", "where the money actually goes"],
        voice_direction="sharp, confident, crisp emphasis on numbers",
        music_mood="uplifting",
        pace=1.05,
        visual_bias=["stat", "chart", "comparison", "footage", "kinetic"],
        structure_notes="Every number gets a unit, a year and a source; explain the mechanism; end with the takeaway for the viewer.",
        cta_examples=["Would you invest in this? Tell us why.", "Which company should we break down next?"],
    ),
    "agriculture": Style(
        key="agriculture",
        name="Agriculture & rural economy",
        description="Practical, respectful stories about farming, food systems and rural livelihoods.",
        hook_patterns=["a farm-gate vs consumer price contrast", "a crop or practice with a surprising impact", "a rural success backed by data"],
        voice_direction="grounded, respectful, practical; avoid sounding urban or condescending",
        music_mood="calm",
        pace=1.0,
        visual_bias=["footage", "chart", "map", "stat", "photo"],
        structure_notes="Use official agricultural statistics where possible; explain what it means for farmers; mention seasons, regions and units clearly.",
        cta_examples=["Farmers, have you seen this in your region?", "Which crop should we cover next?"],
    ),
    "science": Style(
        key="science",
        name="Science & technology",
        description="Explains a discovery or technology accurately, separating evidence from hype.",
        hook_patterns=["a counter-intuitive scientific fact", "a scale comparison", "a 'how does this even work' question"],
        voice_direction="enthusiastic but precise; slow down on technical terms",
        music_mood="curious",
        pace=1.0,
        visual_bias=["footage", "icon", "chart", "kinetic", "stat"],
        structure_notes="State what is known vs. hypothesised; cite the study or agency; use one strong analogy.",
        cta_examples=["What science question should we answer next?"],
    ),
    "current_affairs": Style(
        key="current_affairs",
        name="Current affairs",
        description="Neutral, dated, multi-source summary of a recent development.",
        hook_patterns=["what happened, in one line", "why this matters to you", "the number at the centre of the story"],
        voice_direction="neutral newsreader tone, measured",
        music_mood="tense",
        pace=1.02,
        visual_bias=["footage", "map", "stat", "timeline", "kinetic"],
        structure_notes="Date everything; attribute claims to who made them; present major perspectives fairly; flag what is still unconfirmed.",
        cta_examples=["What's your take? Keep it respectful in the comments."],
    ),
    "facts": Style(
        key="facts",
        name="Interesting facts",
        description="One topic, a fast sequence of verified, surprising facts with a strong final one.",
        hook_patterns=["the most surprising fact first", "a number nobody expects", "'you use this every day but...'"],
        voice_direction="energetic and playful, quick pace",
        music_mood="uplifting",
        pace=1.07,
        visual_bias=["footage", "stat", "kinetic", "icon", "photo"],
        structure_notes="Order facts from surprising to most surprising; each fact gets its own visual; save the best for the payoff.",
        cta_examples=["Which fact surprised you most?", "Save this for your next quiz."],
    ),
    "human_stories": Style(
        key="human_stories",
        name="Human stories & real-world events",
        description="Centres a real person or community, told with dignity and verified details.",
        hook_patterns=["a person in a moment of decision", "an outcome before the journey", "a small act with a big result"],
        voice_direction="warm, empathetic, unhurried",
        music_mood="calm",
        pace=0.97,
        visual_bias=["footage", "photo", "quote", "map", "timeline"],
        structure_notes="Use only verified biographical details and real quotes with attribution; avoid melodrama; respect privacy.",
        cta_examples=["Whose story should we tell next?"],
    ),
}


def get_style(key: str) -> Style:
    return STYLES.get(key, STYLES["documentary"])


def style_options() -> list[dict]:
    return [{"key": s.key, "name": s.name, "description": s.description} for s in STYLES.values()]
