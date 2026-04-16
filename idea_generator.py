from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from config import AppConfig
from llm_fallback import LlmFallbackClient, build_json_with_fallback
from viral_topics import VIRAL_TOPIC_BANK, filter_viral_topics, sample_topic_titles


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
        LOGGER.info("Generating %s new video ideas from static bank", count)
        existing_ideas = self._read_store(self.config.ideas_store)
        existing_fingerprints = {self._idea_fingerprint(item) for item in existing_ideas}
        
        parsed = self._fallback_ideas(theme=theme, language=language)
        import random
        candidates = parsed.get("ideas", [])
        random.shuffle(candidates)
        
        ideas: List[VideoIdea] = []
        for item in candidates:
            candidate = {
                "title": item["title"].strip(),
                "angle": item["angle"].strip(),
                "hook": item["hook"].strip(),
                "topic": item["topic"].strip(),
                "audience_value": item["audience_value"].strip(),
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
                    source_prompt="static-bank",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    language_preference=language,
                    theme_hint=theme or "",
                )
            )
            if len(ideas) >= count:
                break
        LOGGER.info("Generated %s candidate ideas from static bank", len(ideas))
        return ideas

    @staticmethod
    def _fallback_ideas(theme: str | None = None, language: str = "hinglish") -> dict:
        use_hinglish = language.lower() in {"hinglish", "hindi", "mixed", "roman-hindi"}
        filtered_topics = filter_viral_topics(theme)
        hook_bank = [
            "Nobody tells you this.",
            "Stop doing this now.",
            "This is why you fail.",
            "You are doing it wrong.",
            "Try this tonight.",
            "Watch this before workout.",
            "This changed my body.",
            "Secret of fat loss starts here.",
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

    @staticmethod
    def _format_hook(title: str, hook_seed: str, use_hinglish: bool) -> str:
        if use_hinglish:
            return f"{title}. {hook_seed.replace('you', 'tum').replace('This', 'Yeh').replace('this', 'yeh')}"
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
