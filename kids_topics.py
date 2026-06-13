"""
kids_topics.py  –  Chintu Stories Channel
==========================================
Static banks for story seeds, magical elements, and moral lessons.
Used by KidsIdeaGenerator when live YouTube trend data is unavailable.
"""
from __future__ import annotations

import random


# ─── Magical Elements Pool ────────────────────────────────────────────────────
# Every story must use a brand-new magical item not used before.
MAGICAL_ELEMENTS: list[str] = [
    "Magical Watch",
    "Talking School Bag",
    "Magical Shoes",
    "Magic Spoon",
    "Hungry Dustbin",
    "Magical Glasses",
    "Talking Toothbrush",
    "Magic Lunchbox",
    "Magical Alarm Clock",
    "Talking Plant",
    "Magic Mirror",
    "Magical Book",
    "Talking Teddy Bear",
    "Magic Pencil",
    "Magical Water Bottle",
    "Talking Pillow",
    "Magic Soap Bar",
    "Magical Eraser",
    "Talking Tap (Faucet)",
    "Magic Vegetables Basket",
    "Magical Blanket",
    "Talking Shoes",
    "Magic Comb",
    "Magical Umbrella",
    "Talking Clock",
    "Magic Torch",
    "Magical Plate",
    "Talking Door",
    "Magic Backpack",
    "Magical Phone (shows consequences)",
    "Talking Piggy Bank",
    "Magic Study Table",
    "Magical Rainbow",
    "Talking Star",
    "Magic Diary",
    "Magical Bell",
    "Talking Butterfly",
    "Magic Garden",
    "Magical Candle",
    "Talking Book",
    "Magic Helmet",
    "Magical Roller Skates",
    "Talking Fish Bowl",
    "Magic Paint Brush",
    "Magical Kite",
    "Talking Moon",
    "Magic Stone",
    "Magical Compass",
    "Talking Cloud",
    "Magic Whistle",
]


# ─── Bad Habits Pool ──────────────────────────────────────────────────────────
BAD_HABITS: list[dict[str, str]] = [
    {"habit": "eating too much junk food", "hindi": "bahut zyada junk food khana"},
    {"habit": "telling lies to mother", "hindi": "maa se jhooth bolna"},
    {"habit": "not studying and playing games all day", "hindi": "padhai na karna aur din bhar games khelna"},
    {"habit": "wasting water while brushing", "hindi": "brush karte waqt paani barbad karna"},
    {"habit": "playing too much on mobile", "hindi": "mobile pe bahut zyada time waste karna"},
    {"habit": "not sharing toys with friends", "hindi": "doston se khilone share na karna"},
    {"habit": "throwing garbage on the road", "hindi": "sadak par kachra phenkna"},
    {"habit": "not sleeping on time", "hindi": "samay par na sona"},
    {"habit": "being rude to elders", "hindi": "bade logo se badtameezi karna"},
    {"habit": "not washing hands before eating", "hindi": "khane se pehle haath na dhona"},
    {"habit": "wasting food on the plate", "hindi": "plate mein khana barbad karna"},
    {"habit": "fighting with younger sibling", "hindi": "chhote bhai-behen se ladna"},
    {"habit": "stealing from mother's purse", "hindi": "maa ke purse se chori karna"},
    {"habit": "copying homework from friend", "hindi": "dost ka homework copy karna"},
    {"habit": "being jealous of others", "hindi": "doosron se jealous rehna"},
    {"habit": "breaking others' things out of anger", "hindi": "gusse mein doosron ki cheezein todna"},
    {"habit": "not brushing teeth at night", "hindi": "raat ko daant brush na karna"},
    {"habit": "wasting electricity by leaving lights on", "hindi": "lights on chhod kar bijli barbad karna"},
    {"habit": "bullying smaller kids", "hindi": "chhote bacchon ko bully karna"},
    {"habit": "eating chocolates secretly", "hindi": "chhupchhup ke chocolate khaana"},
]


