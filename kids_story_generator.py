"""
kids_story_generator.py  –  Chintu Stories Channel
===================================================
Generates a structured JSON story plan for each episode.

Short format  (~30 s): 4 scenes × 6 s  (AI_VIDEO, IMAGE_FOR_ZOOM, AI_VIDEO, IMAGE_FOR_ZOOM)
Long  format  (~1:30): 8 scenes × 11 s (alternating AI_VIDEO and IMAGE_FOR_ZOOM)

Uses GPT-4o-mini / DeepSeek to produce the scene plan, with a template fallback.
"""
from __future__ import annotations

import json
import logging
import random
import textwrap
from dataclasses import dataclass

from config import AppConfig
from kids_idea_generator import KidsStoryIdea
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)

# 3D Pixar animation style prefix appended to every AI image prompt
PIXAR_STYLE = (
    "3D Pixar style animation, Disney lighting, vibrant colors, "
    "highly detailed characters, warm golden background, "
    "ultra-detailed, professional CGI quality, "
    "soft shadows, bright cheerful scene"
)

CHINTU_DESC = "a short animated character with big round eyes, wearing a bright red t-shirt, chubby cheeks, innocent expression"
MOTHER_DESC = "a tall animated character wearing a beautiful yellow traditional outfit, warm smile, caring eyes"

SUPPORTING_CHARACTERS = {
    "Mother": "a tall animated character wearing a beautiful yellow traditional outfit, warm smile, caring eyes",
    "Golu": "a chubby short animated character wearing a green striped t-shirt, cheerful round face, friendly smile",
    "Pinky": "a short animated character with two little ponytails, wearing a purple dress, bright curious eyes",
    "Mintu": "a playful short animated character wearing a yellow cap and blue t-shirt, active expression"
}


@dataclass(slots=True)
class KidsStoryPlan:
    story_metadata: dict
    scenes: list[dict]
    audio_effects_config: dict
    raw_json: str


class KidsStoryGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_story(self, idea: KidsStoryIdea, kids_mode: str = "veo") -> KidsStoryPlan:
        is_long   = idea.video_type == "long"
        
        # Decide supporting character: Mother (~50% chance), Golu (~16.6%), Pinky (~16.6%), Mintu (~16.6%)
        supporting_name = "Mother" if random.random() < 0.5 else random.choice(["Golu", "Pinky", "Mintu"])
        supporting_desc = SUPPORTING_CHARACTERS[supporting_name]

        if is_long:
            num_scenes = 6
            scene_dur = 13
            word_hint = "30-40"
            gen_type = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        else:
            if kids_mode == "veo":
                num_scenes = 3
                scene_dur = 6
                word_hint = "12-16"
                gen_type = "AI_VIDEO"
            else:  # images
                num_scenes = 4
                scene_dur = 6  # 4 * 6 = 24s (under 25s limit)
                word_hint = "15-20"
                gen_type = "IMAGE_FOR_ZOOM"

        LOGGER.info(
            "Generating kids story for '%s' (type=%s, mode=%s, scene_dur=%ss, partner=%s)",
            idea.title, idea.video_type, kids_mode, scene_dur, supporting_name
        )

        schema_example = self._schema_example(idea, scene_dur, kids_mode, supporting_name, supporting_desc)

        if is_long:
            scene_rules = textwrap.dedent(f"""
                Scene structure RULES (exactly 6 scenes, NO more, NO less, all of type {gen_type}):
                - Scene 1 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                - Scene 2 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                - Scene 3 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                - Scene 4 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                - Scene 5 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                - Scene 6 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
            """).strip()
            scene_sequence_hindi = textwrap.dedent(f"""
                - Scene 1: Introduce Chintu doing the bad habit, {supporting_name} is visibly present and notices him.
                - Scene 2: {supporting_name} warns him and the magical element appears.
                - Scene 3: {supporting_name} introduces the magical element to teach him.
                - Scene 4: Chintu experiences the magical twist and starts learning.
                - Scene 5: Chintu realizes his mistake.
                - Scene 6: Heartwarming ending, hugging {supporting_name}, habit fixed.
            """).strip()
        else:
            if kids_mode == "veo":
                scene_rules = textwrap.dedent(f"""
                    Scene structure RULES (exactly 3 scenes, NO more, NO less, all of type {gen_type}):
                    - Scene 1 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                    - Scene 2 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                    - Scene 3 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                """).strip()
                scene_sequence_hindi = textwrap.dedent(f"""
                    - Scene 1: Introduce Chintu doing the bad habit, with {supporting_name} visibly present and looking concerned or warning him.
                    - Scene 2: The magical element appears and teaches him a lesson.
                    - Scene 3: Chintu realizes, promises to improve, hugging {supporting_name}.
                """).strip()
            else:
                scene_rules = textwrap.dedent(f"""
                    Scene structure RULES (exactly 4 scenes, NO more, NO less, all of type {gen_type}):
                    - Scene 1 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                    - Scene 2 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                    - Scene 3 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                    - Scene 4 → generation_type: "{gen_type}", duration_seconds: {scene_dur}
                """).strip()
                scene_sequence_hindi = textwrap.dedent(f"""
                    - Scene 1: Introduce Chintu doing the bad habit, with {supporting_name} visibly present.
                    - Scene 2: {supporting_name} warns him and introduces the magical element.
                    - Scene 3: The magic happens, teaching Chintu a lesson.
                    - Scene 4: Chintu apologizes, promises to change, and hugs {supporting_name}.
                """).strip()

        prompt = textwrap.dedent(f"""
            You are an expert AI storyteller for the YouTube Kids Shorts channel "Chintu Stories".
            Generate a completely unique, morally educational story as a single valid JSON object.

            Story brief:
            - Title: {idea.title}
            - Bad habit Chintu has: {idea.bad_habit} ({idea.bad_habit_hindi})
            - Magical element: {idea.magical_element}
            - Moral lesson: {idea.moral} ({idea.moral_hindi})
            - Video type: {"Long (~1:30 min)" if is_long else "Short (~30 s)"}

            Characters:
            - Chintu: {CHINTU_DESC}
            - {supporting_name}: {supporting_desc}

            CRITICAL SCENE CONTINUITY & ENGAGEMENT RULES:
            1. Character Presence & Logical Flow: The scenes must link logically to each other. {supporting_name} MUST be visibly present in the first scene.
            2. High Engagement Opening: The first scene must be extremely interesting, active, and colorful to grab the child's attention immediately. Show Chintu doing something dynamic.
            3. Voiceover Flow: The Romanized Hindi voiceover must form a continuous, cohesive story. Each scene's sentence must be fully complete and transition smoothly to the next scene. Do not leave a sentence cut off or incomplete.
            4. Consistent Environment: Keep the background environment (e.g. living room, kitchen, garden) consistent between scenes unless they explicitly move to a new place.
            5. Safety & Copyright: Ensure the story, characters, and magical elements do not violate any copyright, YouTube policies, or community guidelines. Keep it safe for children. NEVER use words like 'boy', 'girl', 'child', 'kid', 'mother', 'father', 'son', 'daughter', 'hug', 'embrace', or 'kiss' in the ai_prompt as they trigger AI safety filters for minors. Use 'short animated character', 'tall animated character', 'family characters standing together', 'smiling happily next to', 'high-five', or 'cheering together' instead.

            {scene_rules}

            Hindi voiceover per scene: {word_hint} words each, narrated in simple, child-friendly Hindi (Roman script only, no Devanagari).
            {scene_sequence_hindi}

            AI image prompt style for every scene (prepend this style prefix to every ai_prompt):
            "{PIXAR_STYLE}"

            Return ONLY a raw JSON object (no markdown, no ```json wrapper) matching this schema exactly:
            {schema_example}
        """).strip()

        def _fallback():
            return self._template_fallback(idea, scene_dur, kids_mode, supporting_name, supporting_desc)

        raw_payload, provider = build_json_with_fallback(self.llm, prompt, _fallback, "kids-story")
        LOGGER.info("Kids story generation provider: %s", provider)

        # Validate & repair
        plan_dict = self._validate_and_repair(raw_payload, idea, scene_dur, kids_mode, supporting_name, supporting_desc)

        return KidsStoryPlan(
            story_metadata=plan_dict["story_metadata"],
            scenes=plan_dict["scenes"],
            audio_effects_config=plan_dict.get("audio_effects_config", self._default_sfx()),
            raw_json=json.dumps(plan_dict, ensure_ascii=False, indent=2),
        )

    # ─── Validation ───────────────────────────────────────────────────────────

    def _validate_and_repair(self, payload: dict, idea: KidsStoryIdea, scene_dur: int, kids_mode: str, supporting_name: str, supporting_desc: str) -> dict:
        """Ensures correct scene count with correct generation_type."""
        scenes = payload.get("scenes", [])
        is_long = idea.video_type == "long"
        
        if is_long:
            num_scenes = 6
        else:
            num_scenes = 3 if kids_mode == "veo" else 4
            
        gen_type = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        file_ext = "mp4" if kids_mode == "veo" else "jpg"

        expected_types = [gen_type] * num_scenes

        repaired = []
        for i, gen_t in enumerate(expected_types):
            if i < len(scenes):
                scene = dict(scenes[i])
            else:
                scene = self._empty_scene(i + 1, gen_t, scene_dur, idea, supporting_name, supporting_desc)
            scene["scene_number"]     = i + 1
            scene["generation_type"]  = gen_t
            scene["duration_seconds"] = scene_dur
            scene["file_name"]        = f"scene{i+1}.{file_ext}"
            # Ensure ai_prompt has Pixar style prefix
            prompt_text = scene.get("ai_prompt", "")
            if prompt_text and not prompt_text.startswith("3D Pixar"):
                scene["ai_prompt"] = f"{PIXAR_STYLE}, {prompt_text}"
            elif not prompt_text:
                scene["ai_prompt"] = self._fallback_prompt(i + 1, gen_t, idea, supporting_name, supporting_desc)
            repaired.append(scene)

        payload["scenes"] = repaired
        payload.setdefault("story_metadata", self._default_metadata(idea, kids_mode, supporting_name, supporting_desc))
        payload.setdefault("audio_effects_config", self._default_sfx())
        return payload

    # ─── Schema / Template Helpers ────────────────────────────────────────────

    def _schema_example(self, idea: KidsStoryIdea, scene_dur: int, kids_mode: str, supporting_name: str, supporting_desc: str) -> str:
        is_long = idea.video_type == "long"
        if is_long:
            num_scenes = 6
        else:
            num_scenes = 3 if kids_mode == "veo" else 4
            
        gen_type = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        file_ext = "mp4" if kids_mode == "veo" else "jpg"
        
        scenes_list = []
        for i in range(num_scenes):
            scenes_list.append({
                "scene_number": i + 1,
                "file_name": f"scene{i+1}.{file_ext}",
                "generation_type": gen_type,
                "duration_seconds": scene_dur,
                "voiceover_hindi": f"Hindi voiceover for scene {i+1} (Roman script, child-friendly)",
                "ai_prompt": f"{PIXAR_STYLE}, scene {i+1} description here",
            })

        return json.dumps({
            "story_metadata": {
                "title": idea.title,
                "total_scenes": num_scenes,
                "global_animation_style": PIXAR_STYLE,
                "character_chintu": CHINTU_DESC,
                f"character_{supporting_name.lower()}": supporting_desc,
            },
            "scenes": scenes_list,
            "audio_effects_config": {
                "background_music": "happy_kids_music.mp3",
                "sfx_scene_1": "curious_chime.mp3",
                "sfx_scene_2": "magic_sparkle.mp3",
                "sfx_scene_3": "surprise_reveal.mp3",
            },
        }, indent=2)

    def _template_fallback(self, idea: KidsStoryIdea, scene_dur: int, kids_mode: str, supporting_name: str, supporting_desc: str) -> dict:
        """Hard-coded template fallback — always produces a valid story."""
        magical = idea.magical_element
        habit   = idea.bad_habit
        habit_h = idea.bad_habit_hindi
        moral_h = idea.moral_hindi
        is_long = idea.video_type == "long"
        
        gen_type = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        file_ext = "mp4" if kids_mode == "veo" else "jpg"

        if is_long:
            scenes = [
                {
                    "scene_number": 1,
                    "file_name": f"scene1.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Ek din Chintu bahut shararat kar raha tha aur woh {habit_h}.",
                    "ai_prompt": f"{PIXAR_STYLE}, {CHINTU_DESC} is busy {habit} in a messy Indian home living room, ignoring toys",
                },
                {
                    "scene_number": 2,
                    "file_name": f"scene2.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Tabhi {supporting_name} wahan aayi aur unhone Chintu ko gusse se dekha aur warn kiya.",
                    "ai_prompt": f"{PIXAR_STYLE}, {supporting_desc} watching Chintu with a concerned and serious face in the dining area",
                },
                {
                    "scene_number": 3,
                    "file_name": f"scene3.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"{supporting_name} ne kaha: Chintu, dekho mere paas kya hai. Ek jaadu ka {magical}!",
                    "ai_prompt": f"{PIXAR_STYLE}, {supporting_desc} holding out a beautiful glowing magical {magical} that sparkles brightly",
                },
                {
                    "scene_number": 4,
                    "file_name": f"scene4.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Tabhi achanak jaadu ka {magical} chamakne laga aur usme se ek roshni nikli.",
                    "ai_prompt": f"{PIXAR_STYLE}, magic swirls and colorful light burst from the {magical} filling the room",
                },
                {
                    "scene_number": 5,
                    "file_name": f"scene5.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Chintu darr gaya aur samajh gaya ki {habit_h} kitna bura tha. Woh bhagte hue {supporting_name} ke paas gaya.",
                    "ai_prompt": f"{PIXAR_STYLE}, {CHINTU_DESC} running towards {supporting_name} with an apologetic face, arms outstretched",
                },
                {
                    "scene_number": 6,
                    "file_name": f"scene6.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Usne {supporting_name} se vaada kiya ki ab se woh {habit_h} nahi karega. {moral_h}!",
                    "ai_prompt": f"{PIXAR_STYLE}, heartwarming scene of {CHINTU_DESC} standing happily next to {supporting_desc}, warm glowing background",
                },
            ]
        else:
            if kids_mode == "veo":
                scenes = [
                    {
                        "scene_number": 1,
                        "file_name": f"scene1.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Ek din Chintu {habit_h}. Woh {supporting_name} ki baat bilkul nahi sun raha tha.",
                        "ai_prompt": f"{PIXAR_STYLE}, {CHINTU_DESC} is {habit}, looking mischievous in a colorful Indian home living room",
                    },
                    {
                        "scene_number": 2,
                        "file_name": f"scene2.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Tabhi wahan jaadu ka {magical} chamka, aur Chintu ko uski galti samajh aa gayi.",
                        "ai_prompt": f"{PIXAR_STYLE}, magical sparkles and light emanating from {magical}, {CHINTU_DESC} looking surprised",
                    },
                    {
                        "scene_number": 3,
                        "file_name": f"scene3.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Chintu ne {supporting_name} se kaha, ab main kabhi {habit_h} nahi karunga. {moral_h}!",
                        "ai_prompt": f"{PIXAR_STYLE}, heartwarming scene of {CHINTU_DESC} standing happily next to {supporting_desc}, golden light",
                    },
                ]
            else:
                scenes = [
                    {
                        "scene_number": 1,
                        "file_name": f"scene1.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Ek din Chintu {habit_h}. Woh bilkul nahi sun raha tha {supporting_name} ki baat.",
                        "ai_prompt": f"{PIXAR_STYLE}, {CHINTU_DESC} is {habit}, looking mischievous in a colorful Indian home living room",
                    },
                    {
                        "scene_number": 2,
                        "file_name": f"scene2.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Tab {supporting_name} ne apna jaadu ka {magical} nikala. Chintu ki aankhein phail gayi!",
                        "ai_prompt": f"{PIXAR_STYLE}, {supporting_desc} holding a glowing magical {magical}, {CHINTU_DESC} watching with wide surprised eyes",
                    },
                    {
                        "scene_number": 3,
                        "file_name": f"scene3.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Chintu ne {magical} ka jaadu dekha, aur samajh gaya ki {habit_h} kitna galat hai.",
                        "ai_prompt": f"{PIXAR_STYLE}, magical sparkles emanating from {magical}, {CHINTU_DESC} experiencing a magical revelation",
                    },
                    {
                        "scene_number": 4,
                        "file_name": f"scene4.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Chintu ne {supporting_name} se vaada kiya: '{supporting_name}, main ab kabhi {habit_h} nahi karunga!' {moral_h}!",
                        "ai_prompt": f"{PIXAR_STYLE}, heartwarming scene of {CHINTU_DESC} standing happily next to {supporting_desc} smiling happily",
                    },
                ]

        return {
            "story_metadata": self._default_metadata(idea, kids_mode, supporting_name, supporting_desc),
            "scenes": scenes,
            "audio_effects_config": self._default_sfx(),
        }

    def _empty_scene(self, num: int, gen_type: str, duration: int, idea: KidsStoryIdea, supporting_name: str, supporting_desc: str) -> dict:
        file_ext = "mp4" if gen_type == "AI_VIDEO" else "jpg"
        return {
            "scene_number": num,
            "file_name": f"scene{num}.{file_ext}",
            "generation_type": gen_type,
            "duration_seconds": duration,
            "voiceover_hindi": f"Scene {num} ki kahani.",
            "ai_prompt": self._fallback_prompt(num, gen_type, idea, supporting_name, supporting_desc),
        }

    def _fallback_prompt(self, scene_num: int, gen_type: str, idea: KidsStoryIdea, supporting_name: str, supporting_desc: str) -> str:
        descs = [
            f"{CHINTU_DESC} looking mischievous, doing {idea.bad_habit}, Indian home living room",
            f"{supporting_desc} looking at Chintu with a concerned expression, warm Indian kitchen background",
            f"{supporting_desc} presenting the magical {idea.magical_element}, sparkling golden light around it",
            f"{CHINTU_DESC} looking curious and amazed at the magical {idea.magical_element}",
            f"{CHINTU_DESC} experiencing the magical effects of the {idea.magical_element}, magic swirls and stars",
            f"{CHINTU_DESC} looking surprised and thoughtful, realizing that doing {idea.bad_habit} is not good",
            f"{CHINTU_DESC} running happily towards {supporting_name} to give a high-five, crying happy tears",
            f"{CHINTU_DESC} standing happily next to {supporting_desc}, both smiling joyfully, warm cozy golden background",
        ]
        base = descs[min(scene_num - 1, len(descs) - 1)]
        return f"{PIXAR_STYLE}, {base}"

    def _default_metadata(self, idea: KidsStoryIdea, kids_mode: str, supporting_name: str, supporting_desc: str) -> dict:
        is_long = idea.video_type == "long"
        if is_long:
            num_scenes = 6
        else:
            num_scenes = 3 if kids_mode == "veo" else 4
        return {
            "title": idea.title,
            "total_scenes": num_scenes,
            "global_animation_style": PIXAR_STYLE,
            "character_chintu": CHINTU_DESC,
            f"character_{supporting_name.lower()}": supporting_desc,
        }

    @staticmethod
    def _default_sfx() -> dict:
        sfx_options = {
            "curious_chime.mp3": "magic_sparkle.mp3",
            "wonder_bell.mp3": "surprise_reveal.mp3",
            "playful_boing.mp3": "happy_celebration.mp3",
        }
        keys = list(sfx_options.keys())
        vals = list(sfx_options.values())
        bg_tracks = ["happy_kids_music.mp3", "cheerful_flute.mp3", "cartoon_adventure.mp3"]
        return {
            "background_music": random.choice(bg_tracks),
            "sfx_scene_1": random.choice(keys),
            "sfx_scene_2": random.choice(vals),
            "sfx_scene_3": random.choice(vals),
            "sfx_scene_4": "happy_celebration.mp3",
        }
