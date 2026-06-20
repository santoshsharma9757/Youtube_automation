"""
kids_tts.py  –  Wonder Stories TV
=======================================

TTS routing strategy:
  veo   (video-to-video) → NO TTS  — Veo clips already have complete audio
  image (short + long)   → ElevenLabs FIRST (premium, human-like)
                           → fallback: Edge TTS (best human-like settings)
                           → last fallback: gTTS

CHARACTER-AWARE VOICE SELECTION:
  Each scene carries a 'voice_hint' field set by the story generator.
  Voice hints → specific ElevenLabs + Edge TTS voices per character:
    narrator_male   → George (ElevenLabs) / MadhurNeural (Edge TTS)
    narrator_female → Sarah (ElevenLabs) / SwaraNeural (Edge TTS)
    mother          → Sarah (ElevenLabs) / SwaraNeural (Edge TTS)
    old_wise        → George (ElevenLabs) / MadhurNeural (slower pace)

ElevenLabs Free quota: 10,000 characters / month
  Short image (~5 scenes × 175 chars) ≈   875 chars → ~11 short image videos/month
  Long  image (~6 scenes × 280 chars) ≈ 1,680 chars → ~5  long  image videos/month
  Mixed (3 short + 1 long)            ≈ 4,305 chars → best monthly balance

Edge TTS fallback voices (tuned for human-like Hindi narration):
  hi-IN-MadhurNeural — male, warm, storytelling pace
  hi-IN-SwaraNeural  — female, soft, emotional storyteller
  Rate: +5% (slightly faster = more energetic, conversational pace)
  Pitch: -1Hz (neutral, avoid robotic highs)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import edge_tts

from config import AppConfig
from gtts import gTTS

LOGGER = logging.getLogger(__name__)

# ─── ElevenLabs Voice Map ─────────────────────────────────────────────────────
# Maps character roles to ElevenLabs voice IDs.
# Default uses the .env ELEVENLABS_VOICE_ID for narrator_male.
# Additional voices can be configured via environment variables.
# George  = JBFqnCBsd6RMkjVDRZzb (Warm, Captivating Storyteller)
# Sarah   = EXAVITQu4vr4xnSDxMaL (Soft, Warm Female Narrator)
ELEVENLABS_VOICE_MAP: dict[str, dict[str, str]] = {
    "narrator_male": {
        "name": "George",
        "desc": "Warm, captivating storyteller",
        # voice_id resolved at runtime from config or env
    },
    "narrator_female": {
        "name": "Sarah",
        "desc": "Soft, warm female narrator",
    },
    "mother": {
        "name": "Sarah",
        "desc": "Caring mother tone",
    },
    "old_wise": {
        "name": "George",
        "desc": "Deep wise elder (slower, lower stability)",
    },
    "default": {
        "name": "George",
        "desc": "Default narrator",
    },
}

# ─── Edge TTS Voice Map (free, unlimited) ─────────────────────────────────────
# Character-matched Hindi voices for Edge TTS fallback.
EDGE_VOICE_MAP: dict[str, dict[str, str]] = {
    "narrator_male":   {"voice": "hi-IN-MadhurNeural", "rate": "+20%",  "pitch": "-1Hz"},
    "narrator_female": {"voice": "hi-IN-SwaraNeural",  "rate": "+20%",  "pitch": "+0Hz"},
    "mother":          {"voice": "hi-IN-SwaraNeural",  "rate": "+15%",  "pitch": "+0Hz"},
    "old_wise":        {"voice": "hi-IN-MadhurNeural", "rate": "+10%",  "pitch": "-3Hz"},
    "default":         {"voice": "hi-IN-MadhurNeural", "rate": "+20%",  "pitch": "-1Hz"},
}

# Legacy constants (kept for backward compatibility)
HINDI_VOICE        = "hi-IN-MadhurNeural"
HINDI_VOICE_FEMALE = "hi-IN-SwaraNeural"

# ElevenLabs credit estimate (1 char ≈ 1 credit)
_ELEVENLABS_MONTHLY_FREE = 10_000  # characters

# ─── ElevenLabs voice settings per character role ─────────────────────────────
# Tuned for warm, energetic narrative storytelling. 
# Lower stability = more dynamic pacing, higher style = more expressive.
_EL_VOICE_SETTINGS: dict[str, dict] = {
    "narrator_male": {
        "stability":         0.35,
        "similarity_boost":  0.90,
        "style":             0.45,
        "use_speaker_boost": True,
    },
    "narrator_female": {
        "stability":         0.35,
        "similarity_boost":  0.90,
        "style":             0.45,
        "use_speaker_boost": True,
    },
    "mother": {
        "stability":         0.40,   # slightly more stable for caring mother tone
        "similarity_boost":  0.90,
        "style":             0.40,
        "use_speaker_boost": True,
    },
    "old_wise": {
        "stability":         0.40,   # deep elder voice, highly expressive
        "similarity_boost":  0.90,
        "style":             0.45,
        "use_speaker_boost": True,
    },
    "default": {
        "stability":         0.35,
        "similarity_boost":  0.90,
        "style":             0.45,
        "use_speaker_boost": True,
    },
}


class KidsTTSEngine:
    """Synthesizes Hindi voiceover for each scene of a Wonder Stories TV story.

    Character-aware: uses voice_hint from story scenes to pick the best
    ElevenLabs or Edge TTS voice per character.
    """

    def __init__(self, config: AppConfig, force_local: bool = False) -> None:
        self.config = config
        self.force_local = force_local  # when True, skip ElevenLabs entirely (use Edge TTS)
        self._el_chars_used: int = 0   # session-level credit tracker
        # Resolve ElevenLabs voice IDs from environment or config
        self._el_voice_ids: dict[str, str] = self._resolve_el_voice_ids()
        if self.force_local:
            LOGGER.info("[TTS] force_local=True — ElevenLabs skipped. Using Edge TTS for all scenes (free).")

    def _resolve_el_voice_ids(self) -> dict[str, str]:
        """Resolve ElevenLabs voice IDs from env vars or config defaults."""
        default_id = self.config.elevenlabs_voice_id or ""
        female_id = os.getenv("ELEVENLABS_VOICE_ID_FEMALE", "")
        return {
            "narrator_male":   default_id,
            "narrator_female": female_id or default_id,
            "mother":          female_id or default_id,
            "old_wise":        default_id,
            "default":         default_id,
        }

    # ─────────────────────────────────────────────────────────────────────────
    #  CHARACTER VOICE DETECTION
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_character_voice(text: str, scene: dict | None = None) -> str:
        """Detect the most appropriate voice character from voiceover text.

        Priority:
          1. Explicit voice_hint in scene dict (set by story generator)
          2. Keyword analysis of voiceover text
          3. Default: narrator_male

        Args:
            text:  The voiceover text (Hindi, Roman script).
            scene: Optional scene dict that may contain 'voice_hint'.
        Returns:
            Voice role string: 'narrator_male', 'narrator_female', 'mother', 'old_wise'.
        """
        # 1. Explicit voice_hint from story generator
        if scene and scene.get("voice_hint"):
            hint = scene["voice_hint"]
            if hint in ELEVENLABS_VOICE_MAP:
                return hint

        # 2. Keyword-based detection from voiceover text
        lower = text.lower()

        # Mother-specific keywords
        mother_kw = [
            "maa ne kaha", "mummy ne kaha", "maa ki awaaz",
            "mummy ki", "maa boli", "mummy boli", "maa ne bola", "mummy ne bola",
            "mother said", "maa ka pyaar", "mummy ne pucha", "maa ne pucha",
        ]
        if any(kw in lower for kw in mother_kw):
            return "mother"

        # Wise elder / guru keywords
        elder_kw = [
            "dadi ne kaha", "nani ne kaha", "budhiya ne",
            "budhaa ne", "guru ne kaha", "baba ne kaha", "dadi ne bola", "nani ne bola",
            "dadi boli", "nani boli", "dadi ne pucha", "nani ne pucha",
            "elder said", "wise", "purani baat",
        ]
        if any(kw in lower for kw in elder_kw):
            return "old_wise"

        # Female narrator keywords (soft, emotional scenes)
        female_kw = [
            "nani ki kahani", "dadi ki kahani",
            "ek purani raat", "pyaar ki baat",
        ]
        if any(kw in lower for kw in female_kw):
            return "narrator_female"

        # 3. Default
        return "narrator_male"

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def synthesize_scene(
        self,
        text: str,
        output_path: Path,
        force_elevenlabs: bool = False,
        voice_hint: str | None = None,
        scene: dict | None = None,
    ) -> Path:
        """
        Synthesize one scene's voiceover with character-aware voice selection.

        Args:
            text:              Hindi text (Roman script) to synthesize.
            output_path:       Where to save the .mp3.
            force_elevenlabs:  (Deprecated) ElevenLabs is now the default primary engine.
            voice_hint:        Explicit voice role override ('narrator_male', 'mother', etc.)
            scene:             Optional scene dict for voice_hint detection.
        Returns:
            Path to the output mp3.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine character voice
        if voice_hint and voice_hint in ELEVENLABS_VOICE_MAP:
            char_voice = voice_hint
        else:
            char_voice = self._detect_character_voice(text, scene)

        LOGGER.info("[TTS] Character voice detected: %s", char_voice)

        # 1. Try ElevenLabs with character-matched voice (skip if force_local)
        el_voice_id = self._el_voice_ids.get(char_voice, self._el_voice_ids.get("default", ""))
        if not self.force_local and self.config.elevenlabs_api_key and el_voice_id:
            try:
                path = self._elevenlabs(text, output_path, voice_id=el_voice_id, role=char_voice)
                self._el_chars_used += len(text)
                voice_name = ELEVENLABS_VOICE_MAP.get(char_voice, {}).get("name", "Unknown")
                LOGGER.info(
                    "[ElevenLabs] scene synthesized | voice: %s (%s) | chars: %s | session total: %s / ~%s free",
                    voice_name, char_voice, len(text), self._el_chars_used, _ELEVENLABS_MONTHLY_FREE,
                )
                return path
            except Exception as exc:
                LOGGER.warning("[ElevenLabs] failed (voice=%s), falling back to Edge TTS: %s", char_voice, exc)

        # 2. Edge TTS with character-matched voice (free, unlimited)
        try:
            return self._edge_tts(text, output_path, role=char_voice)
        except Exception as exc:
            LOGGER.warning("[Edge TTS] failed (voice=%s), falling back to gTTS: %s", char_voice, exc)

        # 3. gTTS last resort (no character awareness, but works)
        return self._gtts(text, output_path)

    def synthesize_story(
        self,
        scenes: list[dict],
        output_dir: Path,
        video_format: str = "short",
        kids_mode: str = "images",
    ) -> dict[int, Path]:
        """
        Synthesize all scenes for a story with character-aware voice switching.

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

        has_el = bool(self.config.elevenlabs_api_key and self._el_voice_ids.get("default"))
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
            # Character-aware TTS: pass scene dict for voice_hint detection
            voice_hint = scene.get("voice_hint")
            path = self.synthesize_scene(
                text, out, force_elevenlabs=True,
                voice_hint=voice_hint, scene=scene,
            )
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
            voice_hint = scene.get("voice_hint")
            path = self.synthesize_scene(text, out, voice_hint=voice_hint, scene=scene)
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
                    voice_hint = scene.get("voice_hint")
                    use_el   = (video_format == "long")
                    self.synthesize_scene(
                        text, tmp_path, force_elevenlabs=use_el,
                        voice_hint=voice_hint, scene=scene,
                    )
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

    def _elevenlabs(
        self,
        text: str,
        output_path: Path,
        voice_id: str | None = None,
        role: str = "default",
    ) -> Path:
        """Synthesize via ElevenLabs API with character-specific voice + settings.

        Args:
            text:        Text to synthesize.
            output_path: Where to save the .mp3.
            voice_id:    ElevenLabs voice ID (overrides config default).
            role:        Character role for voice settings tuning.
        """
        import requests as _requests

        vid = voice_id or self.config.elevenlabs_voice_id
        settings = _EL_VOICE_SETTINGS.get(role, _EL_VOICE_SETTINGS["default"])

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
        resp = _requests.post(
            url,
            headers={
                "xi-api-key":   self.config.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json={
                "text":     text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": settings,
            },
            timeout=90,
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
        return output_path

    @staticmethod
    def _edge_tts(text: str, output_path: Path, role: str = "default") -> Path:
        """
        Edge TTS with character-aware voice selection and SSML prosody tuning.
        Slightly slower pace + natural emphasis = closest to a real storyteller.

        Args:
            text:        Text to synthesize.
            output_path: Where to save the .mp3.
            role:        Character role for voice + rate + pitch selection.
        """
        import re
        # Strip any existing angle-bracket tags from text first (safety)
        safe_text = re.sub(r"<[^>]+>", "", text)

        # Get character-matched voice settings
        voice_cfg = EDGE_VOICE_MAP.get(role, EDGE_VOICE_MAP["default"])
        voice = voice_cfg["voice"]
        rate  = voice_cfg["rate"]
        pitch = voice_cfg["pitch"]

        LOGGER.info("[Edge TTS] Synthesizing with voice=%s (role=%s, rate=%s, pitch=%s)", voice, role, rate, pitch)

        async def _run() -> None:
            communicate = edge_tts.Communicate(
                text=safe_text,
                voice=voice,
                rate=rate,
                pitch=pitch,
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
