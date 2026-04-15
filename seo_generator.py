from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from config import AppConfig
from llm_fallback import LlmFallbackClient, build_json_with_fallback
from script_generator import VideoScript


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SeoPackage:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    primary_keyword: str
    language_code: str = "en"
    audio_language_code: str = "en"
    content_style: str = "fitness"


class SeoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate(self, script: VideoScript) -> SeoPackage:
        LOGGER.info("Generating SEO package")
        language_code = self._detect_language_code(script)
        content_style = self._detect_content_style(script)
        language_line = (
            "The output language should be English."
            if language_code == "en"
            else "The output language should be Hinglish in Roman script only, mixing Hindi and English naturally."
        )
        prompt = (
            "You are a YouTube SEO expert specializing in the Fitness and Motivation niche. "
            "Create metadata optimized for Shorts discovery, CTR, retention expectation, search relevance, and swipe-stop curiosity. "
            "Return strict JSON with keys title, description, tags, hashtags, primary_keyword. "
            "Title should be under 60 characters and create curiosity or urgency without sounding fake. "
            "Description should front-load the keyword, explain the viewer payoff quickly, and sound native to Shorts. "
            "Tags should mix strong evergreen search terms with viral Shorts-style phrases. "
            "Hashtags must include brand and category tags. "
            "Use only Roman script written with normal English letters. "
            "Do not use clickbait that the script does not support. "
            "Prefer SEO that matches what viewers would actually search after seeing the hook."
            f"\n{language_line}"
            f"\nContent style: {content_style}"
            f"\nPrimary keyword from script: {script.primary_keyword}"
            f"\nRetention note from AI script writer: {script.retention_note}"
            f"\n\nScript for Context:\n{script.full_script}"
        )
        payload, provider_used = build_json_with_fallback(
            self.llm,
            prompt,
            lambda: self._fallback_payload(script),
            "static-seo",
        )
        LOGGER.info("SEO generation provider used: %s", provider_used)

        tags = self._normalize_tags(payload.get("tags", []), script.primary_keyword)
        hashtags = self._normalize_hashtags(payload.get("hashtags", []), content_style, language_code)
        description = self._clean_ascii_text(payload["description"].strip())
        hashtag_text = " ".join(hashtags)
        if hashtag_text.lower() not in description.lower():
            description = f"{description}\n\n{hashtag_text}"
        title = self._clean_ascii_text(payload["title"].strip())[:60]
        primary_keyword = self._clean_ascii_text(payload.get("primary_keyword", script.primary_keyword).strip())
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

    def _fallback_payload(self, script: VideoScript) -> dict:
        content_style = self._detect_content_style(script)
        language_code = self._detect_language_code(script)
        keyword = self._clean_ascii_text(script.primary_keyword or script.title).strip()
        title = self._fallback_title(script, content_style, language_code)
        description = self._fallback_description(script, keyword, content_style, language_code)
        tags = self._fallback_tags(script, keyword, content_style, language_code)
        hashtags = self._fallback_hashtags(content_style, language_code)
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "primary_keyword": keyword,
        }

    def _normalize_tags(self, tags: List[str], primary_keyword: str) -> List[str]:
        style = self._infer_style_from_keyword(primary_keyword)
        baseline = self._baseline_tags(style, primary_keyword)
        merged: List[str] = []
        for tag in [*tags, *baseline]:
            cleaned = self._clean_ascii_text(str(tag).strip())
            if cleaned and cleaned.lower() not in {item.lower() for item in merged}:
                merged.append(cleaned[:30])
        return merged[:15]

    @staticmethod
    def _normalize_hashtags(hashtags: List[str], content_style: str, language_code: str) -> List[str]:
        style_defaults = SeoGenerator._fallback_hashtags(content_style, language_code)
        cleaned: List[str] = []
        for tag in [*hashtags, *style_defaults]:
            value = str(tag).strip()
            if not value:
                continue
            if not value.startswith("#"):
                value = f"#{value}"
            if value.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(value)
        return cleaned[:5]

    @staticmethod
    def _detect_content_style(script: VideoScript) -> str:
        blob = f"{script.title} {script.primary_keyword} {script.full_script}".lower()
        if any(term in blob for term in ("yoga", "pranayam", "pranayama", "breath", "sleep yoga", "mobility")):
            return "yoga"
        if any(term in blob for term in ("fat loss", "weight loss", "cardio", "calorie")):
            return "fat_loss"
        if any(term in blob for term in ("muscle", "strength", "bulk", "back", "lift")):
            return "strength"
        return "fitness"

    @staticmethod
    def _detect_language_code(script: VideoScript) -> str:
        blob = f"{script.title} {script.full_script}".lower()
        roman_hindi_markers = ("agar", "tum", "apne", "karo", "nahi", "roz", "sirf", "kal", "aaj", "shanti")
        return "hi" if any(marker in blob for marker in roman_hindi_markers) else "en"

    @staticmethod
    def _clean_ascii_text(value: str) -> str:
        return "".join(char for char in value if ord(char) < 128).strip()

    def _fallback_title(self, script: VideoScript, content_style: str, language_code: str) -> str:
        keyword = self._clean_ascii_text(script.primary_keyword or script.title)
        if content_style == "yoga":
            return (
                f"{keyword} for Calm Mornings"
                if language_code == "en"
                else f"{keyword} se Stress Reset"
            )[:60]
        if content_style == "fat_loss":
            return (
                f"The {keyword} Mistake People Repeat"
                if language_code == "en"
                else f"{keyword} Ki Sabse Badi Galti"
            )[:60]
        if content_style == "strength":
            return (
                f"{keyword} That Builds Real Strength"
                if language_code == "en"
                else f"{keyword} se Real Strength Banao"
            )[:60]
        return (
            f"{keyword} That Gets Results Faster"
            if language_code == "en"
            else f"{keyword} se Fast Results Kaise"
        )[:60]

    def _fallback_description(self, script: VideoScript, keyword: str, content_style: str, language_code: str) -> str:
        opener = (
            f"{keyword}: "
            if language_code == "en"
            else f"{keyword} ke liye "
        )
        if content_style == "yoga":
            body = (
                "A calm but powerful short for stress relief, better posture, and daily balance."
                if language_code == "en"
                else "yeh short stress relief, better posture, aur calm mind ke liye banaya gaya hai."
            )
        elif content_style == "fat_loss":
            body = (
                "A sharp short on fat loss mistakes, smarter routines, and sustainable discipline."
                if language_code == "en"
                else "yeh short fat loss mistakes, smart routine, aur sustainable discipline par focused hai."
            )
        elif content_style == "strength":
            body = (
                "A high-retention short on form, strength, muscle gain, and better execution."
                if language_code == "en"
                else "yeh short strength, muscle gain, form, aur better execution par focused hai."
            )
        else:
            body = (
                "A high-retention short on fitness, mindset, discipline, and visible progress."
                if language_code == "en"
                else "yeh short fitness, mindset, discipline, aur visible progress ke liye banaya gaya hai."
            )
        close = (
            "Watch till the end for the real takeaway."
            if language_code == "en"
            else "End tak dekho for the real takeaway."
        )
        return f"{opener}{body} {close}"

    def _fallback_tags(self, script: VideoScript, keyword: str, content_style: str, language_code: str) -> List[str]:
        tags = self._baseline_tags(content_style, keyword)
        title_words = self._clean_ascii_text(script.title).lower().split()
        if title_words:
            tags.append(" ".join(title_words[:4]))
        if language_code == "hi":
            tags.extend(["hinglish shorts", "hindi english shorts", "roman hindi motivation"])
        return tags

    @staticmethod
    def _fallback_hashtags(content_style: str, language_code: str) -> List[str]:
        style_tags = {
            "yoga": ["#DailyFitX", "#yoga", "#shorts", "#stressrelief", "#hinglish" if language_code == "hi" else "#wellness"],
            "fat_loss": ["#DailyFitX", "#fatloss", "#shorts", "#fitness", "#hinglish" if language_code == "hi" else "#weightloss"],
            "strength": ["#DailyFitX", "#strength", "#shorts", "#gym", "#hinglish" if language_code == "hi" else "#muscle"],
            "fitness": ["#DailyFitX", "#fitness", "#shorts", "#motivation", "#hinglish" if language_code == "hi" else "#workout"],
        }
        return style_tags.get(content_style, style_tags["fitness"])

    def _baseline_tags(self, content_style: str, primary_keyword: str) -> List[str]:
        common = ["DailyFitX", primary_keyword, "viral fitness shorts", "shorts feed fitness"]
        by_style = {
            "yoga": ["yoga motivation hindi", "morning yoga", "stress relief yoga", "yoga for beginners", "mindful movement"],
            "fat_loss": ["fat loss motivation", "weight loss tips", "fat loss routine", "fitness discipline", "body transformation"],
            "strength": ["strength training motivation", "muscle gain tips", "gym motivation hindi", "better workout form", "real strength"],
            "fitness": ["fitness motivation", "gym motivation hindi", "workout motivation", "discipline mindset", "transformation tips"],
        }
        return [*by_style.get(content_style, by_style["fitness"]), *common]

    def _infer_style_from_keyword(self, primary_keyword: str) -> str:
        keyword = primary_keyword.lower()
        if "yoga" in keyword or "pranayam" in keyword or "breath" in keyword:
            return "yoga"
        if "fat loss" in keyword or "weight loss" in keyword or "cardio" in keyword:
            return "fat_loss"
        if "strength" in keyword or "muscle" in keyword or "gym" in keyword:
            return "strength"
        return "fitness"
