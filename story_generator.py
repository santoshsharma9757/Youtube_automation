"""
story_generator.py  –  Wonder Stories TV
=========================================
Generates structured JSON story plans for each episode.

Pipeline Priority:
  1. Generate a COMPLETE Hindi voiceover script (full scene-by-scene narration)
  2. Derive visual scene descriptions from the script
  3. Scene images: cinematic/realistic (no 3D/Pixar/Ghibli)

Formats & Durations:
  short + image : 6-8 scenes × 4-5s   = ~30-35s  — YouTube Shorts / Reels
  short + video : 2 scenes × 8s       = ~16s     — YouTube Shorts / Reels
  long  + image : 15-20 scenes × 8-11s = ~2:30-2:45 — YouTube long-form
  long  + video : disabled; long stories always render in image mode

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
        "authentic Indian settings and Indian people, "
        "photorealistic, 8K quality, dramatic storytelling visual"
    ),
    "dark_facts": (
        "Dark dramatic documentary photography, stark high contrast, "
        "deep shadows with selective lighting, cinematic color grade, "
        "authentic Indian settings and Indian people, "
        "photorealistic, intense atmospheric composition, "
        "historical or investigative feel, 8K quality"
    ),
    "mystery_stories": (
        "Noir cinematic style, dramatic chiaroscuro lighting, atmospheric fog, "
        "mysterious and suspenseful composition, desaturated tones with accent colors, "
        "authentic Indian settings and Indian people, "
        "photorealistic photography, cinematic wide angle, 8K quality, "
        "shadow play, detective atmosphere"
    ),
    "suspense_stories": (
        "Cinematic suspense photography, tight dramatic framing, "
        "shallow depth of field, moody blue-grey tones, "
        "tension-filled composition, authentic Indian settings and Indian people, "
        "photorealistic, motion blur hints, 8K quality, edge-of-seat atmosphere"
    ),
    "crime_stories": (
        "Gritty realistic urban photography, high contrast dramatic lighting, "
        "cinematic film noir inspired, authentic street-level compositions, "
        "authentic Indian settings and Indian people, "
        "photorealistic, raw and intense visual storytelling, "
        "crime thriller color grade, 8K quality"
    ),
    "thriller_stories": (
        "High-stakes cinematic thriller photography, dynamic action-ready composition, "
        "dramatic overhead or Dutch angle shots, intense color grading, "
        "authentic Indian settings and Indian people, "
        "photorealistic, urgent and tense atmosphere, "
        "adrenaline-filled visual storytelling, 8K quality"
    ),
    "psychological": (
        "Surreal cinematic photography, double exposure or dreamlike composition, "
        "emotional close-up portraits, distorted perspective elements, "
        "muted desaturated palette with vivid accent, authentic Indian settings and Indian people, "
        "photorealistic, mind-bending visual metaphors, 8K quality"
    ),
    "shocking_facts": (
        "Documentary photography style, impactful photojournalism composition, "
        "dramatic natural lighting, authentic realistic visuals, "
        "bold and striking imagery, authentic Indian settings and Indian people, "
        "photorealistic, award-winning documentary feel, 8K quality"
    ),
    "real_life_facts": (
        "Cinematic documentary photography, warm authentic lighting, "
        "real human emotion captured, storytelling composition, "
        "authentic Indian settings and Indian people, "
        "photorealistic, inspiring and powerful visual narrative, "
        "golden hour or dramatic studio lighting, 8K quality"
    ),
    "karma_stories": (
        "Warm cinematic storytelling photography, emotional resonant composition, "
        "dramatic lighting with warm tones, poetic visual storytelling, "
        "authentic Indian settings and Indian people, "
        "photorealistic, justice and emotion conveyed through imagery, "
        "cinematic color grade, 8K quality"
    ),
    "moral_stories": (
        "Heartwarming Studio Ghibli style anime illustration, soft nostalgic glow, "
        "detailed painterly environment, expressive character eyes, "
        "authentic Indian setting and Indian people, classic hand-drawn masterpiece feel"
    ),
    "bhagwan_stories": (
        "Ethereal Studio Ghibli style divine anime illustration, radiant celestial glow, "
        "respectful and sacred devotional atmosphere, golden temple or village setting, "
        "authentic Indian setting and Indian people, awe-inspiring hand-drawn animation style"
    ),
    "inspirational_stories": (
        "Beautiful Studio Ghibli inspired hand-drawn anime style, warm nostalgic lighting, "
        "soft painterly background, emotional character expressions, "
        "authentic Indian setting and Indian people, colorful masterpiece animation aesthetic"
    ),
    "motivational_stories": (
        "Inspiring Studio Ghibli hand-drawn animation style, dramatic sun rays, "
        "vibrant warm colors, dynamic storytelling angle, detailed character art, "
        "authentic Indian setting and Indian people, high-quality anime illustration"
    ),
}

DEFAULT_STYLE = (
    "Cinematic photography, dramatic lighting, photorealistic, "
    "authentic Indian settings and Indian people, 8K quality, "
    "professional storytelling composition"
)

# ─── Format Configuration ─────────────────────────────────────────────────────

_FORMAT_BASE: dict[str, dict] = {
    # Short image-to-video: exactly 6 scenes × 5s = 30s for optimal retention
    "short_img": {
        "num_scenes_min": 6,
        "num_scenes_max": 6,
        "scene_dur_min":  5,
        "scene_dur_max":  5,
        "word_hint":      "12-15",    # words per scene voiceover (~5s at normal pace)
        "gen_type":       "IMAGE_FOR_ZOOM",
        "target_total_min": 30,
        "target_total_max": 30,
        "max_total_dur":  30,
    },
    # Short video-to-video: 2 scenes × 8s = 16s total
    "short_veo": {
        "num_scenes_min": 2,
        "num_scenes_max": 2,
        "scene_dur_min":  8,
        "scene_dur_max":  8,
        "word_hint":      "16-20",
        "gen_type":       "AI_VIDEO",
        "target_total_min": 16,
        "target_total_max": 16,
        "max_total_dur":  16,
    },
    # Long image-to-video: exactly 16 scenes × 9-10s = ~150s for complete stories
    "long_img": {
        "num_scenes_min": 16,
        "num_scenes_max": 16,
        "scene_dur_min":  9,
        "scene_dur_max":  10,
        "word_hint":      "18-20",
        "gen_type":       "IMAGE_FOR_ZOOM",
        "target_total_min": 144,
        "target_total_max": 160,
        "max_total_dur":  160,
    },
    # Long video-to-video is intentionally unsupported for retention consistency.
    "long_veo": {
        "num_scenes_min": 16,
        "num_scenes_max": 16,
        "scene_dur_min":  9,
        "scene_dur_max":  10,
        "word_hint":      "18-20",
        "gen_type":       "AI_VIDEO",
        "target_total_min": 144,
        "target_total_max": 160,
        "max_total_dur":  160,
    },
}

FORMAT_CONFIG = _FORMAT_BASE  # kept for external imports


def _resolve_config(fmt: str, mode: str) -> dict:
    """Return format config for (fmt, mode) combination.
    mode: 'image' | 'video'
    """
    if fmt == "long" and mode == "video":
        mode = "image"
    if fmt == "short":
        key = "short_img" if mode == "image" else "short_veo"
    else:
        key = "long_img" if mode == "image" else "long_veo"
    return dict(_FORMAT_BASE[key])


def _get_art_style(category: str) -> str:
    return STYLE_MAP.get(category, DEFAULT_STYLE)


def _normalize_category(category: str | None) -> str:
    if not category:
        return "mystery_stories"
    aliases = {
        "bagwan_stories": "bhagwan_stories",
    }
    return aliases.get(category, category)


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
        if fmt == "long" and mode == "video":
            LOGGER.warning("Long video-to-video is disabled; forcing image mode for '%s'.", idea.title)
            mode = "image"
        cfg = _resolve_config(fmt, mode)
        category = _normalize_category(getattr(idea, "category", "mystery_stories"))
        try:
            idea.category = category
        except Exception:
            pass
        art_style = _get_art_style(category)
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
        category = _normalize_category(getattr(idea, "category", "mystery_stories"))
        hook = getattr(idea, "hook_hindi", "") or getattr(idea, "hook", "")
        twist = getattr(idea, "twist", "")
        conflict = getattr(idea, "core_conflict", "")
        moral = getattr(idea, "moral", "")
        moral_hindi = getattr(idea, "moral_hindi", "")
        audience_hook = getattr(idea, "audience_hook", "")
        return self._build_prompt_v2(
            idea=idea,
            fmt=fmt,
            cfg=cfg,
            art_style=art_style,
            schema=schema,
            is_long=is_long,
            category=category,
            hook=hook,
            conflict=conflict,
            twist=twist,
            moral=moral,
            moral_hindi=moral_hindi,
            audience_hook=audience_hook,
        )

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

    def _build_prompt_v2(
        self,
        idea: StoryIdea,
        fmt: str,
        cfg: dict,
        art_style: str,
        schema: str,
        is_long: bool,
        category: str,
        hook: str,
        conflict: str,
        twist: str,
        moral: str,
        moral_hindi: str,
        audience_hook: str,
    ) -> str:
        category = _normalize_category(category)
        mode = "video" if cfg["gen_type"] == "AI_VIDEO" else "image"
        retention_blueprint = self._retention_blueprint(fmt, mode, category)
        
        if not is_long:
            word_rules = (
                "- STRICT WORD BUDGET: The entire script voiceover across all 6 scenes must NOT exceed 95 words total.\n"
                "- SCENE WORD LIMIT: Each individual scene's voiceover MUST be strictly between 12 and 16 words.\n"
                "- If you write too many words, the voiceover will exceed the 30-second time limit, resulting in a critical failure."
            )
        else:
            word_rules = (
                "- STRICT WORD BUDGET: The entire script voiceover across all 16 scenes must NOT exceed 300 words total.\n"
                "- SCENE WORD LIMIT: Each individual scene's voiceover MUST be strictly between 15 and 20 words.\n"
                "- If you write too many words, the video will exceed the target limit, hurting audience retention."
            )

        duration_hint = (
            f"Target runtime: {cfg['target_total_min']}-{cfg['target_total_max']} seconds total. "
            f"Generate EXACTLY {cfg['num_scenes_min']} scenes, "
            f"each matching target {cfg['scene_dur_min']}s. "
            f"Each voiceover: {cfg['word_hint']} words."
        )
        
        tone_map = {
            "horror_stories":   "Atmospheric horror. Build dread slowly, focus on eerie visual cues and build up to a chilling twist.",
            "mystery_stories":  "Classic mystery. Drop subtle clues in context, lead up to a satisfying twist reveal.",
            "suspense_stories": "Unbearable psychological tension. Every scene raises stakes and leaves an open question.",
            "dark_facts":       "Expose dark side of history or the world. Shocking facts presented in an educational yet intense tone.",
            "psychological":    "Dimag ka khel (Mind game). Make the viewer question what is real. Deliver an emotional gut-punch.",
            "thriller_stories": "Fast-paced, urgent, and high-stakes. Make it feel like there is no room to breathe.",
            "crime_stories":    "Gritty crime details. Show the crime, investigation, and how justice is served cold.",
            "karma_stories":    "Poetic justice. The wrongdoer performs a bad action, and karma returns it with interest in a satisfying end.",
            "shocking_facts":   "Expose a sequence of unbelievable facts. Each scene details a new layer of shock.",
            "real_life_facts":  "Inspirational or unbelievable real events. Capture genuine human emotion and struggle.",
            "moral_stories":    "Emotional journey with a life lesson that lands hard and stays with the viewer.",
            "bhagwan_stories":  "Reverent, devotional, and emotionally uplifting. Show the power of faith, bhakti, or divine grace. The ending must feel sacred and complete.",
            "inspirational_stories": "Inspirational journey. Focus on resilience, overcoming massive struggles, finding hope, and uplifting the viewer's spirit.",
            "motivational_stories": "High-energy motivational narrative. Focus on the value of hard work ('parishram ka phal'), consistency, valuing time ('mulyawan samay'), ambition, and achieving success against all odds.",
        }
        viral_tone = tone_map.get(category, "Gripping story with a powerful ending.")
        
        uplifting_categories = {"inspirational_stories", "motivational_stories", "moral_stories"}
        if category in uplifting_categories:
            transform_instruction = (
                "  - EMOTIONAL HUMAN INTEREST (CRITICAL): If the story brief or title involves ordinary, mundane, or daily subjects (like a clock, a daily routine, simple hard work, or chores), you must build it into a high-stakes emotional human drama or a touching journey of struggle and resilience. E.g., if it's about a watch, make it about a son learning the value of time from his father's final watch, or a student's struggle to afford books. DO NOT turn it into a supernatural mystery, horror, or curse story. Keep it realistic, emotional, and inspiring."
            )
        else:
            transform_instruction = (
                "  - TRANSFORM MUNDANE/DOMESTIC TOPICS (CRITICAL): If the story brief or title involves mundane, domestic, household, or silly subjects (like kitchen utensils, cooking, traffic, simple daily routines), you MUST immediately transform it into a high-stakes supernatural, thriller, or mystery plot. E.g., if the title is about a kitchen pot, turn it into an ancient cursed vessel that traps souls, or a pot cooking a soup of lost memories. NEVER write a simple domestic, mundane, or boring story."
            )
        
        banned_phrases = [
            "Doston, kya aapne kabhi...", "Chaliye jaante hain...", "Aaj hum baat karenge...", 
            "Aaj ki kahani...", "Video achhi lagi toh subscribe karein...", "Comment mein batayein...",
            "Lekin tabhi...", "Aur phir...", "Ek din..."
        ]

        bad_vs_good_reference = """
