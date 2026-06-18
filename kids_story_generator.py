"""
kids_story_generator.py  –  Wonder Stories TV
===============================================
Generates structured JSON story plans for each episode.

Formats & Durations:
  short + veo   : 3 scenes × 5s   = ~12-18s  — YouTube Shorts / FB Reels (video-to-video)
  short + image : 5 scenes × 8s   = ~40-50s  — YouTube Shorts / FB Reels (image-to-video)
  long  + image : 6 scenes × 25s  = ~2.5 min — YouTube (Ghibli-style image storytelling)

Visual Styles:
  short → 3D Pixar animation style
  long  (image only) → Studio Ghibli / watercolor storybook style

Story Quality:
  short → Opens mid-action, cliffhanger at every scene end
  long  → Full 6-act cinematic arc (world/conflict → mentor → struggle → dark → resolution → transformation)

Every story has TWO layers:
  Layer 1 (Kids)  : fun character, magic, action, clear moral
  Layer 2 (Adults): nostalgia, parenting truth, life lesson they recognise deeply
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

# ─── Visual Style Constants ───────────────────────────────────────────────────

# 3-D Pixar — used for short
PIXAR_STYLE = (
    "3D Pixar style animation, Disney lighting, vibrant colors, "
    "highly detailed animated characters, warm golden background, "
    "ultra-detailed CGI quality, soft shadows, bright cheerful scene, "
    "Wonder Stories TV style"
)

# Ghibli / watercolor — used for long image-to-video (like reference video)
GHIBLI_STYLE = (
    "Studio Ghibli inspired 2D illustration, warm hand-painted watercolor style, "
    "soft golden hour lighting, Indian rural village setting with lush green paddy fields, "
    "thatched-roof mud houses, mango trees, gentle brush strokes, "
    "emotionally expressive faces, cinematic storybook composition, "
    "warm amber and ochre colour palette, nostalgic and heartwarming atmosphere, "
    "Wonder Stories TV style"
)

# ─── Character Descriptions ───────────────────────────────────────────────────

CHINTU_DESC = (
    "a short animated character with big round eyes, wearing a bright red t-shirt, "
    "chubby cheeks, innocent expression"
)
ROHAN_DESC = (
    "a young adult character (age 20-25) with mature adult features, sharp jawline, "
    "modern hairstyle, wearing a modern casual t-shirt and jeans"
)

SUPPORTING_CHARACTERS = {
    "Mother": "a tall animated character wearing a beautiful yellow traditional outfit, warm smile, caring eyes",
    "Golu":   "a chubby short animated character wearing a green striped t-shirt, cheerful round face, friendly smile",
    "Pinky":  "a short animated character with two little ponytails, wearing a purple dress, bright curious eyes",
    "Mintu":  "a playful short animated character wearing a yellow cap and blue t-shirt, active expression",
}

# ─── Format Configuration ─────────────────────────────────────────────────────
# Resolved at runtime:  "short" → short_veo or short_img based on kids_mode

_FORMAT_BASE: dict[str, dict] = {
    # Short video-to-video: 3 scenes × 5s ≈ 12-18 sec
    "short_veo": {
        "num_scenes": 3,
        "scene_dur":  5,
        "word_hint":  "10-14",
        "gen_type":   "AI_VIDEO",
    },
    # Short image-to-video: 5 scenes × 8s ≈ 40-50 sec
    "short_img": {
        "num_scenes": 5,
        "scene_dur":  8,
        "word_hint":  "20-28",
        "gen_type":   "IMAGE_FOR_ZOOM",
    },
    # Long image-only: 6 scenes × 25s ≈ 2.5 min Ghibli
    "long": {
        "num_scenes": 6,
        "scene_dur":  25,
        "word_hint":  "35-45",
        "gen_type":   "IMAGE_FOR_ZOOM",
    },
}

FORMAT_CONFIG = _FORMAT_BASE  # kept for external imports / validate


def _resolve_config(fmt: str, kids_mode: str) -> dict:
    """Return resolved config dict for (fmt, kids_mode) combination."""
    if fmt == "short":
        key = "short_veo" if kids_mode == "veo" else "short_img"
        return dict(_FORMAT_BASE[key])
    # long always image-only
    cfg = dict(_FORMAT_BASE.get(fmt, _FORMAT_BASE["short_img"]))
    if cfg["gen_type"] is None:
        cfg["gen_type"] = "AI_VIDEO" if kids_mode == "veo" else "IMAGE_FOR_ZOOM"
    return cfg


def _art_style(fmt: str, kids_mode: str) -> str:
    """Return the correct art-style prefix string."""
    if fmt == "long" and kids_mode != "veo":
        return GHIBLI_STYLE
    return PIXAR_STYLE


@dataclass(slots=True)
class KidsStoryPlan:
    story_metadata: dict
    scenes: list[dict]
    audio_effects_config: dict
    raw_json: str


# ─────────────────────────────────────────────────────────────────────────────


class KidsStoryGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    # ──────────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def generate_story(self, idea: KidsStoryIdea, kids_mode: str = "veo") -> KidsStoryPlan:
        fmt = idea.video_type if idea.video_type in ("short", "long") else "short"
        cfg = _resolve_config(fmt, kids_mode)

        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        word_hint  = cfg["word_hint"]
        gen_type   = cfg["gen_type"]
        art_style  = _art_style(fmt, kids_mode)
        is_long    = fmt == "long"

        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else ROHAN_DESC

        supporting_name = "Mother" if random.random() < 0.5 else random.choice(["Golu", "Pinky", "Mintu"])
        supporting_desc = SUPPORTING_CHARACTERS[supporting_name]
        if not is_made_for_kids:
            supporting_desc = (
                supporting_desc
                .replace("short animated character", "young adult animated character")
                .replace("chubby short animated character", "chubby young adult animated character")
                .replace("two little ponytails, wearing a purple dress", "stylish long hair, wearing a casual jacket and jeans")
                .replace("wearing a yellow cap and blue t-shirt", "wearing a modern jacket, stylish hair")
            )

        LOGGER.info(
            "Generating story '%s' (fmt=%s, mode=%s, scenes=%s, dur=%ss, char=%s)",
            idea.title, fmt, kids_mode, num_scenes, scene_dur, char_name,
        )

        schema   = self._schema_example(idea, cfg, art_style, supporting_name, supporting_desc)
        prompt   = self._build_prompt(
            idea, fmt, cfg, art_style, schema,
            char_name, char_desc, supporting_name, supporting_desc,
            is_made_for_kids, is_long,
        )

        def _fallback():
            return self._template_fallback(idea, cfg, art_style, kids_mode, supporting_name, supporting_desc)

        raw_payload, provider = build_json_with_fallback(self.llm, prompt, _fallback, "kids-story")
        LOGGER.info("Story generation provider: %s", provider)

        plan_dict = self._validate_and_repair(raw_payload, idea, cfg, art_style, kids_mode, supporting_name, supporting_desc)

        return KidsStoryPlan(
            story_metadata=plan_dict["story_metadata"],
            scenes=plan_dict["scenes"],
            audio_effects_config=plan_dict.get("audio_effects_config", self._default_sfx()),
            raw_json=json.dumps(plan_dict, ensure_ascii=False, indent=2),
        )

    # ──────────────────────────────────────────────────────────────────────────
    #  PROMPT BUILDER
    # ──────────────────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        idea: KidsStoryIdea,
        fmt: str,
        cfg: dict,
        art_style: str,
        schema: str,
        char_name: str,
        char_desc: str,
        supporting_name: str,
        supporting_desc: str,
        is_made_for_kids: bool,
        is_long: bool,
    ) -> str:
        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        word_hint  = cfg["word_hint"]
        gen_type   = cfg["gen_type"]
        category   = getattr(idea, "category", "magical_adventure")
        adult_hook = getattr(idea, "adult_hook", "")
        char_safety = "short animated character" if is_made_for_kids else "young adult animated character"

        is_ghibli  = (fmt == "long" and gen_type == "IMAGE_FOR_ZOOM")

        # ── Scene structure rules ─────────────────────────────────────────────
        rules_lines = [
            f"- Scene {i+1} → generation_type: \"{gen_type}\", duration_seconds: {scene_dur}"
            for i in range(num_scenes)
        ]
        scene_rules = (
            f"Scene structure RULES (exactly {num_scenes} scenes, "
            f"NO more NO less, all of type {gen_type}):\n" + "\n".join(rules_lines)
        )

        # ── Scene sequence guidelines ─────────────────────────────────────────
        if is_ghibli:
            # 6-act Ghibli arc for long image format
            guidelines = [
                f"- Scene 1 (WORLD & CONFLICT): Paint a peaceful, beautiful world where {char_name} lives, but immediately introduce a real problem or test of values ({getattr(idea, 'bad_habit', 'a bad habit')}). {supporting_name} is affected. Adult viewers should feel the emotional stakes right away.",
                f"- Scene 2 (TURNING POINT / MENTOR): {char_name} meets a magical element or a wise figure that shows a new perspective. The moment of wonder and magic arrives naturally from the story.",
                f"- Scene 3 (JOURNEY & STRUGGLE): {char_name} faces a true test of character. Things get harder before they get better. Show the beauty of effort and perseverance.",
                f"- Scene 4 (DARK MOMENT): All seems lost. {char_name} questions themselves. This emotional low is what makes the eventual resolution feel EARNED and deeply touching.",
                f"- Scene 5 (RESOLUTION / BRAVE CHOICE): {char_name} makes a selfless, brave choice. The moral is delivered through ACTION — not words. Adults should feel a lump in their throat.",
                f"- Scene 6 (TRANSFORMATION & ENDING): The world feels brighter. {char_name} has changed. {supporting_name} is proud. End with a warm image that viewers want to screenshot and share.",
            ]
        elif num_scenes <= 3:
            # Ultra-short arc (video-to-video ~15s)
            guidelines = [
                f"- Scene 1 (HOOK — mid-action): Start with {char_name} ALREADY in the middle of doing {getattr(idea, 'bad_habit', 'something wrong')}. No setup. Pure action. End with a curious question.",
                f"- Scene 2 (MAGICAL TWIST): The magical element appears suddenly. {char_name} is shocked. Something changes in a surprising, funny, or dramatic way.",
                f"- Scene 3 (RESOLUTION): {char_name} learns the lesson instantly. Warm, joyful ending next to {supporting_name}. The moral should feel like a punchline — short and powerful.",
            ]
        else:
            # Standard short image arc (5 scenes, 40-50s)
            guidelines = [
                f"- Scene 1 (HOOK — mid-action): Open with {char_name} ALREADY in trouble — doing {getattr(idea, 'bad_habit', 'something wrong')}. Do NOT set up slowly. Open with high energy. End scene with a cliffhanger question like 'Kya tum jaante ho yeh kitna galat tha?'",
                f"- Scene 2 (CONSEQUENCE BEGINS): {supporting_name} appears and warns {char_name}. Tension builds. The magical element is introduced with wonder and sparkle.",
                f"- Scene 3 (MAGIC UNLEASHES): The magical element acts on its own! Something funny/dramatic/surprising happens. Viewers must feel 'what happens next?!'",
                f"- Scene 4 (REALIZATION): {char_name} sees the truth. The moment of clarity is emotionally resonant. Adults should recognize themselves.",
                f"- Scene 5 (HEARTWARMING CLOSE): {char_name} makes a promise. Warm, glowing resolution. The moral is delivered naturally — not preachy.",
            ]
        scene_sequence = "\n".join(guidelines)

        # ── Adult character rule ──────────────────────────────────────────────
        adult_rule = ""
        if not is_made_for_kids:
            adult_rule = (
                "\n            8. ADULT VISUALS: ALL characters MUST be young adults (age 20-25) with mature faces. "
                "NEVER use child-like features, school uniforms, or kids' classrooms. "
                "Settings: modern home, college campus, café, office, village."
            )

        # ── Ghibli-specific story quality rules ──────────────────────────────
        ghibli_rules = ""
        if is_ghibli:
            ghibli_rules = textwrap.dedent(f"""
            GHIBLI STORY QUALITY RULES (NON-NEGOTIABLE):
            * Every voiceover must read like LITERARY HINDI NARRATION — poetic, warm, vivid. NOT cartoon script.
            * Voiceover must evoke emotion through imagery: "Ek purani baat hai, jab kheton mein sone ki roshni bichhti thi..."
            * NEVER use the word "moral" in voiceover. Let the moral emerge naturally from events.
            * Visual prompts: Include rich environmental details — time of day, weather, textures, colours, emotions on faces.
            * Story must feel like a SHORT FILM — each scene a beautiful painting that tells its own small story.
            * Tone: "Karma Never Fails" style — real human emotion, real consequence, real redemption.
            """).strip()

        # ── Short cliffhanger rule ────────────────────────────────────────────
        short_rules = ""
        if not is_long:
            short_rules = (
                "\nSHORT FORMAT RULES:\n"
                "* Every scene voiceover MUST end with a question or suspense hook that pulls the viewer to the NEXT scene.\n"
                "* Example hooks: 'Kya {char_name} bach payega?', 'Tabhi achanak kuch aisa hua...', 'Aur phir...'\n"
                "* Scene 1 MUST open mid-action — viewer is dropped INTO the story, not introduced to it.\n"
                "* Keep voiceover PUNCHY — every word must earn its place."
            )

        prompt = textwrap.dedent(f"""
            You are an expert AI storyteller for "Wonder Stories TV" — a family channel
            where EVERY story works on TWO levels:
              LAYER 1 (Kids 3-10): Fun characters, magic, humour, colorful action, clear moral at end.
              LAYER 2 (Adults 25-45): Nostalgia, parenting truth, life lesson they recognise deeply.

            Generate a completely unique story as a single valid JSON object.

            Story brief:
            - Title: {idea.title}
            - Category: {category}
            - Bad habit: {getattr(idea, 'bad_habit', '')} ({getattr(idea, 'bad_habit_hindi', '')})
            - Magical element: {getattr(idea, 'magical_element', 'a magical object')}
            - Moral lesson: {idea.moral} ({idea.moral_hindi})
            - Adult emotional hook: {adult_hook}
            - Format: {fmt} ({num_scenes} scenes × {scene_dur}s each)

            Characters:
            - {char_name}: {char_desc}
            - {supporting_name}: {supporting_desc}

            {ghibli_rules}
            {short_rules}

            CRITICAL QUALITY RULES:
            1. DUAL-LAYER OPENING: Scene 1 hooks kids with action AND plants an adult emotion.
            2. {supporting_name} MUST appear in Scene 1 or Scene 2.
            3. Voiceover: COMPLETE, vivid, emotionally engaging Hindi (Roman script ONLY — no Devanagari).
               NO sentence fragments. Professional narrator tone.
            4. Visual prompts: Emotionally vivid, cinematic. Include lighting, expressions, environment.
            5. Moral must feel EARNED — NOT preachy or stated bluntly.
            6. Policy Safety: NEVER use 'boy', 'girl', 'child', 'kid', 'hug', 'kiss', 'embrace'
               in ai_prompt. Use: '{char_safety}', 'tall animated character',
               'high-five', 'smiling happily next to each other'.
            7. 100% original — different from any previous episode.{adult_rule}

            {scene_rules}

            Hindi voiceover per scene: {word_hint} words. Simple, warm Hindi (Roman script ONLY).
            {scene_sequence}

            Visual style for EVERY ai_prompt (prepend this to every prompt):
            "{art_style}"

            Return ONLY a raw JSON object (no markdown, no ```json wrapper) matching this schema:
            {schema}
        """).strip()

        return prompt

    # ──────────────────────────────────────────────────────────────────────────
    #  VALIDATION & REPAIR
    # ──────────────────────────────────────────────────────────────────────────

    def _validate_and_repair(
        self,
        payload: dict,
        idea: KidsStoryIdea,
        cfg: dict,
        art_style: str,
        kids_mode: str,
        supporting_name: str,
        supporting_desc: str,
    ) -> dict:
        scenes     = payload.get("scenes", [])
        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        gen_type   = cfg["gen_type"]
        file_ext   = "mp4" if gen_type == "AI_VIDEO" else "jpg"

        repaired = []
        for i in range(num_scenes):
            scene = dict(scenes[i]) if i < len(scenes) else self._empty_scene(
                i + 1, gen_type, scene_dur, art_style, idea, supporting_name, supporting_desc
            )
            scene["scene_number"]     = i + 1
            scene["generation_type"]  = gen_type
            scene["duration_seconds"] = scene_dur
            scene["file_name"]        = f"scene{i+1}.{file_ext}"

            prompt_text = scene.get("ai_prompt", "")
            if prompt_text and not prompt_text.startswith(("3D Pixar", "Studio Ghibli")):
                scene["ai_prompt"] = f"{art_style}, {prompt_text}"
            elif not prompt_text:
                scene["ai_prompt"] = self._fallback_prompt(
                    i + 1, gen_type, art_style, idea, supporting_name, supporting_desc
                )
            repaired.append(scene)

        payload["scenes"] = repaired
        payload.setdefault("story_metadata", self._default_metadata(idea, kids_mode, cfg, supporting_name, supporting_desc))
        payload.setdefault("audio_effects_config", self._default_sfx())
        return payload

    # ──────────────────────────────────────────────────────────────────────────
    #  SCHEMA EXAMPLE
    # ──────────────────────────────────────────────────────────────────────────

    def _schema_example(
        self,
        idea: KidsStoryIdea,
        cfg: dict,
        art_style: str,
        supporting_name: str,
        supporting_desc: str,
    ) -> str:
        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        gen_type   = cfg["gen_type"]
        file_ext   = "mp4" if gen_type == "AI_VIDEO" else "jpg"

        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else ROHAN_DESC

        scenes_list = [
            {
                "scene_number":     i + 1,
                "file_name":        f"scene{i+1}.{file_ext}",
                "generation_type":  gen_type,
                "duration_seconds": scene_dur,
                "voiceover_hindi":  f"Hindi voiceover for scene {i+1} (Roman script, warm narrator tone)",
                "ai_prompt":        f"{art_style}, scene {i+1} visual description here",
            }
            for i in range(num_scenes)
        ]

        return json.dumps(
            {
                "story_metadata": {
                    "title":                idea.title,
                    "total_scenes":         num_scenes,
                    "global_animation_style": art_style,
                    f"character_{char_name.lower()}": char_desc,
                    f"character_{supporting_name.lower()}": supporting_desc,
                },
                "scenes": scenes_list,
                "audio_effects_config": {
                    "background_music": "happy_kids_music.mp3",
                    "sfx_scene_1":      "curious_chime.mp3",
                    "sfx_scene_2":      "magic_sparkle.mp3",
                    "sfx_scene_3":      "surprise_reveal.mp3",
                },
            },
            indent=2,
        )

    # ──────────────────────────────────────────────────────────────────────────
    #  TEMPLATE FALLBACK
    # ──────────────────────────────────────────────────────────────────────────

    def _template_fallback(
        self,
        idea: KidsStoryIdea,
        cfg: dict,
        art_style: str,
        kids_mode: str,
        supporting_name: str,
        supporting_desc: str,
    ) -> dict:
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else ROHAN_DESC

        magical = getattr(idea, "magical_element", "magical object")
        habit   = getattr(idea, "bad_habit", "a bad habit")
        habit_h = getattr(idea, "bad_habit_hindi", "ek buri aadat")
        moral_h = idea.moral_hindi
        moral_e = idea.moral

        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        gen_type   = cfg["gen_type"]
        file_ext   = "mp4" if gen_type == "AI_VIDEO" else "jpg"

        def sc(n, vo, ap):
            return {
                "scene_number":     n,
                "file_name":        f"scene{n}.{file_ext}",
                "generation_type":  gen_type,
                "duration_seconds": scene_dur,
                "voiceover_hindi":  vo,
                "ai_prompt":        f"{art_style}, {ap}",
            }

        is_ghibli = art_style.startswith("Studio Ghibli")

        if is_ghibli:
            # 6-scene Ghibli arc
            scenes = [
                sc(1,
                   f"Ek sundar gavon mein, jahan subah ki roshni kheton par bikhar jaati thi, {char_name} apni zindagi mein khush tha. Par ek chota sa andhera tha jo usse rok raha tha — woh {habit_h}. Jiski wajah se {supporting_name} ko takleef hui. Kya aapne kabhi aisa feel kiya hai?",
                   f"peaceful Indian village at golden dawn, {char_desc} looking slightly regretful near lush paddy fields, {supporting_desc} turning away sadly, dramatic warm amber light, serene atmosphere"),
                sc(2,
                   f"Tabhi ek ajab baat hui. Ek budhiya ne {char_name} ko ek jaadu ka {magical} diya. Unhone kaha — 'Yeh tujhe woh dikhayega jo tu kabhi nahi dekh paya.' {char_name} ka dil dharakne laga. Kya hoga aage?",
                   f"elderly wise woman handing a glowing magical {magical} to {char_desc} at twilight, mystical golden sparks, sense of wonder and destiny, old banyan tree background"),
                sc(3,
                   f"Woh {magical} use karke {char_name} ek aisi duniya mein pahuncha jahan usne dekha ki uski galtiyon ka kya asar padta hai. Raasta mushkil tha, par usne haar nahi maani. Har kadam mein ek seekh thi.",
                   f"{char_desc} on a difficult journey through magical landscapes inspired by Indian countryside, determined expression, {magical} glowing ahead as a guiding light, painterly Ghibli backgrounds"),
                sc(4,
                   f"Sab kuch bigad gaya. {char_name} thak gaya tha. Lagta tha ki yeh galti kabhi nahi sudhri. Usne akele baithkar socha — 'Kya main wakai badal sakta hoon?' Yeh woh pal tha jab andar se kuch toot raha tha.",
                   f"{char_desc} sitting alone under a large old tree at dusk, head bowed in deep reflection, single golden leaf falling, melancholic yet beautiful light, echoing silence"),
                sc(5,
                   f"Aur phir {char_name} ne ek bahut bada faisla kiya. Woh wapas aaya — aur usne apni galti maan li. Bina kisi bahaane ke. Dil se. Issi ko kehte hain — karma hamesha wapas aata hai.",
                   f"{char_desc} returning to {supporting_desc} with humble, open expression, warm morning light breaking through, sense of relief and resolution, golden countryside backdrop"),
                sc(6,
                   f"{supporting_name} ne {char_name} ko maaf kiya. Duniya fir se sundar lag rahi thi. Woh jaadu ka {magical} ab chup gaya tha — kyunki asli jaadu toh {char_name} ke andar tha. {moral_e}.",
                   f"heartwarming scene of {char_desc} and {supporting_desc} standing together in a sunlit field, {magical} now dark and still, radiant smiles, golden hour light, butterflies, sense of peace and completion"),
            ]
        elif num_scenes <= 3:
            # Ultra-short 3-scene arc (video-to-video)
            scenes = [
                sc(1,
                   f"Dekho! {char_name} phir se {habit_h}! {supporting_name} sab dekh raha tha — aur tabhi... kuch ajeeb hua! Kya woh ruk payega?",
                   f"{char_desc} caught mid-action doing {habit} with exaggerated comic expression, {supporting_desc} watching with wide shocked eyes, colorful Indian home background"),
                sc(2,
                   f"Woh jaadu ka {magical} achanak chamka! Ek badi magic ki roshni, aur {char_name} ki duniya hi palat gayi! Hairan reh gaya woh!",
                   f"massive magical burst of light from {magical} swirling around {char_desc}, comedic shock and awe expression, sparkling magical particles everywhere"),
                sc(3,
                   f"{char_name} ne {supporting_name} se kaha: 'Ab main kabhi {habit_h} nahi karunga — pakka promise!' {moral_h}!",
                   f"{char_desc} standing next to {supporting_desc} both smiling joyfully, high-five pose, warm golden light, cheerful celebration atmosphere"),
            ]
        else:
            # Standard 5-scene short image arc
            scenes = [
                sc(1,
                   f"Dekho! {char_name} ek baar phir {habit_h}! {supporting_name} sab dekh raha tha — par {char_name} ko koi fark nahi padta tha. Kya tum jaante ho yeh aage jaake kitna bura hoga?",
                   f"{char_desc} caught mid-action doing {habit} with cheeky grin, {supporting_desc} watching with worried expression, colorful Indian living room"),
                sc(2,
                   f"{supporting_name} ne kaha: '{char_name}, ruk jao!' Aur tabhi unhone ek chamakti hui cheez nikaali — woh jaadu ka {magical}! Kya hoga ab?",
                   f"{supporting_desc} holding out a brilliantly glowing magical {magical}, {char_desc} staring with huge surprised eyes, golden magical light fills the scene"),
                sc(3,
                   f"Aur phir woh {magical} apne aap hi chalna laga! Itni magic, itna chamatkar — {char_name} wahan khada soch raha tha ki ab kya hoga!",
                   f"magical {magical} floating and spinning by itself, colorful sparkles and light beams, {char_desc} watching in amazement and slight fear, dramatic magical atmosphere"),
                sc(4,
                   f"{char_name} ko samajh aa gaya — woh galat tha. Uske dil mein ek thand si chali gayi. {supporting_name} ka dard usne feel kiya. Kuch toh badalna tha.",
                   f"{char_desc} with a deeply thoughtful and regretful expression, a single magical sparkle near their heart, soft warm light, {supporting_desc} watching gently in background"),
                sc(5,
                   f"{char_name} ne {supporting_name} se vaada kiya: 'Main ab kabhi {habit_h} nahi karunga.' Aur us din se, {char_name} sach mein badal gaya. {moral_h}!",
                   f"heartwarming scene of {char_desc} and {supporting_desc} smiling warmly next to each other, high-five gesture, gentle golden light, flowers blooming in background"),
            ]

        # Trim or pad to num_scenes
        while len(scenes) < num_scenes:
            n = len(scenes) + 1
            scenes.append(sc(
                n,
                f"Aur kahani aage badhti rahi... Scene {n} mein kuch naya hua.",
                self._fallback_prompt(n, gen_type, art_style, idea, supporting_name, supporting_desc).replace(f"{art_style}, ", ""),
            ))
        scenes = scenes[:num_scenes]

        return {
            "story_metadata": self._default_metadata(idea, "images" if gen_type != "AI_VIDEO" else "veo", cfg, supporting_name, supporting_desc),
            "scenes": scenes,
            "audio_effects_config": self._default_sfx(),
        }

    # ──────────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _empty_scene(
        self,
        num: int,
        gen_type: str,
        duration: int,
        art_style: str,
        idea: KidsStoryIdea,
        supporting_name: str,
        supporting_desc: str,
    ) -> dict:
        file_ext = "mp4" if gen_type == "AI_VIDEO" else "jpg"
        return {
            "scene_number":     num,
            "file_name":        f"scene{num}.{file_ext}",
            "generation_type":  gen_type,
            "duration_seconds": duration,
            "voiceover_hindi":  f"Scene {num} ki kahani.",
            "ai_prompt":        self._fallback_prompt(num, gen_type, art_style, idea, supporting_name, supporting_desc),
        }

    def _fallback_prompt(
        self,
        scene_num: int,
        gen_type: str,
        art_style: str,
        idea: KidsStoryIdea,
        supporting_name: str,
        supporting_desc: str,
    ) -> str:
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_desc = CHINTU_DESC if is_made_for_kids else ROHAN_DESC
        magical   = getattr(idea, "magical_element", "magical object")
        habit     = getattr(idea, "bad_habit", "a bad habit")

        descs = [
            f"{char_desc} looking mischievous, doing {habit}, Indian home living room",
            f"{supporting_desc} watching with a concerned expression, warm Indian kitchen background",
            f"{supporting_desc} presenting the magical {magical}, sparkling golden light around it",
            f"{char_desc} looking curious and amazed at the magical {magical}",
            f"{char_desc} experiencing the magical effects of {magical}, magic swirls and stars",
            f"{char_desc} looking surprised and thoughtful, realising the impact of their actions",
            f"{char_desc} and {supporting_desc} standing happily next to each other, warm glowing background",
        ]
        base = descs[min(scene_num - 1, len(descs) - 1)]
        return f"{art_style}, {base}"

    def _default_metadata(
        self,
        idea: KidsStoryIdea,
        kids_mode: str,
        cfg: dict,
        supporting_name: str,
        supporting_desc: str,
    ) -> dict:
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else ROHAN_DESC
        fmt = idea.video_type if idea.video_type in ("short", "long") else "short"
        return {
            "title":                 idea.title,
            "channel":               "Wonder Stories TV",
            "format":                fmt,
            "total_scenes":          cfg["num_scenes"],
            "global_animation_style": _art_style(fmt, kids_mode),
            f"character_{char_name.lower()}": char_desc,
            f"character_{supporting_name.lower()}": supporting_desc,
        }

    @staticmethod
    def _default_sfx() -> dict:
        bg_tracks = ["happy_kids_music.mp3", "cheerful_flute.mp3", "cartoon_adventure.mp3", "soft_sitar.mp3"]
        sfx_keys  = ["curious_chime.mp3", "wonder_bell.mp3", "playful_boing.mp3"]
        sfx_vals  = ["magic_sparkle.mp3", "surprise_reveal.mp3", "happy_celebration.mp3"]
        return {
            "background_music": random.choice(bg_tracks),
            "sfx_scene_1":      random.choice(sfx_keys),
            "sfx_scene_2":      random.choice(sfx_vals),
            "sfx_scene_3":      random.choice(sfx_vals),
            "sfx_scene_4":      "happy_celebration.mp3",
        }
