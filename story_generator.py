"""
story_generator.py  –  Wonder Stories TV
=========================================
Generates structured JSON story plans for each episode.

Pipeline Priority:
  1. Generate a COMPLETE Hindi voiceover script (full scene-by-scene narration)
  2. Derive visual scene descriptions from the script
  3. Scene images: cinematic/realistic (no 3D/Pixar/Ghibli)

Formats & Durations:
  short + image : 5-7 scenes × 7-8s   = ~35-55s  — YouTube Shorts / Reels
  short + video : 4-5 scenes × 9-10s  = ~36-50s  — YouTube Shorts / Reels
  long  + image : 10-14 scenes × 12-15s = ~2-3.5min — YouTube long-form
  long  + video : 8-10  scenes × 15-20s = ~2-3.3min — YouTube long-form

Visual Styles (cinematic, realistic — NOT Pixar/Ghibli):
  horror_stories, dark_facts  → Dark moody cinematic, shadows, tension
  mystery_stories, suspense   → Noir atmosphere, fog, dramatic lighting
  crime_stories, thriller     → Gritty realistic, urban, high contrast
  psychological               → Surreal dreamlike, emotional close-ups
  shocking_facts, real_life   → Documentary photography style
  karma_stories, moral_stories → Warm cinematic, emotional storytelling
"""
from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass

from config import AppConfig
from story_idea_generator import StoryIdea
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)

# ─── Visual Style Presets ─────────────────────────────────────────────────────

STYLE_MAP: dict[str, str] = {
    "horror_stories": (
        "Dark cinematic photography, moody dramatic lighting, deep shadows, "
        "atmospheric fog, cinematic color grading (teal and orange), "
        "high contrast, eerie and unsettling composition, "
        "photorealistic, 8K quality, dramatic storytelling visual"
    ),
    "dark_facts": (
        "Dark dramatic documentary photography, stark high contrast, "
        "deep shadows with selective lighting, cinematic color grade, "
        "photorealistic, intense atmospheric composition, "
        "historical or investigative feel, 8K quality"
    ),
    "mystery_stories": (
        "Noir cinematic style, dramatic chiaroscuro lighting, atmospheric fog, "
        "mysterious and suspenseful composition, desaturated tones with accent colors, "
        "photorealistic photography, cinematic wide angle, 8K quality, "
        "shadow play, detective atmosphere"
    ),
    "suspense_stories": (
        "Cinematic suspense photography, tight dramatic framing, "
        "shallow depth of field, moody blue-grey tones, "
        "tension-filled composition, photorealistic, "
        "motion blur hints, 8K quality, edge-of-seat atmosphere"
    ),
    "crime_stories": (
        "Gritty realistic urban photography, high contrast dramatic lighting, "
        "cinematic film noir inspired, authentic street-level compositions, "
        "photorealistic, raw and intense visual storytelling, "
        "crime thriller color grade, 8K quality"
    ),
    "thriller_stories": (
        "High-stakes cinematic thriller photography, dynamic action-ready composition, "
        "dramatic overhead or Dutch angle shots, intense color grading, "
        "photorealistic, urgent and tense atmosphere, "
        "adrenaline-filled visual storytelling, 8K quality"
    ),
    "psychological": (
        "Surreal cinematic photography, double exposure or dreamlike composition, "
        "emotional close-up portraits, distorted perspective elements, "
        "muted desaturated palette with vivid accent, photorealistic, "
        "mind-bending visual metaphors, 8K quality"
    ),
    "shocking_facts": (
        "Documentary photography style, impactful photojournalism composition, "
        "dramatic natural lighting, authentic realistic visuals, "
        "bold and striking imagery, photorealistic, "
        "award-winning documentary feel, 8K quality"
    ),
    "real_life_facts": (
        "Cinematic documentary photography, warm authentic lighting, "
        "real human emotion captured, storytelling composition, "
        "photorealistic, inspiring and powerful visual narrative, "
        "golden hour or dramatic studio lighting, 8K quality"
    ),
    "karma_stories": (
        "Warm cinematic storytelling photography, emotional resonant composition, "
        "dramatic lighting with warm tones, poetic visual storytelling, "
        "photorealistic, justice and emotion conveyed through imagery, "
        "cinematic color grade, 8K quality"
    ),
    "moral_stories": (
        "Cinematic emotional storytelling photography, warm and human composition, "
        "dramatic lighting that emphasizes emotion, authentic Indian settings, "
        "photorealistic, heartwarming yet impactful visuals, "
        "award-winning short film aesthetic, 8K quality"
    ),
}