BAD HINGLISH STYLE (Repetitive, filler-heavy, disjointed):
Scene 1: "Doston kya aapne kabhi socha hai ki nadi ka paani laal kyun ho gaya?" (Filler hook)
Scene 2: "Ek gaon mein Ramesh naam ka kisaan rehta tha." (Generic filler)
Scene 3: "Woh kisaan bahut garib tha aur kooda nadi mein phekta tha." (Slow pacing)
Scene 4: "Lekin ek din achanak nadi ka paani laal hone laga." (Repetitive transition)
Scene 5: "Ramesh ne jab yeh dekha toh woh bahut darr gaya." (Telling emotion instead of showing action)
Scene 6: "Nadi ka paani gaon mein ghus gaya aur sab doob gaya." (Unsatisfying, rushed resolution)

GOOD HINGLISH SHORT EXAMPLES (Direct, punchy, active, high tension, complete):

Example 1 (Mystery / Suspense Short - 6 Scenes):
Scene 1 [HOOK]: "Gaon ka ye kamra 20 saal se band tha... kyunki jo bhi andar gaya, zinda wapas nahi aaya."
Scene 2 [CONTEXT]: "Lekin ek raat ek aadmi ne darwaza tod diya... andar dhool thi... aur bilkul sannata."
Scene 3 [ESCALATE]: "Tabhi deewar par lagi ek tasveer chamakne lagi... tasveer mein wahi aadmi tha... lekin uski god mein ek chhota bachha bhi tha."
Scene 4 [TWIST]: "Use achanak sab yaad aa gaya... 20 saal pehle usne isi kamre mein apne bete ko akela band kar diya tha..."
Scene 5 [REVEAL]: "Tabhi peeche se kisi bachhe ne dheere se kaha... 'Papa... main abhi bhi aapka intezar kar raha hoon...'"
Scene 6 [ENDING]: "Agle din kamra phir band mila... lekin ab deewar ki tasveer mein do nahi... teen log khade the."

