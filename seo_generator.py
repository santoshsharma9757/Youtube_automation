"""
seo_generator.py  –  Wonder Stories TV
========================================
Generates maximum-reach YouTube SEO metadata for Wonder Stories TV.

Optimized for viral Hindi stories channel:
  - Mystery, Horror, Thriller, Crime, Karma, Psychological, Moral, Suspense
  - 35+ tags with trending Hindi story keywords
  - Scroll-stopping title formula
  - Suspense hook descriptions to maximize CTR
  - Made for Kids: ALWAYS False (adult/family story content)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from config import AppConfig
from story_idea_generator import StoryIdea
from story_generator import StoryPlan
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)

CHANNEL_NAME   = "Wonder Stories TV"
CHANNEL_HANDLE = "@WonderStoriesTV"
CHANNEL_TAG    = "#WonderStoriesTV"

# ─── Category-specific SEO keyword packs ───────────────────────────────────────
CATEGORY_TAGS: dict[str, list[str]] = {
    "mystery_stories": [
        "mystery story hindi", "rahasya kahani hindi", "mystery kahani",
        "suspense story hindi", "rahasya", "murder mystery hindi",
        "detective story hindi", "thriller hindi story",
    ],
    "shocking_facts": [
        "shocking facts hindi", "hairan kar dene wale facts", "amazing facts hindi",
        "facts in hindi", "rochak tathya", "did you know hindi",
        "interesting facts hindi", "unbelievable facts hindi",
    ],
    "suspense_stories": [
        "suspense story hindi", "रहस्यमयी कहानी", "horror suspense hindi",
        "psychological thriller hindi", "suspense kahani", "cliffhanger story",
        "mind blowing story hindi", "what happens next",
    ],
    "dark_facts": [
        "dark facts hindi", "andheri sach", "dark history hindi",
        "shocking truth hindi", "hidden facts hindi", "dark reality",
        "untold story hindi", "dark side hindi",
    ],
    "psychological": [
        "psychological story hindi", "mind games story", "psychological thriller hindi",
        "dimag ki kahani", "mind twist story hindi", "psychological facts hindi",
        "brain story hindi", "mental health story hindi",
    ],
    "thriller_stories": [
        "thriller story hindi", "action thriller hindi", "suspense thriller hindi",
        "hindi thriller kahani", "edge of seat story", "crime thriller hindi",
    ],
    "horror_stories": [
        "horror story hindi", "डरावनी कहानी", "bhoot ki kahani",
        "horror kahani hindi", "scary story hindi", "ghost story hindi",
        "horror short film hindi", "supernatural story hindi",
    ],
    "crime_stories": [
        "crime story hindi", "true crime hindi", "crime kahani",
        "police story hindi", "murder mystery hindi", "investigation story hindi",
        "criminal story hindi", "crime thriller hindi",
    ],
    "karma_stories": [
        "karma story hindi", "karma ka badla", "justice story hindi",
        "karma kahani", "poetic justice hindi", "karma real story",
        "good karma story", "karma and fate hindi",
    ],
    "real_life_facts": [
        "real life story hindi", "true story hindi", "sach mein hua",
        "real story hindi", "inspiring story hindi", "motivational story hindi",
        "real life incident hindi", "true incident hindi",
    ],
    "moral_stories": [
        "moral story hindi", "moral kahani hindi", "नैतिक कहानी",
        "life lesson hindi story", "moral of the story", "inspirational story hindi",
        "motivational kahani hindi", "moral short story hindi",
    ],
}

# Common viral Hindi story tags added to every video
COMMON_TAGS = [
    "hindi story", "hindi kahani", "wonder stories tv",
    "hindi short film", "story in hindi", "hindi audio story",
    "hindi storytelling", "viral hindi story",
    "hindi moral stories", "short story hindi",
]


@dataclass(slots=True)
class SeoPackage:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    primary_keyword: str
    language_code: str = "hi"
    audio_language_code: str = "hi"
    content_style: str = "story"
    made_for_kids: bool = False          # ALWAYS False — adult story content
    facebook_description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SeoPackage":
        valid_keys = set(cls.__annotations__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class SeoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate(self, idea: StoryIdea, plan: StoryPlan) -> SeoPackage:
        LOGGER.info("Generating SEO for '%s'", idea.title)

        category = getattr(idea, "category", "mystery_stories")
        hook = getattr(idea, "hook_hindi", "") or getattr(idea, "hook", "")
        twist = getattr(idea, "twist", "")
        moral = getattr(idea, "moral", "")
        is_short = idea.video_type == "short"

        primary_keyword = self._build_primary_keyword(idea, category)

        prompt = f"""You are an expert YouTube SEO specialist for 'Wonder Stories TV' — a viral Hindi stories channel.

