"""
kids_seo_generator.py  –  Wonder Stories TV
============================================
Generates maximum-reach YouTube SEO metadata for Wonder Stories TV.

Key improvements over old version:
  - 35+ tags (was 15)
  - 500+ char descriptions with adult_hook layer
  - made_for_kids = False ALWAYS (family content, not COPPA-tagged)
  - Category: 1 (Film & Animation)
  - Facebook-specific Reels description generated separately
  - Title formula: [Hook Phrase] | [Story Name] | Wonder Stories TV
  - Hashtags optimized per format (short vs long)
  - Policy-safe: no keyword stuffing, accurate titles
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from config import AppConfig
from kids_idea_generator import KidsStoryIdea
from kids_story_generator import KidsStoryPlan
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)

CHANNEL_NAME = "Wonder Stories TV"
CHANNEL_HANDLE = "@WonderStoriesTV"
CHANNEL_TAG = "#WonderStoriesTV"


@dataclass(slots=True)
class KidsSeoPackage:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    primary_keyword: str
    language_code: str = "hi"
    audio_language_code: str = "hi"
    content_style: str = "family_story"
    made_for_kids: bool = False          # ALWAYS False — family content, not COPPA-tagged
    facebook_description: str = ""       # Separate FB Reels caption

    @classmethod
    def from_dict(cls, data: dict) -> KidsSeoPackage:
        # Ignore any extra fields present in data
        valid_keys = {f for f in cls.__match_args__} if hasattr(cls, "__match_args__") else set(cls.__annotations__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class KidsSeoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate(self, idea: KidsStoryIdea, plan: KidsStoryPlan) -> KidsSeoPackage:
        LOGGER.info("Generating Wonder Stories TV SEO for '%s'", idea.title)

        is_short = idea.video_type == "short"
        is_long  = idea.video_type in ("long", "series")
        category = getattr(idea, "category", "magical_adventure")
        adult_hook = getattr(idea, "adult_hook", "")
        format_label = {
            "short":  "YouTube Short (max 35 seconds)",
            "mini":   "YouTube video (3-5 minutes)",
            "long":   "YouTube video (8-12 minutes) with mid-roll ads",
            "series": "YouTube series episode (12-18 minutes)",
        }.get(idea.video_type, "YouTube video")

        primary_keyword = self._build_primary_keyword(idea, category)

        # Fetch the dynamically generated character name from the story metadata, fallback to Chintu/Rohan if not found
        is_kids = getattr(idea, "made_for_kids", False)
        char_name = plan.story_metadata.get("protagonist_name", "Chintu" if is_kids else "Rohan")

        clean_title = plan.story_metadata.get("title", idea.title)
        prompt = (
            f"You are a top YouTube SEO expert for the family storytelling channel '{CHANNEL_NAME}'.\n"
            f"Generate maximum-reach SEO metadata for a {format_label}.\n\n"
            f"Story: {clean_title}\n"
            f"Main Character: {char_name}\n"
            f"Category: {category}\n"
            f"Magical element: {getattr(idea, 'magical_element', '')}\n"
            f"Moral: {idea.moral} ({idea.moral_hindi})\n"
            f"Adult hook (why adults watch): {adult_hook}\n"
            f"Primary keyword: {primary_keyword}\n\n"
            f"STRICT SEO RULES:\n"
            f"1. Title: Must strictly follow the template: [English Title] | [Hindi Title in Devanagari Script] | [Related Concept/Hook in Hinglish or Hindi] | {CHANNEL_NAME} #[One Hashtag]\n"
            f"   - The final hashtag must be exactly one hashtag (e.g. '#shorts' for Shorts, or '#moralstories' / '#hindistories' for longer formats).\n"
            f"   - Keep it extremely catchy and total title length MUST be under 95 characters.\n"
            f"   - Example for Shorts: '{idea.title} | कमरे की सफाई | Kamre Ki Safai | Wonder Stories TV #shorts'\n"
            f"   - Example for Long: '{idea.title} | जादुई स्नैक बॉक्स | Healthy Choices | Wonder Stories TV #moralstories'\n"
            f"2. YouTube Description (Minimum 600 characters). Structure it beautifully as follows:\n"
            f"   - A powerful hook/question to make viewers watch till the end.\n"
            f"   - Story Summary (English & Hindi): 3-4 sentences outlining the plot without spoiling the ending.\n"
            f"   - Moral Lesson (English & Hindi).\n"
            f"   - Search terms & Keywords (write a natural paragraph incorporating high-volume search terms related to {category}, moral stories, kids stories in hindi, and {primary_keyword}).\n"
            f"   - CTA: '👉 Subscribe to Wonder Stories TV for daily family stories: {CHANNEL_HANDLE}'\n"
            f"   - Hashtags: 5-8 relevant hashtags, starting with '#WonderStoriesTV' and '#HindiMoralStory'.\n"
            f"3. Tags: Exactly 35 tags mixing: Hindi search terms, English search terms, "
            f"   character tags ({char_name.lower()}), category tags, moral story tags, animated story tags, "
            f"   festival/season tags if relevant. Each tag max 40 chars.\n"
            f"4. Hashtags: 8-10 hashtags for database records. Must include: #WonderStoriesTV #HindiMoralStory #{char_name}Stories\n"
            f"5. Facebook description: Short, highly engaging caption. \n"
            f"   - If this is a Short/Mini, use: 'Short punchy version (max 200 chars) with 5-6 emoji, Hindi text, and Facebook Reels hashtags like #Reels #FBViral #Shorts #HindiKahani'.\n"
            f"   - If this is a Long format, use: 'A warm, engaging caption (300 chars) asking the audience to share with family. Use tags like #FacebookVideo #FamilyContent #HindiStories #MoralStory #WonderStoriesTV'.\n"
            f"6. Return ONLY strict JSON with keys: title, description, tags, hashtags, "
            f"   primary_keyword, facebook_description. No markdown wrapper.\n"
            f"7. NEVER use 'made for kids' or COPPA language. This is family content for all ages."
        )

        def _fallback():
            return self._fallback_payload(idea, primary_keyword, is_short, is_long, category)

        payload, provider = build_json_with_fallback(self.llm, prompt, _fallback, "wonder-seo")
        LOGGER.info("Wonder Stories SEO provider: %s", provider)

        title = self._clean_title(payload.get("title", ""), idea, is_short)
        description = self._clean_text(payload.get("description", ""))
        if len(description) < 200:
            description = self._fallback_description(idea, primary_keyword, is_short, category)

        tags = self._normalize_tags(payload.get("tags", []), idea, category)
        hashtags = self._normalize_hashtags(payload.get("hashtags", []), is_short, is_kids)
        hashtag_str = " ".join(hashtags)
        if hashtag_str and hashtag_str.lower() not in description.lower():
            description = f"{description}\n\n{hashtag_str}"

        facebook_description = self._clean_text(payload.get("facebook_description", ""))
        if not facebook_description:
            facebook_description = self._fallback_facebook_description(idea, hashtags, is_short)

        return KidsSeoPackage(
            title=title,
            description=description,
            tags=tags,
            hashtags=hashtags,
            primary_keyword=primary_keyword,
            language_code="hi",
            audio_language_code="hi",
            content_style="family_story",
            made_for_kids=getattr(idea, "made_for_kids", False),
            facebook_description=facebook_description,
        )

    # ─── Keyword Builder ──────────────────────────────────────────────────────

    def _build_primary_keyword(self, idea: KidsStoryIdea, category: str) -> str:
        magical = getattr(idea, "magical_element", "")
        category_keywords = {
            "magical_adventure": f"{magical.lower()} hindi moral story" if magical else "jadui kahani hindi moral",
            "mythology": "indian mythology story hindi animated",
            "dadi_kahani": "dadi ki kahani hindi animated",
            "real_life": "bacchon ki kahani hindi moral animated",
            "family_funny": "funny family story hindi animated",
            "animal_tales": "animal moral story hindi kids animated",
            "mystery": "mystery story hindi kids animated",
            "seasonal": "festival story hindi animated kids",
            "horror": "spooky horror story hindi kids animated",
        }
        return category_keywords.get(category, "hindi moral story kids animated")

    # ─── Fallbacks ────────────────────────────────────────────────────────────

    def _fallback_payload(self, idea: KidsStoryIdea, keyword: str, is_short: bool, is_long: bool, category: str) -> dict:
        return {
            "title": self._fallback_title(idea, is_short),
            "description": self._fallback_description(idea, keyword, is_short, category),
            "tags": self._baseline_tags(idea, category),
            "hashtags": self._baseline_hashtags(is_short),
            "primary_keyword": keyword,
            "facebook_description": self._fallback_facebook_description(idea, self._baseline_hashtags(is_short)),
        }

    def _fallback_title(self, idea: KidsStoryIdea, is_short: bool) -> str:
        eng_title = idea.title
        is_kids = getattr(idea, "made_for_kids", False)
        hindi_title = "रोहन की नई कहानी" if not is_kids else "चिंटू की कहानी"
        related = str(getattr(idea, "topic", "Moral Story")).title()
        hashtag = "#shorts" if is_short else "#moralstories"
        base = f"{eng_title} | {hindi_title} | {related} | {CHANNEL_NAME} {hashtag}"
        return base[:95]

    def _fallback_description(self, idea: KidsStoryIdea, keyword: str, is_short: bool, category: str) -> str:
        magical = getattr(idea, "magical_element", "jaadu")
        moral_h = idea.moral_hindi
        is_kids = getattr(idea, "made_for_kids", False)
        char_name = "Chintu" if is_kids else "Rohan"

        eng_summary = f"Watch this engaging family animated story where {char_name} learns a life-changing moral lesson with the help of a magical {magical}."
        hindi_summary = f"आज की कहानी में देखें कि कैसे {char_name} को एक जादुई {magical} की मदद से अपनी गलतियों का एहसास होता है और उसकी जिंदगी बदल जाती है।"

        desc = (
            f"🔥 {hindi_summary}\n\n"
            f"📖 Summary (English):\n{eng_summary}\n\n"
            f"📖 कहानी का सारांश (Hindi):\n{hindi_summary}\n\n"
            f"💡 Moral Lesson:\n"
            f"• English: {idea.moral}\n"
            f"• Hindi: {moral_h}\n\n"
            f"✨ Subscribe to Wonder Stories TV for daily family-friendly stories: {CHANNEL_HANDLE}\n"
            f"🔔 Hit the bell icon to stay updated with all new stories!\n\n"
            f"🔍 Search Terms & Keywords: Watch the best {keyword} on Wonder Stories TV. If you love moral story hindi, hindi animation, kids stories, bedtime stories, and {idea.title.lower()}, you will love this emotional journey."
        )
        return desc

    def _fallback_facebook_description(self, idea: KidsStoryIdea, hashtags: list[str], is_short: bool) -> str:
        magical = getattr(idea, "magical_element", "jaadu")
        is_kids = getattr(idea, "made_for_kids", False)
        audience_hashtags = "#MoralStory #WonderStoriesTV #BacchonKiKahani" if is_kids else "#MoralStory #WonderStoriesTV #HindiStories"
        
        if is_short:
            fb_hashtags = f"#Reels #FBViral #HindiKahani #Shorts {audience_hashtags}"
            intro = "✨ Ek aur magical short story! 🌟"
        else:
            fb_hashtags = f"#FacebookVideo #FamilyContent #HindiKahani {audience_hashtags}"
            intro = "🎥 Grab your snacks for this beautiful full story! ❤️✨"
            
        return (
            f"{intro} {idea.title}! Aaj ki kahani ne dil jeet liya! "
            f"Jaadu ka {magical} aur ek bada sabak! Apni family ke saath dekhein aur share karein! 💫\n\n"
            f"{fb_hashtags}"
        )[:500]

    # ─── Tag Builders ─────────────────────────────────────────────────────────

    def _baseline_tags(self, idea: KidsStoryIdea, category: str) -> List[str]:
        magical = getattr(idea, "magical_element", "")
        title_slug = idea.title.lower().replace(" ", " ")
        is_kids = getattr(idea, "made_for_kids", False)
        char_name = "chintu" if is_kids else "rohan"

        base = [
            # Hindi search terms
            "hindi moral story",
            "bacchon ki kahani",
            "moral kahani hindi",
            "naitik kahani hindi",
            "animated moral story hindi",
            "kids story hindi",
            "cartoon story hindi",
            "3d animated story hindi",
            "wonder stories tv",
            f"{char_name} story hindi",
            title_slug,
            # English search terms
            "moral story for kids",
            "animated story for kids",
            "kids cartoon story",
            "short moral story",
            "educational story kids",
            "bedtime story hindi",
            "pixar style story hindi",
            "family story hindi",
            "story with moral",
            # Character tags
            char_name,
            f"{char_name} aur maa" if is_kids else f"{char_name} aur dosto",
            f"{char_name} stories",
            # Category-specific
            f"{category.replace('_', ' ')} story hindi",
        ]

        if magical:
            base.append(f"{magical.lower()} story hindi")
            base.append(f"jadui {magical.lower()} kahani")

        category_extras = {
            "mythology": ["hanuman story hindi", "krishna story hindi", "mythology animated hindi", "purana kahani"],
            "dadi_kahani": ["dadi ki kahani", "nani ki kahani", "panchatantra story hindi", "folk tale hindi animated"],
            "family_funny": ["funny family story hindi", "comedy story kids hindi", "family comedy animated"],
            "animal_tales": ["jungle story hindi", "talking animal story hindi", "panchatantra animated hindi"],
            "mystery": ["mystery story hindi kids", "detective story kids hindi", "puzzle story animated"],
            "seasonal": ["festival story hindi", "diwali story", "holi story hindi", "raksha bandhan story"],
            "real_life": ["relatable story kids hindi", "school story hindi animated", "friendship story hindi"],
            "horror": ["spooky story hindi kids", "horror story kids hindi", "haunted house story hindi", "funny horror hindi"],
        }
        base.extend(category_extras.get(category, ["jadui kahani hindi", "magical story hindi kids"]))

        # Always add these
        base.extend([
            "wonder stories",
            "hindi kahani",
            "moral story 2025",
            "moral story 2026",
        ])

        return base

    @staticmethod
    def _baseline_hashtags(is_short: bool, is_kids: bool = False) -> List[str]:
        char_tag = "#ChintuStories" if is_kids else "#RohanStories"
        audience_tags = ["#KahaniForKids", "#BacchonKiKahani"] if is_kids else ["#HindiStories", "#MoralStories"]
        base = [
            "#WonderStoriesTV",
            "#HindiMoralStory",
            *audience_tags,
            "#MoralStory",
            "#AnimatedStoryHindi",
            char_tag,
            "#FamilyStory",
        ]
        if is_short:
            base.insert(0, "#shorts")
            base.append("#HindiShorts")
        else:
            base.append("#KidsStory" if is_kids else "#AnimatedStory")
            base.append("#HindiKahani")
        return base

    # ─── Normalization ────────────────────────────────────────────────────────

    def _clean_title(self, value: str, idea: KidsStoryIdea, is_short: bool) -> str:
        cleaned = self._clean_text(value)
        if len(cleaned) < 10:
            cleaned = self._fallback_title(idea, is_short)
        return cleaned[:100]

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value)).strip()

    def _normalize_tags(self, tags: List[str], idea: KidsStoryIdea, category: str) -> List[str]:
        merged: List[str] = []
        baseline = self._baseline_tags(idea, category)
        for tag in [*tags, *baseline]:
            cleaned = self._clean_text(str(tag)).lower()
            if cleaned and cleaned not in {t.lower() for t in merged}:
                merged.append(cleaned[:40])
        return merged[:35]

    def _normalize_hashtags(self, hashtags: List[str], is_short: bool, is_kids: bool = False) -> List[str]:
        cleaned: List[str] = []
        for val in [*hashtags, *self._baseline_hashtags(is_short, is_kids)]:
            tag = str(val).strip()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag}"
            if tag.lower() not in {t.lower() for t in cleaned}:
                cleaned.append(tag)
        return cleaned[:10]
