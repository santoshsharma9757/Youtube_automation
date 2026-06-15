"""
kids_topics.py  –  Wonder Stories TV
======================================
Delegates to story_topics.py — the unified topic bank.
Kept for backward compatibility with any imports.
"""
from __future__ import annotations

# Re-export everything from the unified bank
from story_topics import (
    STORY_TOPIC_BANK as KIDS_TOPIC_BANK,
    MAGICAL_ELEMENTS,
    BAD_HABITS,
    MORAL_LESSONS,
    TRENDING_SIGNAL_TERMS,
    get_random_magical_element,
    get_random_bad_habit,
    get_random_moral,
    get_story_seed,
    prioritize_stories,
    filter_by_category,
)

__all__ = [
    "KIDS_TOPIC_BANK",
    "MAGICAL_ELEMENTS",
    "BAD_HABITS",
    "MORAL_LESSONS",
    "TRENDING_SIGNAL_TERMS",
    "get_random_magical_element",
    "get_random_bad_habit",
    "get_random_moral",
    "get_story_seed",
    "prioritize_stories",
    "filter_by_category",
]