# ─── Moral Lessons Pool ───────────────────────────────────────────────────────
MORAL_LESSONS: list[dict[str, str]] = [
    {"lesson": "Always tell the truth", "hindi": "Hamesha sach bolna chahiye"},
    {"lesson": "Save water, it is precious", "hindi": "Paani bachao, yeh bahumulya hai"},
    {"lesson": "Eat healthy food to stay strong", "hindi": "Takat ke liye sehatmand khana khao"},
    {"lesson": "Study hard for a bright future", "hindi": "Roshan bhavishya ke liye mehnat se padho"},
    {"lesson": "Share with friends and be kind", "hindi": "Doston ke saath banto aur dayalu bano"},
    {"lesson": "Keep your surroundings clean", "hindi": "Apne aas paas ko saaf rakho"},
    {"lesson": "Sleep on time to grow healthy", "hindi": "Sehat ke liye samay par so jao"},
    {"lesson": "Respect your elders always", "hindi": "Hamesha bade logo ki izzat karo"},
    {"lesson": "Wash hands to stay healthy", "hindi": "Sehatmand rehne ke liye haath dhote raho"},
    {"lesson": "Never waste food", "hindi": "Kabhi bhi khana barbad mat karo"},
    {"lesson": "Love your siblings", "hindi": "Apne bhai-behen se pyaar karo"},
    {"lesson": "Never steal, always ask", "hindi": "Kabhi chori mat karo, hamesha maango"},
    {"lesson": "Do your own work honestly", "hindi": "Apna kaam imandaari se karo"},
    {"lesson": "Be happy for others' success", "hindi": "Doosron ki safalta par khush raho"},
    {"lesson": "Control your anger", "hindi": "Apne gusse par kabu rakho"},
    {"lesson": "Save electricity for the future", "hindi": "Bhavishya ke liye bijli bachao"},
    {"lesson": "Be brave and kind, not a bully", "hindi": "Bahadur aur dayalu bano, bully nahi"},
    {"lesson": "Spend time with family, not just phone", "hindi": "Phone ki jagah family ke saath waqt bitao"},
]


