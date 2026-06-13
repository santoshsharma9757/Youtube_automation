"""
kids_idea_generator.py  –  Chintu Stories Channel
==================================================
Generates fresh story ideas for the kids animation channel.
Deduplicates against the ideas store to avoid repeating stories.
"""
from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from config import AppConfig
from kids_topics import (
    KIDS_TOPIC_BANK,
    get_random_bad_habit,
    get_random_magical_element,
    get_random_moral,
)
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KidsStoryIdea:
    idea_id: str
    title: str
    bad_habit: str
    bad_habit_hindi: str
    magical_element: str
    moral: str
    moral_hindi: str
    angle: str
    topic: str
    audience_value: str
    source_prompt: str
    created_at: str
    video_type: str = "short"   # "short" or "long"
    language: str = "hindi"


class KidsIdeaGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_ideas(self, count: int = 5, video_type: str = "short", ideas_store: Path | None = None) -> List[KidsStoryIdea]:
        LOGGER.info("Generating %s kids story ideas (type=%s)", count, video_type)
        store  = ideas_store or self.config.ideas_store
        existing = self._read_store(store)
        used_elements = {item.get("magical_element", "") for item in existing}
        used_habits   = {item.get("bad_habit", "") for item in existing}
        used_titles   = {item.get("title", "").lower() for item in existing}

        ideas: List[KidsStoryIdea] = []

        # 1. Try LLM-generated fresh ideas
        llm_ideas = self._llm_ideas(count * 2, used_elements)
        for item in llm_ideas:
            if len(ideas) >= count:
                break
            title = item.get("title", "").strip()
            if not title or title.lower() in used_titles:
                continue
            magical = item.get("magical_element", get_random_magical_element(used_elements)).strip()
            habit_info = get_random_bad_habit(used_habits)
            moral_info = get_random_moral()
            idea = KidsStoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                bad_habit=item.get("bad_habit", habit_info["habit"]),
                bad_habit_hindi=item.get("bad_habit_hindi", habit_info["hindi"]),
                magical_element=magical,
                moral=item.get("moral", moral_info["lesson"]),
                moral_hindi=item.get("moral_hindi", moral_info["hindi"]),
                angle=item.get("angle", "Moral Story"),
                topic=item.get("topic", f"{magical} kids story hindi"),
                audience_value=item.get("audience_value", f"Teach kids a moral lesson using a {magical}"),
                source_prompt="llm-kids",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
            )
            ideas.append(idea)
            used_elements.add(magical)
            used_habits.add(idea.bad_habit)
            used_titles.add(title.lower())

        # 2. Fallback: Static bank
        if len(ideas) < count:
            random.shuffle(KIDS_TOPIC_BANK)
            for seed in KIDS_TOPIC_BANK:
                if len(ideas) >= count:
                    break
                if seed["title"].lower() in used_titles:
                    continue
                magical = get_random_magical_element(used_elements)
                moral_info = get_random_moral()
                idea = KidsStoryIdea(
                    idea_id=str(uuid.uuid4()),
                    title=seed["title"],
                    bad_habit=seed["bad_habit"],
                    bad_habit_hindi=seed.get("bad_habit_hindi", seed["bad_habit"]),
                    magical_element=seed.get("magical_element", magical),
                    moral=seed["moral"],
                    moral_hindi=seed["moral_hindi"],
                    angle=seed["angle"],
                    topic=seed["topic"],
                    audience_value=seed["audience_value"],
                    source_prompt="static-kids-bank",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    video_type=video_type,
                )
                ideas.append(idea)
                used_elements.add(idea.magical_element)
                used_titles.add(seed["title"].lower())

        # 3. Absolute fallback: generate from scratch using random pools
        while len(ideas) < count:
            habit_info   = get_random_bad_habit(used_habits)
            magical      = get_random_magical_element(used_elements)
            moral_info   = get_random_moral()
            title = f"Chintu Aur {magical}"
            if title.lower() in used_titles:
                continue
            idea = KidsStoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                bad_habit=habit_info["habit"],
                bad_habit_hindi=habit_info["hindi"],
                magical_element=magical,
                moral=moral_info["lesson"],
                moral_hindi=moral_info["hindi"],
                angle="Moral Story",
                topic=f"{magical.lower()} kids story hindi moral",
                audience_value=f"Teach kids '{moral_info['lesson']}' using a magical story with {magical}",
                source_prompt="pool-random",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
            )
            ideas.append(idea)
            used_elements.add(magical)
            used_habits.add(habit_info["habit"])
            used_titles.add(title.lower())

        LOGGER.info("Generated %s kids ideas", len(ideas))
        return ideas[:count]

    def _llm_ideas(self, count: int, used_elements: set[str]) -> list[dict]:
        avoid_str = ", ".join(list(used_elements)[:10]) if used_elements else "none"
        prompt = (
            f"You are a creative AI storyteller for a YouTube Kids channel called 'Chintu Stories'.\n"
            f"Generate {count} completely NEW and unique moral story ideas.\n"
            f"Each story must feature:\n"
            f"  - Chintu: A short animated character with big round eyes, wearing a red t-shirt.\n"
            f"  - Mother: A tall animated character in a yellow traditional outfit.\n"
            f"  - A unique bad habit that Chintu has in this story. PLEASE VARY THIS WIDELY (e.g., eating too much junk food, not brushing teeth, playing video games too much, being rude, sleeping late). DO NOT use 'not sharing toys' again.\n"
            f"  - A brand new magical/creative element that the Mother uses to teach the lesson.\n"
            f"  - A clear moral lesson for children.\n\n"
            f"Magical elements already used (DO NOT repeat these): {avoid_str}\n\n"
            f"Return strict JSON with key 'ideas', which is an array of objects.\n"
            f"Each object must have: title, bad_habit, bad_habit_hindi, magical_element, moral, moral_hindi, angle, topic, audience_value.\n"
            f"Title format: 'Chintu Aur [Magical Element Name]'\n"
            f"Language: bad habits and morals in both English and Hindi (Roman script).\n"
            f"Only output the JSON, no other text."
        )
        try:
            payload, _ = build_json_with_fallback(
                self.llm,
                prompt,
                lambda: {"ideas": []},
                "kids-ideas",
            )
            return payload.get("ideas", [])
        except Exception as exc:
            LOGGER.warning("LLM kids idea generation failed: %s", exc)
            return []

    def save_new_ideas(self, ideas: Iterable[KidsStoryIdea], ideas_store: Path | None = None) -> List[KidsStoryIdea]:
        store = ideas_store or self.config.ideas_store
        existing = self._read_store(store)
        existing_titles = {item.get("title", "").lower() for item in existing}
        saved: List[KidsStoryIdea] = []
        for idea in ideas:
            if idea.title.lower() in existing_titles:
                LOGGER.info("Skipping duplicate kids idea: %s", idea.title)
                continue
            existing.append(asdict(idea))
            existing_titles.add(idea.title.lower())
            saved.append(idea)
        self._write_store(store, existing)
        LOGGER.info("Saved %s new kids ideas", len(saved))
        return saved

    @staticmethod
    def _read_store(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_store(path: Path, payload: list[dict]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
