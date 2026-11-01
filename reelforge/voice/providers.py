"""Text-to-speech providers behind one interface.

- kokoro      local, free, Apache-2.0 model; exact word timings (default)
- elevenlabs  premium voices; character-level timestamps from the API
- openai      gpt-4o-mini-tts; low cost; timings via alignment
- azure       Azure AI Speech neural voices (free tier available, strong Indian-language voices);
              timings via alignment
"""

from __future__ import annotations

import base64
import io
import subprocess
from html import escape
from typing import Optional

import numpy as np
import requests
import soundfile as sf

from ..config import Settings, settings as default_settings
from ..languages import get_language
from .kokoro_tts import KokoroEngine, SynthResult
from .normalize import Token

ELEVEN_DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George" (premade, warm British male)
OPENAI_VOICES = ["onyx", "ash", "sage", "coral", "nova", "alloy", "echo", "fable", "shimmer", "ballad", "verse"]

TONE_INSTRUCTIONS = {
    "auto": "Narrate like a professional documentary host: natural, conversational, confident; emphasise numbers and key facts; never robotic.",
    "calm": "Narrate calmly and warmly, unhurried, like a nature documentary.",
    "warm": "Narrate warmly and personally, like telling a true story to a friend.",
    "energetic": "Narrate with energy and momentum, like a top educational short-form creator, crisp emphasis on surprising facts.",
    "serious": "Narrate in a serious, measured news-documentary tone.",
}


def _decode_audio(data: bytes) -> tuple[np.ndarray, int]:
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    except Exception:
        # mp3 or other container: decode with ffmpeg
        proc = subprocess.run(
            [default_settings.ffmpeg_bin, "-v", "error", "-i", "pipe:0", "-f", "wav", "-ac", "1", "-ar", "44100", "pipe:1"],
            input=data, capture_output=True, check=True,
        )
        audio, sr = sf.read(io.BytesIO(proc.stdout), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), sr


def _trim_silence(audio: np.ndarray, sr: int, thresh_db: float = -45.0) -> tuple[np.ndarray, float]:
    """Trim leading/trailing silence; returns (audio, seconds removed at the start)."""
    if len(audio) == 0:
        return audio, 0.0
    frame = max(1, int(0.01 * sr))
    n = len(audio) // frame
    if n == 0:
        return audio, 0.0
    rms = np.sqrt((audio[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-12))
    voiced = np.where(db > thresh_db)[0]
    if len(voiced) == 0:
        return audio, 0.0
    a = max(0, voiced[0] * frame - int(0.03 * sr))
    b = min(len(audio), (voiced[-1] + 1) * frame + int(0.06 * sr))
    return audio[a:b], a / sr


class TTSProvider:
    name = "base"
    native_timings = False

    def __init__(self, s: Settings = default_settings):
        self.s = s

    def synthesize(self, tokens: list[Token], voice: str, speed: float, language: str, tone: str = "auto") -> SynthResult:
        raise NotImplementedError


class KokoroProvider(TTSProvider):
    name = "kokoro"
    native_timings = True

    def synthesize(self, tokens, voice, speed, language, tone="auto"):
        lang = get_language(language)
        if not lang.kokoro_lang:
            raise RuntimeError(f"Kokoro has no {lang.name} voice. Choose Azure, ElevenLabs or OpenAI for this language.")
        if voice not in lang.kokoro_voices and ":" not in voice and lang.kokoro_voices:
            voice = lang.kokoro_voices[0]
        return KokoroEngine.get(self.s).synthesize(tokens, voice, speed, lang.kokoro_lang)


class ElevenLabsProvider(TTSProvider):
    name = "elevenlabs"
    native_timings = True

    def synthesize(self, tokens, voice, speed, language, tone="auto"):
        if not self.s.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")
        words = [w for t in tokens for w in t.spoken]
        text = " ".join(words)
        voice_id = voice if voice and len(voice) >= 16 else ELEVEN_DEFAULT_VOICE
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.s.elevenlabs_api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "language_code": language,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "speed": float(np.clip(speed, 0.7, 1.2))},
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        audio, sr = _decode_audio(base64.b64decode(data["audio_base64"]))
        al = data.get("alignment") or data.get("normalized_alignment") or {}
        chars = al.get("characters") or []
        starts = al.get("character_start_times_seconds") or []
        ends = al.get("character_end_times_seconds") or []
        times: list[tuple[float, float]] = []
        cur_s: Optional[float] = None
        cur_e = 0.0
        for c, a, b in zip(chars, starts, ends):
            if c.isspace():
                if cur_s is not None:
                    times.append((cur_s, cur_e))
                    cur_s = None
            else:
                if cur_s is None:
                    cur_s = a
                cur_e = b
        if cur_s is not None:
            times.append((cur_s, cur_e))
        if len(times) != len(words):
            times = None  # let the aligner handle it
        return SynthResult(audio, sr, times, "elevenlabs-alignment" if times else "none")


class OpenAIProvider(TTSProvider):
    name = "openai"

    def synthesize(self, tokens, voice, speed, language, tone="auto"):
        if not self.s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        text = " ".join(w for t in tokens for w in t.spoken)
        r = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.s.openai_api_key}"},
            json={
                "model": "gpt-4o-mini-tts",
                "voice": voice if voice in OPENAI_VOICES else "onyx",
                "input": text,
                "instructions": TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["auto"]),
                "response_format": "wav",
                "speed": float(np.clip(speed, 0.8, 1.25)),
            },
            timeout=120,
        )
        r.raise_for_status()
        audio, sr = _decode_audio(r.content)
        audio, _ = _trim_silence(audio, sr)
        return SynthResult(audio, sr, None, "none")


class AzureProvider(TTSProvider):
    name = "azure"

    def synthesize(self, tokens, voice, speed, language, tone="auto"):
        if not self.s.azure_speech_key:
            raise RuntimeError("AZURE_SPEECH_KEY is not set")
        lang = get_language(language)
        voice = voice if "Neural" in (voice or "") else (lang.azure_voices[0] if lang.azure_voices else "en-IN-NeerjaNeural")
        locale = "-".join(voice.split("-")[:2])
        text = escape(" ".join(w for t in tokens for w in t.spoken))
        rate = f"{int(round((speed - 1.0) * 100)):+d}%"
        ssml = (
            f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{locale}'>"
            f"<voice name='{voice}'><prosody rate='{rate}'>{text}</prosody></voice></speak>"
        )
        r = requests.post(
            f"https://{self.s.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": self.s.azure_speech_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm",
                "User-Agent": "ReelForge",
            },
            data=ssml.encode("utf-8"),
            timeout=120,
        )
        r.raise_for_status()
        audio, sr = _decode_audio(r.content)
        audio, _ = _trim_silence(audio, sr)
        return SynthResult(audio, sr, None, "none")


PROVIDERS = {p.name: p for p in (KokoroProvider, ElevenLabsProvider, OpenAIProvider, AzureProvider)}


def get_provider(name: str, s: Settings = default_settings) -> TTSProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"unknown TTS provider {name!r}; choose one of {sorted(PROVIDERS)}")
    return cls(s)
