"""
kids_idea_generator.py  –  Wonder Stories TV
=============================================
Generates fresh story ideas for Wonder Stories TV.
Deduplicates against the ideas store to avoid repeating stories.

KidsStoryIdea dataclass now includes:
  - category      : story category (magical_adventure, mythology, etc.)
  - adult_hook    : what makes adults watch/stay
  - kids_hook     : what makes kids laugh/cry/engage
  - format        : short | mini | long | series

These extra fields feed into the dual-layer story prompt in kids_story_generator.py.
"""
from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from config import AppConfig
from kids_topics import (
    KIDS_TOPIC_BANK,
    get_random_bad_habit,
    get_random_magical_element,
    get_random_moral,
    get_story_seed,
    prioritize_stories,
)
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)

CHANNEL_NAME = "Wonder Stories TV"


@dataclass
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
    video_type: str = "short"     # short | mini | long | series
    language: str = "hindi"
    # Wonder Stories TV dual-layer fields
    category: str = "magical_adventure"
    adult_hook: str = ""
    kids_hook: str = ""
    made_for_kids: bool = False


class KidsIdeaGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_ideas(self, count: int = 5, video_type: str = "short", ideas_store: Path | None = None, made_for_kids: bool = False, category: str | None = None) -> List[KidsStoryIdea]:
        LOGGER.info("Generating %s Wonder Stories TV ideas (type=%s, made_for_kids=%s, category=%s)", count, video_type, made_for_kids, category)
        store    = ideas_store or self.config.ideas_store
        existing = self._read_store(store)
        used_elements = set()
        used_habits = set()
        used_titles   = {item.get("title", "").lower() for item in existing}
        for item in existing:
            if item.get("magical_element"):
                used_elements.add(item["magical_element"])
            if item.get("bad_habit"):
                used_habits.add(item["bad_habit"])

        ideas: List[KidsStoryIdea] = []

        # 1. Try LLM-generated fresh ideas
        raw_ideas_list = self._llm_ideas(count * 2, used_elements, made_for_kids=made_for_kids, category=category)
        for item in raw_ideas_list:
            if len(ideas) >= count:
                break
            title = item.get("title", "").strip()
            if not title or title.lower() in used_titles:
                continue
            
            # If not made for kids, ensure character name is Rohan instead of Chintu in title and hooks
            if not made_for_kids:
                title = title.replace("Chintu", "Rohan")
            
            magical = item.get("magical_element") or get_random_magical_element(used_elements)
            
            adult_hook_text = item.get("adult_hook", "")
            kids_hook_text = item.get("kids_hook", "")
            if not made_for_kids:
                adult_hook_text = adult_hook_text.replace("Chintu", "Rohan")
                kids_hook_text = kids_hook_text.replace("Chintu", "Rohan")

            idea = KidsStoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                bad_habit=item.get("bad_habit", "not sharing"),
                bad_habit_hindi=item.get("bad_habit_hindi", "nahi baatna"),
                magical_element=magical,
                moral=item.get("moral", "Sharing is good"),
                moral_hindi=item.get("moral_hindi", "Baatna achha hai"),
                angle=item.get("angle", "Moral Story"),
                topic=item.get("topic", "generosity"),
                audience_value=item.get("audience_value", adult_hook_text or f"Teach moral lesson using a {magical}"),
                source_prompt="llm-wonder",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
                category=item.get("category", "magical_adventure"),
                adult_hook=adult_hook_text,
                kids_hook=kids_hook_text,
                made_for_kids=made_for_kids,
            )
            ideas.append(idea)
            used_elements.add(magical)
            used_habits.add(idea.bad_habit)
            used_titles.add(title.lower())

        # 2. Fallback: prioritized static bank (trending stories first)
        if len(ideas) < count:
            ranked_seeds = prioritize_stories()
            if category:
                ranked_seeds = [s for s in ranked_seeds if s.get("category") == category]
            for seed in ranked_seeds:
                if len(ideas) >= count:
                    break
                seed_title = seed["title"]
                if not made_for_kids:
                    seed_title = seed_title.replace("Chintu", "Rohan")
                if seed_title.lower() in used_titles:
                    continue
                magical = seed.get("magical_element") or get_random_magical_element(used_elements)
                moral_info = get_random_moral()
                
                # Replace character name in hooks
                adult_hook_text = seed.get("adult_hook", "")
                kids_hook_text = seed.get("kids_hook", "")
                if not made_for_kids:
                    adult_hook_text = adult_hook_text.replace("Chintu", "Rohan")
                    kids_hook_text = kids_hook_text.replace("Chintu", "Rohan")

                idea = KidsStoryIdea(
                    idea_id=str(uuid.uuid4()),
                    title=seed_title,
                    bad_habit=seed.get("bad_habit", ""),
                    bad_habit_hindi=seed.get("bad_habit_hindi", ""),
                    magical_element=magical,
                    moral=seed.get("moral", moral_info["lesson"]),
                    moral_hindi=seed.get("moral_hindi", moral_info["hindi"]),
                    angle=seed.get("angle", "Moral Story"),
                    topic=seed.get("topic", f"{magical.lower()} hindi story"),
                    audience_value=seed.get("audience_value", adult_hook_text or f"Teach '{seed.get('moral', '')}' through wonder"),
                    source_prompt="static-wonder-bank",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    video_type=video_type,
                    category=seed.get("category", "magical_adventure"),
                    adult_hook=adult_hook_text,
                    kids_hook=kids_hook_text,
                    made_for_kids=made_for_kids,
                )
                ideas.append(idea)
                used_elements.add(magical)
                used_titles.add(seed_title.lower())

        # 3. Absolute fallback: generate from random pools
        while len(ideas) < count:
            habit_info = get_random_bad_habit(used_habits)
            magical    = get_random_magical_element(used_elements)
            moral_info = get_random_moral()
            char_name  = "Chintu" if made_for_kids else "Rohan"
            title = f"{char_name} Aur {magical}"
            if title.lower() in used_titles:
                continue
            
            adult_hook_text = f"Adults recall being taught the same lesson '{moral_info['lesson']}' as children."
            kids_hook_text = f"A magical {magical} that changes everything for {char_name}!"
            if not made_for_kids:
                adult_hook_text = adult_hook_text.replace("Chintu", "Rohan")

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
                category="magical_adventure",
                adult_hook=adult_hook_text,
                kids_hook=kids_hook_text,
                made_for_kids=made_for_kids,
            )
            ideas.append(idea)
            used_elements.add(magical)
            used_habits.add(habit_info["habit"])
            used_titles.add(title.lower())

        LOGGER.info("Generated %s Wonder Stories TV ideas", len(ideas))
        return ideas[:count]

    def _llm_ideas(self, count: int, used_elements: set[str], made_for_kids: bool = False, category: str | None = None) -> list[dict]:
        avoid_str = ", ".join(list(used_elements)[:10]) if used_elements else "none"
        char_name = "Chintu" if made_for_kids else "Rohan"
        char_desc = (
            "A short animated 5-year-old child character with big round eyes, wearing a red t-shirt."
            if made_for_kids else
            "A young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans."
        )
        category_instruction = f"Each generated story idea MUST strictly belong to the category '{category}'." if category else ""
        prompt = (
            f"You are a creative AI storyteller for '{CHANNEL_NAME}' \u2014 a family storytelling channel.\n"
            f"{category_instruction}\n"
            f"Generate {count} completely NEW, unique, and highly engaging story ideas using the Pixar dual-layer formula:\n"
            f"  LAYER 1 (Kids): Suspenseful adventure, magic, mystery, humor, colorful action, clear moral.\n"
            f"  LAYER 2 (Adults): Nostalgia, parenting truth, life lesson they recognize deeply.\n\n"
            f"Each story must feature:\n"
            f"  - {char_name}: {char_desc}\n"
            f"  - A supporting character (Mother/Golu/Pinky/Mintu).\n"
            f"  - Story concept setup based on category:\n"
            f"    * For 'horror', 'mystery', 'mythology', or 'magical_adventure': focus on a suspenseful mystery, a dark jungle quest, a riddle to solve, or an adventure conflict (e.g. getting lost, finding a secret door, encountering a friendly ghost/monster, escaping a haunted temple). Set 'bad_habit' to the conflict (e.g. 'getting lost in dense jungle', 'exploring a forbidden mansion').\n"
            f"    * For other categories: a unique bad habit that {char_name} has (vary widely — mobile addiction, junk food, wasting water, telling lies).\n"
            f"  - A brand new magical/creative object or event that guides the story.\n"
            f"  - A clear moral or core lesson, AND an adult emotional hook.\n\n"
            f"Magical elements already used (DO NOT repeat): {avoid_str}\n\n"
            f"Return strict JSON with key 'ideas', array of objects. Each object:\n"
            f"  title, bad_habit, bad_habit_hindi, magical_element, moral, moral_hindi,\n"
            f"  angle, topic, category, adult_hook, kids_hook, audience_value\n"
            f"Category must be one of: magical_adventure, mythology, dadi_kahani, real_life,\n"
            f"  family_funny, animal_tales, mystery, seasonal, horror\n"
            f"Only output the JSON, no other text."
        )
        try:
            payload, _ = build_json_with_fallback(
                self.llm,
                prompt,
                lambda: {"ideas": []},
                "wonder-ideas",
            )
            return payload.get("ideas", [])
        except Exception as exc:
            LOGGER.warning("LLM idea generation failed: %s", exc)
            return []

    def save_new_ideas(self, ideas: Iterable[KidsStoryIdea], ideas_store: Path | None = None) -> List[KidsStoryIdea]:
        store = ideas_store or self.config.ideas_store
        existing = self._read_store(store)
        existing_titles = {item.get("title", "").lower() for item in existing}
        saved: List[KidsStoryIdea] = []
        for idea in ideas:
            if idea.title.lower() in existing_titles:
                LOGGER.info("Skipping duplicate idea: %s", idea.title)
                continue
            existing.append(asdict(idea))
            existing_titles.add(idea.title.lower())
            saved.append(idea)
        self._write_store(store, existing)
        LOGGER.info("Saved %s new Wonder Stories TV ideas", len(saved))
        return saved

    @staticmethod
    def _read_store(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_store(path: Path, payload: list[dict]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