Example 2 (Moral / Growth Short - 6 Scenes):
Scene 1 [HOOK]: "Do beej ek saath mitti mein dabaye gaye... lekin sirf ek ped bana."
Scene 2 [CONTEXT]: "Pehla beej bola, 'Main bahar nahi aaunga... kahin baarish, dhoop ya log mujhe nuksan na pahuncha dein.'"
Scene 3 [ESCALATE]: "Doosra bola, 'Jo hoga dekha jayega.' Aur mitti cheerkar bahar nikal aaya."
Scene 4 [TWIST]: "Kuch mahino baad wahi chhota paudha vishal ped ban gaya... aur hazaron logon ko chhaya dene laga."
Scene 5 [REVEAL]: "Udhar pehla beej... darte-darte mitti mein hi sad gaya."
Scene 6 [ENDING]: "Yaad rakho... asafal hone ka darr, safalta ka sabse bada dushman hai."

Example 3 (Karma Short - 6 Scenes):
Scene 1 [HOOK]: "Ek ameer aadmi ne bhikhari ka aakhri sikka bhi chheen liya..."
Scene 2 [CONTEXT]: "Bhikhari muskuraya aur bola, 'Aaj tumne mera nahi... apna naseeb liya hai.'"
Scene 3 [ESCALATE]: "Usi shaam ameer aadmi ki tijori mein achanak aag lag gayi... karodon rupaye raakh ban gaye."
Scene 4 [TWIST]: "Ghabrakar woh usi bhikhari ko dhoondhne laga... lekin woh kahin nahi mila."
Scene 5 [REVEAL]: "Jahan bhikhari baitha karta tha... wahan sirf ek purani chitti padi thi."
Scene 6 [ENDING]: "Us par likha tha— 'Gareeb ka haq churaoge... toh kismat bhi tumhara saath chhod degi.'"

GOOD HINGLISH LONG EXAMPLE (Psychological / Mystery - 16 Scenes):
Scene 1 [HOOK]: "Us gaon mein ek ghar tha... jahan jo bhi raat bitata, subah uski umr 20 saal badh jaati thi."
Scene 2 [CONTEXT]: "Logon ne ghar todne ki koshish ki... lekin har subah woh phir se khada mil jata tha."
Scene 3 [INCITING]: "Ek patrakar sach jaanne pahuncha... camera chalu kiya... aur ghar ke andar chala gaya."
Scene 4 [CLUE_1]: "Andar sab kuch naya tha... lekin deewar par lagi ghadi 1986 par ruki hui thi."
Scene 5 [CLUE_2]: "Tabhi use apni hi bachpan ki photo dikhi... jabki woh kabhi is gaon aaya hi nahi tha."
Scene 6 [ESCALATE]: "Achanak oopar se kisi bachhe ki hansi sunai di..."
Scene 7 [FALSE_LEAD]: "Woh bhaaga... lekin darwaza gayab ho chuka tha."
Scene 8 [MIDPOINT]: "Ghar ki har deewar par ek hi tareekh likhi thi— 12 August 1986."
Scene 9 [SEARCH]: "Use yaad aaya... isi din uske pita achanak laapata hue the."
Scene 10 [COMPLICATION]: "Tabhi tehkhane mein ek purani diary mili... us par uske pita ka naam likha tha."
Scene 11 [CONFRONTATION]: "Diary mein aakhri line thi— 'Agar tum ye padh rahe ho... toh tum bhi bahar nahi ja paoge.'"
Scene 12 [CLIMAX]: "Usi samay camera apne aap record hone laga... lekin usmein patrakar dikhai hi nahi de raha tha."
Scene 13 [REVEAL]: "Usne sheeshe mein dekha... wahan uski jagah ek 70 saal ka boodha khada tha."
Scene 14 [RESOLUTION]: "Poora ghar kaampne laga... aur sabhi tasveeron ke log muskurane lage."
Scene 15 [CONSEQUENCE]: "Agle subah gaon walon ne ghar ka darwaza khola... patrakar kahin nahi tha... lekin deewar par ek nayi tasveer lag chuki thi."
Scene 16 [ENDING]: "Us tasveer mein patrakar muskura raha tha... aur neeche likha tha— 'Ab agle mehmaan ka intezar hai...'"
"""

        return f"""You are a master storyteller and viral content creator for 'Wonder Stories TV' - a Hindi YouTube channel producing HIGHLY VIRAL {category.replace('_', ' ').title()} content.

STORY BRIEF (THEME ONLY):
  Title: {idea.title}
  Category: {category}
  Opening Hook (Hindi): {hook}
  Core Conflict: {conflict}
  Twist/Revelation: {twist}
  Moral/Takeaway: {moral}
  Moral (Hindi): {moral_hindi}
  Viral Angle: {audience_hook}
  Spoken Style: Native Devanagari Hindi (e.g., "गाँव का ये कमरा...") for `voiceover_hindi`, and Conversational Romanized Hinglish (e.g., "Gaon ka ye kamra...") for `voiceover_hinglish`. Natural flow, short punchy sentences, zero filler.