DEFAULT_STYLE = (
    "Cinematic photography, dramatic lighting, photorealistic, "
    "8K quality, professional storytelling composition"
)

# ─── Format Configuration ─────────────────────────────────────────────────────

_FORMAT_BASE: dict[str, dict] = {
    # Short image-to-video: 8-10 scenes × 4-5s ≈ 35-50s (max 45s target) for higher engagement
    "short_img": {
        "num_scenes_min": 8,
        "num_scenes_max": 10,
        "scene_dur_min":  4,
        "scene_dur_max":  5,
        "word_hint":      "10-15",   # words per scene voiceover (~4-5s at fast pace)
        "gen_type":       "IMAGE_FOR_ZOOM",
        "max_total_dur":  45,
    },
    # Short video-to-video: 4-5 scenes × 9-10s ≈ 36-50s (max 45s target)
    "short_veo": {
        "num_scenes_min": 4,
        "num_scenes_max": 5,
        "scene_dur_min":  9,
        "scene_dur_max":  10,
        "word_hint":      "25-35",
        "gen_type":       "AI_VIDEO",
        "max_total_dur":  45,
    },
    # Long image-to-video: 18-22 scenes × 6-8s ≈ 2-3 min (max 3 min) for higher engagement
    "long_img": {
        "num_scenes_min": 18,
        "num_scenes_max": 22,
        "scene_dur_min":  6,
        "scene_dur_max":  8,
        "word_hint":      "18-24",
        "gen_type":       "IMAGE_FOR_ZOOM",
        "max_total_dur":  180,
    },
    # Long video-to-video: 8-10 scenes × 15-20s ≈ 2-3.3 min (max 3 min)
    "long_veo": {
        "num_scenes_min": 8,
        "num_scenes_max": 10,
        "scene_dur_min":  15,
        "scene_dur_max":  20,
        "word_hint":      "55-80",
        "gen_type":       "AI_VIDEO",
        "max_total_dur":  180,
    },
}

FORMAT_CONFIG = _FORMAT_BASE  # kept for external imports


def _resolve_config(fmt: str, mode: str) -> dict:
    """Return format config for (fmt, mode) combination.
    mode: 'image' | 'video'
    """
    if fmt == "short":
        key = "short_img" if mode == "image" else "short_veo"
    else:
        key = "long_img" if mode == "image" else "long_veo"
    return dict(_FORMAT_BASE[key])


def _get_art_style(category: str) -> str:
    return STYLE_MAP.get(category, DEFAULT_STYLE)


@dataclass(slots=True)
class StoryPlan:
    story_metadata: dict
    scenes: list[dict]
    audio_effects_config: dict
    raw_json: str


class StoryGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    # ──────────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def generate_story(self, idea: StoryIdea, mode: str = "image") -> StoryPlan:
        fmt = idea.video_type if idea.video_type in ("short", "long") else "short"
        cfg = _resolve_config(fmt, mode)
        art_style = _get_art_style(getattr(idea, "category", "mystery_stories"))
        is_long = fmt == "long"

        LOGGER.info(
            "Generating story '%s' (fmt=%s, mode=%s, scenes=%s-%s, dur=%s-%ss/scene)",
            idea.title, fmt, mode,
            cfg["num_scenes_min"], cfg["num_scenes_max"],
            cfg["scene_dur_min"], cfg["scene_dur_max"],
        )

        schema = self._schema_example(idea, cfg, art_style)
        prompt = self._build_prompt(idea, fmt, cfg, art_style, schema, is_long)

        def _fallback():
            return self._template_fallback(idea, cfg, art_style)

        raw_payload, provider = build_json_with_fallback(self.llm, prompt, _fallback, "story-plan")
        LOGGER.info("Story generation provider: %s", provider)

        plan_dict = self._validate_and_repair(raw_payload, idea, cfg, art_style)

        return StoryPlan(
            story_metadata=plan_dict["story_metadata"],
            scenes=plan_dict["scenes"],
            audio_effects_config=plan_dict.get("audio_effects_config", self._default_sfx(idea)),
            raw_json=json.dumps(plan_dict, ensure_ascii=False, indent=2),
        )

    # ──────────────────────────────────────────────────────────────────────────
    #  PROMPT BUILDER
    # ──────────────────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        idea: StoryIdea,
        fmt: str,
        cfg: dict,
        art_style: str,
        schema: str,
        is_long: bool,
    ) -> str:
        category = getattr(idea, "category", "mystery_stories")
        hook = getattr(idea, "hook_hindi", "") or getattr(idea, "hook", "")
        twist = getattr(idea, "twist", "")
        conflict = getattr(idea, "core_conflict", "")
        moral = getattr(idea, "moral", "")
        moral_hindi = getattr(idea, "moral_hindi", "")
        audience_hook = getattr(idea, "audience_hook", "")

        duration_hint = (
            f"Target: {cfg['max_total_dur']} seconds max total. "
            f"Choose {cfg['num_scenes_min']}–{cfg['num_scenes_max']} scenes, "
            f"each {cfg['scene_dur_min']}–{cfg['scene_dur_max']}s. "
            f"Each voiceover: {cfg['word_hint']} words."
        )

        viral_tone = {
            "horror_stories":   "Atmospheric horror. Build dread slowly. Reveal at the end.",
            "mystery_stories":  "Classic whodunit. Drop clues. Shocking twist reveal.",
            "suspense_stories": "Unbearable tension. Every scene raises the stakes.",
            "dark_facts":       "Expose dark truths. Shocking yet educational.",
            "psychological":    "Mind games. Question reality. Emotional gut-punch.",
            "thriller_stories": "Fast-paced. High stakes. No room to breathe.",
            "crime_stories":    "Crime, investigation, justice served cold.",
            "karma_stories":    "Poetic justice. The wrongdoer always pays.",
            "shocking_facts":   "One fact per beat. Each more shocking than the last.",
            "real_life_facts":  "Real stories. Real emotions. Truth stranger than fiction.",
            "moral_stories":    "Emotional journey. Life lesson hits hard at the end.",
        }.get(category, "Gripping story with a powerful ending.")

        return f"""You are a master storyteller and viral content creator for 'Wonder Stories TV' — a Hindi YouTube channel producing HIGHLY VIRAL {category.replace('_', ' ').title()} content.

STORY BRIEF:
  Title: {idea.title}
  Category: {category}
  Opening Hook (Hindi): {hook}
  Core Conflict: {conflict}
  Twist/Revelation: {twist}
  Moral/Takeaway: {moral}
  Moral (Hindi): {moral_hindi}
  Viral Angle: {audience_hook}

STORYTELLING DIRECTIVE:
  {viral_tone}

FORMAT:
  {duration_hint}
  Generation type: {cfg['gen_type']}
  Visual style: {art_style}

SCRIPT-FIRST APPROACH:
  Step 1: Write the COMPLETE Hindi voiceover script scene-by-scene FIRST.
          - CRITICAL: Voiceover MUST be written in HINGLISH (Hindi using English letters/Roman script). 
          - DO NOT use Devanagari script. (e.g. use 'kya', NOT 'क्या')
          - Voiceover must be DRAMATIC, EMOTIONAL, and GRIPPING
          - Use short punchy sentences
          - Build tension progressively
          - {'End with a shocking twist or revelation' if is_long else 'Hook viewer in first 3 seconds, deliver twist at end'}
          - Vary pace: fast for action/reveal, slow for suspense
          - Use rhetorical questions to engage viewer
  
  Step 2: From each voiceover block, describe the PERFECT CINEMATIC IMAGE.
          - NO 3D animation, NO cartoons, NO Pixar style
          - Photorealistic, cinematic, dramatic
          - Each image should visually tell what the voiceover describes
          - Scene images must FEEL the emotion of the narration

SCENE COUNT RULES (CRITICAL — FOLLOW EXACTLY):
  Hindi speaking pace ≈ 120–130 words per minute.
  Scene duration = word count ÷ 2.1 (approximate seconds).
  
  For SHORT format (max {cfg['max_total_dur']}s total):
    - Each scene voiceover: {cfg['word_hint']} words = ~{cfg['scene_dur_min']}–{cfg['scene_dur_max']}s
    - Total scenes: EXACTLY {cfg['num_scenes_min']}–{cfg['num_scenes_max']} scenes
    - DO NOT add more scenes just to fill time
    - DO NOT pad with empty/filler scenes
    - EVERY scene must serve the story
    - If story fits in {cfg['num_scenes_min']} scenes — USE {cfg['num_scenes_min']} SCENES
  
  {f"For LONG format: tell the FULL story properly. {cfg['num_scenes_min']}–{cfg['num_scenes_max']} scenes with complete arc." if fmt == 'long' else ''}

Return ONLY valid JSON matching this schema exactly:
{schema}"""

    # ──────────────────────────────────────────────────────────────────────────
    #  SCHEMA EXAMPLE
    # ──────────────────────────────────────────────────────────────────────────

    def _schema_example(self, idea: StoryIdea, cfg: dict, art_style: str) -> str:
        n_ex = cfg["num_scenes_min"]
        gen_type = cfg["gen_type"]
        expected_file = "1.mp4" if gen_type == "AI_VIDEO" else "1_image.png"
        return json.dumps({
            "story_metadata": {
                "title": idea.title,
                "title_hindi": "Hindi title here",
                "category": getattr(idea, "category", "mystery_stories"),
                "hook_line": getattr(idea, "hook_hindi", "Opening hook in Hindi"),
                "twist_reveal": getattr(idea, "twist", "The big twist"),
                "moral": getattr(idea, "moral", ""),
                "moral_hindi": getattr(idea, "moral_hindi", ""),
                "total_scenes": n_ex,
                "estimated_duration_seconds": cfg["scene_dur_min"] * n_ex,
                "thumbnail_prompt": f"Epic cinematic thumbnail for: {idea.title}. {art_style}. Bold dramatic composition. No text in image.",
                "thumbnail_title_hindi": "Thumbnail text in Hindi (5 words max)",
            },
            "scenes": [
                {
                    "scene_number": 1,
                    "generation_type": gen_type,
                    "expected_file": expected_file,
                    "duration_seconds": cfg["scene_dur_min"],
                    "voiceover_hindi": "Hinglish mein poori kahani yahan likhein. English letters ka hi prayog karein.",
                    "voice_hint": "narrator_dramatic",
                    "ai_prompt": f"Cinematic image description for scene 1. {art_style}. No text, no watermarks.",
                    "scene_beat": "HOOK",
                    "sfx_hint": "suspense_music",
                }
            ],
            "audio_effects_config": {
                "background_music": "suspense_loop",
                "music_volume": 0.08,
                "sfx_enabled": True,
                "fade_in_duration": 1.0,
                "fade_out_duration": 1.5,
            },
        }, ensure_ascii=False, indent=2)

    # ──────────────────────────────────────────────────────────────────────────
    #  VALIDATION + REPAIR
    # ──────────────────────────────────────────────────────────────────────────

    def _validate_and_repair(
        self, payload: dict, idea: StoryIdea, cfg: dict, art_style: str
    ) -> dict:
        if "story_metadata" not in payload:
            payload["story_metadata"] = {
                "title": idea.title,
                "title_hindi": idea.title,
                "category": getattr(idea, "category", "mystery_stories"),
                "hook_line": getattr(idea, "hook_hindi", ""),
                "twist_reveal": getattr(idea, "twist", ""),
                "moral": getattr(idea, "moral", ""),
                "moral_hindi": getattr(idea, "moral_hindi", ""),
                "total_scenes": cfg["num_scenes_min"],
                "estimated_duration_seconds": cfg["scene_dur_min"] * cfg["num_scenes_min"],
                "thumbnail_prompt": f"Epic cinematic thumbnail: {idea.title}. {art_style}",
                "thumbnail_title_hindi": idea.title[:30],
            }

        scenes = payload.get("scenes", [])

        # Clamp scene count
        if len(scenes) < cfg["num_scenes_min"]:
            scenes = self._template_fallback(idea, cfg, art_style)["scenes"]
        if len(scenes) > cfg["num_scenes_max"]:
            scenes = scenes[:cfg["num_scenes_max"]]

        gen_type = cfg["gen_type"]
        for i, scene in enumerate(scenes, 1):
            scene["scene_number"] = i
            if "generation_type" not in scene:
                scene["generation_type"] = gen_type
            # Fix expected file name
            ext = ".mp4" if scene["generation_type"] == "AI_VIDEO" else "_image.png"
            scene["expected_file"] = f"{i}{ext}"
            # Clamp duration
            dur = float(scene.get("duration_seconds", cfg["scene_dur_min"]))
            dur = max(cfg["scene_dur_min"], min(dur, cfg["scene_dur_max"]))
            scene["duration_seconds"] = dur
            # Ensure voiceover exists
            if not scene.get("voiceover_hindi", "").strip():
                scene["voiceover_hindi"] = f"Aur phir hua kuch aisa jo kisine socha nahi tha..."
            # Ensure AI prompt exists
            if not scene.get("ai_prompt", "").strip():
                scene["ai_prompt"] = f"Scene {i}: Dramatic cinematic shot. {art_style}"
            # Voice hint
            if "voice_hint" not in scene:
                scene["voice_hint"] = "narrator_dramatic"
            # Scene beat label
            if "scene_beat" not in scene:
                beats = ["HOOK", "BUILD", "ESCALATE", "CRISIS", "REVEAL", "RESOLUTION"]
                scene["scene_beat"] = beats[min(i - 1, len(beats) - 1)]

        payload["scenes"] = scenes
        payload["story_metadata"]["total_scenes"] = len(scenes)
        payload["story_metadata"]["estimated_duration_seconds"] = sum(
            s.get("duration_seconds", cfg["scene_dur_min"]) for s in scenes
        )
        if "audio_effects_config" not in payload:
            payload["audio_effects_config"] = self._default_sfx(idea)

        return payload

    # ──────────────────────────────────────────────────────────────────────────
    #  TEMPLATE FALLBACK
    # ──────────────────────────────────────────────────────────────────────────

    def _template_fallback(self, idea: StoryIdea, cfg: dict, art_style: str) -> dict:
        category = getattr(idea, "category", "mystery_stories")
        hook = getattr(idea, "hook_hindi", "Kuch aisa hua jo aapko sochne par majboor kar dega...")
        conflict = getattr(idea, "core_conflict", "")
        twist = getattr(idea, "twist", "Sach saamne aaya")
        moral = getattr(idea, "moral", "")
        moral_hindi = getattr(idea, "moral_hindi", "")
        gen_type = cfg["gen_type"]
        n = cfg["num_scenes_min"]
        dur = cfg["scene_dur_min"]

        beat_scripts = [
            (hook, "HOOK", "suspense_rise"),
            (f"Yeh kahani hai {idea.title} ki... {conflict}", "BUILD", "tension_build"),
            ("Aur phir hua kuch aisa jo kisine socha nahi tha...", "ESCALATE", "heartbeat"),
            ("Sab kuch ek pal mein badal gaya.", "CRISIS", "dramatic_hit"),
            (twist, "REVEAL", "revelation_sting"),
            (f"Seekh: {moral_hindi or moral}", "RESOLUTION", "peaceful_end"),
        ]

        scenes = []
        for i in range(1, n + 1):
            script_text, beat, sfx = beat_scripts[min(i - 1, len(beat_scripts) - 1)]
            ext = ".mp4" if gen_type == "AI_VIDEO" else "_image.png"
            scenes.append({
                "scene_number": i,
                "generation_type": gen_type,
                "expected_file": f"{i}{ext}",
                "duration_seconds": dur,
                "voiceover_hindi": script_text,
                "voice_hint": "narrator_dramatic",
                "ai_prompt": f"Scene {i} — {beat}: Cinematic {category.replace('_', ' ')} visual. {art_style}. No text.",
                "scene_beat": beat,
                "sfx_hint": sfx,
            })

        return {
            "story_metadata": {
                "title": idea.title,
                "title_hindi": idea.title,
                "category": category,
                "hook_line": hook,
                "twist_reveal": twist,
                "moral": moral,
                "moral_hindi": moral_hindi,
                "total_scenes": n,
                "estimated_duration_seconds": n * dur,
                "thumbnail_prompt": f"Epic cinematic thumbnail: {idea.title}. {art_style}. Bold dramatic composition.",
                "thumbnail_title_hindi": idea.title[:30],
            },
            "scenes": scenes,
            "audio_effects_config": self._default_sfx(idea),
        }

    def _default_sfx(self, idea: StoryIdea | None = None) -> dict:
        category = getattr(idea, "category", "mystery_stories") if idea else "mystery_stories"
        music_map = {
            "horror_stories":   "horror_ambient",
            "mystery_stories":  "mystery_suspense",
            "suspense_stories": "tension_build",
            "dark_facts":       "dark_documentary",
            "psychological":    "psychological_ambient",
            "thriller_stories": "thriller_action",
            "crime_stories":    "crime_noir",
            "karma_stories":    "karma_dramatic",
            "shocking_facts":   "documentary_dramatic",
            "real_life_facts":  "emotional_cinematic",
            "moral_stories":    "emotional_warm",
        }
        return {
            "background_music": music_map.get(category, "suspense_loop"),
            "music_volume": 0.07,
            "sfx_enabled": True,
            "fade_in_duration": 1.0,
            "fade_out_duration": 2.0,
        }
