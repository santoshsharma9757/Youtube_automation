from __future__ import annotations

import json
import logging
import random
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

import requests

from config import AppConfig
from llm_fallback import LlmFallbackClient, build_json_with_fallback
from viral_topics import VIRAL_TOPIC_BANK, prioritize_viral_topics


LOGGER = logging.getLogger(__name__)


def canonicalize_title(value: str) -> str:
    text = re.sub(r"\b\d{8,}\b", "", value.lower())
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonicalize_text(value: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_display_text(value: str) -> str:
    text = re.sub(r"\b\d{8,}\b", "", value)
    text = re.sub(r"\s+", " ", text).strip(" -_")
    return text.strip()


@dataclass(slots=True)
class VideoIdea:
    idea_id: str
    title: str
    angle: str
    hook: str
    topic: str
    audience_value: str
    source_prompt: str
    created_at: str
    language_preference: str = "hinglish"
    theme_hint: str = ""
    video_type: str = "short"


class IdeaGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_ideas(self, count: int = 5, theme: str | None = None, language: str = "hinglish") -> List[VideoIdea]:
        LOGGER.info("Generating %s new video ideas", count)
        existing_ideas = self._read_store(self.config.ideas_store)
        existing_fingerprints = {self._idea_fingerprint(item) for item in existing_ideas}

        parsed = self._live_or_fallback_ideas(theme=theme, language=language)
        candidates = parsed.get("ideas", [])
        high_priority_band = candidates[: min(len(candidates), max(count * 4, 12))]
        low_priority_band = candidates[min(len(candidates), max(count * 4, 12)) :]
        random.shuffle(high_priority_band)
        random.shuffle(low_priority_band)
        candidates = [*high_priority_band, *low_priority_band]
        
        ideas: List[VideoIdea] = []
        for item in candidates:
            candidate = {
                "title": clean_display_text(item["title"]),
                "angle": clean_display_text(item["angle"]),
                "hook": clean_display_text(item["hook"]),
                "topic": clean_display_text(item["topic"]),
                "audience_value": clean_display_text(item["audience_value"]),
            }
            if self._idea_fingerprint(candidate) in existing_fingerprints:
                continue
            ideas.append(
                VideoIdea(
                    idea_id=str(uuid.uuid4()),
                    title=candidate["title"],
                    angle=candidate["angle"],
                    hook=candidate["hook"],
                    topic=candidate["topic"],
                    audience_value=candidate["audience_value"],
                    source_prompt=parsed.get("source", "static-bank"),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    language_preference=language,
                    theme_hint=theme or "",
                )
            )
            if len(ideas) >= count:
                break
        LOGGER.info("Generated %s candidate ideas using source=%s", len(ideas), parsed.get("source", "unknown"))
        return ideas

    def _live_or_fallback_ideas(self, theme: str | None = None, language: str = "hinglish") -> dict:
        live_titles = self._fetch_live_youtube_titles(theme)
        if live_titles:
            payload = self._build_live_ideas_from_titles(live_titles, theme=theme, language=language)
            if payload.get("ideas"):
                payload["source"] = "youtube-live"
                return payload
        fallback = self._fallback_ideas(theme=theme, language=language)
        fallback["source"] = "static-bank"
        return fallback

    def _fetch_live_youtube_titles(self, theme: str | None = None) -> list[dict[str, str]]:
        if not self.config.youtube_api_key:
            return []

        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds").replace("+00:00", "Z")
        collected: list[dict[str, str | float | int]] = []
        seen_titles: set[str] = set()

        for query in self._youtube_queries(theme)[:6]:
            try:
                response = requests.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "key": self.config.youtube_api_key,
                        "part": "snippet",
                        "type": "video",
                        "maxResults": 8,
                        "q": query,
                        "order": "viewCount",
                        "publishedAfter": cutoff,
                        "regionCode": "IN",
                        "relevanceLanguage": "en",
                        "videoDuration": "short",
                        "safeSearch": "moderate",
                    },
                    timeout=20,
                )
                response.raise_for_status()
                items = response.json().get("items", [])
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("YouTube trend fetch failed for query '%s': %s", query, exc)
                continue

            video_ids = [item.get("id", {}).get("videoId", "") for item in items if item.get("id", {}).get("videoId")]
            stats_by_id = self._fetch_youtube_video_stats(video_ids)

            for item in items:
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")
                title = clean_display_text(snippet.get("title", ""))
                if not title:
                    continue
                fingerprint = canonicalize_title(title)
                if fingerprint in seen_titles:
                    continue
                seen_titles.add(fingerprint)
                stat_block = stats_by_id.get(video_id, {})
                score = self._trend_score(
                    view_count=int(stat_block.get("view_count", 0)),
                    like_count=int(stat_block.get("like_count", 0)),
                    comment_count=int(stat_block.get("comment_count", 0)),
                    published_at=snippet.get("publishedAt", ""),
                    title=title,
                    query=query,
                )
                collected.append(
                    {
                        "query": query,
                        "video_id": video_id,
                        "channel": clean_display_text(snippet.get("channelTitle", "")),
                        "title": title,
                        "published_at": snippet.get("publishedAt", ""),
                        "view_count": int(stat_block.get("view_count", 0)),
                        "like_count": int(stat_block.get("like_count", 0)),
                        "comment_count": int(stat_block.get("comment_count", 0)),
                        "trend_score": score,
                    }
                )
        collected.sort(key=lambda item: float(item.get("trend_score", 0)), reverse=True)
        LOGGER.info("Collected %s live YouTube titles", len(collected))
        return collected[:30]

    def _fetch_youtube_video_stats(self, video_ids: list[str]) -> dict[str, dict[str, int]]:
        if not video_ids:
            return {}
        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "key": self.config.youtube_api_key,
                    "part": "statistics",
                    "id": ",".join(video_ids[:50]),
                },
                timeout=20,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("YouTube video stats fetch failed: %s", exc)
            return {}

        stats: dict[str, dict[str, int]] = {}
        for item in items:
            statistics = item.get("statistics", {})
            stats[item.get("id", "")] = {
                "view_count": int(statistics.get("viewCount", 0)),
                "like_count": int(statistics.get("likeCount", 0)),
                "comment_count": int(statistics.get("commentCount", 0)),
            }
        return stats

    @staticmethod
    def _trend_score(
        view_count: int,
        like_count: int,
        comment_count: int,
        published_at: str,
        title: str,
        query: str,
    ) -> float:
        age_hours = 72.0
        if published_at:
            try:
                published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                age_hours = max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 1.0)
            except ValueError:
                age_hours = 72.0
        velocity = view_count / age_hours
        engagement = (like_count * 4) + (comment_count * 10)
        title_blob = f"{title.lower()} {query.lower()}"
        hook_bonus = 0
        if any(term in title_blob for term in ("why", "how", "mistake", "truth", "best", "vs", "sahi", "galat", "reset", "challenge")):
            hook_bonus += 250
        if any(term in title_blob for term in ("walking yoga", "breath", "pranayama", "5 minute", "2 minute", "protein", "fasted", "plateau")):
            hook_bonus += 350
        return float(velocity + engagement + hook_bonus)

    def _build_live_ideas_from_titles(
        self,
        live_titles: list[dict[str, str]],
        theme: str | None = None,
        language: str = "hinglish",
    ) -> dict:
        language_instruction = self._language_instruction(language)
        titles_blob = "\n".join(
            f"- score={int(item.get('trend_score', 0))} | views={int(item.get('view_count', 0))} | "
            f"query={item['query']} | channel={item['channel']} | title={item['title']}"
            for item in live_titles[:24]
        )
        prompt = (
            "You are a YouTube Shorts trend strategist for DailyFitX.\n"
            "Use the recent YouTube titles below as live trend signals.\n"
            f"{language_instruction}\n"
            f"Theme preference: {theme or 'fitness, yoga, meditation, motivation'}\n"
            "Return strict JSON with key ideas.\n"
            "Each idea must include title, angle, hook, topic, audience_value.\n"
            "Rules:\n"
            "- Generate up to 12 ideas.\n"
            "- Improve the trend into a better DailyFitX title instead of copying it.\n"
            "- Favor the highest-scoring live trends first.\n"
            "- Titles must be Shorts-style and usually 28 to 48 characters.\n"
            "- Focus only on fitness, yoga, meditation, motivation, fat loss, sleep, breathwork, mobility, and home workouts.\n"
            "- Prefer India-friendly Shorts topics.\n"
            "- Use Roman script only.\n"
            "- Never generate politics or non-fitness content.\n"
            f"\nLive YouTube titles:\n{titles_blob}"
        )
        payload, provider_used = build_json_with_fallback(
            self.llm,
            prompt,
            lambda: self._heuristic_live_ideas(live_titles, theme=theme, language=language),
            "youtube-live-heuristic",
        )
        LOGGER.info("Live trend idea synthesis provider used: %s", provider_used)
        return payload

    @staticmethod
    def _fallback_ideas(theme: str | None = None, language: str = "hinglish") -> dict:
        use_hinglish = language.lower() in {"hinglish", "hindi", "mixed", "roman-hindi"}
        filtered_topics = prioritize_viral_topics(theme)
        hook_bank = [
            "Most people get this wrong.",
            "Do not ignore this.",
            "This is why progress gets stuck.",
            "One tweak changes everything.",
            "Try this tonight.",
            "Watch this before your next workout.",
            "This can save months of effort.",
            "This topic is blowing up for a reason.",
        ]
        return {
            "ideas": [
                {
                    "title": item["title"],
                    "angle": item["angle"],
                    "hook": IdeaGenerator._format_hook(item["title"], hook_bank[index % len(hook_bank)], use_hinglish),
                    "topic": item["topic"],
                    "audience_value": item["audience_value"],
                }
                for index, item in enumerate(filtered_topics or VIRAL_TOPIC_BANK)
            ]
        }

    def _heuristic_live_ideas(
        self,
        live_titles: list[dict[str, str]],
        theme: str | None = None,
        language: str = "hinglish",
    ) -> dict:
        use_hinglish = language.lower() in {"hinglish", "hindi", "mixed", "roman-hindi"}
        title_blobs = " ".join(item["title"].lower() for item in live_titles)
        ideas: list[dict[str, str]] = []
        boosted_terms = [
            ("walking yoga", "Walking Yoga Se Stress Kaise Kam Hota Hai?", "Trend Explainer", "walking yoga benefits"),
            ("breath", "30 Second Breath Reset Before Workout", "Breathwork", "breathwork before workout"),
            ("pranayama", "Pranayama Se Focus Kaise Improve Hota Hai?", "Breathwork", "pranayama for focus"),
            ("protein", "Indian Diet Mein Protein Itna Low Kyun Hota Hai?", "Diet Myth", "protein indian diet"),
            ("fasted", "Fasted Morning Workout Sahi Hai Ya Nahi?", "Comparison", "fasted morning workout"),
            ("plateau", "Body 3 Mahine Baad Change Kyun Ruk Jata Hai?", "Plateau Fix", "fitness plateau"),
            ("5 minute", "5 Minute Workout Jo Busy Logo Ko Suit Kare", "Quick Workout", "5 minute workout"),
            ("2 minute", "2 Minute Workout Habit Jo Streak Bacha Le", "Habit", "2 minute workout"),
        ]
        for term, title, angle, topic_name in boosted_terms:
            if term in title_blobs:
                ideas.append(
                    {
                        "title": title,
                        "angle": angle,
                        "hook": self._format_hook(title, "This is showing up everywhere right now.", use_hinglish),
                        "topic": topic_name,
                        "audience_value": "Turn a live trending pattern into a useful Short people save",
                    }
                )
        ideas.extend(self._fallback_ideas(theme=theme, language=language).get("ideas", []))
        return {"ideas": ideas[:12]}

    @staticmethod
    def _youtube_queries(theme: str | None = None) -> list[str]:
        base_queries = [
            "fitness shorts india",
            "yoga shorts india",
            "meditation shorts",
            "motivation shorts workout",
            "breathwork shorts",
            "home workout shorts",
            "fat loss shorts india",
            "walking yoga",
        ]
        if not theme:
            return base_queries
        theme_parts = [part.strip() for part in re.split(r"[,/|]", theme) if part.strip()]
        if not theme_parts:
            theme_parts = [theme.strip()]
        return [*[f"{part} shorts" for part in theme_parts], *base_queries]

    @staticmethod
    def _format_hook(title: str, hook_seed: str, use_hinglish: bool) -> str:
        if use_hinglish:
            return (
                f"{clean_display_text(title)}. "
                f"{hook_seed.replace('you', 'tum').replace('This', 'Yeh').replace('this', 'yeh')}"
            )
        return f"{title}. {hook_seed}"

    @staticmethod
    def _language_instruction(language: str) -> str:
        mapping = {
            "english": "The language should be English-first with clean, punchy spoken delivery.",
            "hindi": "The language should be Roman Hindi mixed with a little English for clarity.",
            "hinglish": "The language should be Hinglish, with natural Roman Hindi plus strategic English phrases.",
        }
        return mapping.get(language.lower(), mapping["hinglish"])

    def save_new_ideas(self, ideas: Iterable[VideoIdea]) -> List[VideoIdea]:
        existing = self._read_store(self.config.ideas_store)
        existing_fingerprints = {self._idea_fingerprint(item) for item in existing}
        saved: List[VideoIdea] = []

        for idea in ideas:
            fingerprint = self._idea_fingerprint(asdict(idea))
            if fingerprint in existing_fingerprints:
                LOGGER.info("Skipping duplicate idea: %s", idea.title)
                continue
            existing.append(asdict(idea))
            existing_fingerprints.add(fingerprint)
            saved.append(idea)

        self._write_store(self.config.ideas_store, existing)
        LOGGER.info("Saved %s new ideas", len(saved))
        return saved

    @staticmethod
    def _read_store(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_store(path: Path, payload: list[dict]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _idea_fingerprint(item: dict) -> tuple[str, str, str]:
        return (
            canonicalize_title(str(item.get("title", ""))),
            canonicalize_text(str(item.get("topic", ""))),
            canonicalize_text(str(item.get("hook", ""))),
        )
