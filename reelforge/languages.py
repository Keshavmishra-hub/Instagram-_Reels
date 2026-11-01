"""Supported narration/subtitle languages and their per-provider voice defaults."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Language:
    code: str  # ISO 639-1
    name: str
    script: str  # latin | deva | beng | taml | telu | gujr | knda | mlym | guru
    espeak: str  # espeak-ng voice for phonemisation / alignment
    kokoro_lang: str = ""  # kokoro-onnx language code ('' = not supported locally)
    kokoro_voices: list[str] = field(default_factory=list)
    azure_voices: list[str] = field(default_factory=list)
    openai_ok: bool = True
    elevenlabs_ok: bool = True
    spellcheck: str = ""  # pyspellchecker language code if available
    whisper: str = ""  # whisper language code


LANGUAGES: dict[str, Language] = {
    "en": Language(
        "en", "English", "latin", "en-us", "en-us",
        ["af_heart", "af_bella", "am_michael", "am_fenrir", "bf_emma", "bm_george", "am_puck", "af_nicole", "bm_fable", "af_aoede"],
        ["en-IN-NeerjaNeural", "en-IN-PrabhatNeural", "en-US-AndrewNeural", "en-US-AvaNeural", "en-GB-RyanNeural"],
        spellcheck="en", whisper="en",
    ),
    "hi": Language(
        "hi", "Hindi", "deva", "hi", "hi",
        ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
        ["hi-IN-SwaraNeural", "hi-IN-MadhurNeural", "hi-IN-AaravNeural", "hi-IN-AnanyaNeural"],
        whisper="hi",
    ),
    "mr": Language("mr", "Marathi", "deva", "mr", azure_voices=["mr-IN-AarohiNeural", "mr-IN-ManoharNeural"], whisper="mr"),
    "bn": Language("bn", "Bengali", "beng", "bn", azure_voices=["bn-IN-TanishaaNeural", "bn-IN-BashkarNeural"], whisper="bn"),
    "ta": Language("ta", "Tamil", "taml", "ta", azure_voices=["ta-IN-PallaviNeural", "ta-IN-ValluvarNeural"], whisper="ta"),
    "te": Language("te", "Telugu", "telu", "te", azure_voices=["te-IN-ShrutiNeural", "te-IN-MohanNeural"], whisper="te"),
    "gu": Language("gu", "Gujarati", "gujr", "gu", azure_voices=["gu-IN-DhwaniNeural", "gu-IN-NiranjanNeural"], whisper="gu"),
    "kn": Language("kn", "Kannada", "knda", "kn", azure_voices=["kn-IN-SapnaNeural", "kn-IN-GaganNeural"], whisper="kn"),
    "ml": Language("ml", "Malayalam", "mlym", "ml", azure_voices=["ml-IN-SobhanaNeural", "ml-IN-MidhunNeural"], whisper="ml"),
    "pa": Language("pa", "Punjabi", "guru", "pa", azure_voices=["pa-IN-OjasNeural", "pa-IN-VaaniNeural"], whisper="pa"),
    "es": Language("es", "Spanish", "latin", "es", "es", ["ef_dora", "em_alex"], ["es-ES-ElviraNeural", "es-MX-JorgeNeural"], spellcheck="es", whisper="es"),
    "fr": Language("fr", "French", "latin", "fr-fr", "fr-fr", ["ff_siwis"], ["fr-FR-DeniseNeural", "fr-FR-HenriNeural"], spellcheck="fr", whisper="fr"),
    "pt": Language("pt", "Portuguese", "latin", "pt-br", "pt-br", ["pf_dora", "pm_alex"], ["pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"], spellcheck="pt", whisper="pt"),
    "it": Language("it", "Italian", "latin", "it", "it", ["if_sara", "im_nicola"], ["it-IT-ElsaNeural", "it-IT-DiegoNeural"], spellcheck="it", whisper="it"),
    "de": Language("de", "German", "latin", "de", azure_voices=["de-DE-KatjaNeural", "de-DE-ConradNeural"], spellcheck="de", whisper="de"),
}

# Font family stacks used by the renderer, keyed by script.
FONT_STACKS: dict[str, dict[str, str]] = {
    "latin": {"display": "Anton", "body": "Inter", "subtitle": "Montserrat"},
    "deva": {"display": "Teko", "body": "Noto Sans Devanagari", "subtitle": "Poppins"},
    "beng": {"display": "Noto Sans Bengali", "body": "Noto Sans Bengali", "subtitle": "Noto Sans Bengali"},
    "taml": {"display": "Noto Sans Tamil", "body": "Noto Sans Tamil", "subtitle": "Noto Sans Tamil"},
    "telu": {"display": "Noto Sans Telugu", "body": "Noto Sans Telugu", "subtitle": "Noto Sans Telugu"},
    "gujr": {"display": "Noto Sans Gujarati", "body": "Noto Sans Gujarati", "subtitle": "Noto Sans Gujarati"},
    "knda": {"display": "Noto Sans Kannada", "body": "Noto Sans Kannada", "subtitle": "Noto Sans Kannada"},
    "mlym": {"display": "Noto Sans Malayalam", "body": "Noto Sans Malayalam", "subtitle": "Noto Sans Malayalam"},
    "guru": {"display": "Noto Sans Gurmukhi", "body": "Noto Sans Gurmukhi", "subtitle": "Noto Sans Gurmukhi"},
}


def get_language(code: str) -> Language:
    return LANGUAGES.get(code, LANGUAGES["en"])


def language_options() -> list[dict]:
    return [
        {
            "code": l.code,
            "name": l.name,
            "kokoro": bool(l.kokoro_lang),
            "kokoro_voices": l.kokoro_voices,
            "azure_voices": l.azure_voices,
        }
        for l in LANGUAGES.values()
    ]


# Human-friendly labels for the local Kokoro voices (grades from the Kokoro model card).
KOKORO_VOICE_LABELS = {
    "af_heart": "Heart - US female, warm (best quality)",
    "af_bella": "Bella - US female, bright",
    "af_nicole": "Nicole - US female, soft/intimate",
    "af_aoede": "Aoede - US female, calm",
    "am_michael": "Michael - US male, steady",
    "am_fenrir": "Fenrir - US male, deep",
    "am_puck": "Puck - US male, lively",
    "bf_emma": "Emma - UK female, polished",
    "bm_george": "George - UK male, documentary",
    "bm_fable": "Fable - UK male, storyteller",
    "hf_alpha": "Alpha - Hindi female",
    "hf_beta": "Beta - Hindi female",
    "hm_omega": "Omega - Hindi male",
    "hm_psi": "Psi - Hindi male",
    "ef_dora": "Dora - Spanish female",
    "em_alex": "Alex - Spanish male",
    "ff_siwis": "Siwis - French female",
    "pf_dora": "Dora - Portuguese female",
    "pm_alex": "Alex - Portuguese male",
    "if_sara": "Sara - Italian female",
    "im_nicola": "Nicola - Italian male",
}
