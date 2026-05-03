from __future__ import annotations

import logging
import random
import re
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
        is_long = getattr(script, "video_type", "short") == "long"
        
        video_format_type = "Long-form cinematic video (16:9 Landscape)" if is_long else "YouTube Short (9:16 Vertical)"
        discovery_focus = "YouTube Search traffic, Suggested Videos, and high-CTR thumbnail clickability" if is_long else "the Shorts Feed, instant swipe-stop curiosity, and high replay retention"
        
        language_code = self._detect_language_code(script)
        content_style = self._detect_content_style(script)
        language_line = (
            "The output language should be English."
            if language_code == "en"
            else "The output language should be Hinglish in Roman script only, mixing Hindi and English naturally."
        )
        prompt = (
            "You are a master YouTube packaging strategist specializing in fitness, gym, motivation, lifestyle, and sports-fitness Shorts. "
            f"You are creating metadata for a {video_format_type}. "
            f"Your strict goal is to completely maximize virality and optimize for {discovery_focus}. "
            "Return strict JSON with keys title, description, tags, hashtags, primary_keyword. "
            + "Title should be under 52 characters, easy to read in one glance, include 1-2 relevant emojis (like 🔥, 💪), and feel emotionally punchy. "
            + ("Description for this SHORT: write 2 very short lines, under 140 characters before hashtags. Start with the payoff and a relevant emoji. End with: Save this or Follow DailyFitX. No filler. "
               if not is_long else
               "Description should front-load the keyword, explain the viewer payoff in 2-3 sentences, and feel native to the long-form format. ")
            + "Tags should be exact phrases people search. Mix high-volume evergreen with specific niche phrases. No vanity tags. "
            + ("Hashtags: provide exactly 8. Must include #shorts and #ytshorts. Add topic-specific tags plus one broad discovery tag like #viralshorts or #motivationshorts when relevant. "
               if not is_long else
               "Hashtags: provide exactly 5. Include brand, niche, and category tags. ")
            + "Use normal English letters for text, but you MUST use emojis to increase CTR. "
            + "Do not use clickbait the script does not support. "
            + "Prefer title patterns that work in Shorts: truth bomb, warning, challenge, identity, emotional payoff, or strong curiosity."
            + "Prefer SEO that matches what viewers actually search to solve the problem the hook introduces."
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

        tags = self._normalize_tags(payload.get("tags", []), script.primary_keyword, is_long)
        hashtags = self._normalize_hashtags(payload.get("hashtags", []), content_style, language_code, is_long)
        description = self._clean_ascii_text(payload["description"].strip())
        hashtag_text = " ".join(hashtags)
        if not is_long:
            description = self._compress_short_description(description)
        if hashtag_text.lower() not in description.lower():
            description = f"{description}\n\n{hashtag_text}"
        title = self._clean_title(payload["title"].strip(), script.title)
        if not is_long:
            # Append 1-2 viral hashtags to the title for Shorts Feed boost
            # Prioritize #shorts and the first niche-specific one
            title_hashtags = ["#shorts"]
            niche_hashtags = [
                h for h in hashtags 
                if h.lower() not in {"#shorts", "#ytshorts", "#dailyfitx", "#viralshorts"}
            ]
            if niche_hashtags:
                title_hashtags.append(niche_hashtags[0])
            
            # Ensure at least one emoji if the AI didn't provide one
            if not any(ord(c) > 127 for c in title):
                emojis = ["🔥", "💪", "🚀", "😱", "✅", "⚠️"]
                title = f"{title} {random.choice(emojis)}"

            suffix = " ".join(title_hashtags)
            if len(title) + len(suffix) + 1 <= 95:
                title = f"{title} {suffix}"

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
        is_long = getattr(script, "video_type", "short") == "long"
        tags = self._fallback_tags(script, keyword, content_style, language_code, is_long)
        hashtags = self._fallback_hashtags(content_style, language_code, is_long)
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "primary_keyword": keyword,
        }

    def _normalize_tags(self, tags: List[str], primary_keyword: str, is_long: bool = False) -> List[str]:
        style = self._infer_style_from_keyword(primary_keyword)
        baseline = self._baseline_tags(style, primary_keyword, is_long)
        merged: List[str] = []
        for tag in [*tags, *baseline]:
            cleaned = self._clean_ascii_text(str(tag).strip())
            if is_long and "short" in cleaned.lower():
                continue
            if cleaned and cleaned.lower() not in {item.lower() for item in merged}:
                merged.append(cleaned[:30])
        return merged[:15]

    @staticmethod
    def _normalize_hashtags(hashtags: List[str], content_style: str, language_code: str, is_long: bool = False) -> List[str]:
        style_defaults = SeoGenerator._fallback_hashtags(content_style, language_code, is_long)
        cleaned: List[str] = []
        for tag in [*hashtags, *style_defaults]:
            value = str(tag).strip()
            if not value:
                continue
            if not value.startswith("#"):
                value = f"#{value}"
            if is_long and "short" in value.lower():
                continue
            if value.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(value)
        limit = 5 if is_long else 8
        return cleaned[:limit]

    @staticmethod
    def _detect_content_style(script: VideoScript) -> str:
        blob = f"{script.title} {script.primary_keyword} {script.full_script}".lower()
        if any(term in blob for term in ("yoga", "pranayam", "pranayama", "breath", "sleep yoga", "mobility")):
            return "yoga"
        if any(term in blob for term in ("fat loss", "weight loss", "cardio", "calorie")):
            return "fat_loss"
        if any(term in blob for term in ("muscle", "strength", "bulk", "back", "lift")):
            return "strength"
        if any(term in blob for term in ("motivation", "discipline", "mindset", "consistency", "focus", "lazy", "identity")):
            return "motivation"
        if any(term in blob for term in ("lifestyle", "habit", "routine", "sleep", "morning", "productivity", "self care")):
            return "lifestyle"
        if any(term in blob for term in ("sport", "athlete", "stamina", "speed", "performance", "endurance", "running")):
            return "sports_fitness"
        return "fitness"

    @staticmethod
    def _detect_language_code(script: VideoScript) -> str:
        blob = f"{script.title} {script.full_script}".lower()
        roman_hindi_markers = ("agar", "tum", "apne", "karo", "nahi", "roz", "sirf", "kal", "aaj", "shanti")
        return "hi" if any(marker in blob for marker in roman_hindi_markers) else "en"

    @staticmethod
    def _clean_ascii_text(value: str) -> str:
        return "".join(char for char in value if ord(char) < 128).strip()

    @classmethod
    def _clean_title(cls, value: str, fallback: str) -> str:
        cleaned = cls._clean_ascii_text(re.sub(r"\b\d{8,}\b", "", value))
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")
        if len(cleaned) < 12:
            cleaned = cls._clean_ascii_text(re.sub(r"\b\d{8,}\b", "", fallback))
        return cleaned[:48]

    @staticmethod
    def _compress_short_description(value: str) -> str:
        compact = re.sub(r"\s+", " ", value).strip()
        if len(compact) <= 140:
            return compact
        cut = compact[:140].rstrip(" ,.-_")
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut

    def _fallback_title(self, script: VideoScript, content_style: str, language_code: str) -> str:
        keyword = self._clean_ascii_text(script.primary_keyword or script.title)
        if content_style == "yoga":
            return (
                f"Why {keyword} Works When Nothing Else Does"
                if language_code == "en"
                else f"{keyword}: Iska Result Tab Milta Hai Jab Yeh Karo"
            )[:60]
        if content_style == "fat_loss":
            return (
                f"The {keyword} Truth Nobody Tells Beginners"
                if language_code == "en"
                else f"{keyword}: Yeh Galti Sabse Zyada Log Karte Hain"
            )[:60]
        if content_style == "strength":
            return (
                f"{keyword}: The Form Cue That Changes Everything"
                if language_code == "en"
                else f"{keyword} se Real Strength: Yeh Cue Try Karo"
            )[:60]
        if content_style == "motivation":
            return (
                f"Why {keyword} Fails on Bad Days"
                if language_code == "en"
                else f"{keyword}: Bad Days Mein Asli Test Hota Hai"
            )[:60]
        if content_style == "lifestyle":
            return (
                f"The Tiny {keyword} Habit That Changes Everything"
                if language_code == "en"
                else f"{keyword}: Choti Habit Jo Life Badal De"
            )[:60]
        if content_style == "sports_fitness":
            return (
                f"{keyword}: The Performance Mistake Most People Miss"
                if language_code == "en"
                else f"{keyword}: Performance Ki Yeh Galti Mat Karo"
            )[:60]
        return (
            f"Why Most People Fail at {keyword} (And How to Fix It)"
            if language_code == "en"
            else f"{keyword}: Kyun Fail Hote Hain Aur Kaise Bachein"
        )[:60]

    def _fallback_description(self, script: VideoScript, keyword: str, content_style: str, language_code: str) -> str:
        """Shorts descriptions should stay short, useful, and CTA-ready."""
        if language_code == "hi":
            lines = {
                "yoga": f"{keyword} se body aur mind dono calm hote hain. Save karo.",
                "fat_loss": f"{keyword} ki yeh galti band karo. Real results aate hain. Save karo.",
                "strength": f"{keyword} ka ek cue sab badal sakta hai. Aaj try karo. Save karo.",
                "motivation": f"{keyword} tab matter karta hai jab mood low ho. Save karo.",
                "lifestyle": f"{keyword} ek choti habit hai jo din badal sakti hai. Save karo.",
                "sports_fitness": f"{keyword} performance ko quietly improve karta hai. Save karo.",
                "fitness": f"{keyword} tumhara perspective change kar dega. Save karo.",
            }
        else:
            lines = {
                "yoga": f"{keyword}: calm your body and mind fast. Save this.",
                "fat_loss": f"{keyword} mistake is costing you results. Fix it today. Save this.",
                "strength": f"{keyword}: one cue that unlocks real gains. Save this.",
                "motivation": f"{keyword}: this matters most on bad days. Save this.",
                "lifestyle": f"{keyword}: one small shift changes the day. Save this.",
                "sports_fitness": f"{keyword}: the overlooked cue behind better performance. Save this.",
                "fitness": f"{keyword}: the truth most beginners miss. Save this.",
            }
        return lines.get(content_style, lines["fitness"])

    def _fallback_tags(self, script: VideoScript, keyword: str, content_style: str, language_code: str, is_long: bool = False) -> List[str]:
        tags = self._baseline_tags(content_style, keyword, is_long)
        title_words = self._clean_ascii_text(script.title).lower().split()
        if title_words:
            tags.append(" ".join(title_words[:4]))
        if language_code == "hi":
            if is_long:
                tags.extend(["hinglish fitness", "hindi english workout", "roman hindi motivation"])
            else:
                tags.extend(["hinglish shorts", "hindi english shorts", "roman hindi motivation"])
        return tags

    @staticmethod
    def _fallback_hashtags(content_style: str, language_code: str, is_long: bool = False) -> List[str]:
        if is_long:
            style_tags = {
                "yoga": ["#DailyFitX", "#yoga", "#yogaforstressrelief", "#fitness", "#wellness"],
                "fat_loss": ["#DailyFitX", "#fatloss", "#weightloss", "#fitness", "#fatlosstips"],
                "strength": ["#DailyFitX", "#strength", "#musclebuilding", "#gym", "#gymtips"],
                "motivation": ["#DailyFitX", "#motivation", "#discipline", "#mindset", "#selfimprovement"],
                "lifestyle": ["#DailyFitX", "#lifestyle", "#habits", "#productivity", "#wellness"],
                "sports_fitness": ["#DailyFitX", "#sportsfitness", "#athletetraining", "#performance", "#endurance"],
                "fitness": ["#DailyFitX", "#fitness", "#workout", "#motivation", "#fitnessmotivation"],
            }
            return style_tags.get(content_style, style_tags["fitness"])

        # Shorts: 8 tags balance discovery plus niche relevance.
        lang_tag = "#hinglishfitness" if language_code == "hi" else "#fitnessmotivation"
        style_tags = {
            "yoga": [
                "#shorts", "#ytshorts", "#DailyFitX", "#yoga",
                "#stressrelief", "#morningyoga", "#yogaflow", lang_tag,
            ],
            "fat_loss": [
                "#shorts", "#ytshorts", "#DailyFitX", "#fatloss",
                "#weightloss", "#fatlosstips", "#bellyfat", lang_tag,
            ],
            "strength": [
                "#shorts", "#ytshorts", "#DailyFitX", "#gym",
                "#musclebuilding", "#strengthtraining", "#workouttips", lang_tag,
            ],
            "motivation": [
                "#shorts", "#ytshorts", "#DailyFitX", "#motivation",
                "#discipline", "#mindset", "#motivationshorts", lang_tag,
            ],
            "lifestyle": [
                "#shorts", "#ytshorts", "#DailyFitX", "#lifestyle",
                "#habits", "#selfimprovement", "#productivity", lang_tag,
            ],
            "sports_fitness": [
                "#shorts", "#ytshorts", "#DailyFitX", "#sportsfitness",
                "#athletetraining", "#performance", "#endurance", "#viralshorts",
            ],
            "fitness": [
                "#shorts", "#ytshorts", "#DailyFitX", "#fitness",
                "#workouttips", "#viralshorts", "#fitnessmotivation", lang_tag,
            ],
        }
        return style_tags.get(content_style, style_tags["fitness"])

    def _baseline_tags(self, content_style: str, primary_keyword: str, is_long: bool = False) -> List[str]:
        # Use actual search-intent phrases people TYPE, not vanity tags
        if not is_long:
            common = [
                primary_keyword,
                f"{primary_keyword} hindi",
                f"{primary_keyword} for beginners",
                "fitness shorts india",
                "DailyFitX",
            ]
        else:
            common = [
                primary_keyword,
                f"{primary_keyword} explained",
                f"{primary_keyword} india",
                "fitness channel india",
                "DailyFitX",
            ]

        by_style = {
            "yoga": [
                "yoga for beginners in hindi",
                "yoga for stress relief",
                "morning yoga routine",
                "yoga poses for flexibility",
                "daily yoga hindi",
            ],
            "fat_loss": [
                "fat loss tips hindi",
                "belly fat reduce kaise karein",
                "weight loss diet india",
                "fat loss for beginners india",
                "how to lose fat fast hindi",
            ],
            "strength": [
                "muscle building tips hindi",
                "gym workout for beginners india",
                "how to build muscle at home",
                "strength training hindi",
                "gym motivation hindi",
            ],
            "motivation": [
                "discipline motivation hindi",
                "mindset motivation shorts",
                "self improvement hindi",
                "consistency motivation",
                "how to stay disciplined",
            ],
            "lifestyle": [
                "healthy habits hindi",
                "morning routine motivation",
                "self improvement habits",
                "productive lifestyle hindi",
                "daily routine for success",
            ],
            "sports_fitness": [
                "running performance tips",
                "sports fitness training",
                "athlete mindset hindi",
                "stamina improve kaise kare",
                "endurance training tips",
            ],
            "fitness": [
                "fitness tips for beginners india",
                "workout motivation hindi",
                "how to stay consistent gym",
                "discipline mindset hindi",
                "daily workout routine india",
            ],
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
        if "motivation" in keyword or "discipline" in keyword or "mindset" in keyword:
            return "motivation"
        if "habit" in keyword or "routine" in keyword or "lifestyle" in keyword:
            return "lifestyle"
        if "running" in keyword or "performance" in keyword or "stamina" in keyword or "athlete" in keyword:
            return "sports_fitness"
        return "fitness"

    def generate(self, script: VideoScript) -> SeoPackage:
        LOGGER.info("Generating SEO package")
        is_long = getattr(script, "video_type", "short") == "long"

        video_format_type = "Long-form cinematic video (16:9 Landscape)" if is_long else "YouTube Short (9:16 Vertical)"
        discovery_focus = "YouTube Search traffic, Suggested Videos, and high-CTR thumbnail clickability" if is_long else "the Shorts Feed, instant swipe-stop curiosity, and high replay retention"

        language_code = self._detect_language_code(script)
        content_style = self._detect_content_style(script)
        language_line = (
            "The output language should be English."
            if language_code == "en"
            else "The output language should be Hinglish in Roman script only, mixing Hindi and English naturally."
        )
        prompt = (
            "You are a master YouTube packaging strategist specializing in fitness, gym, motivation, lifestyle, and sports-fitness Shorts. "
            f"You are creating metadata for a {video_format_type}. "
            f"Your strict goal is to completely maximize virality and optimize for {discovery_focus}. "
            "Return strict JSON with keys title, description, tags, hashtags, primary_keyword. "
            + "Title should be under 52 characters, easy to read in one glance, and feel emotionally punchy. "
            + ("Description for this SHORT: write 2 very short lines, under 140 characters before hashtags. Start with the payoff. End with: Save this or Follow DailyFitX. No filler. "
               if not is_long else
               "Description should front-load the keyword, explain the viewer payoff in 2-3 sentences, and feel native to the long-form format. ")
            + "Tags should be exact phrases people search. Mix high-volume evergreen with specific niche phrases. No vanity tags. "
            + ("Hashtags: provide exactly 8. Must include #shorts and #ytshorts. Add topic-specific tags plus one broad discovery tag like #viralshorts or #motivationshorts when relevant. "
               if not is_long else
               "Hashtags: provide exactly 5. Include brand, niche, and category tags. ")
            + "Use normal English letters for text. "
            + "Do not use clickbait the script does not support. "
            + "Prefer title patterns that work in Shorts: truth bomb, warning, challenge, identity, emotional payoff, or strong curiosity."
            + "Prefer SEO that matches what viewers actually search to solve the problem the hook introduces."
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

        tags = self._normalize_tags(payload.get("tags", []), script.primary_keyword, is_long)
        hashtags = self._normalize_hashtags(payload.get("hashtags", []), content_style, language_code, is_long)
        description = self._clean_ascii_text(payload["description"].strip())
        hashtag_text = " ".join(hashtags)
        if not is_long:
            description = self._compress_short_description(description)
        if hashtag_text.lower() not in description.lower():
            description = f"{description}\n\n{hashtag_text}"
        title = self._clean_title(payload["title"].strip(), script.title)

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

    @classmethod
    def _clean_title(cls, value: str, fallback: str) -> str:
        cleaned = cls._clean_ascii_text(re.sub(r"\b\d{6,}\b", "", value))
        cleaned = re.sub(r"#\w+", "", cleaned)
        cleaned = re.sub(r"[_-]\d{4,}\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")
        if len(cleaned) < 12:
            cleaned = cls._clean_ascii_text(re.sub(r"\b\d{6,}\b", "", fallback))
        return cleaned[:55]