CRITICAL CREATIVE LIBERTY DIRECTIVE:
  - Do NOT copy the opening hook or conflict word-for-word if they sound abstract, generic, or boring.
  - The STORY BRIEF is only a thematic seed. You have 100% creative liberty to craft a highly concrete, high-stakes, dramatic, spooky, or emotional narrative from it.
  - **LOGICAL AND COHESIVE NARRATIVE FLOW (MANDATORY)**: The story must read like a single, continuous, highly engaging narrative. Every scene's voiceover must flow naturally and logically from the previous one, building a cohesive storyline. Avoid disjointed, robotic, or template-like sentences. The narrative must make perfect logical sense (do not insert random, unrelated clauses like 'kahaniya sajiv ho uthin').
  - **NO SEMICOLONS OR WEIRD PUNCTUATION**: Never end a scene voiceover with a semicolon (`;`). Always end with a standard period (`.`) for Hinglish and a poorna viram (`।`) for Devanagari.
  - **NARRATIVE STORY ONLY (MANDATORY)**: You are strictly BANNED from writing listicles, lists of facts, educational lectures, or general explanations. Even for categories like `shocking_facts` or `dark_facts`, you MUST craft a gripping **character-driven narrative story** focusing on a specific individual (e.g., a specific merchant, a traveler, an officer, a scientist) who experiences the event.
  - **NATURAL HINGLISH GRAMMAR & GENDER CONGRUENCE**: The Hinglish script must have 100% correct grammar. Adjectives, verbs, and pronouns must agree with the gender of the noun. (e.g., "kitaab" is feminine, so use "tijori ke andar chhupi ek khufiya kitaab", NOT "chhupa"; "classroom" is masculine/neutral, so use "ek purane classroom", NOT "purani"). Avoid typos like "benda" for "banda", "musekarte" for "muskurate", "logoski" for "logon ki", "aakhrein" for "aawazein".
  - **BANNED PASSIVE EMOTIONS & METAPHORS**: You are strictly BANNED from writing script scenes describing abstract feelings, thoughts, or passive states (e.g., do NOT write: "he was sad", "he felt empty inside", "he realized", "he thought about life", "he looked at a sun ray", "his heart was filled with darkness"). This results in boring, unwatchable videos.
  - **MANDATORY PHYSICAL ACTIONS & VISUAL EVENTS**: Every scene voiceover MUST describe a specific physical action, event, or concrete dialogue (e.g., a vault catching fire, a mysterious letter appearing, a physical seed decaying or growing, a door vanishing, a mirror showing a different reflection). If a character is sad or greedy, show it through a physical action or event, never state it abstractly.
{transform_instruction}
  - **PHYSICAL RESOLUTION IN THE FINAL SCENE (MANDATORY)**: The final scene (Scene 6 for shorts, Scene 16 for longs) **MUST physically resolve the events of the plot**. Do NOT end the story with just a generic moral lesson, general advice, or abstract thought. The final scene must show the concrete aftermath, a physical climax, or a visual revelation (e.g., the cursed statue dissolving, the vault burning, the person vanishing, a new photo appearing). The story arc must feel completely closed, resolved, and tightly connected to the hook.
  - Make sure the plot is incredibly engaging and matches the pacing, tension, and completeness of the GOOD HINGLISH EXAMPLES below.
  - Every sentence must paint a clear picture and build anticipation for the next scene. Avoid abstract definitions or explanations. Show specific actions and events.

STORYTELLING DIRECTIVE:
  {viral_tone}

WORD COUNT RULES (CRITICAL):
  {word_rules}

BANNED FILLER AND TRANSITIONS:
  - Do NOT use introductory filler or greetings like: {", ".join([f'"{p}"' for p in banned_phrases[:6]])}
  - Do NOT start consecutive scenes with repetitive transition words like: {", ".join([f'"{p}"' for p in banned_phrases[6:]])}
  - Let each scene flow naturally into the next without using clunky transitional templates.

FORMAT REQUIREMENTS:
  {duration_hint}
  Generation type: {cfg['gen_type']}
  Visual style: {art_style}

SCRIPT-FIRST APPROACH:
  Step 1: Write the COMPLETE script scene-by-scene FIRST.
          - **DUAL-SCRIPT SCRIPT SENSITIVITY (MANDATORY)**:
            1. `voiceover_hindi` **MUST BE 100% WRITTEN IN NATIVE DEVANAGARI HINDI SCRIPT** (e.g., "गाँव का ये कमरा 20 साल से बंद था..."). You are STRICTLY BANNED from writing English characters, Roman characters, or Romanized Hinglish script in `voiceover_hindi`. It must be pure native Hindi script for TTS audio generation.
            2. `voiceover_hinglish` **MUST BE 100% WRITTEN IN ROMAN/LATIN HINGLISH SCRIPT** (e.g., "Gaon ka ye kamra 20 saal se band tha..."). You are STRICTLY BANNED from writing Devanagari script here. This is used for visual subtitles.
          - **EXPRESSIVE TTS PUNCTUATION (CRITICAL)**: To ensure the generated voiceover sounds highly dramatic, emotional, and naturally paced (rather than a flat, monotonous reading), you MUST inject expressive punctuation in both fields. Use ellipsis (`...`) for suspenseful pauses, hyphens/dashes (`—`) to separate shocking reveals, commas (`,`) for pacing, and exclamation marks (`!`) for intensity.
          - **NATURAL GRAMMAR & PHRASING (MANDATORY)**: The script MUST be written in grammatically correct, natural spoken Hinglish/Hindi. Do NOT generate word salads, disjointed clauses, or broken/weird grammar. Use common conversational words (e.g., "banda" not "benda", "muskurate" not "musekarte", "logon ki" not "logoski", "kapde" not "vastra").
          - Start DIRECTLY with the action or mystery in Scene 1. Hook the viewer in the first 3 seconds.
          - Vary the pace: fast for action/twist, slow/atmospheric for buildup.
          - Use punctuation for natural narrator pauses. Avoid complex tongue-twisters.
          - Ensure a complete story arc with a satisfying climax and resolution. The ending must feel complete, not cut off.
          - Devotional stories (bhagwan_stories) must end with an uplifting realization or divine blessing.
          - Karma stories must show logical poetic justice.

  Step 2: Describe a PERFECT CINEMATIC IMAGE for each scene based on the voiceover.
          - NO 3D animation, NO Pixar, NO anime, NO cartoons.
          - Gritty, photorealistic, cinematic, dramatic lighting.
          - **ETHNICITY & SETTINGS (MANDATORY)**: All people, characters, clothing, settings, and environments MUST be described as Indian (e.g., traditional Indian clothing, rural Indian settings, Indian faces) to match the cultural context of the Hindi storytelling. Do NOT describe Western, Caucasian, or Hollywood-like people or settings. You MUST explicitly use the word "Indian" or "authentic Indian" before every mention of a person, group, or setting (e.g., "Indian children", "Indian classroom", "Indian young girl", "Indian villagers") in EVERY scene prompt to guarantee correct style output.
          - **CHARACTER CONSISTENCY (MANDATORY)**: To ensure characters do not change faces, outfits, or appearances from scene to scene:
            1. Define a detailed, consistent physical description for the main character (and secondary characters, if any) in the `"character_appearance"` field of `story_metadata`.
            2. This description must include: gender, specific age (e.g., "28-year-old"), skin tone, hair style and color (e.g., "short messy black hair"), facial features (e.g., "clean-shaven", "short stubble beard"), and a specific outfit (e.g., "wearing a dark green woolen sweater").
            3. In EVERY scene's `ai_prompt` where the character is present, you MUST include the exact same physical description details (e.g., "a 28-year-old Indian man with short messy black hair, short stubble beard, wearing a dark green woolen sweater"). Never just write "an Indian man" or "the boy" without these specific details, as this causes the AI image generator to change their face and clothing.
            4. Keep the clothing and styling identical across all scenes unless the story explicitly spans different days/years (even then, keep physical features like eyes, facial hair, and hair style identical).
          - The visual must match the scene's emotional tone and describe the key focal point.

STYLE REFERENCE GUIDE:
{bad_vs_good_reference}

RETENTION BLUEPRINT:
{retention_blueprint}

