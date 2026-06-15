"""
kids_story_generator.py  –  Wonder Stories TV
===============================================
Generates structured JSON story plans for each episode.

Formats:
  short  (max 35s) : 3 scenes × 11s   — YouTube Shorts / FB Reels
  mini   (~4 min)  : 8 scenes × 30s   — YouTube mid-length
  long   (~10 min) : 14 scenes × 43s  — YouTube with mid-roll ads
  series (~15 min) : 20 scenes × 45s  — YouTube series episode

Every story has TWO layers:
  Layer 1 (Kids)  : fun character, magic, action, clear moral
  Layer 2 (Adults): nostalgia, parenting truth, life lesson

Uses GPT-4o-mini / DeepSeek with template fallback.
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

# 3D Pixar animation style prefix appended to every AI image/video prompt
PIXAR_STYLE = (
    "3D Pixar style animation, Disney lighting, vibrant colors, "
    "highly detailed animated characters, warm golden background, "
    "ultra-detailed CGI quality, soft shadows, bright cheerful scene, "
    "Wonder Stories TV style"
)

CHINTU_DESC = "a short animated character with big round eyes, wearing a bright red t-shirt, chubby cheeks, innocent expression"
MOTHER_DESC = "a tall animated character wearing a beautiful yellow traditional outfit, warm smile, caring eyes"

# Scene count and duration per format
FORMAT_CONFIG: dict[str, dict] = {
    "short":  {"num_scenes": 4,  "scene_dur_veo": 8,  "scene_dur_img": 8,  "word_hint": "15-20"},
    "mini":   {"num_scenes": 8,  "scene_dur_veo": 30, "scene_dur_img": 30, "word_hint": "40-55"},
    "long":   {"num_scenes": 14, "scene_dur_veo": 43, "scene_dur_img": 43, "word_hint": "60-80"},
    "series": {"num_scenes": 20, "scene_dur_veo": 45, "scene_dur_img": 45, "word_hint": "70-90"},
}

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
        # Resolve format — default to 'short' if video_type not in FORMAT_CONFIG
        fmt = idea.video_type if idea.video_type in FORMAT_CONFIG else "short"
        cfg = FORMAT_CONFIG[fmt]

        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur_veo"] if kids_mode == "veo" else cfg["scene_dur_img"]
        word_hint  = cfg["word_hint"]
        gen_type   = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        is_long    = fmt in ("long", "series")

        # Resolve main character dynamically
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else "a young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans"

        # Decide supporting character: Mother (~50% chance), Golu (~16.6%), Pinky (~16.6%), Mintu (~16.6%)
        supporting_name = "Mother" if random.random() < 0.5 else random.choice(["Golu", "Pinky", "Mintu"])
        supporting_desc = SUPPORTING_CHARACTERS[supporting_name]
        if not is_made_for_kids:
            supporting_desc = supporting_desc.replace("short animated character", "young adult animated character")
            supporting_desc = supporting_desc.replace("chubby short animated character", "chubby young adult animated character")
            supporting_desc = supporting_desc.replace("two little ponytails, wearing a purple dress", "stylish long hair, wearing a casual jacket and jeans")
            supporting_desc = supporting_desc.replace("wearing a yellow cap and blue t-shirt", "wearing a modern jacket, stylish hair")

        LOGGER.info(
            "Generating story for '%s' (type=%s, mode=%s, scene_dur=%ss, main=%s, partner=%s)",
            idea.title, idea.video_type, kids_mode, scene_dur, char_name, supporting_name
        )

        schema_example = self._schema_example(idea, scene_dur, kids_mode, supporting_name, supporting_desc)

        # Dynamically build scene structure rules and sequence guidelines matching num_scenes
        rules_lines = []
        for idx in range(num_scenes):
            rules_lines.append(f"- Scene {idx+1} → generation_type: \"{gen_type}\", duration_seconds: {scene_dur}")
        scene_rules = f"Scene structure RULES (exactly {num_scenes} scenes, NO more, NO less, all of type {gen_type}):\n" + "\n".join(rules_lines)

        guidelines = [
            f"- Scene 1: Introduce {char_name} displaying the bad habit (ignored advice), with {supporting_name} observing.",
            f"- Scene 2: {supporting_name} warns him and introduces the magical element/event."
        ]
        if num_scenes > 4:
            for s in range(3, num_scenes - 1):
                if s == 3:
                    guidelines.append(f"- Scene {s}: The magical element starts to act, showing curious, funny effects.")
                elif s == num_scenes - 2:
                    guidelines.append(f"- Scene {s}: The magical effects escalate, teaching {char_name} a clear lesson.")
                else:
                    guidelines.append(f"- Scene {s}: {char_name} struggles with the magical consequences, {supporting_name} looks on supportively.")
        guidelines.append(f"- Scene {num_scenes - 1}: {char_name} realizes his mistake and feels apologetic.")
        guidelines.append(f"- Scene {num_scenes}: Heartwarming resolution, promise to change, standing happily next to {supporting_name}.")
        scene_sequence_hindi = "\n".join(guidelines)

        adult_hook = getattr(idea, "adult_hook", "")
        category   = getattr(idea, "category", "magical_adventure")
        char_safety_term = "short animated character" if is_made_for_kids else "young adult animated character"

        adult_rule = ""
        if not is_made_for_kids:
            adult_rule = (
                "\n            8. ADULT CHARACTER VISUALS: Since this story is NOT made for kids (Rohan/Normal mode), "
                "ALL characters (Rohan, Golu, Pinky, Mintu, Mother) MUST be fully depicted in visual prompts as grown young adults "
                "(age 20-25) with mature faces. NEVER describe them with child-like features, baby faces, school uniforms, school classrooms, "
                "or kids' play areas. The setting should be modern young-adult environments (like a tidy living room, college campus, café, "
                "library, or office)."
            )

        prompt = textwrap.dedent(f"""
            You are an expert AI storyteller for "Wonder Stories TV" — a family storytelling channel
            where EVERY story works on TWO levels:
              LAYER 1 (Kids 3-10): Fun characters, magic, humor, colorful action, clear moral at end.
              LAYER 2 (Adults 25-45): Nostalgia, parenting truth, life lesson they recognize deeply.
            This Pixar-formula dual-layer approach is what makes stories go viral with millions of views.

            Generate a completely unique story as a single valid JSON object.

            Story brief:
            - Title: {idea.title}
            - Category: {category}
            - Bad habit {char_name} has: {getattr(idea, 'bad_habit', '')} ({getattr(idea, 'bad_habit_hindi', '')})
            - Magical element: {getattr(idea, 'magical_element', 'a magical object')}
            - Moral lesson: {idea.moral} ({idea.moral_hindi})
            - Adult hook (make adults feel this): {adult_hook}
            - Video format: {fmt} ({num_scenes} scenes × {scene_dur}s each)

            Characters:
            - {char_name}: {char_desc}
            - {supporting_name}: {supporting_desc}

            VIRAL STORYTELLING & SUSPENSE GUIDELINES:
            * CLIFFHANGERS & SUSPENSE: Every scene's voiceover must end with a curiosity question or high-stakes hook that makes the viewer ask "what happens next?" (e.g., "Kya {char_name} is ghane jungle se bach payega?", "Tabhi achanak zameen ke neeche se ek chamakdar roshni nikli...").
            * DRAMATIC ENGAGEMENT: Avoid flat or boring narrations. Use a highly expressive, dramatic, and warm storytelling tone in Hinglish (Hindi in Roman script). Use words like "achanak", "ekdum se", "par tabhi", "hairan reh gaya", "chamatkar".
            * ADVENTURE & MYSTERY FOCUS: Instead of a repetitive "fixing a bad habit" formula, focus heavily on the adventure. Explore mysterious settings (e.g., dense jungle, ancient temples, cozy haunted spaces, magical floating kingdoms).
            * NARRATIVE ARC: Let the story unfold step-by-step. Establish mystery, build tension, reveal magical twists, and resolve happily.

            CRITICAL QUALITY RULES (A-ONE CONTENT STANDARD):
            1. DUAL-LAYER OPENING: Scene 1 must hook kids with action AND plant an adult emotion (nostalgia/parenting truth).
            2. Character Flow: {supporting_name} MUST be visible in Scene 1. All scenes must connect logically.
            3. Voiceover Quality: Each scene voiceover must be COMPLETE, vivid, emotionally engaging Hindi (Roman script).
               NO sentence fragments. Each line should feel like a professional narrator.
            4. Visual Richness: Every ai_prompt must describe an emotionally vivid, colorful, cinematic scene.
               Use lighting, expressions, environment details to create a STUNNING visual.
            5. Moral Delivery: The moral must feel earned and natural — NOT preachy or forced.
            6. Policy Safety: NEVER use 'boy', 'girl', 'child', 'kid', 'mother', 'father', 'hug', 'kiss', 'embrace' 
               in ai_prompt (triggers AI safety filters). Use:
               '{char_safety_term}', 'tall animated character', 'family characters cheering together',
               'high-five', 'smiling happily next to each other' instead.
            7. Uniqueness: Every story must be 100% original and different from any previous episode.{adult_rule}

            {scene_rules}

            Hindi voiceover per scene: {word_hint} words each. Simple, warm, child-friendly Hindi (Roman script ONLY — no Devanagari).
            {scene_sequence_hindi}

            Visual style for every ai_prompt (prepend this to every prompt):
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
        fmt = idea.video_type if idea.video_type in FORMAT_CONFIG else "short"
        cfg = FORMAT_CONFIG[fmt]
        num_scenes = cfg["num_scenes"]
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
        fmt = idea.video_type if idea.video_type in FORMAT_CONFIG else "short"
        num_scenes = FORMAT_CONFIG[fmt]["num_scenes"]
        gen_type = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        file_ext = "mp4" if kids_mode == "veo" else "jpg"

        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else "a young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans"
        
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
                f"character_{char_name.lower()}": char_desc,
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
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else "a young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans"

        magical = getattr(idea, "magical_element", "magical object")
        habit   = getattr(idea, "bad_habit", "a bad habit")
        habit_h = getattr(idea, "bad_habit_hindi", "ek buri aadat")
        moral_h = idea.moral_hindi
        fmt     = idea.video_type if idea.video_type in FORMAT_CONFIG else "short"
        is_long = fmt in ("long", "series")

        gen_type = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
        file_ext = "mp4" if kids_mode == "veo" else "jpg"

        if is_long:
            scenes = [
                {
                    "scene_number": 1,
                    "file_name": f"scene1.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Ek din {char_name} bahut shararat kar raha tha aur woh {habit_h}.",
                    "ai_prompt": f"{PIXAR_STYLE}, {char_desc} is busy {habit} in a messy Indian home living room, ignoring toys",
                },
                {
                    "scene_number": 2,
                    "file_name": f"scene2.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Tabhi {supporting_name} wahan aayi aur unhone {char_name} ko gusse se dekha aur warn kiya.",
                    "ai_prompt": f"{PIXAR_STYLE}, {supporting_desc} watching {char_name} with a concerned and serious face in the dining area",
                },
                {
                    "scene_number": 3,
                    "file_name": f"scene3.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"{supporting_name} ne kaha: {char_name}, dekho mere paas kya hai. Ek jaadu ka {magical}!",
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
                    "voiceover_hindi": f"{char_name} darr gaya aur samajh gaya ki {habit_h} kitna bura tha. Woh bhagte hue {supporting_name} ke paas gaya.",
                    "ai_prompt": f"{PIXAR_STYLE}, {char_desc} running towards {supporting_name} with an apologetic face, arms outstretched",
                },
                {
                    "scene_number": 6,
                    "file_name": f"scene6.{file_ext}",
                    "generation_type": gen_type,
                    "duration_seconds": scene_dur,
                    "voiceover_hindi": f"Usne {supporting_name} se vaada kiya ki ab se woh {habit_h} nahi karega. {moral_h}!",
                    "ai_prompt": f"{PIXAR_STYLE}, heartwarming scene of {char_desc} standing happily next to {supporting_desc}, warm glowing background",
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
                        "voiceover_hindi": f"Ek din {char_name} {habit_h}. Woh {supporting_name} ki baat bilkul nahi sun raha tha.",
                        "ai_prompt": f"{PIXAR_STYLE}, {char_desc} is {habit}, looking mischievous in a colorful Indian home living room",
                    },
                    {
                        "scene_number": 2,
                        "file_name": f"scene2.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Tabhi wahan jaadu ka {magical} chamka, aur {char_name} ko uski galti samajh aa gayi.",
                        "ai_prompt": f"{PIXAR_STYLE}, magical sparkles and light emanating from {magical}, {char_desc} looking surprised",
                    },
                    {
                        "scene_number": 3,
                        "file_name": f"scene3.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"{char_name} ne {supporting_name} se kaha, ab main kabhi {habit_h} nahi karunga. {moral_h}!",
                        "ai_prompt": f"{PIXAR_STYLE}, heartwarming scene of {char_desc} standing happily next to {supporting_desc}, golden light",
                    },
                ]
            else:
                scenes = [
                    {
                        "scene_number": 1,
                        "file_name": f"scene1.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Ek din {char_name} {habit_h}. Woh bilkul nahi sun raha tha {supporting_name} ki baat.",
                        "ai_prompt": f"{PIXAR_STYLE}, {char_desc} is {habit}, looking mischievous in a colorful Indian home living room",
                    },
                    {
                        "scene_number": 2,
                        "file_name": f"scene2.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"Tab {supporting_name} ne apna jaadu ka {magical} nikala. {char_name} ki aankhein phail gayi!",
                        "ai_prompt": f"{PIXAR_STYLE}, {supporting_desc} holding a glowing magical {magical}, {char_desc} watching with wide surprised eyes",
                    },
                    {
                        "scene_number": 3,
                        "file_name": f"scene3.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"{char_name} ne {magical} ka jaadu dekha, aur samajh gaya ki {habit_h} kitna galat hai.",
                        "ai_prompt": f"{PIXAR_STYLE}, magical sparkles emanating from {magical}, {char_desc} experiencing a magical revelation",
                    },
                    {
                        "scene_number": 4,
                        "file_name": f"scene4.{file_ext}",
                        "generation_type": gen_type,
                        "duration_seconds": scene_dur,
                        "voiceover_hindi": f"{char_name} ne {supporting_name} se vaada kiya: '{supporting_name}, main ab kabhi {habit_h} nahi karunga!' {moral_h}!",
                        "ai_prompt": f"{PIXAR_STYLE}, heartwarming scene of {char_desc} standing happily next to {supporting_desc} smiling happily",
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
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else "a young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans"

        descs = [
            f"{char_desc} looking mischievous, doing {idea.bad_habit}, Indian home living room",
            f"{supporting_desc} looking at {char_name} with a concerned expression, warm Indian kitchen background",
            f"{supporting_desc} presenting the magical {idea.magical_element}, sparkling golden light around it",
            f"{char_desc} looking curious and amazed at the magical {idea.magical_element}",
            f"{char_desc} experiencing the magical effects of the {idea.magical_element}, magic swirls and stars",
            f"{char_desc} looking surprised and thoughtful, realizing that doing {idea.bad_habit} is not good",
            f"{char_desc} running happily towards {supporting_name} to give a high-five, crying happy tears",
            f"{char_desc} standing happily next to {supporting_desc}, both smiling joyfully, warm cozy golden background",
        ]
        base = descs[min(scene_num - 1, len(descs) - 1)]
        return f"{PIXAR_STYLE}, {base}"

    def _default_metadata(self, idea: KidsStoryIdea, kids_mode: str, supporting_name: str, supporting_desc: str) -> dict:
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else "a young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans"

        fmt = idea.video_type if idea.video_type in FORMAT_CONFIG else "short"
        num_scenes = FORMAT_CONFIG[fmt]["num_scenes"]
        return {
            "title": idea.title,
            "channel": "Wonder Stories TV",
            "format": fmt,
            "total_scenes": num_scenes,
            "global_animation_style": PIXAR_STYLE,
            f"character_{char_name.lower()}": char_desc,
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
