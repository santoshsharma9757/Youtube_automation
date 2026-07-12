"""
story_topics_fallback.py  –  Wonder Stories TV
===============================================
Minimal fallback topic seeds for the story idea generator.
Used when STORY_TOPIC_BANK in story_topics.py runs out of unused ideas.
"""
from __future__ import annotations
import random


# Minimal fallback pool per category
FALLBACK_SEEDS: dict[str, list[str]] = {
    "mystery_stories": [
        "Woh Ghar Jahan Koi Nahi Rehta Tha",
        "Raaz Jo 20 Saal Baad Khula",
        "Woh Cheez Jo Sab Dekhte The Par Koi Samjha Nahi",
    ],
    "shocking_facts": [
        "Duniya Ka Sabse Bada Raaz",
        "Woh Sach Jo Aapko Hairan Kar Dega",
        "History Ka Woh Pal Jo Sab Bhool Gaye",
    ],
    "suspense_stories": [
        "Koi Tha Wahan — Ya Sirf Ek Wahm",
        "Aakhri 5 Minute Ka Suspense",
        "Woh Awaaz Jo Raat Ko Aati Thi",
    ],
    "dark_facts": [
        "Itihaas Ka Woh Andhera Panna",
        "Jo Sach Chhupa Diya Gaya",
        "Duniya Ki Sabse Khatarnak Hakikat",
    ],
    "psychological": [
        "Insaan Apna Dushman Khud",
        "Ek Soch Ne Zindagi Badal Di",
        "Dimag Ka Khel — Sach Ya Wahm",
    ],
    "thriller_stories": [
        "48 Ghante Aur Sab Kuch Badal Gaya",
        "Galat Jagah Galat Waqt",
        "Ek Galti Ne Poori Zindagi Badal Di",
    ],
    "horror_stories": [
        "Woh Ghar Jo Kabhi Khali Nahi Tha",
        "Raat Ke 3 Baje Ki Awaaz",
        "Jo Wapas Aata Hai",
    ],
    "crime_stories": [
        "Perfect Crime Ka Ant",
        "Jo Chhupa Nahi Reh Sakta",
        "Sach Ki Jeet — Hamesha",
    ],
    "karma_stories": [
        "Karma Ne Hisaab Kiya",
        "Jo Booge Wahi Kaatoge",
        "Waqt Ne Badla Liya",
    ],
    "real_life_facts": [
        "Ek Insaan Ki Asli Kahani",
        "Sach Mein Hua Tha Yeh",
        "Duniya Ki Sabse Amazing Real Story",
    ],
    "moral_stories": [
        "Ek Seekh Jo Zindagi Bhar Yaad Rahe",
        "Sacchi Daulat Kya Hai",
        "Rishtey Aur Zimmedari",
    ],
}


def get_fallback_seed(category: str | None = None) -> dict:
    """Return a random fallback seed dict for use in IdeaGenerator."""
    import random as _r
    cat = category or _r.choice(list(FALLBACK_SEEDS.keys()))
    titles = FALLBACK_SEEDS.get(cat, FALLBACK_SEEDS["mystery_stories"])
    title = _r.choice(titles)
    return {
        "title": title,
        "category": cat,
        "format": "short",
        "hook": "Ek aisi kahani jo aapko sochne par majboor kar degi...",
        "hook_hindi": "Kya aap sach sunne ke liye taiyaar hain?",
        "core_conflict": f"Ek raaz jo saalon se chhupa tha",
        "twist": "Ant mein sab kuch badal jaata hai",
        "moral": "Sach hamesha saamne aata hai",
        "moral_hindi": "सच्चाई हमेशा सामने आती है",
        "angle": "Suspense Story",
        "topic": cat.replace("_", " "),
        "audience_hook": "Share karo agar tumhe bhi yeh baat pata nahi thi!",
    }
