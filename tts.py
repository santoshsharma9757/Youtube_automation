from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts
import requests
from gtts import gTTS

from config import AppConfig


LOGGER = logging.getLogger(__name__)


class TextToSpeechEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def synthesize(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        voice_profile = self._detect_voice_profile(text)

        if self.config.elevenlabs_api_key and self.config.elevenlabs_voice_id:
            try:
                return self._synthesize_elevenlabs(text, output_path)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("ElevenLabs failed, trying Edge TTS fallback: %s", exc)

        try:
            return self._synthesize_edge_tts(text, output_path, voice_profile)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Edge TTS failed, falling back to gTTS: %s", exc)

        return self._synthesize_gtts(text, output_path, voice_profile)

    def _synthesize_elevenlabs(self, text: str, output_path: Path) -> Path:
        LOGGER.info("Synthesizing speech with ElevenLabs")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}"
        response = requests.post(
            url,
            headers={
                "xi-api-key": self.config.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.75,
                },
            },
            timeout=60,
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return output_path

    @staticmethod
    def _synthesize_edge_tts(text: str, output_path: Path, voice_profile: str) -> Path:
        LOGGER.info("Synthesizing speech with Edge TTS fallback")

        async def _run() -> None:
            voice = "hi-IN-SwaraNeural" if voice_profile == "hindi" else "en-IN-PrabhatNeural"
            rate = "+2%" if voice_profile == "hindi" else "+8%"
            pitch = "+0Hz" if voice_profile == "hindi" else "-1Hz"
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await communicate.save(str(output_path))

        asyncio.run(_run())
        return output_path

    @staticmethod
    def _synthesize_gtts(text: str, output_path: Path, voice_profile: str) -> Path:
        LOGGER.info("Synthesizing speech with gTTS fallback")
        lang = "hi" if voice_profile == "hindi" else "en"
        tts = gTTS(text=text, lang=lang)
        tts.save(str(output_path))
        return output_path

    @staticmethod
    def _detect_voice_profile(text: str) -> str:
        devanagari_present = any(ord(char) > 127 for char in text)
        if devanagari_present:
            return "hindi"
        return "english"
