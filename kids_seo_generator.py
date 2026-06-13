"""
kids_seo_generator.py  –  Chintu Stories Channel
=================================================
Generates YouTube Kids-optimized SEO metadata for Chintu Stories.
Titles are Hindi-first, high-CTR, and include relevant hashtags.
Category: 1 (Film & Animation) – YouTube Kids compatible.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List

from config import AppConfig
from kids_idea_generator import KidsStoryIdea
from kids_story_generator import KidsStoryPlan
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KidsSeoPackage:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    primary_keyword: str
    language_code: str = "hi"
    audio_language_code: str = "hi"
    content_style: str = "kids_animation"


class KidsSeoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate(self, idea: KidsStoryIdea, plan: KidsStoryPlan) -> KidsSeoPackage:
        LOGGER.info("Generating kids SEO for '%s'", idea.title)
        is_long  = idea.video_type == "long"
        keyword  = f"{idea.magical_element} kids story hindi"
        moral_h  = idea.moral_hindi

        format_label = "2:30 min YouTube Kids story video" if is_long else "YouTube Kids Short (~30 seconds)"
        prompt = (
            f"You are an expert YouTube Kids SEO strategist for the channel 'Chintu Stories'.\n"
            f"Generate SEO metadata for a {format_label}.\n"
            f"Story title: {idea.title}\n"
            f"Magical element: {idea.magical_element}\n"
            f"Moral lesson: {idea.moral} ({moral_h})\n"
            f"Primary keyword: {keyword}\n\n"
            f"Rules:\n"
            f"- Title must be in Hindi (Roman script), ultra-catchy, child-friendly, 40-60 chars.\n"
            f"  Example: 'Chintu Aur Magical Watch! ⌚😱 | Bacchon Ki Kahani'\n"
            f"- For Shorts: add exactly '#shorts #kidsstory' at end of title.\n"
            f"- For Long: title under 70 chars, no hashtags in title.\n"
            f"- Description: 2-3 child-friendly sentences in Hindi (Roman script).\n"
            f"- Tags: 15 high-intent YouTube Kids search phrases.\n"
            f"- Hashtags: 6-8 kids channel hashtags (#shorts, #kidsstory, #bachonkikahani, #moralstory, etc.)\n"
            f"- Return strict JSON with keys: title, description, tags, hashtags, primary_keyword.\n"
            f"- Output only the JSON, no markdown wrapper."
        )

        def _fallback():
            return self._fallback_payload(idea, keyword, is_long)

        payload, provider = build_json_with_fallback(self.llm, prompt, _fallback, "kids-seo")
        LOGGER.info("Kids SEO provider: %s", provider)

        title       = self._clean_title(payload.get("title", ""), idea, is_long)
        description = self._clean_text(payload.get("description", ""))
        if not description:
            description = self._fallback_description(idea, keyword)
        tags        = self._normalize_tags(payload.get("tags", []), keyword)
        hashtags    = self._normalize_hashtags(payload.get("hashtags", []), is_long)
        hashtag_str = " ".join(hashtags)
        if hashtag_str.lower() not in description.lower():
            description = f"{description}\n\n{hashtag_str}"

        return KidsSeoPackage(
            title=title,
            description=description,
            tags=tags,
            hashtags=hashtags,
            primary_keyword=keyword,
            language_code="hi",
            audio_language_code="hi",
            content_style="kids_animation",
        )

    # ─── Fallbacks ────────────────────────────────────────────────────────────

    def _fallback_payload(self, idea: KidsStoryIdea, keyword: str, is_long: bool) -> dict:
        return {
            "title": self._fallback_title(idea, is_long),
            "description": self._fallback_description(idea, keyword),
            "tags": self._baseline_tags(keyword),
            "hashtags": self._baseline_hashtags(is_long),
            "primary_keyword": keyword,
        }

    @staticmethod
    def _fallback_title(idea: KidsStoryIdea, is_long: bool) -> str:
        base = f"{idea.title}! 🌟✨ | Bacchon Ki Kahani"
        if not is_long:
            base = f"{idea.title}! 😱✨ #shorts #kidsstory"
        return base[:70]

    @staticmethod
    def _fallback_description(idea: KidsStoryIdea, keyword: str) -> str:
        return (
            f"Aaj ki kahani mein Chintu {idea.bad_habit_hindi} karta tha. "
            f"Maa ne apna jaadu ka {idea.magical_element} nikala aur Chintu ne seekha ki {idea.moral_hindi}. "
            f"Yeh moral story zaroor dekho! {keyword}."
        )

    @staticmethod
    def _baseline_tags(keyword: str) -> List[str]:
        return [
            keyword,
            "chintu stories",
            "bacchon ki kahani",
            "moral story hindi",
            "kids cartoon story hindi",
            "animated moral story",
            "kids story in hindi",
            "moral kahani hindi",
            "cartoon story for kids hindi",
            "3d animated kids story",
            "pixar style kids story",
            "hindi moral stories for children",
            "chintu aur maa",
            "magical story for kids",
            "youtube kids hindi story",
        ]

    @staticmethod
    def _baseline_hashtags(is_long: bool) -> List[str]:
        if is_long:
            return [
                "#kidsstory",
                "#bachonkikahani",
                "#moralstory",
                "#hindistory",
                "#kidscartoon",
                "#animatedstory",
                "#ChintuStories",
            ]
        return [
            "#shorts",
            "#kidsstory",
            "#bachonkikahani",
            "#moralstory",
            "#hindishorts",
            "#kidscartoon",
            "#ChintuStories",
        ]

    # ─── Normalization ────────────────────────────────────────────────────────

    def _clean_title(self, value: str, idea: KidsStoryIdea, is_long: bool) -> str:
        cleaned = self._clean_text(value)
        if len(cleaned) < 10:
            cleaned = self._fallback_title(idea, is_long)
        limit = 70 if is_long else 60
        return cleaned[:limit]

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value)).strip()

    def _normalize_tags(self, tags: List[str], keyword: str) -> List[str]:
        merged: List[str] = []
        for tag in [*tags, *self._baseline_tags(keyword)]:
            cleaned = self._clean_text(str(tag))
            if cleaned and cleaned.lower() not in {t.lower() for t in merged}:
                merged.append(cleaned[:50])
        if keyword.lower() not in {t.lower() for t in merged}:
            merged.insert(0, keyword[:50])
        return merged[:15]

    def _normalize_hashtags(self, hashtags: List[str], is_long: bool) -> List[str]:
        cleaned: List[str] = []
        for val in [*hashtags, *self._baseline_hashtags(is_long)]:
            tag = str(val).strip()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag}"
            if tag.lower() not in {t.lower() for t in cleaned}:
                cleaned.append(tag)
        return cleaned[:8]