Return ONLY valid JSON matching this schema exactly:
{schema}"""

    def _retention_blueprint(self, fmt: str, mode: str, category: str) -> str:
        category = _normalize_category(category)
        scenes = self._scene_blueprint(fmt, mode, category)
        lines = []
        for scene in scenes:
            lines.append(f"  {scene['scene_number']}. {scene['scene_beat']} - {scene['purpose']}")

        if fmt == "short" and mode == "video":
            lines.append("  Rule: exactly 2 scenes, total 16 seconds, no filler, answer the question immediately.")
        elif fmt == "short":
            lines.append("  Rule: exactly 6 scenes, total 30 seconds. Every scene must lead logically to the next, ending with complete satisfaction.")
            lines.append("  Rule: make every non-final scene end with a curiosity gap.")
        else:
            lines.append("  Rule: exactly 16 scenes, total ~150 seconds. Complete story arc with final resolution.")
            lines.append("  Rule: do not repeat details. Each scene must advance the story.")

        if category == "bhagwan_stories":
            lines.append("  Tone: reverent, devotional, uplifting, and respectful.")

        return "\n".join(lines)

    def _scene_blueprint(self, fmt: str, mode: str, category: str) -> list[dict]:
        category = _normalize_category(category)
        is_video = mode == "video"

        if fmt == "short" and is_video:
            beats = [
                ("HOOK", "Open with the strongest curiosity bomb and the most striking visual."),
                ("PAYOFF", "Reveal the full answer and close the story cleanly."),
            ]
        elif fmt == "short":
            beats = [
                ("HOOK", "Open with the most shocking detail, consequence, or question to capture attention instantly."),
                ("CONTEXT", "Set up the cause, inciting incident, or background of the mystery/story."),
                ("ESCALATE", "Raise the stakes, build suspense, or add a complication."),
                ("TWIST", "Deliver the shocking twist or unexpected turn of events."),
                ("REVEAL", "Reveal the truth, showing the final connection or resolution."),
                ("ENDING", "Close the loop with a satisfying, punchy final line or moral takeaway."),
            ]
        else:
            beats = [
                ("HOOK", "Open with the biggest curiosity gap to hook the audience."),
                ("CONTEXT", "Set up the characters, setting, or core theme of the mystery/fact."),
                ("INCITING", "Trigger the inciting incident that launches the narrative."),
                ("CLUE_1", "Reveal the first clue or anomaly."),
                ("CLUE_2", "Reveal the second clue or a contradiction."),
                ("ESCALATE", "Raise the stakes and build tension."),
                ("FALSE_LEAD", "Introduce a misleading theory or explanation."),
                ("MIDPOINT", "Shift the story's direction with a key reveal or event."),
                ("SEARCH", "Focus on characters investigating the situation."),
                ("COMPLICATION", "Add a major setback or new challenge."),
                ("CONFRONTATION", "Force the characters to face the threat or problem directly."),
                ("CLIMAX", "Deliver the highest point of conflict or key decision."),
                ("REVEAL", "Unveil the main twist or truth."),
                ("RESOLUTION", "Resolve the core conflict and answer outstanding questions."),
                ("CONSEQUENCE", "Show the aftermath and how the characters or world have changed."),
                ("ENDING", "End on a memorable line, lesson, or lingering thought."),
            ]

        scenes = []
        for idx, (beat, purpose) in enumerate(beats, 1):
            scenes.append(
                {
                    "scene_number": idx,
                    "scene_beat": beat,
                    "purpose": purpose,
                    "voice_hint": self._voice_hint_for_beat(category, beat),
                }
            )
        return scenes

    def _voice_hint_for_beat(self, category: str, beat: str) -> str:
        category = _normalize_category(category)
        beat = (beat or "").upper()

        if category == "bhagwan_stories":
            if beat in {"HOOK", "REVEAL", "CLIMAX", "PAYOFF"}:
                return "narrator_devotional"
            if beat in {"RESOLUTION", "ENDING"}:
                return "narrator_warm"
            return "narrator_devotional"

        if beat in {"HOOK", "REVEAL", "MIDPOINT", "CLIMAX", "PAYOFF", "FINAL_TWIST"}:
            return "narrator_intense"
        if beat in {"FALSE_LEAD", "ESCALATE", "SETBACK", "CONFRONTATION", "INCITING", "SEARCH", "NEW_CLUE", "SECOND_REVEAL"}:
            return "narrator_suspense"
        if beat in {"RESOLUTION", "AFTERMATH", "FINAL_ECHO", "ENDING", "CONSEQUENCE", "FINAL_CHOICE"}:
            return "narrator_warm"
        if beat in {"WHISPER"}:
            return "narrator_whisper"
        return "narrator_dramatic"

    def _duration_pattern(self, cfg: dict, count: int) -> list[int]:
        min_total = cfg.get("target_total_min", cfg["scene_dur_min"] * count)
        max_total = cfg.get("target_total_max", cfg["scene_dur_max"] * count)
        target_total = int(round((min_total + max_total) / 2))
        target_total = max(count * cfg["scene_dur_min"], min(target_total, count * cfg["scene_dur_max"]))

        durations = [cfg["scene_dur_min"]] * count
        extra = target_total - (count * cfg["scene_dur_min"])
        idx = 0
        while extra > 0 and count > 0:
            slot = idx % count
            if durations[slot] < cfg["scene_dur_max"]:
                durations[slot] += 1
                extra -= 1
            idx += 1
            if idx > count * max(1, cfg["scene_dur_max"] - cfg["scene_dur_min"] + 2):
                break
        return durations

    def _sfx_for_beat(self, beat: str) -> str:
        beat = (beat or "").upper()
        mapping = {
            "HOOK": "suspense_rise",
            "PAYOFF": "revelation_sting",
            "TWIST": "revelation_sting",
            "CLUE": "tension_build",
            "CLUE_1": "tension_build",
            "CLUE_2": "tension_build",
            "ESCALATE": "heartbeat",
            "FALSE_LEAD": "low_drum_hit",
            "REVEAL": "revelation_sting",
            "ENDING": "peaceful_end",
            "CONTEXT": "soft_underscore",
            "INCITING": "riser",
            "PERSONAL_STAKE": "emotional_swell",
            "SETBACK": "dramatic_hit",
            "MIDPOINT": "reveal_pad",
            "SEARCH": "pulse_loop",
            "COMPLICATION": "tension_build",
            "CONFRONTATION": "dramatic_hit",
            "CLIMAX": "revelation_sting",
            "RESOLUTION": "peaceful_end",
            "AFTERMATH": "soft_underscore",
            "FINAL_TWIST": "revelation_sting",
            "NEW_CLUE": "tension_build",
            "SECOND_REVEAL": "revelation_sting",
            "CONSEQUENCE": "soft_underscore",
            "FINAL_CHOICE": "emotional_swell",
            "FINAL_ECHO": "peaceful_end",
        }
        return mapping.get(beat, "suspense_music")

    def _fallback_voiceover_for_beat(
        self,
        idea: StoryIdea,
        beat: str,
        index: int,
        total: int,
        category: str,
        lang: str = "hinglish",
    ) -> str:
        category = _normalize_category(category)
        
        def is_devanagari(text: str) -> bool:
            return any('\u0900' <= char <= '\u097f' for char in text)
            
        hook_val = getattr(idea, "hook_hindi", "") or getattr(idea, "hook", "")
        twist_val = getattr(idea, "twist", "")
        moral_val = getattr(idea, "moral_hindi", "") or getattr(idea, "moral", "")
        title = getattr(idea, "title", "This story")
        
        if lang == "hindi":
            if hook_val and not is_devanagari(hook_val):
                hook_val = ""
            if twist_val and not is_devanagari(twist_val):
                twist_val = ""
            if moral_val and not is_devanagari(moral_val):
                moral_val = ""
        else:
            hook_val = getattr(idea, "hook", "") or getattr(idea, "hook_hindi", "")
            if hook_val and is_devanagari(hook_val):
                hook_val = ""
            twist_val = getattr(idea, "twist", "")
            if twist_val and is_devanagari(twist_val):
                twist_val = ""
            moral_val = getattr(idea, "moral", "") or getattr(idea, "moral_hindi", "")
            if moral_val and is_devanagari(moral_val):
                moral_val = ""

        if category == "bhagwan_stories":
            if lang == "hindi":
                if beat == "HOOK":
                    return hook_val or "क्या आपने कभी महसूस किया है कि कृपा सही वक्त पर आती है?"
                if beat in {"CONTEXT", "INCITING"}:
                    return f"यह भक्ति और विश्वास की कहानी है, {title}."
                if beat in {"CLUE_1", "CLUE_2", "ESCALATE"}:
                    return "एक छोटा सा संकेत मिला, और उसने सबका ध्यान खींच लिया।"
                if beat in {"FALSE_LEAD", "PERSONAL_STAKE", "SETBACK"}:
                    return "जितना समझ आया, उतना ही यह एहसास हुआ कि बात और गहरी है।"
                if beat in {"MIDPOINT", "SEARCH", "COMPLICATION", "TWIST", "REVEAL"}:
                    return twist_val or "तब समझ आया कि यह सिर्फ घटना नहीं, एक इशारा था।"
                if beat in {"CONFRONTATION", "CLIMAX"}:
                    return twist_val or "उसी पल भक्ति की असली ताकत सामने आ गई।"
                if beat == "AFTERMATH":
                    return "उस पल के बाद सबके दिल में एक नई शांति आ गई।"
                if beat == "FINAL_TWIST":
                    return "और इसी एक पल ने उनकी श्रद्धा को और गहरा कर दिया।"
                if beat == "NEW_CLUE":
                    return "फिर एक और छोटा इशारा मिला, जैसे भगवान ने दोबारा याद दिलाया हो।"
                if beat == "SECOND_REVEAL":
                    return "इस बार सच और भी साफ था, और सबने उसे दिल से महसूस किया।"
                if beat == "CONSEQUENCE":
                    return "उस संकेत के बाद उनकी जिंदगी पहले जैसी नहीं रही।"
                if beat == "FINAL_CHOICE":
                    return "अब उनके पास सिर्फ एक ही रास्ता था: विश्वास को अपनाना।"
                if beat == "FINAL_ECHO":
                    return "और यह याद रह गया कि कृपा हमेशा सही वक्त पर आती है।"
                return moral_val or "भगवान की कृपा सही वक्त पर ही मिलती है।"
            else:
                if beat == "HOOK":
                    return hook_val or "Kya aapne kabhi mehsoos kiya hai ki kripa sahi waqt par aati hai?"
                if beat in {"CONTEXT", "INCITING"}:
                    return f"Yeh bhakti aur vishwas ki kahani hai, {title}."
                if beat in {"CLUE_1", "CLUE_2", "ESCALATE"}:
                    return "Ek chhota sa sanket mila, aur usne sabka dhyan kheench liya."
                if beat in {"FALSE_LEAD", "PERSONAL_STAKE", "SETBACK"}:
                    return "Jitna samajh aaya, utna hi yeh ehsaas hua ki baat aur gehri hai."
                if beat in {"MIDPOINT", "SEARCH", "COMPLICATION", "TWIST", "REVEAL"}:
                    return twist_val or "Tab samajh aaya ki yeh sirf ghatna nahi, ek ishara tha."
                if beat in {"CONFRONTATION", "CLIMAX"}:
                    return twist_val or "Usi pal bhakti ki asli taakat saamne aa gayi."
                if beat == "AFTERMATH":
                    return "Us pal ke baad sabke dil mein ek nayi shanti aa gayi."
                if beat == "FINAL_TWIST":
                    return "Aur isi ek pal ne unki shraddha ko aur gehra kar diya."
                if beat == "NEW_CLUE":
                    return "Phir ek aur chhota ishara mila, jaise bhagwan ne dobara yaad dilaya ho."
                if beat == "SECOND_REVEAL":
                    return "Is baar sach aur bhi saaf tha, aur sabne use dil se mehsoos kiya."
                if beat == "CONSEQUENCE":
                    return "Us sanket ke baad unki zindagi pehle jaisi nahi rahi."
                if beat == "FINAL_CHOICE":
                    return "Ab unke paas sirf ek hi raasta tha: vishwas ko apnana."
                if beat == "FINAL_ECHO":
                    return "Aur yeh yaad reh gaya ki kripa hamesha sahi waqt par aati hai."
                return moral_val or "Bhagwan ki kripa sahi waqt par hi milti hai."

        if lang == "hindi":
            if beat == "HOOK":
                return hook_val or "क्या आपने कभी ऐसा देखा है जो पहली नज़र में मुमकिन न लगे?"
            if beat in {"PAYOFF", "TWIST", "REVEAL"}:
                return twist_val or "यहीं था जवाब और यहीं खत्म हुई कहानी।"
            if beat == "CONTEXT":
                return f"यह कहानी {title} से शुरू होती है, जब सब कुछ सामान्य लग रहा था।"
            if beat == "INCITING":
                return "फिर एक ऐसा पल आया जिसने सब कुछ बदल दिया।"
            if beat in {"CLUE_1", "CLUE_2", "CLUE"}:
                return "एक नया सुराग मिला, लेकिन उसने जवाब से ज़्यादा सवाल खड़े कर दिए।"
            if beat == "ESCALATE":
                return "अब समझ आया कि यह सिर्फ एक छोटी बात नहीं थी।"
            if beat == "FALSE_LEAD":
                return "सबको लगा जवाब मिल गया, पर वो सिर्फ पहला धोखा था।"
            if beat == "PERSONAL_STAKE":
                return "अब यह कहानी किसी एक की नहीं, सबकी बन चुकी थी।"
            if beat == "SETBACK":
                return "जितना करीब गए, उतना ही सच और दूर होता गया।"
            if beat == "MIDPOINT":
                return twist_val or "तब पता चला कि असली सच कुछ और ही था।"
            if beat == "SEARCH":
                return "सब लोग जवाब ढूंढने लगे, और वक्त कम होता गया।"
            if beat == "COMPLICATION":
                return "हर नई बात के साथ एक नई पहेली खुल रही थी।"
            if beat == "CONFRONTATION":
                return "अब सच से भागने का कोई रास्ता नहीं था।"
            if beat == "CLIMAX":
                return twist_val or "उसी पल सबसे बड़ा सच सामने आ गया।"
            if beat == "AFTERMATH":
                return "सच सामने आने के बाद सबके चेहरे पर अलग ही खामोशी थी।"
            if beat == "FINAL_TWIST":
                return "और फिर एक आखिरी मोड़ आया, जिसने पूरी कहानी को यादगार बना दिया।"
            if beat == "NEW_CLUE":
                return "फिर एक और छोटी सी जानकारी ने पूरी कहानी को दोबारा खोल दिया।"
            if beat == "SECOND_REVEAL":
                return twist_val or "और फिर दूसरा सच भी सामने आ गया।"
            if beat == "CONSEQUENCE":
                return "इस सच के बाद कुछ भी पहले जैसा नहीं रहा।"
            if beat == "FINAL_CHOICE":
                return "अब फैसला उनके हाथ में था: आगे बढ़ना या रुक जाना।"
            if beat in {"RESOLUTION", "ENDING", "FINAL_ECHO"}:
                return f"सीख: {moral_val}" if moral_val else "सीख: हमेशा अच्छे कर्म करें।"
            return "और फिर कहानी ने एक और नया मोड़ ले लिया।"
        else:
            if beat == "HOOK":
                return hook_val or "Kya aapne kabhi aisa dekha hai jo pehli nazar mein mumkin na lage?"
            if beat in {"PAYOFF", "TWIST", "REVEAL"}:
                return twist_val or "Yahin tha jawab aur yahin khatam hui kahani."
            if beat == "CONTEXT":
                return f"Yeh kahani {title} se shuru hoti hai, jab sab kuch normal lag raha tha."
            if beat == "INCITING":
                return "Phir ek aisa pal aaya jo sab kuch badal gaya."
            if beat in {"CLUE_1", "CLUE_2", "CLUE"}:
                return "Ek naya clue mila, lekin usne jawab se zyada sawal khade kar diye."
            if beat == "ESCALATE":
                return "Ab samajh aaya ki yeh sirf ek chhoti baat nahi thi."
            if beat == "FALSE_LEAD":
                return "Sabko laga jawab mil gaya, par woh sirf pehla dhoka tha."
            if beat == "PERSONAL_STAKE":
                return "Ab yeh kahani kisi ek ki nahi, sabki ban chuki thi."
            if beat == "SETBACK":
                return "Jitna kareeb gaye, utna hi sach aur door hota gaya."
            if beat == "MIDPOINT":
                return twist_val or "Tab pata chala ki asli sach kuch aur hi tha."
            if beat == "SEARCH":
                return "Sab log jawab dhoondhne lage, aur waqt kam hota gaya."
            if beat == "COMPLICATION":
                return "Har nayi baat ke saath ek nayi paheli khul rahi thi."
            if beat == "CONFRONTATION":
                return "Ab sach se bhagne ka koi raasta nahi tha."
            if beat == "CLIMAX":
                return twist_val or "Usi pal sabse bada sach saamne aa gaya."
            if beat == "AFTERMATH":
                return "Sach saamne aane ke baad sabke chehre par alag hi khaamoshi thi."
            if beat == "FINAL_TWIST":
                return "Aur phir ek aakhri mod aaya, jisne poori kahani ko yaadgar bana diya."
            if beat == "NEW_CLUE":
                return "Phir ek aur chhoti si detail ne poori kahani ko dobara khol diya."
            if beat == "SECOND_REVEAL":
                return twist_val or "Aur phir doosra sach bhi saamne aa gaya."
            if beat == "CONSEQUENCE":
                return "Is sach ke baad kuch bhi pehle jaisa nahi raha."
            if beat == "FINAL_CHOICE":
                return "Ab faisla unke haath mein tha: aage badhna ya ruk jaana."
            if beat in {"RESOLUTION", "ENDING", "FINAL_ECHO"}:
                return f"Seekh: {moral_val}" if moral_val else "Seekh: Hamesha acche karma karein."
            return "Aur phir kahani ne ek aur naya mod le liya."

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
                "estimated_duration_seconds": int(
                    round(
                        (
                            cfg.get("target_total_min", cfg["scene_dur_min"] * n_ex)
                            + cfg.get("target_total_max", cfg["scene_dur_max"] * n_ex)
                        )
                        / 2
                    )
                ),
                "thumbnail_prompt": f"Epic cinematic thumbnail for: {idea.title}. {art_style}. Bold dramatic composition. Include the Hindi title text prominently on the image in a highly stylish and attractive font.",
                "thumbnail_title_hindi": "Thumbnail text in Hindi (5 words max)",
                "character_appearance": "A detailed physical description of the main protagonist(s) for character consistency (e.g., 'A 28-year-old Indian man with short messy black hair, short stubble beard, wearing a dark green woolen sweater'). Use these exact descriptive elements consistently in every scene's ai_prompt where the character is visible.",
            },
            "scenes": [
                {
                    "scene_number": 1,
                    "generation_type": gen_type,
                    "expected_file": expected_file,
                    "duration_seconds": cfg["scene_dur_min"],
                    "voiceover_hindi": "इस दृश्य की पूरी कहानी देवनागरी लिपि (Hindi script) में यहाँ लिखें, जैसे: गाँव का ये कमरा 20 साल से बंद था...",
                    "voiceover_hinglish": "Gaon ka ye kamra 20 saal se band tha...",
                    "voice_hint": "narrator_dramatic",
                    "ai_prompt": f"Cinematic image description for scene 1. {art_style}. No text, no watermarks.",
                    "scene_beat": "HOOK",
                    "sfx_hint": "suspense_music",
                }
            ],
            "audio_effects_config": {
                "background_music": "suspense_loop",
                "music_volume": 0.28,
                "sfx_enabled": True,
                "fade_in_duration": 1.0,
                "fade_out_duration": 1.5,
            },
        }, ensure_ascii=False, indent=2)

    def _transliterate_to_devanagari(self, text: str) -> str:
        prompt = f"""You are a professional Hindi translator. Convert the following Hinglish (Hindi written in Roman/English script) text into native Hindi written in **Devanagari script**.
