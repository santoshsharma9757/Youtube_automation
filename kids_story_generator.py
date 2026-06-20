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

# ─── Diverse Character Name Pool ─────────────────────────────────────────────
# Each entry: (name, visual_description)
# Used to randomize the protagonist name so stories don't always say 'Rohan'

ADULT_CHARACTERS = [
    ("Arjun",    "a young adult animated character (age 20-25), lean build, short dark hair, sharp focused eyes, wearing a simple white kurta and navy trousers"),
    ("Vikram",   "a young adult animated character (age 22-27), tall and confident, wavy hair, wearing a simple cotton shirt and dhoti-style trousers, village setting"),
    ("Meera",    "a young adult animated character (age 20-24), graceful, long dark braid, expressive eyes, wearing a simple salwar kameez, warm village attire"),
    ("Priya",    "a young adult animated character (age 20-24), bright eyes, medium-length wavy hair, wearing a printed kurta and churidar, cheerful expression"),
    ("Rahul",    "a young adult animated character (age 20-25), friendly face, short curly hair, wearing a casual checked shirt and jeans, urban-rural blend"),
    ("Riya",     "a young adult animated character (age 20-24), sharp intelligent eyes, neat short hair, wearing a simple salwar kameez with a dupatta"),
    ("Kabir",    "a young adult animated character (age 22-26), artistic curly hair, thoughtful deep eyes, wearing a plain kurta and cotton trousers"),
    ("Ananya",   "a young adult animated character (age 20-24), soft warm expression, long loose hair, wearing a light cotton saree blouse and skirt combination"),
    ("Siddharth","a young adult animated character (age 22-27), studious look, round spectacles, short hair, wearing a crisp cotton shirt and trousers"),
    ("Kavya",    "a young adult animated character (age 20-24), bright determined eyes, hair tied in a bun, wearing a simple salwar kameez, ambitious expression"),
    ("Ishaan",   "a young adult animated character (age 20-25), energetic open face, spiky hair, wearing a casual graphic t-shirt and jeans"),
    ("Nandini",  "a young adult animated character (age 20-24), serene wise expression, long dark straight hair, wearing a traditional Indian blouse and skirt"),
]

KIDS_CHARACTERS = [
    ("Chintu",  "a short animated character with big round eyes, wearing a bright red t-shirt, chubby cheeks, innocent expression"),
    ("Bablu",   "a short animated character with a round face, big curious eyes, wearing a yellow striped t-shirt, eager friendly expression"),
    ("Pintu",   "a short animated character with messy hair, wearing a blue t-shirt with a star pattern, adventurous excited expression"),
    ("Monu",    "a short animated character with rosy cheeks, neat side-parted hair, wearing an orange kurta, shy but warm expression"),
    ("Guddu",   "a short animated character with big glasses, curious bright eyes, wearing a green t-shirt, bookish clever expression"),
]

