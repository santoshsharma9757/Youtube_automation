"""
story_idea_generator.py  –  Wonder Stories TV
=============================================
Generates fresh viral story ideas for Wonder Stories TV.

Story Categories:
  mystery_stories     → Mystery Stories (suspense + twist endings)
  shocking_facts      → Shocking Facts (jaw-dropping real/fictional facts)
  suspense_stories    → Suspense Stories (psychological tension builds)
  dark_facts          → Dark Facts (dark side of history/world)
  psychological       → Psychological Stories (mind-bending)
  thriller_stories    → Thriller Stories (high stakes, fast paced)
  horror_stories      → Horror Stories (atmospheric horror)
  crime_stories       → Crime Stories (real/fictional crime)
  karma_stories       → Karma Stories (justice served, poetic endings)
  real_life_facts     → Real-Life Facts (inspiring/shocking real events)
  moral_stories       → Moral Stories (strong life lessons)
  bhagwan_stories     → Bhagwan Stories (devotional, uplifting, respectful)
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
from story_topics import STORY_TOPIC_BANK
from llm_fallback import LlmFallbackClient, build_json_with_fallback

LOGGER = logging.getLogger(__name__)

CHANNEL_NAME = "Wonder Stories TV"

VALID_CATEGORIES = {
    "mystery_stories",
    "shocking_facts",
    "suspense_stories",
    "dark_facts",
    "psychological",
    "thriller_stories",
    "horror_stories",
    "crime_stories",
    "karma_stories",
    "real_life_facts",
    "moral_stories",
    "bhagwan_stories",
    "inspirational_stories",
    "motivational_stories",
}

# Fallback topic seeds per category for LLM-guided generation
CATEGORY_SEEDS: dict[str, list[str]] = {
    "mystery_stories": [
        "ek raaz jo saalon baad khula (A secret revealed after years)",
        "woh cheez jo sab dekhte the magar koi samajh na paaya (What everyone saw but none understood)",
        "paheli jo khud jawab ban gayi (The puzzle that became the answer)",
    ],
    "shocking_facts": [
        "duniya ki sabse badi gehri sach (World's deepest hidden truth)",
        "woh baat jo textbooks mein nahi likhi (What textbooks never tell you)",
        "ittefaq ya niyati — hairan kar dene wala sach (Coincidence or fate — shocking truth)",
    ],
    "suspense_stories": [
        "aakhri 5 minute ka suspense (The suspense of the last 5 minutes)",
        "koi tha wahan — ya sirf ek dhoka (Someone was there — or just an illusion)",
        "woh awaaz raat ko (That voice in the night)",
    ],
    "dark_facts": [
        "itihaas ka woh andhera panna (The dark page of history)",
        "jo sach chhupa diya gaya (The truth that was hidden)",
        "duniya ki sabse khatarnak sach (The world's most dangerous truth)",
    ],
    "psychological": [
        "insaan apna dushman khud (Man is his own enemy)",
        "ek soch ne zindagi badal di (One thought changed everything)",
        "dimag ka khel — sach ya wahm (Mind's game — reality or illusion)",
    ],
    "thriller_stories": [
        "48 ghante — aur sab kuch badal gaya (48 hours — and everything changed)",
        "galat jagah galat waqt (Wrong place, wrong time)",
        "ek galti ne poori zindagi badal di (One mistake changed an entire life)",
    ],
    "horror_stories": [
        "woh ghar jo kabhi khali nahi tha (That house that was never truly empty)",
        "raat ke 3 baje ki awaaz (The sound at 3 AM)",
        "jo wapas aata hai (What comes back)",
    ],
    "crime_stories": [
        "perfect crime ka ant (The end of a perfect crime)",
        "jo chhupa nahi reh sakta (What cannot stay hidden)",
        "sach ki jeet — hamesha (Truth always wins)",
    ],
    "karma_stories": [
        "karma ne hisaab kiya (Karma settled the score)",
        "jo booge wahi kaatoge (You reap what you sow)",
        "waqt ne badla liya (Time took its revenge)",
    ],
    "real_life_facts": [
        "ek insaan ki asli kahani jo inspire kare (A real person's story that inspires)",
        "duniya ki sabse amazing real story (World's most amazing real story)",
        "sach mein hua tha yeh — believe it or not (This really happened — believe it or not)",
    ],
    "moral_stories": [
        "ek seekh jo zindagi bhar yaad rahe (A lesson remembered for life)",
        "sacchi daulat kya hai (What is true wealth)",
        "rishtey aur zimmedari (Relationships and responsibility)",
    ],
    "bhagwan_stories": [
        "bhakti ka woh pal jo zindagi badal de (The moment of devotion that changes everything)",
        "bhagwan ka woh sanket jo kisi ne nahi samjha (The sign from Bhagwan nobody understood)",
        "mandir mein mila woh jawab jo dil se aaya (The answer found in a temple that came from the heart)",
    ],
    "inspirational_stories": [
        "haar na maanane wali kahani (A story of resilience and never giving up)",
        "ek chhota sa badlaav, ek badi umeed (A small action that brought huge hope)",
        "toota sapna par buland housla (Overcoming a tragedy to inspire others)",
    ],
    "motivational_stories": [
        "parishram ka phal aur safalta (The reward of hard work and struggle)",
        "mulyawan samay ki keemat (The value and proper utilization of precious time)",
        "shuruat zero se, safar shikhar tak (Starting from nothing and achieving success through consistency)",
    ],
}


@dataclass
class StoryIdea:
    idea_id: str
    title: str
    hook: str                   # viral hook / first-line attention grabber
    hook_hindi: str             # hook in Hindi
    core_conflict: str          # central conflict/tension of the story
    twist: str                  # the twist or shocking revelation
    moral: str                  # moral / takeaway
    moral_hindi: str            # moral in Hindi
    angle: str                  # storytelling angle
    topic: str                  # SEO topic keyword
    audience_hook: str          # why viewers will share/comment
    source_prompt: str
    created_at: str
    video_type: str = "short"   # short | long
    language: str = "hindi"
    category: str = "mystery_stories"


class IdeaGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_ideas(
        self,
        count: int = 5,
        video_type: str = "short",
        ideas_store: Path | None = None,
        category: str | None = None,
    ) -> List[StoryIdea]:
        LOGGER.info(
            "Generating %s Wonder Stories TV ideas (type=%s, category=%s)",
            count, video_type, category,
        )
        store    = ideas_store or self.config.ideas_store
        existing = self._read_store(store)
        used_titles = {item.get("title", "").lower() for item in existing}

        # If a specific category is requested, use the original legacy single-category logic
        if category is not None:
            ideas: List[StoryIdea] = []

            # ── STEP 1: PRIMARY — Sample from STORY_TOPIC_BANK ─────────────────────
            bank_pool = [
                s for s in STORY_TOPIC_BANK
                if s["title"].lower() not in used_titles
                and s.get("category") == category
            ]
            fmt_preferred = [s for s in bank_pool if s.get("format") == video_type]
            fmt_fallback  = [s for s in bank_pool if s.get("format") != video_type]
            ordered_pool  = fmt_preferred + fmt_fallback
            random.shuffle(ordered_pool)

            for seed in ordered_pool:
                if len(ideas) >= count:
                    break
                seed_title = seed["title"]
                if seed_title.lower() in used_titles:
                    continue

                idea = StoryIdea(
                    idea_id=str(uuid.uuid4()),
                    title=seed_title,
                    hook=seed.get("hook", ""),
                    hook_hindi=seed.get("hook_hindi", ""),
                    core_conflict=seed.get("core_conflict", ""),
                    twist=seed.get("twist", ""),
                    moral=seed.get("moral", ""),
                    moral_hindi=seed.get("moral_hindi", ""),
                    angle=seed.get("angle", "Story"),
                    topic=seed.get("topic", ""),
                    audience_hook=seed.get("audience_hook", ""),
                    source_prompt="story-topic-bank",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    video_type=video_type,
                    category=category,
                )
                ideas.append(idea)
                used_titles.add(seed_title.lower())

            # ── STEP 2: SECONDARY — LLM for remaining slots ─────────────────────────
            if len(ideas) < count:
                raw_list = self._llm_ideas(
                    (count - len(ideas)) * 2, used_titles, category=category, video_type=video_type,
                )
                for item in raw_list:
                    if len(ideas) >= count:
                        break
                    title = item.get("title", "").strip()
                    if not title or title.lower() in used_titles:
                        continue
                    idea = StoryIdea(
                        idea_id=str(uuid.uuid4()),
                        title=title,
                        hook=item.get("hook", ""),
                        hook_hindi=item.get("hook_hindi", ""),
                        core_conflict=item.get("core_conflict", ""),
                        twist=item.get("twist", ""),
                        moral=item.get("moral", ""),
                        moral_hindi=item.get("moral_hindi", ""),
                        angle=item.get("angle", "Story"),
                        topic=item.get("topic", ""),
                        audience_hook=item.get("audience_hook", ""),
                        source_prompt="llm-generated",
                        created_at=datetime.now(timezone.utc).isoformat(),
                        video_type=video_type,
                        category=category,
                    )
                    ideas.append(idea)
                    used_titles.add(title.lower())

            # ── STEP 3: ABSOLUTE FALLBACK ────────────────────────────────────────────
            while len(ideas) < count:
                seeds = CATEGORY_SEEDS.get(category, CATEGORY_SEEDS["mystery_stories"])
                seed_text = random.choice(seeds)
                title = f"Wonder Stories TV — {seed_text.split('(')[0].strip()}"
                if title.lower() in used_titles:
                    continue
                idea = StoryIdea(
                    idea_id=str(uuid.uuid4()),
                    title=title,
                    hook="Ek aisi kahani jo aapko sochne par majboor kar degi...",
                    hook_hindi="Kya aap sach sunn-ne ke liye taiyaar hain?",
                    core_conflict=seed_text,
                    twist="Ant mein sab kuch badal jaata hai",
                    moral="Sach hamesha saamne aata hai",
                    moral_hindi="सच्चाई हमेशा सामने आती है",
                    angle="Story",
                    topic=category.replace("_", " "),
                    audience_hook="Share karo agar tumhe bhi yeh baat pata nahi thi!",
                    source_prompt="pool-random",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    video_type=video_type,
                    category=category,
                )
                ideas.append(idea)
                used_titles.add(title.lower())

            LOGGER.info("Generated %s Wonder Stories TV ideas for category %s", len(ideas), category)
            return ideas[:count]

        # ── 50/50 BALANCED CATEGORY SPLIT ──────────────────────────────────────────
        # Determine how many slots go to Inspirational vs Suspenseful
        if count == 1:
            if random.random() < 0.5:
                count_insp, count_susp = 1, 0
            else:
                count_insp, count_susp = 0, 1
        else:
            count_insp = count // 2
            count_susp = count - count_insp
            if count % 2 != 0 and random.random() < 0.5:
                count_insp, count_susp = count_susp, count_insp

        insp_cats = {"karma_stories", "moral_stories", "real_life_facts", "bhagwan_stories", "inspirational_stories", "motivational_stories"}
        susp_cats = {"horror_stories", "mystery_stories", "suspense_stories", "crime_stories", "psychological", "thriller_stories", "shocking_facts", "dark_facts"}

        # Gather bank candidates
        bank_pool = [
            s for s in STORY_TOPIC_BANK
            if s["title"].lower() not in used_titles
        ]

        bank_insp = [s for s in bank_pool if s.get("category", "mystery_stories") in insp_cats]
        bank_susp = [s for s in bank_pool if s.get("category", "mystery_stories") in susp_cats]

        # Prefer requested video type
        def sort_by_format(pool):
            pref = [s for s in pool if s.get("format") == video_type]
            fallback = [s for s in pool if s.get("format") != video_type]
            res = pref + fallback
            random.shuffle(res)
            return res

        bank_insp = sort_by_format(bank_insp)
        bank_susp = sort_by_format(bank_susp)

        selected_insp = []
        selected_susp = []

        def make_idea(seed, cat_name):
            return StoryIdea(
                idea_id=str(uuid.uuid4()),
                title=seed["title"],
                hook=seed.get("hook", ""),
                hook_hindi=seed.get("hook_hindi", ""),
                core_conflict=seed.get("core_conflict", ""),
                twist=seed.get("twist", ""),
                moral=seed.get("moral", ""),
                moral_hindi=seed.get("moral_hindi", ""),
                angle=seed.get("angle", "Story"),
                topic=seed.get("topic", ""),
                audience_hook=seed.get("audience_hook", ""),
                source_prompt="story-topic-bank",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
                category=cat_name,
            )

        # Pull from bank
        for seed in bank_insp:
            if len(selected_insp) >= count_insp:
                break
            selected_insp.append(make_idea(seed, seed.get("category", "karma_stories")))
            used_titles.add(seed["title"].lower())

        for seed in bank_susp:
            if len(selected_susp) >= count_susp:
                break
            selected_susp.append(make_idea(seed, seed.get("category", "mystery_stories")))
            used_titles.add(seed["title"].lower())

        # Pull from LLM if needed
        needed_insp = count_insp - len(selected_insp)
        needed_susp = count_susp - len(selected_susp)

        if needed_insp > 0 or needed_susp > 0:
            llm_count = (needed_insp + needed_susp) * 2
            raw_list = self._llm_ideas(llm_count, used_titles, category=None, video_type=video_type)
            
            llm_insp = []
            llm_susp = []
            for item in raw_list:
                title = item.get("title", "").strip()
                if not title or title.lower() in used_titles:
                    continue
                cat = item.get("category", "mystery_stories")
                if cat not in VALID_CATEGORIES:
                    cat = "mystery_stories"

                idea = StoryIdea(
                    idea_id=str(uuid.uuid4()),
                    title=title,
                    hook=item.get("hook", ""),
                    hook_hindi=item.get("hook_hindi", ""),
                    core_conflict=item.get("core_conflict", ""),
                    twist=item.get("twist", ""),
                    moral=item.get("moral", ""),
                    moral_hindi=item.get("moral_hindi", ""),
                    angle=item.get("angle", "Story"),
                    topic=item.get("topic", ""),
                    audience_hook=item.get("audience_hook", ""),
                    source_prompt="llm-generated",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    video_type=video_type,
                    category=cat,
                )
                if cat in insp_cats:
                    llm_insp.append(idea)
                else:
                    llm_susp.append(idea)

            for idea in llm_insp:
                if len(selected_insp) >= count_insp:
                    break
                selected_insp.append(idea)
                used_titles.add(idea.title.lower())

            for idea in llm_susp:
                if len(selected_susp) >= count_susp:
                    break
                selected_susp.append(idea)
                used_titles.add(idea.title.lower())

        # Fallback to random if still lacking slots
        needed_insp = count_insp - len(selected_insp)
        needed_susp = count_susp - len(selected_susp)

        while needed_insp > 0:
            cat = random.choice(list(insp_cats))
            seeds = CATEGORY_SEEDS.get(cat, CATEGORY_SEEDS["karma_stories"])
            seed_text = random.choice(seeds)
            title = f"Wonder Stories TV — {seed_text.split('(')[0].strip()}"
            if title.lower() in used_titles:
                continue
            idea = StoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                hook="Ek aisi kahani jo aapko seekh de...",
                hook_hindi="Kya aap is seekh ko samajh paayenge?",
                core_conflict=seed_text,
                twist="Ant mein sacchai ki jeet hoti hai",
                moral="Seekh: Hamesha saccha raho",
                moral_hindi="सीख: हमेशा सच्चे रहो",
                angle="Karma Story",
                topic=cat.replace("_", " "),
                audience_hook="Share karo agar aap bhi is seekh se sehmat hain!",
                source_prompt="pool-random",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
                category=cat,
            )
            selected_insp.append(idea)
            used_titles.add(title.lower())
            needed_insp -= 1

        while needed_susp > 0:
            cat = random.choice(list(susp_cats))
            seeds = CATEGORY_SEEDS.get(cat, CATEGORY_SEEDS["mystery_stories"])
            seed_text = random.choice(seeds)
            title = f"Wonder Stories TV — {seed_text.split('(')[0].strip()}"
            if title.lower() in used_titles:
                continue
            idea = StoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                hook="Ek aisi kahani jo aapko sochne par majboor kar degi...",
                hook_hindi="Kya aap sach sunn-ne ke liye taiyaar hain?",
                core_conflict=seed_text,
                twist="Ant mein sab kuch badal jaata hai",
                moral="Sach hamesha saamne aata hai",
                moral_hindi="सच्चाई हमेशा सामने आती है",
                angle="Suspense Story",
                topic=cat.replace("_", " "),
                audience_hook="Share karo agar aapko bhi yeh baat pata nahi thi!",
                source_prompt="pool-random",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=video_type,
                category=cat,
            )
            selected_susp.append(idea)
            used_titles.add(title.lower())
            needed_susp -= 1

        ideas = selected_insp + selected_susp
        random.shuffle(ideas)
        LOGGER.info("Generated %d balanced Wonder Stories TV ideas (Inspirational: %d, Suspenseful: %d)", len(ideas), len(selected_insp), len(selected_susp))
        return ideas[:count]

    def _llm_ideas(
        self,
        count: int,
        used_titles: set[str],
        category: str | None = None,
        video_type: str = "short",
    ) -> list[dict]:
        """Generate LLM story ideas for the viral Hindi stories channel."""
        avoid_titles = ", ".join(list(used_titles)[:20]) or "none"
        cat_instruction = (
            f"Each story MUST strictly belong to the category '{category}'."
            if category else
            "You MUST generate exactly 50% of the ideas from the Inspirational/Moral categories: "
            "['karma_stories', 'moral_stories', 'real_life_facts', 'bhagwan_stories']. "
            "The other 50% MUST be from the Suspense/Thriller/Horror/Mystery/Facts categories: "
            "['horror_stories', 'mystery_stories', 'suspense_stories', 'crime_stories', 'psychological', 'thriller_stories', 'shocking_facts', 'dark_facts']."
        )
        cat_seeds = CATEGORY_SEEDS.get(category or "mystery_stories", [])
        seed_hint = random.choice(cat_seeds) if cat_seeds else "emotional, gripping story"
        if category == "bhagwan_stories":
            cat_instruction += (
                "\nFor bhagwan_stories, keep the tone reverent, devotional, uplifting, and respectful. "
                "Focus on bhakti, darshan, guidance, blessings, or a meaningful miracle."
            )

        uplifting_categories = {"inspirational_stories", "motivational_stories", "moral_stories"}
        if category in uplifting_categories:
            formula_rules = (
                f"  - EMOTIONAL HUMAN DRAMA (MANDATORY): For '{category}', the story must focus on an emotional, inspiring human struggle or growth (e.g., overcoming poverty, dedication to hard work, valuing time, helping others, achieving a dream against all odds).\n"
                f"  - NO HORROR/SUPERNATURAL/CRIME: Strictly avoid ghosts, curses, murders, horror, or criminal themes for this category.\n"
                f"  - SHOW, DON'T TELL: Do not write general self-help lectures. Instead, write a concrete character-driven narrative (e.g., a poor student studying under a street light, a farmer who digs a well in dry land, a father teaching his child using a broken clock).\n"
                f"  - HIGH RETENTION BENCHMARK EXAMPLES:\n"
                f"    * Example 1: A poor boy who walks 5 miles everyday in torn shoes to study, eventually becoming an officer and helping others.\n"
                f"    * Example 2: A father who gives his son a broken clock to teach him the value of lost time.\n"
                f"    * Example 3: A farmer who keeps digging a well in dry land for months while the village laughs, until he finally strikes water.\n"
            )
        else:
            formula_rules = (
                f"  - NO ABSTRACT IDEAS: Avoid abstract, corporate, or self-help concepts (e.g., do NOT generate ideas about 'safalta', 'kamyabi', 'nayi soch', 'duniya badalna', 'hard work', 'success', 'positivity'). These are boring and get skipped.\n"
                f"  - NO MUNDANE OR DOMESTIC TOPICS: Do NOT generate ideas about kitchen utensils, cooking, household items, daily office work, traffic, or simple domestic chores. These are extremely boring and result in bad videos.\n"
                f"  - HIGH-STAKES DRAMA ONLY: Every story concept must involve a high-stakes, dramatic conflict: life or death, deep family secrets, ancient curses, supernatural mysteries, severe betrayal, heavy karma payback, or mind-bending psychological shifts.\n"
                f"  - CONCRETE SCENARIOS ONLY: Focus on highly specific, physical, character-driven, or supernatural situations (e.g., a locked room, a changing photo, a stolen coin, a clock stopping, a mysterious disease, a physical choice).\n"
                f"  - HIGH RETENTION BENCHMARK EXAMPLES:\n"
                f"    * Example 1: A locked room where a photo changes to include the intruder and his lost child from 20 years ago.\n"
                f"    * Example 2: Two seeds planted together; one decays in the dirt due to fear, while the other grows into a giant tree.\n"
                f"    * Example 3: A rich man who steals a beggar's last coin, only to have his vault burn to ashes that very evening.\n"
                f"    * Example 4: A house where staying the night ages you 20 years, and a missing investigator's photo appears on the wall.\n"
            )

        prompt = (
            f"You are a viral content creator for 'Wonder Stories TV' — a Hindi storytelling channel "
            f"on YouTube that creates HIGHLY VIRAL mystery, suspense, horror, crime, karma, "
            f"psychological, moral, and devotional stories in Hindi.\n\n"
            f"{cat_instruction}\n"
            f"Anchor concept for THIS batch: '{seed_hint}'\n\n"
            f"Generate {count} completely NEW, unique, HIGHLY VIRAL story ideas.\n\n"
            f"VIRAL FORMULA (CRITICAL RULES):\n"
            f"{formula_rules}\n"
            f"  - Open with a concrete incident, visible consequence, or shocking change. Avoid vague teaser questions.\n"
            f"  - Build the story like a mini film: situation -> trouble -> escalation -> reveal -> complete ending.\n"
            f"  - The first line should feel like the opening shot, not a trailer.\n"
            f"  - The twist must re-frame the opening, not just add another fact.\n"
            f"  - Leave the viewer with a strong feeling and a complete payoff.\n"
            f"  - Titles that make people STOP scrolling (max 10 words, Hindi + English mix)\n\n"
            f"AVOID these already-used titles: {avoid_titles}\n\n"
            f"Return strict JSON with key 'ideas', array of objects. Each object:\n"
            f"  title (Hindi + English mix, max 10 words, scroll-stopping),\n"
            f"  hook (English — first line that grabs attention),\n"
            f"  hook_hindi (same hook in Hindi),\n"
            f"  core_conflict (the central tension),\n"
            f"  twist (the surprising revelation or ending),\n"
            f"  moral (English takeaway),\n"
            f"  moral_hindi (Hindi takeaway),\n"
            f"  angle (e.g. 'Mystery Thriller', 'Karma Story', 'Dark Truth'),\n"
            f"  topic (SEO keyword phrase),\n"
            f"  audience_hook (why people share/comment),\n"
            f"  category (one of the valid categories above)\n"
            f"Only output the JSON, no other text."
        )
        try:
            payload, _ = build_json_with_fallback(
                self.llm,
                prompt,
                lambda: {"ideas": []},
                "story-ideas",
            )
            return payload.get("ideas", [])
        except Exception as exc:
            LOGGER.warning("LLM idea generation failed: %s", exc)
            return []

    def save_new_ideas(
        self, ideas: Iterable[StoryIdea], ideas_store: Path | None = None
    ) -> List[StoryIdea]:
        store = ideas_store or self.config.ideas_store
        existing = self._read_store(store)
        existing_titles = {item.get("title", "").lower() for item in existing}
        saved: List[StoryIdea] = []
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