# ─── Story Seeds Bank ─────────────────────────────────────────────────────────
# Each seed pairs a bad habit + magical element title + moral for quick idea gen
KIDS_TOPIC_BANK: list[dict[str, str]] = [
    {
        "title": "Chintu Aur Magical Watch",
        "bad_habit": "playing too much on mobile",
        "magical_element": "Magical Watch",
        "moral": "Time is precious – use it wisely",
        "moral_hindi": "Samay bahumulya hai, iska sahi upyog karo",
        "audience_value": "Teach kids to manage screen time through magical story",
        "angle": "Time Management",
        "topic": "mobile addiction kids story hindi",
    },
    {
        "title": "Chintu Aur Hungry Dustbin",
        "bad_habit": "throwing garbage on the road",
        "magical_element": "Hungry Dustbin",
        "moral": "Keep your surroundings clean",
        "moral_hindi": "Apne aas paas ko saaf rakho",
        "audience_value": "Teach kids cleanliness through a funny dustbin character",
        "angle": "Cleanliness",
        "topic": "kids moral story cleanliness hindi",
    },
    {
        "title": "Chintu Aur Talking School Bag",
        "bad_habit": "not studying and playing games all day",
        "magical_element": "Talking School Bag",
        "moral": "Study hard for a bright future",
        "moral_hindi": "Roshan bhavishya ke liye mehnat se padho",
        "audience_value": "Motivate kids to study with a fun talking bag story",
        "angle": "Education",
        "topic": "kids moral story study hindi cartoon",
    },
    {
        "title": "Chintu Aur Magic Spoon",
        "bad_habit": "eating too much junk food",
        "magical_element": "Magic Spoon",
        "moral": "Eat healthy food to stay strong",
        "moral_hindi": "Takat ke liye sehatmand khana khao",
        "audience_value": "Show kids the magic of healthy eating through a story",
        "angle": "Healthy Eating",
        "topic": "kids cartoon story healthy food hindi",
    },
    {
        "title": "Chintu Aur Talking Toothbrush",
        "bad_habit": "not brushing teeth at night",
        "magical_element": "Talking Toothbrush",
        "moral": "Brush your teeth daily for good health",
        "moral_hindi": "Rozana daant brush karo acchi sehat ke liye",
        "audience_value": "Make dental hygiene fun with a talking toothbrush character",
        "angle": "Hygiene",
        "topic": "kids story brushing teeth hindi moral",
    },
    {
        "title": "Chintu Aur Magic Water Bottle",
        "bad_habit": "wasting water while brushing",
        "magical_element": "Magic Water Bottle",
        "moral": "Save water, it is precious",
        "moral_hindi": "Paani bachao, yeh bahumulya hai",
        "audience_value": "Teach water conservation to kids through a magical story",
        "angle": "Save Water",
        "topic": "save water kids story hindi moral cartoon",
    },
    {
        "title": "Chintu Aur Magical Alarm Clock",
        "bad_habit": "not sleeping on time",
        "magical_element": "Magical Alarm Clock",
        "moral": "Sleep on time to grow healthy and strong",
        "moral_hindi": "Sehat ke liye samay par so jao",
        "audience_value": "Help kids understand the importance of sleep schedule",
        "angle": "Sleep Routine",
        "topic": "kids story sleep time hindi cartoon moral",
    },
    {
        "title": "Chintu Aur Talking Piggy Bank",
        "bad_habit": "stealing from mother's purse",
        "magical_element": "Talking Piggy Bank",
        "moral": "Never steal, always ask politely",
        "moral_hindi": "Kabhi chori mat karo, hamesha pyaar se maango",
        "audience_value": "Teach honesty and asking vs taking through a piggy bank",
        "angle": "Honesty",
        "topic": "kids moral story honesty hindi cartoon",
    },
    {
        "title": "Chintu Aur Magic Mirror",
        "bad_habit": "being rude to elders",
        "magical_element": "Magic Mirror",
        "moral": "Always respect your elders",
        "moral_hindi": "Hamesha bade logo ki izzat karo",
        "audience_value": "Show kids the importance of respect through a magic mirror",
        "angle": "Respect",
        "topic": "kids story respect elders hindi moral",
    },
    {
        "title": "Chintu Aur Magical Lunchbox",
        "bad_habit": "wasting food on the plate",
        "magical_element": "Magic Lunchbox",
        "moral": "Never waste food – many children are hungry",
        "moral_hindi": "Kabhi bhi khana barbad mat karo",
        "audience_value": "Create empathy for hunger by showing magical food consequences",
        "angle": "No Food Waste",
        "topic": "kids moral story food wastage hindi cartoon",
    },
    {
        "title": "Chintu Aur Talking Star",
        "bad_habit": "telling lies to mother",
        "magical_element": "Talking Star",
        "moral": "Always tell the truth",
        "moral_hindi": "Hamesha sach bolna chahiye",
        "audience_value": "Teach honesty through a beautiful night sky magical story",
        "angle": "Truth",
        "topic": "kids story truth telling hindi moral cartoon",
    },
    {
        "title": "Chintu Aur Magical Eraser",
        "bad_habit": "copying homework from friend",
        "magical_element": "Magical Eraser",
        "moral": "Do your own work honestly",
        "moral_hindi": "Apna kaam imandaari se karo",
        "audience_value": "Discourage cheating with a fun magical eraser story",
        "angle": "Honesty in Studies",
        "topic": "kids story no cheating hindi moral cartoon",
    },
    {
        "title": "Chintu Aur Magical Phone",
        "bad_habit": "playing too much on mobile",
        "magical_element": "Magical Phone (shows consequences)",
        "moral": "Spend time with family, not just phone",
        "moral_hindi": "Phone ki jagah family ke saath waqt bitao",
        "audience_value": "Show the real consequences of phone addiction for kids",
        "angle": "Family Time",
        "topic": "kids mobile addiction story hindi moral cartoon",
    },
    {
        "title": "Chintu Aur Magical Blanket",
        "bad_habit": "fighting with younger sibling",
        "magical_element": "Magical Blanket",
        "moral": "Love and share with your siblings",
        "moral_hindi": "Apne bhai-behen se pyaar karo aur share karo",
        "audience_value": "Promote sibling love through a warm magical story",
        "angle": "Sibling Love",
        "topic": "kids story sibling love hindi moral cartoon",
    },
    {
        "title": "Chintu Aur Talking Plant",
        "bad_habit": "not washing hands before eating",
        "magical_element": "Talking Plant",
        "moral": "Always wash hands to stay healthy",
        "moral_hindi": "Hamesha haath dhoke hi khana khao",
        "audience_value": "Promote hygiene habits with a fun talking plant story",
        "angle": "Hygiene Habits",
        "topic": "kids hand washing story hindi moral cartoon",
    },
]


def get_random_magical_element(used_elements: set[str] | None = None) -> str:
    """Pick a fresh magical element not used before in this session."""
    available = [e for e in MAGICAL_ELEMENTS if e not in (used_elements or set())]
    if not available:
        available = MAGICAL_ELEMENTS  # Reset if all used
    return random.choice(available)


def get_random_bad_habit(used_habits: set[str] | None = None) -> dict[str, str]:
    """Pick a bad habit not recently used."""
    available = [h for h in BAD_HABITS if h["habit"] not in (used_habits or set())]
    if not available:
        available = BAD_HABITS
    return random.choice(available)


def get_random_moral(used_morals: set[str] | None = None) -> dict[str, str]:
    """Pick a moral lesson not recently used."""
    available = [m for m in MORAL_LESSONS if m["lesson"] not in (used_morals or set())]
    if not available:
        available = MORAL_LESSONS
    return random.choice(available)
