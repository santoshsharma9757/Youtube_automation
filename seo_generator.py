from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from config import AppConfig
from llm_fallback import LlmFallbackClient, build_json_with_fallback


LOGGER = logging.getLogger(__name__)


@dataclass
class SeoPackage:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    primary_keyword: str
    language_code: str = "hi"
    audio_language_code: str = "hi"
    content_style: str = "family_story"
    # Wonder Stories TV fields (optional — ignored if not present in old records)
    made_for_kids: bool = False
    facebook_description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SeoPackage":
        """Safe deserialization — ignores unknown keys to avoid crashes."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()} if hasattr(cls, '__dataclass_fields__') else set()
        # Fallback: use only known init params
        known = {k: v for k, v in data.items() if k in {
            'title', 'description', 'tags', 'hashtags', 'primary_keyword',
            'language_code', 'audio_language_code', 'content_style',
            'made_for_kids', 'facebook_description',
        }}
        return cls(**known)


class SeoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate(self, script: VideoScript) -> SeoPackage:
        LOGGER.info("Generating SEO package")
        is_long = getattr(script, "video_type", "short") == "long"
        language_code = self._detect_language_code(script)
        content_style = self._detect_content_style(script)
        keyword = self._clean_ascii_text(script.primary_keyword or script.title).strip() or "fitness tips india"

        format_label = "long-form YouTube video" if is_long else "YouTube Short"
        language_line = (
            "The output language should be English."
            if language_code == "en"
            else "The output language should be Hinglish in Roman script only, mixing Hindi and English naturally."
        )
        prompt = (
            "You are an elite YouTube SEO strategist specializing in viral fitness, yoga, gym, meditation, and health content. "
            f"You are packaging a {format_label}. "
            "Return strict JSON with keys title, description, tags, hashtags, primary_keyword. "
            "The packaging must be HEAVILY optimized for the YouTube Shorts Feed algorithm (high click-through-rate, trending appeal) and YouTube Search (high-intent SEO) to maximize views and reach. "
            "Rules:\n"
            f"- primary_keyword must stay exactly or very close to this search phrase: {keyword}\n"
            "- title must be a viral, High-CTR 'curiosity gap' title that is extremely short, human-style, natural, and highly clickable (typically 2 to 4 words). It should provoke extreme curiosity while naturally aligning to the keyword.\n"
            "- for Hinglish/Hindi content: write the title in natural, extremely catchy Roman script Hindi (Hinglish) with highly click-worthy Indian phrasings (e.g., 'Belly Fat Hack #shorts' or 'Ye 3 Exercises Karo! 🔥'). Do NOT write generic or dry English titles for Hinglish scripts.\n"
            "- tags must be exact, high-intent phrases viewers actively type into the YouTube search bar, including trending variations.\n"
            "- avoid generic vanity terms that do not match the topic.\n"
            "- description must front-load the keyword in the very first sentence to increase Search and Suggested Video ranking, and explain the viewer payoff quickly.\n"
            "- hashtags should support aggressive feed discovery and algorithmic matching.\n"
            "- do not put hashtags inside the title if it is a long-form video. BUT for Shorts, you MUST include exactly 1 or 2 high-volume, clean hashtags at the end of the title (e.g., 'fun #shorts #motivation' or 'Belly Fat Hack #shorts').\n"
            + (
                "- for Shorts: title must be ultra-short, human-style, natural, and highly clickable (2-4 words, under 30 characters) containing exactly 1-2 clean hashtags at the end. Focus on curiosity + emotional trigger (e.g. 'fun #shorts #motivation' or 'Stomach Hack #shorts'). Description should be 2 short lines before hashtags; provide 5-7 hashtags: #shorts, #shortsfeed, #viral, and high-volume trending hashtags.\n"
                if not is_long
                else "- for long-form: title under 70 characters; description should be 2-3 short sentences; provide 5-7 high-volume trending hashtags including #viral.\n"
            )
            + f"{language_line}\n"
            + f"Content style: {content_style}\n"
            + f"Primary keyword: {keyword}\n"
            + f"Retention note: {script.retention_note}\n"
            + f"\nScript context:\n{script.full_script}"
        )

        payload, provider_used = build_json_with_fallback(
            self.llm,
            prompt,
            lambda: self._fallback_payload(script, keyword, content_style, language_code, is_long),
            "search-first-seo",
        )
        LOGGER.info("SEO generation provider used: %s", provider_used)

        primary_keyword = self._clean_ascii_text(payload.get("primary_keyword", keyword)).strip() or keyword
        title = self._clean_title(payload.get("title", script.title), script.title, is_long=is_long)
        description = self._clean_ascii_text(payload.get("description", "")).strip()
        if not description:
            description = self._fallback_description(primary_keyword, content_style, language_code, is_long)
        if not description.lower().startswith(primary_keyword.lower()):
            description = f"{primary_keyword}: {description}"
        if not is_long:
            description = self._compress_short_description(description)

        tags = self._normalize_tags(payload.get("tags", []), primary_keyword, content_style, is_long)
        hashtags = self._normalize_hashtags(payload.get("hashtags", []), content_style, language_code, is_long)
        hashtag_text = " ".join(hashtags)
        if hashtag_text.lower() not in description.lower():
            description = f"{description}\n\n{hashtag_text}"

        return SeoPackage(
            title=title,
            description=description,
            tags=tags,
            hashtags=hashtags,
            primary_keyword=primary_keyword,
            language_code=language_code,
            audio_language_code=language_code,
            content_style=content_style,
        )

    def _fallback_payload(
        self,
        script: VideoScript,
        keyword: str,
        content_style: str,
        language_code: str,
        is_long: bool,
    ) -> dict:
        return {
            "title": self._fallback_title(keyword, script.title, content_style, language_code, is_long),
            "description": self._fallback_description(keyword, content_style, language_code, is_long),
            "tags": self._baseline_tags(content_style, keyword, is_long),
            "hashtags": self._fallback_hashtags(content_style, language_code, is_long),
            "primary_keyword": keyword,
        }

    def _normalize_tags(self, tags: List[str], primary_keyword: str, content_style: str, is_long: bool) -> List[str]:
        merged: List[str] = []
        for tag in [*tags, *self._baseline_tags(content_style, primary_keyword, is_long)]:
            cleaned = self._clean_ascii_text(str(tag)).strip()
            if not cleaned:
                continue
            if is_long and "shorts" in cleaned.lower():
                continue
            if cleaned.lower() not in {item.lower() for item in merged}:
                merged.append(cleaned[:40])
        if primary_keyword.lower() not in {item.lower() for item in merged}:
            merged.insert(0, primary_keyword[:40])
        return merged[:15]

    def _normalize_hashtags(self, hashtags: List[str], content_style: str, language_code: str, is_long: bool) -> List[str]:
        cleaned: List[str] = []
        for value in [*hashtags, *self._fallback_hashtags(content_style, language_code, is_long)]:
            tag = str(value).strip()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag}"
            if is_long and "shorts" in tag.lower():
                continue
            if tag.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(tag)
        return cleaned[:5]

    @staticmethod
    def _detect_content_style(script: VideoScript) -> str:
        blob = f"{script.title} {script.primary_keyword} {script.full_script}".lower()
        if any(term in blob for term in ("yoga", "pranayam", "pranayama", "breath", "mobility", "meditation")):
            return "yoga"
        if any(term in blob for term in ("fat loss", "weight loss", "belly fat", "calorie")):
            return "fat_loss"
        if any(term in blob for term in ("muscle", "strength", "gym", "pushup", "pullup", "squat")):
            return "strength"
        if any(term in blob for term in ("sleep", "gut", "health", "bloating", "energy")):
            return "health"
        return "fitness"

    @staticmethod
    def _detect_language_code(script: VideoScript) -> str:
        blob = f"{script.title} {script.full_script}".lower()
        roman_hindi_markers = ("agar", "tum", "apne", "karo", "nahi", "roz", "sirf", "kal", "aaj")
        return "hi" if any(marker in blob for marker in roman_hindi_markers) else "en"

    @staticmethod
    def _clean_ascii_text(value: str) -> str:
        return "".join(char for char in str(value) if ord(char) < 128)

    @classmethod
    def _clean_title(cls, value: str, fallback: str, is_long: bool) -> str:
        cleaned = cls._clean_ascii_text(value)
        if is_long:
            cleaned = re.sub(r"#\w+", "", cleaned)
        cleaned = re.sub(r"\b\d{6,}\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")
        if len(cleaned) < 5:
            cleaned = cls._clean_ascii_text(fallback).strip()
        return cleaned[: (68 if is_long else 58)]

    @staticmethod
    def _compress_short_description(value: str) -> str:
        compact = re.sub(r"\s+", " ", value).strip()
        if len(compact) <= 140:
            return compact
        cut = compact[:140].rstrip(" ,.-_")
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut

    def _fallback_title(self, keyword: str, fallback_title: str, content_style: str, language_code: str, is_long: bool) -> str:
        if not is_long:
            if content_style == "yoga":
                title = "Yoga Hack #shorts #motivation"
            elif content_style == "fat_loss":
                title = "Fat Loss Secret #shorts #fitness"
            elif content_style == "strength":
                title = "Gym Hack #shorts #gym"
            elif content_style == "health":
                title = "Health Trick #shorts #health"
            else:
                title = "Fitness Tip #shorts #motivation"
        else:
            if language_code == "hi":
                title = f"{keyword}: Yeh Galti Mat Karo"
            else:
                title = f"{keyword}: The Fix Most People Miss"
            if content_style == "yoga":
                title = f"{keyword}: Mind Aur Body Calm Karo" if language_code == "hi" else f"{keyword}: Calm Your Body Fast"
            elif content_style == "fat_loss":
                title = f"{keyword}: Fat Loss Ka Sach" if language_code == "hi" else f"{keyword}: Fat Loss Truth"
        cleaned_fallback = self._clean_ascii_text(fallback_title).strip()
        return (title or cleaned_fallback)[: (68 if is_long else 58)]

    @staticmethod
    def _fallback_description(keyword: str, content_style: str, language_code: str, is_long: bool) -> str:
        if is_long:
            if language_code == "hi":
                return f"{keyword} ko simple language mein samjho. Real steps, real fixes, aur clear viewer payoff."
            return f"{keyword} explained simply with real fixes, practical steps, and a clear viewer payoff."
        if language_code == "hi":
            return f"{keyword} ka real use samjho. Save karo aur DailyFitX follow karo."
        return f"{keyword} explained fast. Save this and follow DailyFitX."

    @staticmethod
    def _fallback_hashtags(content_style: str, language_code: str, is_long: bool) -> List[str]:
        if is_long:
            mapping = {
                "yoga": ["#yoga", "#YogaForBeginners", "#YogaForStress", "#healthylifestyle", "#DailyFitX"],
                "fat_loss": ["#fitness", "#fitnessjourney", "#healthylifestyle", "#fatloss", "#DailyFitX"],
                "strength": ["#fitness", "#fitnessmotivation", "#gym", "#workout", "#DailyFitX"],
                "health": ["#health", "#healthylifestyle", "#healthtips", "#healthyliving", "#DailyFitX"],
                "fitness": ["#fitness", "#fitnessmotivation", "#fitnessjourney", "#healthylifestyle", "#DailyFitX"],
            }
            return mapping.get(content_style, mapping["fitness"])

        mapping = {
            "yoga": ["#shorts", "#shortsfeed", "#yoga", "#YogaForBeginners", "#YogaForStress", "#DailyFitX"],
            "fat_loss": ["#shorts", "#shortsfeed", "#fitness", "#fitnessjourney", "#healthylifestyle", "#DailyFitX"],
            "strength": ["#shorts", "#shortsvideos", "#fitnessmotivation", "#gym", "#musclebuilding", "#DailyFitX"],
            "health": ["#shorts", "#shortsreels", "#health", "#healthylifestyle", "#healthtips", "#DailyFitX"],
            "fitness": ["#shorts", "#shortsfeed", "#fitness", "#fitnessmotivation", "#fitnessjourney", "#DailyFitX"],
        }
        return mapping.get(content_style, mapping["fitness"])

    def _baseline_tags(self, content_style: str, primary_keyword: str, is_long: bool) -> List[str]:
        common = [
            primary_keyword,
            f"{primary_keyword} india",
            f"{primary_keyword} for beginners",
            "fitness tips india",
            "DailyFitX",
        ]
        style_map = {
            "yoga": ["yoga for stress relief", "morning yoga routine", "yoga for beginners", "meditation and breathwork"],
            "fat_loss": ["fat loss tips hindi", "weight loss diet india", "belly fat reduce", "calorie deficit india"],
            "strength": ["gym workout for beginners india", "strength training hindi", "workout form tips", "muscle building tips"],
            "health": ["health tips hindi", "gut health india", "sleep recovery tips", "healthy habits india"],
            "fitness": ["fitness shorts india", "workout motivation hindi", "exercise tips india", "home workout india"],
        }
        if is_long:
            common[3] = "fitness channel india"
        return [*style_map.get(content_style, style_map["fitness"]), *common]
