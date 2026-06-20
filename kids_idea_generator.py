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
from story_topics import STORY_TOPIC_BANK
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

    def generate_ideas(
        self,
        count: int = 5,
        video_type: str = "short",
        ideas_store: Path | None = None,
        made_for_kids: bool = False,
        category: str | None = None,
    ) -> List[KidsStoryIdea]:
        LOGGER.info(
            "Generating %s Wonder Stories TV ideas (type=%s, made_for_kids=%s, category=%s)",
            count, video_type, made_for_kids, category,
        )
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

        # ── STEP 1: PRIMARY — Sample diverse seeds from STORY_TOPIC_BANK ────────
        # Filter the bank by category and format, exclude already-used titles.
        bank_pool = [
            s for s in STORY_TOPIC_BANK
            if s["title"].lower() not in used_titles
            and (not category or s.get("category") == category)
        ]
        # Prefer format match (short/long), but don't exclude mismatches entirely
        fmt_preferred = [s for s in bank_pool if s.get("format") == video_type]
        fmt_fallback  = [s for s in bank_pool if s.get("format") != video_type]
        ordered_pool  = fmt_preferred + fmt_fallback

        import random as _rand
        _rand.shuffle(ordered_pool)  # full shuffle for variety every run

        for seed in ordered_pool:
            if len(ideas) >= count:
                break
            seed_title = seed["title"]
            if not made_for_kids:
                seed_title = seed_title.replace("Chintu", "Rohan")
            if seed_title.lower() in used_titles:
                continue

            idea_category = seed.get("category", category or "magical_adventure")
            magical = seed.get("magical_element", "") or ""
            if not magical and idea_category in ("magical_adventure", "mystery"):
                magical = get_random_magical_element(used_elements)

            adult_hook_text = seed.get("adult_hook", "")
            kids_hook_text  = seed.get("kids_hook", "")
            if not made_for_kids:
                adult_hook_text = adult_hook_text.replace("Chintu", "Rohan")
                kids_hook_text  = kids_hook_text.replace("Chintu", "Rohan")

            idea = KidsStoryIdea(
                idea_id=str(uuid.uuid4()),
                title=seed_title,
                bad_habit=seed.get("bad_habit", ""),
                bad_habit_hindi=seed.get("bad_habit_hindi", ""),
                magical_element=magical,
                moral=seed.get("moral", ""),
                moral_hindi=seed.get("moral_hindi", ""),
                angle=seed.get("angle", "Moral Story"),
                topic=seed.get("topic", ""),
                audience_value=seed.get("audience_value", adult_hook_text or f"Teach moral lesson"),
                source_prompt="story-topic-bank",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
                category=idea_category,
                adult_hook=adult_hook_text,
                kids_hook=kids_hook_text,
                made_for_kids=made_for_kids,
            )
            ideas.append(idea)
            used_elements.add(magical)
            used_habits.add(idea.bad_habit)
            used_titles.add(seed_title.lower())

        # ── STEP 2: SECONDARY — LLM-generated ideas for remaining slots ─────────
        # LLM is given a specific topic seed so it can't generate generic patterns.
        if len(ideas) < count:
            raw_ideas_list = self._llm_ideas(
                count * 2, used_elements, used_habits, used_titles,
                made_for_kids=made_for_kids, category=category,
            )
            for item in raw_ideas_list:
                if len(ideas) >= count:
                    break
                title = item.get("title", "").strip()
                if not title or title.lower() in used_titles:
                    continue
                if not made_for_kids:
                    title = title.replace("Chintu", "Rohan")

                idea_category = item.get("category", category or "magical_adventure")
                magical = item.get("magical_element", "") or ""
                if not magical and idea_category in ("magical_adventure", "mystery"):
                    magical = get_random_magical_element(used_elements)

                adult_hook_text = item.get("adult_hook", "")
                kids_hook_text  = item.get("kids_hook", "")
                if not made_for_kids:
                    adult_hook_text = adult_hook_text.replace("Chintu", "Rohan")
                    kids_hook_text  = kids_hook_text.replace("Chintu", "Rohan")

                idea = KidsStoryIdea(
                    idea_id=str(uuid.uuid4()),
                    title=title,
                    bad_habit=item.get("bad_habit", "not sharing"),
                    bad_habit_hindi=item.get("bad_habit_hindi", "nahi baatna"),
                    magical_element=magical,
                    moral=item.get("moral", "Sharing is good"),
                    moral_hindi=item.get("moral_hindi", "Baatna achha hai"),
                    angle=item.get("angle", "Moral Story"),
                    topic=item.get("topic", ""),
                    audience_value=item.get("audience_value", adult_hook_text or f"Teach moral lesson"),
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

        # ── STEP 3: ABSOLUTE FALLBACK — Random pool if still not enough ──────────
        while len(ideas) < count:
            habit_info = get_random_bad_habit(used_habits)
            idea_category = category or "magical_adventure"
            magical = get_random_magical_element(used_elements) if idea_category in ("magical_adventure", "mystery") else ""
            moral_info = get_random_moral()
            char_name  = "Chintu" if made_for_kids else "Rohan"
            title = f"{char_name} Aur {magical}" if magical else f"{char_name} Ki Seekh: {habit_info['habit'].title()}"
            if title.lower() in used_titles:
                continue
            adult_hook_text = f"Adults recall being taught the same lesson '{moral_info['lesson']}' as children."
            kids_hook_text  = f"A magical {magical} that changes everything for {char_name}!" if magical else f"{char_name} learns a life-changing lesson!"
            idea = KidsStoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                bad_habit=habit_info["habit"],
                bad_habit_hindi=habit_info["hindi"],
                magical_element=magical,
                moral=moral_info["lesson"],
                moral_hindi=moral_info["hindi"],
                angle="Moral Story",
                topic=f"{magical.lower()} kids story hindi moral" if magical else "moral story hindi",
                audience_value=f"Teach kids '{moral_info['lesson']}' using a {('magical ' + magical) if magical else 'heartfelt'} story",
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

    def _llm_ideas(
        self,
        count: int,
        used_elements: set[str],
        used_habits: set[str] = None,
        used_titles: set[str] = None,
        made_for_kids: bool = False,
        category: str | None = None,
    ) -> list[dict]:
        """Generate LLM ideas seeded from a specific topic to prevent same-pattern generation."""
        import random as _rand
        avoid_elements = ", ".join(list(used_elements)[:10]) if used_elements else "none"
        avoid_habits   = ", ".join(list(used_habits or set())[:10]) or "none"
        avoid_titles   = ", ".join(list(used_titles or set())[:20]) or "none"
        char_name = "Chintu" if made_for_kids else "Rohan"
        char_desc = (
            "A short animated 5-year-old child character with big round eyes, wearing a red t-shirt."
            if made_for_kids else
            "A young adult character (age 20-25) with mature adult features, sharp jawline, modern hairstyle, wearing a modern casual t-shirt and jeans."
        )
        category_instruction = f"Each generated story idea MUST strictly belong to the category '{category}'." if category else ""

        # Pick a random topic seed to anchor the LLM — prevents same-pattern hallucination
        topic_seeds = [
            "samay ki keemat (Value of Time)",
            "maddagar vyavhar (Helpful Behavior)",
            "imaandari ka mahatva (Importance of Honesty)",
            "mehnat ka fal (Reward of Hard Work)",
            "anushasan (Discipline)",
            "sakaaratmak soch (Positive Thinking)",
            "aatmavishwas (Self-Confidence)",
            "dhairya (Patience)",
            "zimmedari (Responsibility)",
            "sacchi dosti (True Friendship)",
            "daya aur karuna (Kindness and Compassion)",
            "bade logon ka sammaan (Respect for Elders)",
            "sahyog (Cooperation)",
            "kritagyata (Gratitude)",
            "lakshya aur safalta (Goals and Success)",
            "asafalta se seekh (Learning from Failure)",
            "kabhi haar mat maano (Never Give Up)",
            "maafi ki taaqat (Power of Forgiveness)",
            "lalach ka nuksaan (Greed's Consequences)",
            "gyaan hi shakti (Knowledge Is Power)",
            "paryavaran bachao (Save Environment)",
            "paani ka mahatva (Value of Water)",
        ]
        chosen_topic = _rand.choice(topic_seeds)

        prompt = (
            f"You are a creative AI storyteller for '{CHANNEL_NAME}' — a family storytelling channel.\n"
            f"{category_instruction}\n"
            f"Generate {count} completely NEW, unique, highly engaging story ideas.\n\n"
            f"MANDATORY: Each story MUST be based on a specific MORAL TOPIC, not a random magical adventure.\n"
            f"Anchor topic for THIS batch: '{chosen_topic}'\n"
            f"Build stories that explore THIS topic from different angles, situations, and settings.\n\n"
            f"Each story must feature {char_name}: {char_desc}\n"
            f"Use the Pixar dual-layer formula:\n"
            f"  LAYER 1 (Kids): Emotional story, relatable character, clear moral earned through events\n"
            f"  LAYER 2 (Adults): Life truth, nostalgia, parenting wisdom, recognized human experience\n\n"
            f"Story types:\n"
            f"  - For real_life / family_funny / animal_tales: NO magic, grounded everyday situations\n"
            f"  - For magical_adventure: A magical object that REVEALS or INTENSIFIES a consequence, never randomly solves the plot\n"
            f"  - For mythology / dadi_kahani: Classic Indian storytelling tone\n\n"
            f"STRICTLY AVOID:\n"
            f"  - Previously used magical elements: {avoid_elements}\n"
            f"  - Previously used bad habits/conflicts: {avoid_habits}\n"
            f"  - Previously used titles (do not repeat or closely resemble): {avoid_titles}\n\n"
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