Do NOT translate the meaning to formal/pure Hindi; keep the exact spoken words and tone, just write them in Devanagari.
Inject dramatic punctuation (ellipses '...', em-dashes '—', exclamation marks '!') for TTS pacing.

Hinglish Text:
{text}

Return the output as a valid JSON object matching this schema exactly:
{{
  "devanagari": "translated Devanagari script here"
}}"""
        try:
            res = self.llm.generate_text(prompt)
            out_dict = json.loads(res.text)
            return out_dict.get("devanagari", "").strip()
        except Exception as e:
            LOGGER.error("Transliteration to Devanagari failed: %s", e)
            return ""

    # ──────────────────────────────────────────────────────────────────────────
    #  VALIDATION + REPAIR
    # ──────────────────────────────────────────────────────────────────────────

    def _validate_and_repair(
        self, payload: dict, idea: StoryIdea, cfg: dict, art_style: str
    ) -> dict:
        category = _normalize_category(getattr(idea, "category", "mystery_stories"))
        fmt = "short" if cfg["num_scenes_min"] <= 8 else "long"
        mode = "video" if cfg["gen_type"] == "AI_VIDEO" else "image"
        blueprint = self._scene_blueprint(fmt, mode, category)

        if "story_metadata" not in payload:
            payload["story_metadata"] = {
                "title": idea.title,
                "title_hindi": idea.title,
                "category": category,
                "hook_line": getattr(idea, "hook_hindi", ""),
                "twist_reveal": getattr(idea, "twist", ""),
                "moral": getattr(idea, "moral", ""),
                "moral_hindi": getattr(idea, "moral_hindi", ""),
                "total_scenes": cfg["num_scenes_min"],
                "estimated_duration_seconds": int(
                    round(
                        (
                            cfg.get("target_total_min", cfg["scene_dur_min"] * cfg["num_scenes_min"])
                            + cfg.get("target_total_max", cfg["scene_dur_max"] * cfg["num_scenes_min"])
                        )
                        / 2
                    )
                ),
                "thumbnail_prompt": f"Epic cinematic thumbnail: {idea.title}. {art_style}. Include the Hindi title text prominently on the image in a highly stylish and attractive font.",
                "thumbnail_title_hindi": idea.title[:30],
                "character_appearance": "",
            }

        if "character_appearance" not in payload["story_metadata"]:
            payload["story_metadata"]["character_appearance"] = ""

        # Ensure thumbnail prompt has Indian context
        thumb_p = payload["story_metadata"].get("thumbnail_prompt", "").strip()
        if thumb_p and "indian" not in thumb_p.lower():
            thumb_p = thumb_p.rstrip().rstrip(".")
            thumb_p += f", authentic Indian settings and Indian people"
            payload["story_metadata"]["thumbnail_prompt"] = thumb_p

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
            beat = scene.get("scene_beat", "")
            if not beat:
                beat = blueprint[min(i - 1, len(blueprint) - 1)]["scene_beat"]
                scene["scene_beat"] = beat
            # Ensure voiceover exists and is in the correct script representation
            voice_hindi = scene.get("voiceover_hindi", "").strip()
            if not voice_hindi or not any('\u0900' <= char <= '\u097f' for char in voice_hindi):
                # Try to transliterate Hinglish voiceover to Devanagari first to preserve the custom story content
                hinglish_source = scene.get("voiceover_hinglish", "").strip()
                if not hinglish_source or any('\u0900' <= char <= '\u097f' for char in hinglish_source):
                    if voice_hindi and not any('\u0900' <= char <= '\u097f' for char in voice_hindi):
                        hinglish_source = voice_hindi
                
                devanagari_rep = ""
                if hinglish_source and not any('\u0900' <= char <= '\u097f' for char in hinglish_source):
                    devanagari_rep = self._transliterate_to_devanagari(hinglish_source)
                
                if devanagari_rep:
                    scene["voiceover_hindi"] = devanagari_rep
                else:
                    scene["voiceover_hindi"] = self._fallback_voiceover_for_beat(idea, beat, i, len(scenes), category, lang="hindi")
                
            voice_hinglish = scene.get("voiceover_hinglish", "").strip()
            if not voice_hinglish or any('\u0900' <= char <= '\u097f' for char in voice_hinglish):
                if voice_hindi and not any('\u0900' <= char <= '\u097f' for char in voice_hindi):
                    scene["voiceover_hinglish"] = voice_hindi
                else:
                    scene["voiceover_hinglish"] = self._fallback_voiceover_for_beat(idea, beat, i, len(scenes), category, lang="hinglish")
            
            # Clean up trailing semicolons or periods that might mess with the voiceover
            vh = scene.get("voiceover_hindi", "").strip()
            vgh = scene.get("voiceover_hinglish", "").strip()
            if vh.endswith(";"):
                vh = vh[:-1].strip()
            if vgh.endswith(";"):
                vgh = vgh[:-1].strip()
            scene["voiceover_hindi"] = vh
            scene["voiceover_hinglish"] = vgh

            # Ensure AI prompt exists and contains Indian context and style tags
            ai_p = scene.get("ai_prompt", "").strip()
            if not ai_p:
                scene["ai_prompt"] = f"Scene {i} - {beat}: Cinematic {category.replace('_', ' ')} visual. {art_style}. No text, no watermarks."
            else:
                if "indian" not in ai_p.lower():
                    ai_p = ai_p.rstrip().rstrip(".")
                    ai_p += f", authentic Indian settings and Indian people"
                scene["ai_prompt"] = ai_p
            # Voice hint
            if "voice_hint" not in scene:
                scene["voice_hint"] = self._voice_hint_for_beat(category, beat)

        payload["scenes"] = scenes
        payload["story_metadata"]["category"] = category
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
        category = _normalize_category(getattr(idea, "category", "mystery_stories"))
        fmt = "short" if cfg["num_scenes_min"] <= 8 else "long"
        mode = "video" if cfg["gen_type"] == "AI_VIDEO" else "image"
        blueprint = self._scene_blueprint(fmt, mode, category)
        durations = self._duration_pattern(cfg, len(blueprint))

        scenes = []
        for i, scene_meta in enumerate(blueprint, 1):
            beat = scene_meta["scene_beat"]
            purpose = scene_meta["purpose"]
            ext = ".mp4" if cfg["gen_type"] == "AI_VIDEO" else "_image.png"
            scenes.append({
                "scene_number": i,
                "generation_type": cfg["gen_type"],
                "expected_file": f"{i}{ext}",
                "duration_seconds": durations[i - 1],
                "voiceover_hindi": self._fallback_voiceover_for_beat(idea, beat, i, len(blueprint), category, lang="hindi"),
                "voiceover_hinglish": self._fallback_voiceover_for_beat(idea, beat, i, len(blueprint), category, lang="hinglish"),
                "voice_hint": scene_meta["voice_hint"],
                "ai_prompt": f"Scene {i} - {beat}: {purpose}. Cinematic {category.replace('_', ' ')} visual. {art_style}. No text, no watermarks.",
                "scene_beat": beat,
                "sfx_hint": self._sfx_for_beat(beat),
            })

        return {
            "story_metadata": {
                "title": idea.title,
                "title_hindi": idea.title,
                "category": category,
                "hook_line": getattr(idea, "hook_hindi", "") or getattr(idea, "hook", ""),
                "twist_reveal": getattr(idea, "twist", ""),
                "moral": getattr(idea, "moral", ""),
                "moral_hindi": getattr(idea, "moral_hindi", ""),
                "total_scenes": len(blueprint),
                "estimated_duration_seconds": sum(durations),
                "thumbnail_prompt": f"Epic cinematic thumbnail: {idea.title}. {art_style}. Bold dramatic composition. Include the Hindi title text prominently on the image in a highly stylish and attractive font.",
                "thumbnail_title_hindi": idea.title[:30],
                "character_appearance": "",
            },
            "scenes": scenes,
            "audio_effects_config": self._default_sfx(idea),
        }

    def _default_sfx(self, idea: StoryIdea | None = None) -> dict:
        category = _normalize_category(getattr(idea, "category", "mystery_stories") if idea else "mystery_stories")
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
            "bhagwan_stories":  "devotional_cinematic",
            "inspirational_stories": "emotional_cinematic",
            "motivational_stories": "documentary_dramatic",
        }
        return {
            "background_music": music_map.get(category, "suspense_loop"),
            "music_volume": 0.28,
            "sfx_enabled": True,
            "fade_in_duration": 1.0,
            "fade_out_duration": 2.0,
        }
