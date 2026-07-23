"""
tts_engine.py  –  Wonder Stories TV
=====================================

TTS routing strategy:
  video (AI_VIDEO)  → NO TTS  — Video clips already have audio, no TTS needed
  image (IMAGE)     → ElevenLabs FIRST (Raunak — viral Hindi storyteller)
                     → fallback: Edge TTS hi-IN-MadhurNeural (medium-fast pace)
                     → last fallback: gTTS

VOICE SETTINGS (ElevenLabs — tuned for viral Hindi storytelling):
  Stability:   0.35  → Expressive, emotional delivery
  Similarity:  0.85  → Strong voice consistency
  Style:       0.45  → Cinematic dramatic style
  Speed:       1.10  → Medium-fast pace (viral storytelling energy)

Edge TTS fallback voices (medium-fast pace for Hindi narration):
  hi-IN-MadhurNeural — male, warm, fast storytelling pace (primary)
  hi-IN-SwaraNeural  — female, energetic (secondary)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import edge_tts
from gtts import gTTS

from config import AppConfig

LOGGER = logging.getLogger(__name__)

# ─── ElevenLabs Voice Config ───────────────────────────────────────────────────
# Primary: Raunak — viral Hindi storyteller
# Voice ID configured via ELEVENLABS_VOICE_ID in .env
# Fallback: any available Hindi-capable voice

ELEVENLABS_SETTINGS = {
    "stability":          0.35,   # expressive, emotional
    "similarity_boost":   0.85,   # voice consistency
    "style":              0.45,   # cinematic dramatic delivery
    "speed":              1.22,   # slightly faster, snappy pace
    "use_speaker_boost":  True,
}

# ─── Edge TTS Voice Map (free, unlimited fallback) ──────────────────────────────────
EDGE_VOICE_MAP: dict[str, dict[str, str]] = {
    # Balanced for fast but still human-sounding Hindi narration
    "narrator_dramatic":  {"voice": "hi-IN-MadhurNeural", "rate": "+18%", "pitch": "-1Hz"},
    "narrator_suspense":  {"voice": "hi-IN-MadhurNeural", "rate": "+16%", "pitch": "-2Hz"},
    "narrator_female":    {"voice": "hi-IN-SwaraNeural",  "rate": "+18%", "pitch": "+0Hz"},
    "narrator_whisper":   {"voice": "hi-IN-MadhurNeural", "rate": "+12%", "pitch": "-3Hz"},
    "narrator_intense":   {"voice": "hi-IN-MadhurNeural", "rate": "+22%", "pitch": "+0Hz"},
    "narrator_warm":      {"voice": "hi-IN-MadhurNeural", "rate": "+14%", "pitch": "-1Hz"},
    "narrator_devotional": {"voice": "hi-IN-MadhurNeural", "rate": "+14%", "pitch": "-1Hz"},
    "default":            {"voice": "hi-IN-MadhurNeural", "rate": "+16%", "pitch": "-1Hz"},
}


class TTSEngine:
    def __init__(self, config: AppConfig, force_local: bool = False) -> None:
        self.config = config
        self.force_local = force_local
        self._elevenlabs_client = None
        self._el_key = config.elevenlabs_api_key
        self._el_voice_id = config.elevenlabs_voice_id

    # ──────────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def synthesize_scene(
        self,
        text: str,
        output_path: Path,
        voice_hint: str = "narrator_dramatic",
    ) -> Path:
        """
        Synthesize a single scene's voiceover to output_path (.mp3).
        Returns the output_path on success.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not text.strip():
            LOGGER.warning("Empty text for TTS, skipping: %s", output_path)
            return output_path

        # Try ElevenLabs (Raunak) first — unless force_local
        if not self.force_local and self._el_key and self._el_voice_id:
            try:
                self._synthesize_elevenlabs(text, output_path, voice_hint)
                LOGGER.info("TTS [ElevenLabs/Raunak]: %s", output_path.name)
                return output_path
            except Exception as exc:
                LOGGER.warning("ElevenLabs failed, falling back to Edge TTS: %s", exc)

        # Fallback: Edge TTS
        try:
            self._synthesize_edge(text, output_path, voice_hint)
            LOGGER.info("TTS [Edge TTS]: %s", output_path.name)
            return output_path
        except Exception as exc:
            LOGGER.warning("Edge TTS failed, falling back to gTTS: %s", exc)

        # Last resort: gTTS
        try:
            self._synthesize_gtts(text, output_path)
            LOGGER.info("TTS [gTTS]: %s", output_path.name)
            return output_path
        except Exception as exc:
            LOGGER.error("All TTS providers failed: %s", exc)
            raise

    def synthesize_full_script(
        self,
        scenes: list[dict],
        output_dir: Path,
    ) -> list[Path]:
        """
        Synthesize all scene voiceovers and return list of audio paths.
        Each scene gets its own file: scene_1.mp3, scene_2.mp3, etc.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_paths = []
        for scene in scenes:
            num = scene.get("scene_number", 0)
            text = scene.get("voiceover_hindi", "").strip()
            voice_hint = scene.get("voice_hint", "narrator_dramatic")
            out_path = output_dir / f"scene_{num}.mp3"

            if not text:
                LOGGER.info("Scene %s: no voiceover text, skipping TTS", num)
                audio_paths.append(None)
                continue

            try:
                self.synthesize_scene(text, out_path, voice_hint)
                audio_paths.append(out_path)
            except Exception as exc:
                LOGGER.error("TTS failed for scene %s: %s", num, exc)
                audio_paths.append(None)

        return audio_paths

    # ──────────────────────────────────────────────────────────────────────────
    #  PRIVATE METHODS
    # ──────────────────────────────────────────────────────────────────────────

    def _synthesize_elevenlabs(
        self, text: str, output_path: Path, voice_hint: str
    ) -> None:
        """Generate audio using ElevenLabs API (Raunak viral Hindi voice)."""
        try:
            from elevenlabs.client import ElevenLabs
            from elevenlabs import VoiceSettings

            client = ElevenLabs(api_key=self._el_key)

            # Raunak voice ID from config — set in .env as ELEVENLABS_VOICE_ID
            voice_id = self._el_voice_id

            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2",   # best for Hindi
                voice_settings=VoiceSettings(
                    stability=ELEVENLABS_SETTINGS["stability"],
                    similarity_boost=ELEVENLABS_SETTINGS["similarity_boost"],
                    style=ELEVENLABS_SETTINGS["style"],
                    speed=ELEVENLABS_SETTINGS["speed"],           # medium-fast pace
                    use_speaker_boost=ELEVENLABS_SETTINGS["use_speaker_boost"],
                ),
            )

            with open(output_path, "wb") as f:
                for chunk in audio_generator:
                    if chunk:
                        f.write(chunk)

        except ImportError:
            raise RuntimeError("elevenlabs package not installed. Run: pip install elevenlabs")

    def _synthesize_edge(
        self, text: str, output_path: Path, voice_hint: str
    ) -> None:
        """Generate audio using Edge TTS (free, unlimited fallback)."""
        voice_cfg = EDGE_VOICE_MAP.get(voice_hint, EDGE_VOICE_MAP["default"])
        voice = voice_cfg["voice"]
        rate  = voice_cfg["rate"]
        pitch = voice_cfg["pitch"]

        async def _run():
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )
            await communicate.save(str(output_path))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run())
                    future.result(timeout=60)
            else:
                loop.run_until_complete(_run())
        except RuntimeError:
            asyncio.run(_run())

    def _synthesize_gtts(self, text: str, output_path: Path) -> None:
        """Generate audio using gTTS (last resort)."""
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(str(output_path))