SUPPORTING_CHARACTERS = {
    "Maa":    "a tall animated character wearing a beautiful yellow traditional saree, warm motherly smile, caring eyes, gentle hands",
    "Dadi":   "a tall elderly animated character with silver hair in a bun, wearing a simple cotton saree, warm wrinkled face, wisdom in eyes",
    "Golu":   "a chubby young adult animated character wearing a green striped kurta, cheerful round face, friendly smile",
    "Pinky":  "a young adult animated character with stylish long hair, wearing a casual jacket and jeans, bright curious eyes",
    "Mintu":  "a young adult animated character wearing a modern jacket, stylish hair, active energetic expression",
    "Ravi":   "a young adult animated character, serious studious face, short neat hair, wearing a plain shirt, reliable trustworthy expression",
    "Tara":   "a young adult animated character, calm and wise expression, long braided hair, wearing a simple salwar kameez",
    "Sonu":   "a chubby young adult animated character, cheerful dimpled face, wearing a casual t-shirt, loyal best-friend energy",
    "Devi":   "a young adult animated character, sharp intelligent eyes, hair tied back, wearing a printed kurta, determined expression",
    "Babu":   "a middle-aged animated character, kind weathered face, wearing a dhoti and cotton shirt, farmer background",
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
    # Long image-only: 8 scenes × 25s  = ~2.5-3.5 min Ghibli
    "long": {
        "num_scenes": 8,
        "scene_dur":  25,
        "word_hint":  "80-100",
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

        # ── Pick a varied character name from pool (hash-based for consistency) ──
        # Uses the idea title to deterministically pick a name — same title = same name.
        # Different titles = different names from the pool.
        title_hash = sum(ord(c) for c in idea.title)
        if is_made_for_kids:
            name_pool = KIDS_CHARACTERS
        else:
            name_pool = ADULT_CHARACTERS
        # Check if idea already has a char override from the story bank title
        chosen_idx  = title_hash % len(name_pool)
        char_name, char_desc = name_pool[chosen_idx]

        # ── Pick diverse supporting character ──────────────────────────────────
        supporting_pool = [
            k for k in SUPPORTING_CHARACTERS.keys()
            if k != char_name  # avoid same name as protagonist
        ]
        # For kids stories: prefer Maa/Dadi; for adult: prefer friends
        if is_made_for_kids:
            preferred_supports = ["Maa", "Dadi", "Golu", "Sonu"]
        else:
            preferred_supports = ["Maa", "Ravi", "Tara", "Golu", "Sonu", "Devi", "Mintu", "Pinky"]
        # Hash-based pick but offset by 3 so it's different from char pick
        support_pool_filtered = [s for s in preferred_supports if s in SUPPORTING_CHARACTERS]
        supporting_name = support_pool_filtered[(title_hash + 3) % len(support_pool_filtered)]
        supporting_desc = SUPPORTING_CHARACTERS[supporting_name]

        # ── Override characters if the title specifies them (e.g., "Sudama Aur Krishna") ──
        import re
        match_aur = re.search(r'^([A-Z][a-z]+)\s+(Aur|And)\s+([A-Z][a-z]+)', idea.title)
        match_ki = re.search(r'^([A-Z][a-z]+)\s+(Ki|Ka|Ke)\s+', idea.title)
        if match_aur:
            char_name = match_aur.group(1)
            char_desc = f"The main character {char_name}"
            supporting_name = match_aur.group(3)
            supporting_desc = f"The supporting character {supporting_name}"
        elif getattr(idea, "category", "") == "mythology" and match_ki:
            char_name = match_ki.group(1)
            char_desc = f"The legendary figure {char_name}"
        elif getattr(idea, "category", "") == "mythology":
            # Just extract the first word as the character name to be safe
            char_name = idea.title.split()[0]
            char_desc = f"The legendary figure {char_name}"

        LOGGER.info(
            "Generating story '%s' (fmt=%s, mode=%s, scenes=%s, dur=%ss, char=%s, support=%s)",
            idea.title, fmt, kids_mode, num_scenes, scene_dur, char_name, supporting_name
        )

        # ── Replace hardcoded names in idea fields with chosen char_name ─────────
        import re
        # Remove character names to make titles topic-focused
        base_title = re.sub(r'^(Chintu|Rohan|Kabir)\s+(Ka|Ki|Ke)\s+', '', idea.title, flags=re.IGNORECASE)
        base_title = re.sub(r'^(Chintu|Rohan|Kabir)\s+(Aur|And)\s+', '', base_title, flags=re.IGNORECASE)
        dynamic_title = re.sub(r'^(Chintu|Rohan|Kabir)\s+', '', base_title, flags=re.IGNORECASE)
        # Capitalize first letter just in case
        if dynamic_title:
            dynamic_title = dynamic_title[0].upper() + dynamic_title[1:]

        dynamic_adult_hook = getattr(idea, "adult_hook", "").replace("Chintu", char_name).replace("Rohan", char_name)
        dynamic_kids_hook  = getattr(idea, "kids_hook", "").replace("Chintu", char_name).replace("Rohan", char_name)
        dynamic_bad_habit  = getattr(idea, "bad_habit", "making a poor choice").replace("Chintu", char_name).replace("Rohan", char_name)
        dynamic_bad_hindi  = getattr(idea, "bad_habit_hindi", "ek buri aadat").replace("Chintu", char_name).replace("Rohan", char_name)

        schema   = self._schema_example(idea, cfg, art_style, char_name, char_desc, supporting_name, supporting_desc, dynamic_title)
        prompt   = self._build_prompt(
            idea, fmt, cfg, art_style, schema,
            char_name, char_desc, supporting_name, supporting_desc,
            is_made_for_kids, is_long,
            dynamic_title, dynamic_adult_hook, dynamic_kids_hook, dynamic_bad_habit, dynamic_bad_hindi
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
        dynamic_title: str,
        dynamic_adult_hook: str,
        dynamic_kids_hook: str,
        dynamic_bad_habit: str,
        dynamic_bad_hindi: str
    ) -> str:
        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        word_hint  = cfg["word_hint"]
        gen_type   = cfg["gen_type"]
        category   = getattr(idea, "category", "magical_adventure")
        magical_element = getattr(idea, "magical_element", "").strip()
        char_safety = "short animated character" if is_made_for_kids else "young adult animated character"

        is_ghibli  = (fmt == "long" and gen_type == "IMAGE_FOR_ZOOM")

        # ── Scene structure rules ─────────────────────────────────────────────
        rules_lines = [
            f"- Scene {i+1} → generation_type: \"{gen_type}\", duration_seconds: {scene_dur}"
            for i in range(num_scenes)
        ]
        scene_rules = (
            f"Scene structure RULES (ABSOLUTELY EXACTLY {num_scenes} scenes — "
            f"NO more NO less. If you write fewer than {num_scenes} scenes you have FAILED. "
            f"ALL of type {gen_type}):\n" + "\n".join(rules_lines)
        )

        # ── Word count enforcement with concrete example ──────────────────────
        word_count_rule = (
            f"VOICEOVER LENGTH (NON-NEGOTIABLE): EVERY scene voiceover MUST be EXACTLY {word_hint} words long.\n"
            f"Count carefully. Short one-line voiceovers are STRICTLY FORBIDDEN for {fmt.upper()} format.\n"
            f"\nEXAMPLE of correct {word_hint}-word voiceover in DEVANAGARI HINDI for Scene 1:\n"
            f"  BAD (12 words, Roman): 'Ek sundar gaon mein Rohan aur uska dost rehte the.'\n"
            f"  GOOD ({word_hint} words, Devanagari): 'एक छोटे से गाँव में {char_name} नाम का एक लड़का रहता था। उसका घर खेतों के पास था जहाँ सुबह की धूप सोने की तरह चमकती थी। गाँव के छोटे-छोटे घर, आम के पेड़ों की छाया और दूर से आती चिड़ियों की आवाज़ एक पुरानी कहानी सुनाती लगती थी। उसी गाँव में {supporting_name} नाम का उसका मित्र रहता था — साधारण सा लेकिन वफ़ादार, हर वक्त मुस्कुराता हुआ। {char_name} अक्सर सोचता था कि बिना मेहनत किए भी सफलता मिल सकती है।'\n"
            f"Write EVERY scene's voiceover in this style, length, and Devanagari script."
        )

        # ── Scene sequence guidelines ─────────────────────────────────────────
        if is_ghibli:
            # 8-act Ghibli arc for LONG_IMAGE format — guarantees 2.5-3.5 min video
            guidelines = [
                f"- Scene 1 (WORLD & CHARACTER) [{word_hint} words]: The story's very first sentence MUST open in a classic, warm Indian storytelling style ('Ek sundar aur shaant gaon mein, {char_name} naam ka ek ladka rehta tha...'). Paint the world richly: describe the village, the weather, the light, the sounds. Introduce {char_name}'s daily life, personality, relationships. Show their flaw '{getattr(idea, 'bad_habit', 'a bad habit')}' as a natural part of how they live. End scene 1 with the viewer feeling they know this person and this world.",
                f"- Scene 2 (FLAW IN DAILY LIFE) [{word_hint} words]: Show {char_name} living their flawed habit as completely normal. The world still feels safe. Introduce {supporting_name} warmly. Show the specific way {supporting_name} gently tries to bring {char_name}'s attention to the flaw — describe their expression, their voice, the moment. {char_name} brushes it off casually. Paint the everyday detail vividly — what does {char_name} see, smell, hear in this moment?",
                f"- Scene 3 (TRIGGER EVENT) [{word_hint} words]: Something small but consequential happens directly because of {char_name}'s flaw. Describe the exact moment it occurs — the specific action, the specific reaction of {supporting_name}. {char_name} still doesn't fully grasp the weight of it. But the viewer already feels the storm coming. End with a detail that makes the audience lean forward.",
                f"- Scene 4 (CONFLICT BEGINS) [{word_hint} words]: The problem from Scene 3 grows. Describe how {char_name}'s flaw is directly causing real pain or loss. {supporting_name}'s situation is clearly worsening. Show the emotional reactions — eyes, posture, voice. {char_name} starts to feel the first pang of guilt but still rationalizes. Describe the environment changing — weather, light, sound — to match the emotional shift.",
                f"- Scene 5 (ESCALATION) [{word_hint} words]: The situation gets much worse. Describe in vivid, cinematic detail how the consequences are now impossible to ignore. {supporting_name} is visibly in pain, danger, or deep distress directly because of {char_name}. Write the emotion on their faces, in their body language. {char_name} feels panic, shame, fear. The world around them reflects this — describe the light, the silence, the weight in the air.",
                f"- Scene 6 (DARK MOMENT) [{word_hint} words]: The absolute lowest point. All hope seems lost. Describe this scene as the most emotionally intense painting of the entire story. Show what {char_name} physically sees and feels when they realize the full truth of the damage their flaw caused to {supporting_name}. Write {char_name}'s internal devastation in vivid, poetic Hindi narration. The viewer must feel this like a punch to the heart.",
                f"- Scene 7 (TURNING POINT & SACRIFICE) [{word_hint} words]: {char_name} makes a brave, difficult, selfless decision OR discovers what {supporting_name} secretly did or sacrificed to protect {char_name}. Describe this revelation in full — what {char_name} discovers, how they discover it, the exact moment they understand the truth. The narration must feel like watching something beautiful crack open. This scene must earn the emotional payoff in Scene 8.",
                f"- Scene 8 (RESOLUTION + EARNED LESSON) [{word_hint} words]: {char_name} actively works to repair the damage through real, concrete actions — not just words. Describe what {char_name} does, step by step, and how {supporting_name} responds. The moral '{idea.moral}' must emerge from WHAT HAPPENS — never from a character stating it. End with a warm, beautiful image: the world restored, the relationship healed, the lesson felt in the viewer's heart like a long exhale.",
            ]
        elif num_scenes <= 3:
            # SHORT_VEO format (3 scenes)
            guidelines = [
                f"- Scene 1 (HOOK): Open mid-action, creating curiosity in the first 3 seconds with {char_name} doing {getattr(idea, 'bad_habit', 'something wrong')}.",
                f"- Scene 2 (CONFLICT): The conflict arises. The bad action causes a direct consequence or problem.",
                f"- Scene 3 (RESOLUTION + LESSON): {char_name} corrects the mistake and earns the moral lesson. Warm, punchy ending.",
            ]
        else:
            # SHORT_IMAGE format (5 scenes)
            guidelines = [
                f"- Scene 1 (HOOK): The story's very first sentence MUST open in a classic, warm Indian storytelling style (e.g., 'Ek sundar aur shaant gaon mein, {char_name} naam ka ek ladka rehta tha...'). Paint a peaceful village, introduce {char_name}, and immediately show them doing or choosing {getattr(idea, 'bad_habit', 'something wrong')} to create instant curiosity in the first 3 seconds.",
                f"- Scene 2 (PROBLEM): {supporting_name} warns {char_name}, or a direct problem occurs because of {char_name}'s actions.",
                f"- Scene 3 (ESCALATION): The problem gets worse. The consequences intensify, and tension peaks. Viewers should feel 'what happens next?'",
                f"- Scene 4 (LOWEST POINT OR TWIST): A twist or lowest point. {char_name} sees the truth and feels deep regret or experiences a surprising consequence.",
                f"- Scene 5 (RESOLUTION + LESSON): {char_name} resolves to do better. A warm close where the lesson is delivered naturally and earned.",
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

        # ── Category-specific narrative tone ──────────────────────────────────
        category_tone = ""
        if category == "mythology":
            category_tone = (
                "\nCATEGORY TONE — MYTHOLOGY:\n"
                "* Voiceover should feel EPIC, grand, reverential — like a Mahabharata narrator.\n"
                "* Use phrases like: 'Ek yug tha...', 'Us samay ki baat hai jab...', 'Dharti par devta chalte the...'\n"
                "* Characters should feel larger than life. Emotions are intense, consequences are cosmic."
            )
        elif category == "dadi_kahani":
            category_tone = (
                "\nCATEGORY TONE — DADI KI KAHANI:\n"
                "* Voiceover should feel WARM, cozy, nostalgic — like grandmother telling a bedtime story.\n"
                "* Use phrases like: 'Bahut purani baat hai...', 'Dadi kehti thi ki...', 'Chand ki roshni mein...'\n"
                "* The listener should feel wrapped in a blanket of love. Pace is gentle, words are chosen with care."
            )
        elif category == "horror":
            category_tone = (
                "\nCATEGORY TONE — HORROR/SPOOKY:\n"
                "* Voiceover should build SUSPENSE and MYSTERY — whisper-like, measured pace.\n"
                "* Use phrases like: 'Andheri raat mein...', 'Tabhi ek ajeeb si awaaz aayi...', 'Kisi ne peeche se bulaaya...'\n"
                "* Keep it family-friendly spooky — thrilling, not traumatizing. Mystery > gore."
            )
        elif category == "real_life":
            category_tone = (
                "\nCATEGORY TONE — REAL LIFE:\n"
                "* Voiceover should feel RELATABLE and EVERYDAY — like talking to a friend.\n"
                "* Use phrases like: 'Roz ki tarah subah hui...', 'Hum sab ke saath hota hai yeh...', 'Kya tumne kabhi socha...'\n"
                "* Ground the magical element in reality. Viewers must think: 'Yeh toh mere saath bhi hua hai!'"
            )
        elif category == "animal_tales":
            category_tone = (
                "\nCATEGORY TONE — ANIMAL TALES:\n"
                "* Voiceover should feel PLAYFUL, adventurous, full of wonder.\n"
                "* Use phrases like: 'Jungle ke beech mein...', 'Ek chhota sa...', 'Sabne socha yeh toh namumkin hai...'\n"
                "* Animals should have distinct personalities. Make kids fall in LOVE with the characters."
            )
        elif category == "family_funny":
            category_tone = (
                "\nCATEGORY TONE — FAMILY FUNNY:\n"
                "* Voiceover should have COMIC TIMING — pauses, exaggeration, relatable humor.\n"
                "* Use phrases like: 'Aur phir jo hua... haha...', 'Mummy ka chehra dekh kar...', 'Socho, kitna funny hoga...'\n"
                "* Comedy should come from situations, not mockery. Make BOTH kids and adults laugh out loud."
            )

        # ── Voice hint guidance ───────────────────────────────────────────────
        voice_hint_guide = (
            "\nVOICE HINT FIELD (REQUIRED for each scene):\n"
            "* Add a 'voice_hint' field to each scene JSON. Values: 'narrator_male', 'narrator_female', 'mother', 'old_wise'.\n"
            "* Default is 'narrator_male' for general narration.\n"
            "* Use 'mother' when the scene voiceover is primarily from the mother's perspective or dialogue.\n"
            "* Use 'old_wise' when a wise elder, guru, or magical figure speaks.\n"
            "* Use 'narrator_female' for soft, emotional scenes or Nani/Dadi narration.\n"
        )

        # ── Short cliffhanger rule ────────────────────────────────────────────
        short_rules = ""
        if not is_long:
            open_style = (
                "* For image-based shorts (IMAGE_FOR_ZOOM): Scene 1 MUST open in a classic storytelling style (e.g. 'Ek sundar aur shaant gaon mein, Chintu/Rohan naam ka...')."
                if gen_type == "IMAGE_FOR_ZOOM"
                else f"* For video-based shorts (AI_VIDEO): Scene 1 MUST open mid-action, BUT you MUST explicitly use the main character's name ({char_name}) in the very first sentence (e.g., '{char_name} hamesha khelo mein khoya rehta tha...'). Do NOT use 'wah' or 'usne' without introducing them first!"
            )
            
            # Use dynamic scene count to not break image shorts
            short_rules = (
                f"\nSHORT FORMAT RULES (CRITICAL):\n"
                f"* You only have {cfg['num_scenes']} scenes total.\n"
                f"* Despite the short length, you MUST tell a COMPLETE micro-story. Do not leave the story hanging!\n"
                f"* VARY YOUR STORY STRUCTURES: Do not use the exact same pattern every time. Mix it up! Use structures like:\n"
                f"   - Problem -> Escalation -> Surprising Resolution\n"
                f"   - Mystery Setup -> Climax -> Funny Reveal\n"
                f"   - Mid-Action Chase -> Catch -> Consequence/Moral\n"
                f"* Only Scene 1 or Scene 2 may end with a suspense hook. Do NOT force a question at the end of every scene.\n"
                f"{open_style}\n"
                f"* Keep voiceover PUNCHY and FAST-PACED — every word must earn its place."
            )

        if gen_type != "AI_VIDEO":
            # The classic epic story engine used for ALL image videos (both long and short)
            story_engine = textwrap.dedent(f"""
                STORY ENGINE (NON-NEGOTIABLE):
                * First decide one clear cause-and-effect chain:
                  flaw -> trigger -> consequence -> escalation -> twist/revelation -> repair.
                * Flaw: {dynamic_bad_habit} ({dynamic_bad_hindi})
                * Emotional payoff: {idea.moral} ({idea.moral_hindi})
                * {supporting_name} must matter emotionally. Their pain, sacrifice, or risk should make the viewer feel something.
                * If you use the supplied magical element "{magical_element or 'none'}", introduce it early and use it only to reveal or intensify a consequence already caused by {char_name}. It must never randomly solve the plot.
                * The twist must come from truth, sacrifice, discovery, or consequence. Never from a random monster, villain, or creature.
                * Each scene should make the next scene unavoidable.
                * Prefer concrete stakes over vague narration: broken trust, missed chance, hidden sacrifice, public embarrassment, lost time, family pain, hard-earned repair.
            """).strip()
        else:
            # The extremely simple engine ONLY for Veo video-to-video (3 scenes)
            story_engine = textwrap.dedent(f"""
                STORY ENGINE (NON-NEGOTIABLE FOR SHORTS):
                * You ONLY have 3 scenes. Keep the cause-and-effect chain EXTREMELY SIMPLE and linear: Action -> Immediate Consequence -> Lesson/Reaction.
                * Flaw: {dynamic_bad_habit} ({dynamic_bad_hindi})
                * Emotional payoff: {idea.moral} ({idea.moral_hindi})
                * DO NOT make unexplained jumps in location or time! If Scene 1 is in a bedroom, Scene 2 must naturally follow. Do not suddenly jump to a magical pond unless it makes logical sense in a 10-second window.
                * If you use the magical element "{magical_element or 'none'}", it must be organically tied to the immediate setting.
                * No complex subplots. Just ONE clear action, ONE clear reaction, and ONE clear resolution.
            """).strip()

        output_quality_rules = textwrap.dedent("""
            OUTPUT QUALITY RULES (CRITICAL SCRIPT FORMATTING):
            * Write voiceover like a real Hindi storybook author — literary, warm, vivid Devanagari Hindi.
            * NO ENGLISH LETTERS ALLOWED IN HINDI FIELDS: You MUST write the character's name in Devanagari script (e.g., write सिद्धार्थ instead of Siddharth, गोलू instead of Golu, रोहन instead of Rohan). Do not leave any A-Z characters in the voiceover_hindi field!
            * Show the lesson through events before stating it.
            * Avoid vague filler adjectives unless tied to a concrete visual or feeling.
            * Every ai_prompt must capture a dynamic frozen moment: visible action, facial emotion, environment, lighting, and mood.
            * No empty warning scenes. A warning must immediately lead to a consequence or decision.
            * No unexplained jumps in location, conflict, or tone.
        """).strip()

        prompt = textwrap.dedent(f"""
            Generate a HIGHLY ENGAGING, EMOTIONAL, and RETENTION-OPTIMIZED YouTube story for Wonder Stories TV.

            TARGET AUDIENCE:
            - Kids
            - Families
            - General Audience

            PRIMARY GOAL:
            Keep viewers emotionally invested from the first second until the final scene.

            STORY REQUIREMENTS:
            1. The first 3 seconds MUST create strong curiosity, emotion, suspense, mystery, shock, or anticipation.
            2. The viewer should continuously think: "What happens next?"
            3. Create relatable and memorable characters.
            4. The story must contain: Emotion, Conflict, Curiosity, Suspense, Struggle, Surprise, Resolution.
            5. Every scene must move the story forward.
            6. No filler scenes.
            7. No scenes where characters simply stand and talk.
            8. Every scene must contain at least one of: Action, Discovery, Emotion, Sacrifice, Mystery, Decision, Consequence, Surprise.
            9. Include at least one meaningful plot twist.
            10. Increase emotional intensity as the story progresses.
            11. The climax should be the most emotional moment.
            12. End with a satisfying emotional payoff and a powerful life lesson.
            13. The lesson must feel natural and earned, not forced.

            STRICT CAUSE AND EFFECT & RETENTION RULES (CRITICAL):
            * Do NOT generate random events.
            * Every single major event in the story MUST have a clear cause-and-effect relationship. Every scene must directly cause the next scene.
              - Example of GOOD cause-and-effect: Boy wastes time -> misses exam -> loses opportunity -> feels regret -> works harder -> succeeds later.
              - Example of BAD cause-and-effect (NONSENSE): Boy wastes time -> mother is angry -> a monster appears -> magic happens -> lesson.
            * No sudden scene jumps: Every scene must flow logically from the previous one. (e.g., if he stays up late in Scene 1/2, explicitly explain in Scene 3 that he overslept and ran late, causing him to fail the exam).
            * Early Object/Magic Integration: If a magical element or a key symbolic object (like "Papa's old alarm clock") is present in the brief, it MUST be introduced early in Scene 1 or Scene 2 as part of the setup. Do NOT suddenly introduce it in Scene 4 out of nowhere.
            * Do NOT suddenly introduce monsters, magic, villains, or new characters unless they are directly connected to the theme/bad habit of the story.
            * No random magical objects. If a magical element is used (like a watch or a tool), it must serve as a direct tool for the character's realization or struggle, not a random plot solver.
            * Avoid generic, preachy AI-style moral stories. Keep all situations and events realistic, logical, and grounded. Do NOT exaggerate numbers or facts in a way that is physically impossible or makes no sense (e.g., do NOT say a character slept for 12 days or stayed awake for a month; keep it to realistic human terms like 'der se utha' or 'pariksha chhoot gayi'). The story must feel like a real animated short film with emotional depth.
            * Viewers must constantly wonder: "What happens next?" Maintain suspense and keep emotional intensity rising in every scene until the final scene's emotional payoff.
            * Write beautiful, natural Devanagari Hindi (हिंदी में लिखें) that flows like a real Hindi storybook — NOT Roman transliteration, NOT English. Use words like 'एक सुंदर सुबह', 'वह गहरी नींद में', 'मिट्टी की खुशबू', 'रोशनी की लकीरें'. Avoid broken/garbled grammar.
            * CLASSIC INDIAN STORYTELLING OPENER: The story's very first sentence in Scene 1 MUST open in Devanagari Hindi with a classic, warm Indian storytelling style, such as: "एक छोटे से गाँव में अर्जुन नाम का एक लड़का रहता था..." or "बहुत पुरानी बात है..." — exactly like a real Hindi children's book.
            * SUPPORTING CHARACTER RULE (NON-NEGOTIABLE): {supporting_name} MUST be introduced naturally in Scene 1 or Scene 2 as part of {char_name}'s daily life — as a friend, sibling, neighbour, or classmate. They must NOT suddenly appear in Scene 3 or later as if from nowhere. Scene 1 should mention both characters.
            * Because Scene 1 happens, Scene 2 must happen. Because Scene 2 happens, Scene 3 must happen. Continue this chain until the ending.
            * The biggest emotional hit should come from a revealed consequence, sacrifice, or truth, not from random fantasy chaos.

            STORY STRUCTURE & SCENE SEQUENCE:
            Hook -> Character Introduction -> Problem -> Escalation -> Lowest Point -> Twist -> Resolution -> Lesson
            {scene_sequence}

            PREFERRED STORY THEMES:
            Karma, Kindness, Honesty, Friendship, Family Love, Mother's Sacrifice, Courage, Gratitude, Forgiveness, Helping Others, Village Life, Animal Rescue, Hard Work, Hope, Good Deeds Rewarded.

            AVOID:
            - Generic magical object stories
            - Random events without consequences
            - Weak endings
            - Repetitive scenes
            - Boring introductions
            - Excessive dialogue
            - Characters talking without action
            - Suddenly introducing monsters, magical objects, or creatures out of nowhere
            - Disconnected scenes (e.g. going from talking to a monster appearing with no explanation)

            VISUAL REQUIREMENTS:
            1. Every scene must feel like a frame from an animated movie.
            2. Use strong facial expressions and emotions.
            3. Use cinematic storytelling.
            4. Include dynamic actions instead of static poses.
            5. Describe: Character emotions, Actions, Environment, Lighting, Atmosphere, Mood.
            6. Maintain consistent character appearance across all scenes.
            7. Create visually rich, thumbnail-worthy moments.
            8. Prepend the following art style to EVERY scene's ai_prompt: "{art_style}"

            SUCCESS CRITERIA:
            The audience should be emotionally hooked within 3 seconds, stay curious throughout the story, and remember the lesson after the video ends.

            TARGET CHANNEL:
            Wonder Stories TV

            FORMAT INPUT:
            {fmt.upper()} ({num_scenes} scenes × {scene_dur}s each)

            STORY BRIEF:
            - Title: {dynamic_title}
            - Category: {category}
            - Bad habit/Problem: {dynamic_bad_habit} ({dynamic_bad_hindi})
            - Magical element: {magical_element or 'Do not force one if it weakens the story'}
            - Moral lesson: {idea.moral} ({idea.moral_hindi})
            - Adult emotional hook: {dynamic_adult_hook}
            - Kids emotional hook: {dynamic_kids_hook}

            CHARACTERS:
            - {char_name}: {char_desc}
            - {supporting_name}: {supporting_desc}

            {story_engine}
            {ghibli_rules}
            {category_tone}
            {voice_hint_guide}
            {short_rules}
            {output_quality_rules}

            CRITICAL QUALITY & SAFETY RULES:
            1. Voiceover Language, Tone & Book-Reading Style (MANDATORY):
               * LANGUAGE: DEVANAGARI HINDI ONLY (हिंदी में लिखें — देवनागरी लिपि). DO NOT write in Roman/English transliteration.
               * STYLE: Must feel like a warm, classic illustrated Hindi storybook read-aloud. Read like a real author like the following example:
                 "एक छोटे से गाँव में अर्जुन नाम का एक लड़का रहता था। वह बहुत बुद्धिमान था, लेकिन उसे मेहनत करना बिलकुल पसंद नहीं था। गाँव में ही उसका एक मित्र था, जिसका नाम {supporting_name} था। वह साधारण बुद्धि का था, लेकिन बहुत मेहनती।"
               * ABSOLUTELY NO Roman/English transliteration in voiceover. Pure Devanagari only.
               * Third-person narrator voice: warm, poetic, literary. NOT a cartoon script.
               * ABSOLUTE BAN ON DIRECT DIALOGUES AND QUOTES: No direct speech in quotes. Write indirectly:
                 WRONG: "माँ ने कहा, ‘बेटा, पढ़ाई करो।’"
                 RIGHT: "माँ ने प्यार से समझाया कि पढ़ाई कितनी ज़रूरी है।"
               * No robotic scene-ending questions like 'क्या होगा अब?' repeated every scene.
               * SUPPORTING CHARACTER: {supporting_name} MUST be mentioned by name in Scene 1 as {char_name}'s close friend/sibling. Never introduce them abruptly mid-story.
            2. Policy Safety: NEVER use 'boy', 'girl', 'child', 'kid', 'hug', 'kiss', 'embrace'
               in ai_prompt. Use: '{char_safety}', 'tall animated character',
               'high-five', 'smiling happily next to each other'.
            3. 100% original — different from any previous episode.{adult_rule}

            {word_count_rule}

            {scene_rules}

            CRITICAL WORD COUNT REMINDER: Each voiceover MUST be {word_hint} words. Count your words before outputting.
            Do NOT generate short 15-25 word voiceovers. They are WRONG.
            Do NOT generate only {num_scenes-2} or {num_scenes-3} scenes. You MUST generate EXACTLY {num_scenes} scenes.

            Hindi voiceover per scene: {word_hint} words. Devanagari Hindi ONLY (हिंदी में लिखें — देवनागरी लिपि).

            OUTPUT:
            Include these JSON fields:
            - story_metadata.title
            - story_metadata.thumbnail_title_devanagari
            - story_metadata.thumbnail_prompt
            - story_metadata.character_consistency_description
            - story_metadata.full_story_script
            - For every scene: emotion, action, voice_hint, voiceover_hindi, ai_prompt
            Return ONLY a raw JSON object (no markdown, no ```json wrapper) matching this schema exactly:
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
            scene.setdefault("emotion", self._default_scene_emotion(i + 1, num_scenes))
            scene.setdefault("action", self._default_scene_action(i + 1, num_scenes, idea, supporting_name))

            # Ensure voice_hint is present (default narrator_male)
            if "voice_hint" not in scene:
                vo_text = scene.get("voiceover_hindi", "").lower()
                if any(kw in vo_text for kw in ["maa ne kaha", "mummy ne", "mother", "maa ka"]):
                    scene["voice_hint"] = "mother"
                elif any(kw in vo_text for kw in ["dadi", "nani", "budhiya", "budhaa", "guru"]):
                    scene["voice_hint"] = "old_wise"
                elif any(kw in vo_text for kw in ["nani ki", "dadi ki", "ek purani"]):
                    scene["voice_hint"] = "narrator_female"
                else:
                    scene["voice_hint"] = "narrator_male"

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
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        payload["story_metadata"].setdefault(
            "character_consistency_description",
            self._character_consistency_text(idea, supporting_name, supporting_desc),
        )
        payload["story_metadata"].setdefault(
            "full_story_script",
            self._full_story_summary(idea, num_scenes, supporting_name),
        )
        payload["story_metadata"].setdefault(
            "thumbnail_title_devanagari",
            getattr(idea, "moral_hindi", "Seekh")
        )
        payload["story_metadata"].setdefault(
            "thumbnail_prompt",
            f"{art_style}, highly engaging and emotional thumbnail illustration for '{idea.title}', featuring {char_name} and {supporting_name} with vibrant colors, cinematic composition, text-safe space"
        )
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
        char_name: str,
        char_desc: str,
        supporting_name: str,
        supporting_desc: str,
        dynamic_title: str,
    ) -> str:
        num_scenes = cfg["num_scenes"]
        scene_dur  = cfg["scene_dur"]
        gen_type   = cfg["gen_type"]
        file_ext   = "mp4" if gen_type == "AI_VIDEO" else "jpg"

        scenes_list = [
            {
                "scene_number":     i + 1,
                "file_name":        f"scene{i+1}.{file_ext}",
                "generation_type":  gen_type,
                "duration_seconds": scene_dur,
                "emotion":          "emotion for this beat",
                "action":           "what visibly happens in this beat",
                "voice_hint":       "narrator_male",
                "voiceover_hindi":  f"दृश्य {i+1} के लिए हिंदी वॉइसओवर नीचे लिखें (देवनागरी लिपि में)",
                "ai_prompt":        f"{art_style}, scene {i+1} visual description here",
            }
            for i in range(num_scenes)
        ]

        return json.dumps(
            {
                "story_metadata": {
                    "title":                dynamic_title,
                    "protagonist_name":     char_name,
                    "thumbnail_title_devanagari": f"Write a catchy 2-3 word Hindi title in Devanagari script for {dynamic_title}",
                    "thumbnail_prompt":     f"{art_style}, highly engaging and emotional clickbait style thumbnail showing {char_name} and {supporting_name} in a dramatic village moment, cinematic composition, text-safe space",
                    "total_scenes":         num_scenes,
                    "global_animation_style": art_style,
                    "character_consistency_description": f"{char_name}: {char_desc}. {supporting_name}: {supporting_desc}. Keep faces, age group, clothing family, and relationship consistent in every scene.",
                    "full_story_script":    "पूरी कहानी का सारांश देवनागरी हिंदी में लिखें।",
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
        consequence = self._consequence_text(idea, supporting_name)

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
                "emotion":          self._default_scene_emotion(n, num_scenes),
                "action":           self._default_scene_action(n, num_scenes, idea, supporting_name),
                "voice_hint":       "narrator_male",
                "voiceover_hindi":  vo,
                "ai_prompt":        f"{art_style}, {ap}",
            }

        is_ghibli = art_style.startswith("Studio Ghibli")

        # Category-specific opening & tone for fallbacks
        _cat = getattr(idea, 'category', 'magical_adventure')

        if is_ghibli:
            # 6-scene Ghibli arc — with category-aware emotional tone
            if _cat == "mythology":
                opener = f"Bahut samay pehle ki baat hai, ek chote se gaon mein {char_name} naam ka ek yodha rehta tha, jiska dil sachai se bhara tha. Lekin uski agni pariksha abhi baaki thi..."
                closer = f"Aur us din se, {char_name} ka naam sabhi ke dilon mein amrit ho gaya. Kuch seekh humesha ke liye amar ho jaati hain. {moral_e}."
            elif _cat == "dadi_kahani":
                opener = f"Ek sundar aur shaant gaon mein, {char_name} naam ka ek ladka rehta tha. Har andheri raat mein, dadi use ek nayi aur seekh dene wali kahani sunati thi..."
                closer = f"Kahani sunte-sunte {char_name} ki aankhon mein pyaari neend thi, par dil mein ek nayi roshni thi. Woh seekh uski zindagi badal gayi. {moral_e}."
            elif _cat == "horror":
                opener = f"Bahut samay pehle, ek sunsaan gaon ke kone mein, {char_name} naam ka ek ladka rehta tha, jo kisi ki baat nahi sunta tha. Ek raat hawa mein ek ajeeb si khamoshi thi..."
                closer = f"Subah ki pehli kiran ke saath hi darr pighal gaya. {char_name} ne samjha ki darr asli nahi tha, par seekhi gayi himmat humesha asli rahegi. {moral_e}."
            elif _cat == "real_life":
                opener = f"Ek shaant aur pyaare gaon mein, {char_name} apne parivaar ke saath rehta tha. Roz ki tarah sab kuch thik chal raha tha, par uski ek aadat unpar bhaari padne wali thi..."
                closer = f"Us din ke baad {char_name} bilkul badal gaya. {supporting_name} ki aankhon mein sachhi khushi thi, kyunki asli badlaav dil se hota hai. {moral_e}."
            elif _cat == "animal_tales":
                opener = f"Ek ghane aur sundar jungle ke paas, ek chote se gaon mein {char_name} naam ka ek ladka rehta tha. Use jungle ke janwaron se bahut prem tha..."
                closer = f"Jungle mein khabar phail gayi ki sabhi jeev surakshit hain. Kyunki taakat size mein nahi, balki himmat aur dosti mein hoti hai. {moral_e}."
            elif _cat == "family_funny":
                opener = f"Ek chote se pyaare gaon mein, {char_name} apne chulbule parivaar ke saath rehta tha. Ek shaam usne ek aisi mazedaar galti ki jisne sabko hasne par majboor kar diya..."
                closer = f"Poora parivaar ek saath thahake lagakar hans raha tha. {char_name} ne sikha ki apno ke saath bitaya har pal anmol hota hai. {moral_e}."
            else:
                opener = f"Ek sundar aur shaant gaon mein, {char_name} apne parivaar ke saath rehta tha. Wo dil ka achha tha par usme ek buri aadat thi, jo thi {habit_h}."
                closer = f"{supporting_name} ne pyaar se {char_name} ko gale lagaya. Duniya fir se sundar lag rahi thi, kyunki asli badlaav dil se ho chuka tha. {moral_e}."

            scenes = [
                sc(1,
                   f"{opener} Rohan ko bilkul andaza nahi tha ki aaj ka din uski zindagi ko humesha ke liye badal dega.",
                   f"peaceful Indian village at golden dawn, {char_desc} looking slightly regretful near lush paddy fields, {supporting_desc} turning away sadly, dramatic warm amber light, serene atmosphere"),
                sc(2,
                   f"Usi shaam ek bade bargad ke ped ke neeche, {char_name} ko ek buddhi dadi mili. Unhone {char_name} ko ek sundar sa {magical} diya aur bataya ki yeh use wahi sach dikhayega jo sabse chhupa hai.",
                   f"elderly wise woman handing a glowing magical {magical} to {char_desc} at twilight, mystical golden sparks, sense of wonder and destiny, old banyan tree background"),
                sc(3,
                   f"Jaise hi {char_name} ne use chhua, use apni kiye hue faislon ka asar saaf dekhne laga. Apne aalsi aur laparwah vyavahar ki wajah se {supporting_name} ka uthaya dard dekhkar uska dil bhar aaya.",
                   f"{char_desc} on a difficult journey through magical landscapes inspired by Indian countryside, determined expression, {magical} glowing ahead as a guiding light, painterly Ghibli backgrounds"),
                sc(4,
                   f"Galti ka pashchatap bade dukh mein badal gaya jab use laga ki ab shayad bahut der ho chuki hai. {char_name} ne akele baithkar apne bure vyavahar par bahut dukh jataya aur khud ko badalne ki thaan li.",
                   f"{char_desc} sitting alone under a large old tree at dusk, head bowed in deep reflection, single golden leaf falling, melancholic yet beautiful light, echoing silence"),
                sc(5,
                   f"Bina kisi bahaane ke, {char_name} ne subah hote hi apni galti sudhari aur {supporting_name} ke paas jaakar dil se maafi maangi. Use samajh aa gaya tha ki mehnat aur sachai se hi rishte bachte hain.",
                   f"{char_desc} returning to {supporting_desc} with humble, open expression, warm morning light breaking through, sense of relief and resolution, golden countryside backdrop"),
                sc(6,
                   f"{closer}",
                   f"heartwarming scene of {char_desc} and {supporting_desc} standing together in a sunlit field, {magical} now dark and still, radiant smiles, golden hour light, butterflies, sense of peace and completion"),
            ]
        elif num_scenes <= 3:
            # Ultra-short 3-scene arc (video-to-video)
            scenes = [
                sc(1,
                   f"{char_name} ne socha {habit_h} bas chhoti si baat hai, lekin ussi pal {supporting_name} ko seedha nuksaan hua. {char_name} ka chehra turant utar gaya.",
                   f"{char_desc} caught in the exact moment of causing trouble through {habit}, a sudden consequence hitting {supporting_desc}, dynamic home setting, shock frozen on both faces"),
                sc(2,
                   f"Baat sirf daant tak nahi ruki. Jab {char_name} ko pata chala ki {supporting_name} ne chup-chaap uski galti sambhali, usse apne aap par sharm aane lagi.",
                   f"{char_desc} discovering the emotional cost of the mistake, watching {supporting_desc} quietly fixing the damage, guilt and realization, cinematic close-up"),
                sc(3,
                   f"Us din {char_name} ne sirf maafi nahi maangi, galti bhi theek ki. Tab jaakar {supporting_name} ke chehre par muskaan aayi. {moral_h}.",
                   f"{char_desc} actively repairing the damage and earning forgiveness from {supporting_desc}, warm light returning, relieved smiles, emotionally satisfying finish"),
            ]
        else:
            # Standard 5-scene short image arc
            scenes = [
                sc(1,
                   f"Sab kuch tab shuru hua jab {char_name} ne socha ki {habit_h} sirf chhoti si baat hai. Agle hi pal {supporting_name} ki aankhon mein ghabrahat dikhne lagi.",
                   f"{char_desc} mid-action while doing {habit}, a sudden problem beginning for {supporting_desc}, cinematic movement, tense home or street setting, sharp facial reactions"),
                sc(2,
                   f"{supporting_name} ne rokne ki koshish ki, par der ho chuki thi. {char_name} ki ek galti ne poori situation uljha di, aur ab use samajh hi nahi aa raha tha ki pehle kya bachaye.",
                   f"{supporting_desc} trying to stop the fallout while {char_desc} realizes the mess has grown, urgent body language, cluttered consequence-filled environment, rising tension"),
                sc(3,
                   f"Lekin asli jhatka tab laga jab {char_name} ko pata chala ki {supporting_name} chup-chaap uski wajah se hui pareshani khud jhel raha tha. Ab baat sirf galti ki nahi, rishte ki thi.",
                   f"{char_desc} witnessing {supporting_desc} silently bearing the cost of the mistake, emotional reveal, heavier lighting, strong close-up expressions, meaningful visual tension"),
                sc(4,
                   f"Phir sach aur bhi gehra nikla. Jise {char_name} roz ki aadat samajh raha tha, wahi {supporting_name} ki sabse badi takleef ban chuki thi. Yeh pal uske liye tootne jaisa tha.",
                   f"{char_desc} at the emotional lowest point after realizing the full damage, trembling regret, dim evening light, visible heartbreak on face, powerful cinematic still"),
                sc(5,
                   f"Isi liye agle subah {char_name} ne vaada nahi, kaam karke dikhaya. Jab usne sab theek kar diya, tab {supporting_name} ne use bharose se apnaya. {moral_h}.",
                   f"{char_desc} making amends through visible action and earning back trust from {supporting_desc}, sunrise light, emotional relief, richly cinematic family resolution"),
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
            "emotion":          self._default_scene_emotion(num, 5),
            "action":           self._default_scene_action(num, 5, idea, supporting_name),
            "voice_hint":       "narrator_male",
            "voiceover_hindi":  f"दृश्य {num} — जे से मुख्य स्थान से हिंदी वॉइसओवर लिखा जाएगा।",
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

        has_magic = magical and magical not in ("", "a magical object", "magical object")
        # Build 8 fallback scene descriptions for long format, 6 for others
        if has_magic:
            descs = [
                f"{char_desc} living peacefully in a sunlit Indian village, going about daily life with their habit of {habit}, warm morning light",
                f"{supporting_desc} watching {char_desc} with gentle concern, sitting in warm Indian home, soft indoor lighting",
                f"{char_desc} and {supporting_desc} in a tense moment as the habit causes a small but consequential problem",
                f"{char_desc} facing the growing consequence of {habit}, worried expression, the magical {magical} now visible in scene",
                f"{char_desc} seeing the full consequence of their actions, shocked and overwhelmed, dramatic lighting",
                f"{char_desc} sitting alone at twilight, head in hands, deep regret — the magical {magical} glowing dimly nearby",
                f"{char_desc} making a brave decision to fix the damage, the magical {magical} as a symbolic witness, hopeful golden light",
                f"{char_desc} and {supporting_desc} standing together, relationship restored, warm sunrise glow, peaceful resolution",
            ]
        else:
            descs = [
                f"{char_desc} living peacefully in a sunlit Indian village, the habit of {habit} woven naturally into daily life",
                f"{supporting_desc} watching {char_desc} with loving concern, a quiet moment in the home, afternoon golden light",
                f"{char_desc} experiencing the first consequence of {habit}, a small but significant shift in the world around them",
                f"{char_desc} seeing the problem grow, looking anxious and confused, streets or home background, tense atmosphere",
                f"{char_desc} confronting a painful truth about the damage their habit caused to {supporting_desc}, close-up emotional shot",
                f"{char_desc} sitting alone at dusk under a tree, tears in eyes, feeling deep regret and isolation",
                f"{char_desc} making amends — concrete action, working hard, approaching {supporting_desc} with humility and courage",
                f"{char_desc} and {supporting_desc} reunited warmly, faces showing relief and love, soft sunrise light, restored peace",
            ]
        base = descs[min(scene_num - 1, len(descs) - 1)]
        return f"{art_style}, {base}"

    def _default_scene_emotion(self, scene_num: int, total_scenes: int) -> str:
        if total_scenes == 3:
            return ["shock", "guilt", "relief"][min(scene_num - 1, 2)]
        if total_scenes == 5:
            return ["curiosity", "panic", "hurt", "regret", "hope"][min(scene_num - 1, 4)]
        # 8-scene Ghibli arc emotions
        return [
            "wonder",    # Scene 1: World & Character
            "unease",    # Scene 2: Flaw visible
            "tension",   # Scene 3: Trigger event
            "worry",     # Scene 4: Conflict begins
            "fear",      # Scene 5: Escalation
            "grief",     # Scene 6: Dark moment
            "resolve",   # Scene 7: Turning point
            "healing",   # Scene 8: Resolution
        ][min(scene_num - 1, 7)]

    def _default_scene_action(
        self,
        scene_num: int,
        total_scenes: int,
        idea: KidsStoryIdea,
        supporting_name: str,
    ) -> str:
        habit = getattr(idea, "bad_habit_hindi", "galti")
        if total_scenes == 3:
            actions = [
                f"Hero ki {habit} se turant nuksaan hota hai",
                f"Hero ko pata chalta hai ki {supporting_name} ne chup-chaap bojh uthaya",
                "Hero galti theek karke bharosa wapas jeetta hai",
            ]
            return actions[min(scene_num - 1, 2)]
        if total_scenes == 5:
            actions = [
                f"Hero ki {habit} se museebat shuru hoti hai",
                "Situation control se bahar nikalne lagti hai",
                f"{supporting_name} par asar khul kar saamne aata hai",
                "Sach sabse dardnaak roop mein samne aata hai",
                "Hero action lekar sab theek karne ki koshish karta hai",
            ]
            return actions[min(scene_num - 1, 4)]
        actions = [
            "Duniya aur khatra ek saath dikhte hain",
            "Rishta aur aadat ka tanav saaf hota hai",
            "Galti ka asar dikhne lagta hai",
            "Museebat gehri hoti hai",
            "Sach ya balidaan sab kuch badal deta hai",
            "Sudhaar aur maafi ki roshni laut aati hai",
        ]
        return actions[min(scene_num - 1, 5)]

    def _character_consistency_text(
        self,
        idea: KidsStoryIdea,
        supporting_name: str,
        supporting_desc: str,
    ) -> str:
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        char_desc = CHINTU_DESC if is_made_for_kids else ROHAN_DESC
        return (
            f"{char_name}: {char_desc}. "
            f"{supporting_name}: {supporting_desc}. "
            "Keep the same age group, face shape, clothing family, and emotional relationship across every scene."
        )

    def _consequence_text(self, idea: KidsStoryIdea, supporting_name: str) -> str:
        habit = getattr(idea, "bad_habit_hindi", "is buri aadat")
        moral = (getattr(idea, "moral_hindi", "") or "").lower()
        if "samay" in moral or "time" in moral:
            return f"{supporting_name} ek zaroori kaam ke liye intezar karta raha, aur {habit} ne sab kuch der se kar diya"
        if "maa" in moral or "family" in moral or "parivaar" in moral:
            return f"{supporting_name} ne apni takleef chhupa kar ghar sambhala, jabki {habit} ne uska bojh aur badha diya"
        if "mehnat" in moral or "hard work" in moral:
            return f"{supporting_name} ki mehnat daav par lag gayi, kyunki {habit} ne mauka haath se nikal diya"
        return f"{supporting_name} ko us galti ka seedha nuksaan uthana pada, jo {habit} se shuru hui thi"

    def _full_story_summary(self, idea: KidsStoryIdea, num_scenes: int, supporting_name: str) -> str:
        is_made_for_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_made_for_kids else "Rohan"
        habit_h = getattr(idea, "bad_habit_hindi", "ek buri aadat")
        consequence = self._consequence_text(idea, supporting_name)
        if num_scenes <= 3:
            return (
                f"{char_name} ki {habit_h} se turant museebat khadi hoti hai. "
                f"Phir use pata chalta hai ki {supporting_name} ne uski galti ka bojh khud uthaya. "
                f"Aakhir mein {char_name} maafi maangne ke saath galti theek bhi karta hai, aur tab usse sachchi seekh milti hai."
            )
        return (
            f"{char_name} apni {habit_h} ko halka samajhta hai, lekin jaldi hi us aadat ka asar {supporting_name} par dikhne lagta hai. "
            f"Jab sach khulta hai ki {consequence}, tab {char_name} toot kar apni galti samajhta hai. "
            f"Climax mein woh bhaagne ke bajay zimmedari leta hai, sab theek karta hai, aur earned tareeke se {idea.moral_hindi} ki seekh jeetta hai."
        )

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
        art_style = _art_style(fmt, kids_mode)
        title_h = getattr(idea, "moral_hindi", "Kahani")
        return {
            "title":                 idea.title,
            "thumbnail_title_devanagari": title_h,
            "thumbnail_prompt":      f"{art_style}, highly engaging and emotional thumbnail illustration for '{idea.title}', featuring {char_name} and {supporting_name} with vibrant colors, cinematic composition, text-safe space",
            "channel":               "Wonder Stories TV",
            "format":                fmt,
            "total_scenes":          cfg["num_scenes"],
            "global_animation_style": art_style,
            "character_consistency_description": self._character_consistency_text(idea, supporting_name, supporting_desc),
            "full_story_script":     self._full_story_summary(idea, cfg["num_scenes"], supporting_name),
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
            "sfx_scene_4":      random.choice(sfx_vals),
            "sfx_scene_5":      random.choice(sfx_vals),
            "sfx_scene_6":      random.choice(sfx_vals),
            "sfx_scene_7":      random.choice(sfx_vals),
            "sfx_scene_8":      "happy_celebration.mp3",
        }