Story Brief:
  Title: {idea.title}
  Category: {category.replace('_', ' ').title()}
  Hook: {hook}
  Twist: {twist}
  Moral: {moral}
  Format: {'YouTube Short (max 45 seconds)' if is_short else 'YouTube video (max 3 minutes)'}
  Primary keyword: {primary_keyword}

Generate maximum-reach SEO metadata. Return only valid JSON:
{{
  "title": "Scroll-stopping YouTube title (max 80 chars). Formula: [Hook phrase] | {idea.title} | Wonder Stories TV. Make it IRRESISTIBLE to click.",
  "description": "Engaging 500+ char description. Start with the hook line in Hindi. Build suspense. Include 3-5 relevant hashtags inline. End with: Watch more → @WonderStoriesTV",
  "tags": ["35+ highly searched tags mixing Hindi + English. Include trending story/fact/suspense tags. Each tag max 30 chars."],
  "hashtags": ["12-15 hashtags: mix of channel, category, viral Hindi story tags. Start with #"],
  "primary_keyword": "{primary_keyword}",
  "facebook_description": "150-200 char viral Facebook/Instagram Reels caption with hook + emoji + hashtags"
}}

TITLE RULES:
- Start with an emotion trigger or shocking question
- Include the story title or key concept
- End with | Wonder Stories TV
- Max 80 chars, no clickbait that doesn't match content
- For shorts: add #shorts at end if space allows

