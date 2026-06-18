"""
kids_tts.py  –  Chintu Stories Channel
=======================================

TTS routing strategy:
  veo   (video-to-video) → NO TTS  — Veo clips already have complete audio
  image (short + long)   → ElevenLabs FIRST (premium, human-like)
                           → fallback: Edge TTS (best human-like settings)
                           → last fallback: gTTS

ElevenLabs Free quota: 10,000 characters / month
  Short image (~5 scenes × 175 chars) ≈   875 chars → ~11 short image videos/month
  Long  image (~6 scenes × 280 chars) ≈ 1,680 chars → ~5  long  image videos/month
  Mixed (3 short + 1 long)            ≈ 4,305 chars → best monthly balance

Edge TTS fallback voice (tuned for human-like Hindi narration):
  hi-IN-MadhurNeural — male, warm, storytelling pace
  Rate: -5% (slightly slower = more natural, emotional)
  Pitch: +0Hz (neutral, avoid robotic highs)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts

from config import AppConfig
from gtts import gTTS

LOGGER = logging.getLogger(__name__)

# Edge TTS Hindi voices (free, unlimited)
HINDI_VOICE        = "hi-IN-MadhurNeural"   # male, warm narrator
HINDI_VOICE_FEMALE = "hi-IN-SwaraNeural"    # female, soft storyteller

# ElevenLabs credit estimate (1 char ≈ 1 credit)
_ELEVENLABS_MONTHLY_FREE = 10_000  # characters


class KidsTTSEngine:
    """Synthesizes Hindi voiceover for each scene of a Chintu story."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._el_chars_used: int = 0   # session-level credit tracker

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def synthesize_scene(
        self,
        text: str,
        output_path: Path,
        force_elevenlabs: bool = False,
    ) -> Path:
        """
        Synthesize one scene's voiceover.

        Args:
            text:              Hindi text (Roman script) to synthesize.
            output_path:       Where to save the .mp3.
            force_elevenlabs:  Pass True to force ElevenLabs regardless of format
                               (normally set automatically by synthesize_story).
        Returns:
            Path to the output mp3.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if force_elevenlabs and self.config.elevenlabs_api_key and self.config.elevenlabs_voice_id:
            try:
                path = self._elevenlabs(text, output_path)
                self._el_chars_used += len(text)
                LOGGER.info(
                    "[ElevenLabs] scene synthesized | chars: %s | session total: %s / ~%s free",
                    len(text), self._el_chars_used, _ELEVENLABS_MONTHLY_FREE,
                )
                return path
            except Exception as exc:
                LOGGER.warning("ElevenLabs failed, falling back to Edge TTS: %s", exc)

        # Edge TTS (free, unlimited) → gTTS fallback
        try:
            return self._edge_tts(text, output_path)
        except Exception as exc:
            LOGGER.warning("Edge TTS failed, falling back to gTTS: %s", exc)
        return self._gtts(text, output_path)

    def synthesize_story(
        self,
        scenes: list[dict],
        output_dir: Path,
        video_format: str = "short",
        kids_mode: str = "images",
    ) -> dict[int, Path]:
        """
        Synthesize all scenes for a story.

        Routing:
          veo mode    → returns {} immediately (Veo clips have own audio)
          image mode  → ElevenLabs FIRST → fallback: Edge TTS → last: gTTS

        Returns {scene_number: audio_path}
        """
        # Veo clips are complete videos — they already have audio. Skip TTS.
        if kids_mode == "veo":
            LOGGER.info("[TTS] Veo mode → skipping TTS (Veo clips have own audio).")
            return {}

        output_dir.mkdir(parents=True, exist_ok=True)

        has_el = bool(self.config.elevenlabs_api_key and self.config.elevenlabs_voice_id)
        total_chars = sum(len(s.get("voiceover_hindi", "")) for s in scenes)
        remaining   = _ELEVENLABS_MONTHLY_FREE - self._el_chars_used

        if has_el:
            LOGGER.info(
                "[ElevenLabs] Image video (%s, %s scenes): ~%s chars needed | "
                "~%s remaining this session | free quota ~%s chars/month",
                video_format, len(scenes), total_chars, remaining, _ELEVENLABS_MONTHLY_FREE,
            )
            if total_chars > remaining:
                LOGGER.warning(
                    "[ElevenLabs] Session quota may be exhausted (%s chars needed, %s left). "
                    "Will auto-fall back to Edge TTS per scene if API rejects.",
                    total_chars, remaining,
                )
        else:
            LOGGER.warning(
                "[TTS] ElevenLabs not configured (no API key / voice ID). "
                "Using Edge TTS fallback for all scenes."
            )

        results: dict[int, Path] = {}
        for scene in scenes:
            num  = scene["scene_number"]
            text = scene.get("voiceover_hindi", "").strip()
            if not text:
                LOGGER.warning("No voiceover text for scene %s", num)
                continue
            out  = output_dir / f"scene_{num}.mp3"
            # ElevenLabs is first priority for ALL image modes
            path = self.synthesize_scene(text, out, force_elevenlabs=True)
            results[num] = path
        return results

    # Legacy alias kept for backward compatibility
    def synthesize_full_story(
        self,
        scenes: list[dict],
        output_dir: Path,
        base_name: str,
    ) -> dict[int, Path]:
        results: dict[int, Path] = {}
        for scene in scenes:
            num  = scene["scene_number"]
            text = scene.get("voiceover_hindi", "").strip()
            if not text:
                continue
            out  = output_dir / f"{base_name}_scene{num}.mp3"
            path = self.synthesize_scene(text, out)
            results[num] = path
        return results

    def synthesize_combined(
        self,
        scenes: list[dict],
        output_path: Path,
        video_format: str = "short",
    ) -> Path:
        """Synthesize all scenes and combine into one audio file."""
        try:
            from pydub import AudioSegment

            combined = AudioSegment.empty()
            pause    = AudioSegment.silent(duration=400)  # 400ms between scenes

            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                for scene in scenes:
                    num  = scene["scene_number"]
                    text = scene.get("voiceover_hindi", "").strip()
                    if not text:
                        combined += AudioSegment.silent(duration=2000)
                        continue
                    tmp_path = Path(tmpdir) / f"scene{num}.mp3"
                    use_el   = (video_format == "long")
                    self.synthesize_scene(text, tmp_path, force_elevenlabs=use_el)
                    if tmp_path.exists() and tmp_path.stat().st_size > 0:
                        seg = AudioSegment.from_mp3(str(tmp_path))
                        combined += seg + pause
                    else:
                        combined += AudioSegment.silent(duration=2000)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined.export(str(output_path), format="mp3")
            LOGGER.info("Combined story audio saved: %s (%.1fs)", output_path, len(combined) / 1000)
            return output_path

        except Exception as exc:
            LOGGER.warning("pydub combine failed, single TTS pass: %s", exc)
            full_text = " ".join(
                s.get("voiceover_hindi", "") for s in scenes if s.get("voiceover_hindi")
            )
            return self.synthesize_scene(full_text, output_path)

    # ─── Backend implementations ──────────────────────────────────────────────

    def _elevenlabs(self, text: str, output_path: Path) -> Path:
        # Voice: George (JBFqnCBsd6RMkjVDRZzb) — Warm, Captivating Storyteller
        # Settings tuned for warm narrative storytelling:
        #   stability        0.45 → more natural variation (less robotic, more human)
        #   similarity_boost 0.82 → stays close to George's warm character
        #   style            0.40 → expressive storytelling without overdoing it
        #   use_speaker_boost     → cleaner, fuller audio output
        import requests as _requests
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.elevenlabs_voice_id}"
        resp = _requests.post(
            url,
            headers={
                "xi-api-key":   self.config.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json={
                "text":     text,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability":         0.45,
                    "similarity_boost":  0.82,
                    "style":             0.40,
                    "use_speaker_boost": True,
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
        return output_path

    @staticmethod
    def _edge_tts(text: str, output_path: Path) -> Path:
        """
        Edge TTS with SSML prosody tuned for warm, human-like Hindi narration.
        Slightly slower pace + natural emphasis = closest to a real storyteller.
        """
        import re
        # Strip any existing angle-bracket tags from text first (safety)
        safe_text = re.sub(r"<[^>]+>", "", text)

        async def _run() -> None:
            communicate = edge_tts.Communicate(
                text=safe_text,
                voice=HINDI_VOICE,
                rate="-5%",
                pitch="-1Hz",
            )
            await communicate.save(str(output_path))

        asyncio.run(_run())
        return output_path

    @staticmethod
    def _gtts(text: str, output_path: Path) -> Path:
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(str(output_path))
        return output_path

    # ─── Utility ──────────────────────────────────────────────────────────────

    def estimate_credits(self, scenes: list[dict]) -> dict:
        """Returns credit estimate for a story. Call before generating to check quota."""
        total_chars = sum(len(s.get("voiceover_hindi", "")) for s in scenes)
        remaining   = max(0, _ELEVENLABS_MONTHLY_FREE - self._el_chars_used)
        videos_left = remaining // max(total_chars, 1)
        return {
            "chars_this_video":     total_chars,
            "session_chars_used":   self._el_chars_used,
            "approx_remaining":     remaining,
            "approx_videos_left":   videos_left,
            "monthly_free_quota":   _ELEVENLABS_MONTHLY_FREE,
        }
