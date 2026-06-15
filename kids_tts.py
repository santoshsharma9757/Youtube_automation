"""
kids_tts.py  –  Chintu Stories Channel
=======================================
Hindi TTS wrapper that produces per-scene audio clips.
Uses the existing TextToSpeechEngine but forces the Hindi voice
and produces one audio file per scene.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts

from config import AppConfig
from gtts import gTTS

LOGGER = logging.getLogger(__name__)

# Edge TTS Hindi voice — warm, storytelling style
HINDI_VOICE = "hi-IN-MadhurNeural"
HINDI_VOICE_FEMALE = "hi-IN-SwaraNeural"


class KidsTTSEngine:
    """Synthesizes Hindi voiceover for each scene of a Chintu story."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def synthesize_scene(self, text: str, output_path: Path) -> Path:
        """
        Synthesize one scene's voiceover.
        Returns path to the mp3 file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Try ElevenLabs (if configured)
        if self.config.elevenlabs_api_key and self.config.elevenlabs_voice_id:
            try:
                return self._elevenlabs(text, output_path)
            except Exception as exc:
                LOGGER.warning("ElevenLabs failed for scene TTS, falling back: %s", exc)

        # 2. Try Edge TTS (best free Hindi voice)
        try:
            return self._edge_tts(text, output_path)
        except Exception as exc:
            LOGGER.warning("Edge TTS failed for scene TTS, falling back to gTTS: %s", exc)

        # 3. gTTS fallback
        return self._gtts(text, output_path)

    def synthesize_full_story(
        self,
        scenes: list[dict],
        output_dir: Path,
        base_name: str,
    ) -> dict[int, Path]:
        """
        Synthesize voiceover for all 4 scenes.
        Returns {scene_number: audio_path}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results: dict[int, Path] = {}
        for scene in scenes:
            num  = scene["scene_number"]
            text = scene.get("voiceover_hindi", "").strip()
            if not text:
                LOGGER.warning("No voiceover text for scene %s", num)
                continue
            out = output_dir / f"{base_name}_scene{num}.mp3"
            path = self.synthesize_scene(text, out)
            results[num] = path
        return results

    def synthesize_combined(
        self,
        scenes: list[dict],
        output_path: Path,
    ) -> Path:
        """
        Synthesize all scene voiceovers as one combined audio file.
        Joins them with a tiny pause between scenes.
        """
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent

            combined = AudioSegment.empty()
            pause    = AudioSegment.silent(duration=400)  # 400ms pause between scenes

            import tempfile, os
            with tempfile.TemporaryDirectory() as tmpdir:
                for scene in scenes:
                    num  = scene["scene_number"]
                    text = scene.get("voiceover_hindi", "").strip()
                    if not text:
                        combined += AudioSegment.silent(duration=2000)
                        continue
                    tmp_path = Path(tmpdir) / f"scene{num}.mp3"
                    self.synthesize_scene(text, tmp_path)
                    if tmp_path.exists() and tmp_path.stat().st_size > 0:
                        seg = AudioSegment.from_mp3(str(tmp_path))
                        combined += seg + pause
                    else:
                        combined += AudioSegment.silent(duration=2000)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined.export(str(output_path), format="mp3")
            LOGGER.info("Combined story audio saved: %s (%.1f s)", output_path, len(combined) / 1000)
            return output_path

        except Exception as exc:
            LOGGER.warning("pydub combine failed, doing single TTS pass: %s", exc)
            # Fallback: concatenate all text and synthesize at once
            full_text = " ".join(
                scene.get("voiceover_hindi", "") for scene in scenes if scene.get("voiceover_hindi")
            )
            return self.synthesize_scene(full_text, output_path)

    # ─── Backend implementations ──────────────────────────────────────────────

    def _elevenlabs(self, text: str, output_path: Path) -> Path:
        import requests as _requests
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}"
        resp = _requests.post(
            url,
            headers={"xi-api-key": self.config.elevenlabs_api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=60,
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
        return output_path

    @staticmethod
    def _edge_tts(text: str, output_path: Path) -> Path:
        async def _run() -> None:
            communicate = edge_tts.Communicate(
                text=text,
                voice=HINDI_VOICE,
                rate="+15%",
                pitch="+0Hz",
            )
            await communicate.save(str(output_path))
        asyncio.run(_run())
        return output_path

    @staticmethod
    def _gtts(text: str, output_path: Path) -> Path:
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(str(output_path))
        return output_path