Only output the JSON, no extra text."""

        try:
            payload, _ = build_json_with_fallback(
                self.llm, prompt, lambda: {}, "seo-package"
            )
            return self._build_package(payload, idea, category, primary_keyword)
        except Exception as exc:
            LOGGER.warning("LLM SEO generation failed: %s — using fallback", exc)
            return self._fallback_package(idea, category, primary_keyword, is_short)

    # ──────────────────────────────────────────────────────────────────────────
    #  PRIVATE
    # ──────────────────────────────────────────────────────────────────────────

    def _build_primary_keyword(self, idea: StoryIdea, category: str) -> str:
        topic = getattr(idea, "topic", "")
        if topic:
            return topic.lower().strip()
        cat_map = {
            "mystery_stories":  "mystery story hindi",
            "shocking_facts":   "shocking facts hindi",
            "suspense_stories": "suspense story hindi",
            "dark_facts":       "dark facts hindi",
            "psychological":    "psychological story hindi",
            "thriller_stories": "thriller story hindi",
            "horror_stories":   "horror story hindi",
            "crime_stories":    "crime story hindi",
            "karma_stories":    "karma story hindi",
            "real_life_facts":  "real life story hindi",
            "moral_stories":    "moral story hindi",
        }
        return cat_map.get(category, "hindi story")

    def _build_package(
        self,
        payload: dict,
        idea: StoryIdea,
        category: str,
        primary_keyword: str,
    ) -> SeoPackage:
        title = payload.get("title", "")
        if not title or len(title) < 10:
            title = self._fallback_title(idea)
        title = title[:80]

        description = payload.get("description", "")
        if not description or len(description) < 50:
            description = self._fallback_description(idea, category)

        tags = payload.get("tags", [])
        if not tags:
            tags = []
        # Merge with category tags + common tags
        cat_tags = CATEGORY_TAGS.get(category, [])
        all_tags = list(dict.fromkeys(tags + cat_tags + COMMON_TAGS))
        all_tags = [t[:30] for t in all_tags if t.strip()][:50]

        hashtags = payload.get("hashtags", [])
        if not hashtags:
            hashtags = self._fallback_hashtags(category, idea.video_type)
        hashtags = [h if h.startswith("#") else f"#{h}" for h in hashtags][:15]

        fb_desc = payload.get("facebook_description", "")
        if not fb_desc:
            fb_desc = f"🔥 {getattr(idea, 'hook_hindi', idea.title)} | Wonder Stories TV 👇"

        return SeoPackage(
            title=title,
            description=description,
            tags=all_tags,
            hashtags=hashtags,
            primary_keyword=primary_keyword,
            language_code="hi",
            audio_language_code="hi",
            content_style=category,
            made_for_kids=False,
            facebook_description=fb_desc,
        )

    def _fallback_title(self, idea: StoryIdea) -> str:
        hook = getattr(idea, "hook", "")
        if hook:
            return f"{hook[:40]} | {idea.title[:30]} | Wonder Stories TV"[:80]
        return f"{idea.title} | Wonder Stories TV"[:80]

    def _fallback_description(self, idea: StoryIdea, category: str) -> str:
        hook_hindi = getattr(idea, "hook_hindi", "")
        hook = hook_hindi or getattr(idea, "hook", idea.title)
        moral = getattr(idea, "moral_hindi", "") or getattr(idea, "moral", "")
        cat_label = category.replace("_", " ").title()
        return (
            f"{hook}\n\n"
            f"Wonder Stories TV पर आपका स्वागत है — यहाँ हर कहानी आपको सोचने पर मजबूर करती है।\n\n"
            f"इस {cat_label} में आप जानेंगे कि सच कितना हैरान करने वाला हो सकता है।\n\n"
            f"Seekh: {moral}\n\n"
            f"Like करो, Share करो, और Channel Subscribe करो → {CHANNEL_HANDLE}\n\n"
            f"#WonderStoriesTV #{cat_label.replace(' ', '')} #HindiStory #ViralStory"
        )

    def _fallback_hashtags(self, category: str, video_type: str) -> list[str]:
        base = [
            "#WonderStoriesTV",
            "#HindiStory",
            "#ViralStory",
            CHANNEL_TAG,
        ]
        cat_specific = {
            "mystery_stories":  ["#MysteryStory", "#RahasyaKahani", "#Suspense"],
            "shocking_facts":   ["#ShockingFacts", "#AmazingFacts", "#FactsInHindi"],
            "suspense_stories": ["#SuspenseStory", "#HindiSuspense", "#Thriller"],
            "dark_facts":       ["#DarkFacts", "#AndheriSach", "#HiddenTruth"],
            "psychological":    ["#PsychologicalStory", "#MindGames", "#Thriller"],
            "thriller_stories": ["#ThrillerStory", "#HindiThriller", "#EdgeOfSeat"],
            "horror_stories":   ["#HorrorStory", "#BhootKiKahani", "#ScaryStory"],
            "crime_stories":    ["#CrimeStory", "#TrueCrime", "#MurderMystery"],
            "karma_stories":    ["#KarmaStory", "#KarmaKaBadla", "#Justice"],
            "real_life_facts":  ["#TrueStory", "#RealLifeStory", "#Inspiring"],
            "moral_stories":    ["#MoralStory", "#LifeLesson", "#MoralKahani"],
        }
        tags = base + cat_specific.get(category, ["#Story"])
        if video_type == "short":
            tags.append("#shorts")
        return tags[:15]

    def _fallback_package(
        self,
        idea: StoryIdea,
        category: str,
        primary_keyword: str,
        is_short: bool,
    ) -> SeoPackage:
        title = self._fallback_title(idea)
        description = self._fallback_description(idea, category)
        cat_tags = CATEGORY_TAGS.get(category, [])
        all_tags = list(dict.fromkeys(cat_tags + COMMON_TAGS + [idea.title.lower()]))[:50]
        hashtags = self._fallback_hashtags(category, idea.video_type)

        return SeoPackage(
            title=title,
            description=description,
            tags=all_tags,
            hashtags=hashtags,
            primary_keyword=primary_keyword,
            language_code="hi",
            audio_language_code="hi",
            content_style=category,
            made_for_kids=False,
            facebook_description=f"🔥 {getattr(idea, 'hook_hindi', idea.title)} | Wonder Stories TV",
        )
