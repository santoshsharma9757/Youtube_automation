"""
story_topics.py  –  Wonder Stories TV
======================================
Unified story topic bank for ALL video formats.

Categories:
  1. magical_adventure   – Chintu + magical element + moral (core series)
  2. mythology           – Indian epics retold for modern audience
  3. dadi_kahani         – Grandma tales (nostalgia for adults, magic for kids)
  4. real_life           – Relatable everyday situations with magical twist
  5. family_funny        – Relatable family comedy moments
  6. animal_tales        – Talking animal stories (universal appeal)
  7. mystery             – Short whodunit / puzzle stories
  8. seasonal            – Festival & seasonal content (Diwali, Holi, etc.)

Each story seed has TWO layers:
  - kids_hook:   What makes children laugh/cry/watch
  - adult_hook:  What makes adults stay (nostalgia, parenting, life truth)
"""
from __future__ import annotations

import random


# ─── Trending Signals (Story Niche 2026) ──────────────────────────────────────
TRENDING_SIGNAL_TERMS: list[dict[str, object]] = [
    {
        "label": "moral-story-hindi",
        "weight": 5,
        "keywords": ["moral story", "naitik kahani", "bacchon ki kahani", "hindi moral", "sikhane wali kahani"],
    },
    {
        "label": "mythology-simplified",
        "weight": 5,
        "keywords": ["ram", "krishna", "hanuman", "mahabharat", "ramayana", "purana kahani", "devta"],
    },
    {
        "label": "family-content",
        "weight": 4,
        "keywords": ["family story", "family funny", "maa ki kahani", "dadi ki kahani", "gharelu", "parivar"],
    },
    {
        "label": "magical-adventure",
        "weight": 5,
        "keywords": ["jadui", "magic", "magical", "jaadu", "chamatkar", "wonder"],
    },
    {
        "label": "festival-seasonal",
        "weight": 4,
        "keywords": ["diwali", "holi", "eid", "christmas", "new year", "navratri", "raksha bandhan"],
    },
    {
        "label": "animal-tales",
        "weight": 4,
        "keywords": ["jungle story", "talking animal", "lion", "monkey", "elephant", "panchatantra", "janwar"],
    },
]


# ─── Magical Elements Pool ────────────────────────────────────────────────────
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
    {"lesson": "Time is precious, use it wisely", "hindi": "Samay bahumulya hai, iska sahi upyog karo"},
    {"lesson": "Kindness always wins in the end", "hindi": "Daya aur kindness hamesha jeetti hai"},
]


# ─── Unified Story Topic Bank ─────────────────────────────────────────────────
# Dual-layer: kids_hook (what children love) + adult_hook (what adults feel)
STORY_TOPIC_BANK: list[dict] = [

    # ══════════════════════════════════════════════════════
    # CATEGORY 1: MAGICAL ADVENTURE (Chintu Series — Core)
    # ══════════════════════════════════════════════════════
    {
        "title": "Chintu Aur Magical Watch",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "playing too much on mobile",
        "bad_habit_hindi": "mobile pe bahut zyada time waste karna",
        "magical_element": "Magical Watch",
        "moral": "Time is precious – use it wisely",
        "moral_hindi": "Samay bahumulya hai, iska sahi upyog karo",
        "kids_hook": "A watch that magically speeds up time to show Chintu all the things he missed!",
        "adult_hook": "Every parent recognizes this struggle — we all wish we could make our kids put the phone down.",
        "angle": "Time Management",
        "topic": "mobile addiction kids story hindi",
        "keywords": ["mobile addiction kids story", "jadui ghadi kahani", "bacchon ki moral story"],
    },
    {
        "title": "Chintu Aur Hungry Dustbin",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "throwing garbage on the road",
        "bad_habit_hindi": "sadak par kachra phenkna",
        "magical_element": "Hungry Dustbin",
        "moral": "Keep your surroundings clean",
        "moral_hindi": "Apne aas paas ko saaf rakho",
        "kids_hook": "A dustbin that chases Chintu everywhere demanding he clean up his mess!",
        "adult_hook": "Teaching kids civic responsibility the fun way — what parents wish school taught.",
        "angle": "Cleanliness",
        "topic": "kids moral story cleanliness hindi",
        "keywords": ["safai ki kahani", "kachra mat phenko moral story", "kids cleanliness story hindi"],
    },
    {
        "title": "Chintu Aur Talking School Bag",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "not studying and playing games all day",
        "bad_habit_hindi": "padhai na karna aur din bhar games khelna",
        "magical_element": "Talking School Bag",
        "moral": "Study hard for a bright future",
        "moral_hindi": "Roshan bhavishya ke liye mehnat se padho",
        "kids_hook": "Chintu's school bag starts talking and goes on strike until he opens his books!",
        "adult_hook": "Adults laugh remembering their own excuses for not studying — now they're the worried parents.",
        "angle": "Education",
        "topic": "kids moral story study hindi cartoon",
        "keywords": ["study moral story hindi", "school bag kahani", "padhai ki moral story bacchon ke liye"],
    },
    {
        "title": "Chintu Aur Magic Spoon",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "eating too much junk food",
        "bad_habit_hindi": "bahut zyada junk food khana",
        "magical_element": "Magic Spoon",
        "moral": "Eat healthy food to stay strong",
        "moral_hindi": "Takat ke liye sehatmand khana khao",
        "kids_hook": "A magic spoon that magically transforms junk food into healthy alternatives right in front of Chintu's eyes!",
        "adult_hook": "Every parent's dream — if only food could teach itself. Adults remember being force-fed vegetables too.",
        "angle": "Healthy Eating",
        "topic": "kids cartoon story healthy food hindi",
        "keywords": ["healthy food story kids hindi", "junk food moral story", "magic spoon cartoon"],
    },
    {
        "title": "Chintu Aur Talking Toothbrush",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "not brushing teeth at night",
        "bad_habit_hindi": "raat ko daant brush na karna",
        "magical_element": "Talking Toothbrush",
        "moral": "Brush your teeth daily for good health",
        "moral_hindi": "Rozana daant brush karo acchi sehat ke liye",
        "kids_hook": "The toothbrush begs and pleads with Chintu in the funniest way ever!",
        "adult_hook": "The nightly battle every parent fights — finally explained in a way kids WANT to listen to.",
        "angle": "Hygiene",
        "topic": "kids story brushing teeth hindi moral",
        "keywords": ["daant saaf karne ki kahani", "brushing teeth story kids", "dental hygiene moral story hindi"],
    },
    {
        "title": "Chintu Aur Magic Mirror",
        "category": "magical_adventure",
        "audience": "family",
        "format": "mini",
        "bad_habit": "being rude to elders",
        "bad_habit_hindi": "bade logo se badtameezi karna",
        "magical_element": "Magic Mirror",
        "moral": "Always respect your elders",
        "moral_hindi": "Hamesha bade logo ki izzat karo",
        "kids_hook": "A mirror that shows Chintu exactly how he LOOKS to others when he is rude — and it's not pretty!",
        "adult_hook": "A beautiful reminder that respect is taught, not born. Adults reflect on how they model respect.",
        "angle": "Respect",
        "topic": "kids story respect elders hindi moral",
        "keywords": ["bade logo ki izzat kahani", "respect moral story hindi", "magic mirror kids cartoon"],
    },
    {
        "title": "Chintu Aur Magical Lunchbox",
        "category": "magical_adventure",
        "audience": "family",
        "format": "mini",
        "bad_habit": "wasting food on the plate",
        "bad_habit_hindi": "plate mein khana barbad karna",
        "magical_element": "Magic Lunchbox",
        "moral": "Never waste food – many children are hungry",
        "moral_hindi": "Kabhi bhi khana barbad mat karo",
        "kids_hook": "The lunchbox shows Chintu a magical world where food is super precious and he sees hungry kids for the first time.",
        "adult_hook": "Touches every adult's heart — food wastage is a real crisis. Makes them reflect on their own habits too.",
        "angle": "No Food Waste",
        "topic": "kids moral story food wastage hindi cartoon",
        "keywords": ["khana barbad mat karo story", "food wastage moral story kids", "magical lunchbox hindi kahani"],
    },
    {
        "title": "Chintu Aur Talking Star",
        "category": "magical_adventure",
        "audience": "family",
        "format": "mini",
        "bad_habit": "telling lies to mother",
        "bad_habit_hindi": "maa se jhooth bolna",
        "magical_element": "Talking Star",
        "moral": "Always tell the truth",
        "moral_hindi": "Hamesha sach bolna chahiye",
        "kids_hook": "A star from the sky visits Chintu at night and reveals that all his lies have made the star lose its shine!",
        "adult_hook": "Nostalgic, poetic, and real. Adults remember the guilt of lying to their parents — it hits differently.",
        "angle": "Truth and Honesty",
        "topic": "kids story truth telling hindi moral cartoon",
        "keywords": ["sach bolne ki kahani", "jhooth ki saza story hindi", "talking star moral story kids"],
    },
    {
        "title": "Chintu Aur Magical Blanket",
        "category": "magical_adventure",
        "audience": "family",
        "format": "mini",
        "bad_habit": "fighting with younger sibling",
        "bad_habit_hindi": "chhote bhai-behen se ladna",
        "magical_element": "Magical Blanket",
        "moral": "Love and share with your siblings",
        "moral_hindi": "Apne bhai-behen se pyaar karo aur share karo",
        "kids_hook": "A magical blanket wraps both Chintu and his sibling together making it impossible to fight!",
        "adult_hook": "Sibling fights are universal. Adults laugh remembering their own — and feel the warmth of those bonds now.",
        "angle": "Sibling Love",
        "topic": "kids story sibling love hindi moral cartoon",
        "keywords": ["bhai behen pyaar story", "sibling love moral story hindi", "magical blanket kids cartoon"],
    },
    {
        "title": "Chintu Aur Magic Piggy Bank",
        "category": "magical_adventure",
        "audience": "family",
        "format": "mini",
        "bad_habit": "stealing from mother's purse",
        "bad_habit_hindi": "maa ke purse se chori karna",
        "magical_element": "Talking Piggy Bank",
        "moral": "Never steal, always ask politely",
        "moral_hindi": "Kabhi chori mat karo, hamesha pyaar se maango",
        "kids_hook": "The piggy bank actually talks to Chintu and counts every coin he stole — with exact memory!",
        "adult_hook": "Parents see this and know exactly how to use it as a teachable moment with their own kids.",
        "angle": "Honesty",
        "topic": "kids moral story honesty hindi cartoon",
        "keywords": ["imandari ki kahani hindi", "chori mat karo moral story", "piggy bank cartoon kids"],
    },
    {
        "title": "Chintu Aur Magical Phone",
        "category": "magical_adventure",
        "audience": "family",
        "format": "long",
        "bad_habit": "playing too much on mobile",
        "bad_habit_hindi": "mobile pe bahut zyada time waste karna",
        "magical_element": "Magical Phone (shows consequences)",
        "moral": "Spend time with family, not just phone",
        "moral_hindi": "Phone ki jagah family ke saath waqt bitao",
        "kids_hook": "A phone that shows Chintu what his life will be like if he never stops using it — an empty future!",
        "adult_hook": "Every adult struggles with screen time. This story speaks to parents AND makes them check their own phone habits.",
        "angle": "Family Time vs Screen Time",
        "topic": "kids mobile addiction story hindi moral cartoon",
        "keywords": ["mobile addiction family story hindi", "screen time moral story", "phone addiction kids cartoon hindi"],
    },
    {
        "title": "Chintu Aur Magical Eraser",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "copying homework from friend",
        "bad_habit_hindi": "dost ka homework copy karna",
        "magical_element": "Magical Eraser",
        "moral": "Do your own work honestly",
        "moral_hindi": "Apna kaam imandaari se karo",
        "kids_hook": "The eraser erases everything Chintu copied AND erases his memory of the answers — now he has to learn for real!",
        "adult_hook": "Adults who copied homework recognize themselves — and understand why honest hard work is the only path.",
        "angle": "Honesty in Studies",
        "topic": "kids story no cheating hindi moral cartoon",
        "keywords": ["cheating nahi karna story hindi", "homework copy moral story", "magical eraser kids cartoon"],
    },
    {
        "title": "Chintu Aur Talking Plant",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "not washing hands before eating",
        "bad_habit_hindi": "khane se pehle haath na dhona",
        "magical_element": "Talking Plant",
        "moral": "Always wash hands to stay healthy",
        "moral_hindi": "Hamesha haath dhoke hi khana khao",
        "kids_hook": "The plant narrates the journey of germs as tiny invisible monsters climbing onto Chintu's food!",
        "adult_hook": "Scientifically correct + delivered in the most memorable story format. Parents feel vindicated.",
        "angle": "Hygiene Habits",
        "topic": "kids hand washing story hindi moral cartoon",
        "keywords": ["haath dhone ki kahani hindi", "hygiene moral story kids", "germ story kids animated hindi"],
    },
    {
        "title": "Chintu Aur Magic Water Bottle",
        "category": "magical_adventure",
        "audience": "family",
        "format": "short",
        "bad_habit": "wasting water while brushing",
        "bad_habit_hindi": "brush karte waqt paani barbad karna",
        "magical_element": "Magic Water Bottle",
        "moral": "Save water, it is precious",
        "moral_hindi": "Paani bachao, yeh bahumulya hai",
        "kids_hook": "A magic water bottle that shows Chintu children in dry villages desperate for a single drop of water.",
        "adult_hook": "Water scarcity is a real 2026 crisis. Adults reflect on their own habits watching this powerful story.",
        "angle": "Save Water",
        "topic": "save water kids story hindi moral cartoon",
        "keywords": ["paani bachao story hindi", "save water moral story kids", "magic water bottle cartoon"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 2: INDIAN MYTHOLOGY (Simplified)
    # ══════════════════════════════════════════════════════
    {
        "title": "Hanuman Ji Ki Shaktishali Kahani",
        "category": "mythology",
        "audience": "family",
        "format": "long",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Hanuman's Gada",
        "moral": "Devotion and courage can conquer any obstacle",
        "moral_hindi": "Bhakti aur sahas se har mushkil par vijay milti hai",
        "kids_hook": "Hanuman grows GIANT and leaps across the ocean — kids are amazed by the superpower visuals!",
        "adult_hook": "Every Indian adult has grown up with Hanuman. This takes them back to grandma's lap with a fresh animated feel.",
        "angle": "Courage and Devotion",
        "topic": "hanuman story hindi animated kids",
        "keywords": ["hanuman kahani hindi animated", "hanuman ji story for kids", "mythology story kids hindi"],
    },
    {
        "title": "Krishna Aur Makhan Chor Ki Kahani",
        "category": "mythology",
        "audience": "family",
        "format": "mini",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Krishna's Flute",
        "moral": "Innocence and mischief are the purest forms of joy",
        "moral_hindi": "Masoomiyat aur shararat mein hi saccha anand hai",
        "kids_hook": "Krishna steals butter in the most adorable, funny ways — kids want to be just like him!",
        "adult_hook": "Pure nostalgia. Every adult smiles remembering Krishna's mischief as a child. Connects deeply.",
        "angle": "Joy and Innocence",
        "topic": "krishna makhan chor story hindi kids",
        "keywords": ["krishna story for kids hindi", "makhan chor kahani animated", "bal krishna story kids"],
    },
    {
        "title": "Eklavya Ki Mehnat Ki Kahani",
        "category": "mythology",
        "audience": "lean_adult",
        "format": "long",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Eklavya's Arrow",
        "moral": "True dedication needs no guru — self-belief is the greatest teacher",
        "moral_hindi": "Sacchi lagan mein hi guru hain — khud par yakeen hi sabse bada ustaad hai",
        "kids_hook": "A boy who taught himself archery by practicing in front of a clay statue! Epic skill reveal!",
        "adult_hook": "Deeply emotional. A story about self-made people, social barriers, and the price of excellence.",
        "angle": "Self-belief and Dedication",
        "topic": "eklavya story hindi animated moral",
        "keywords": ["eklavya story hindi kids", "mahabharat animated story", "self learning moral story hindi"],
    },
    {
        "title": "Ganesha Ka Pahla Pooja Ka Vardan",
        "category": "mythology",
        "audience": "family",
        "format": "mini",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Ganesha's Modak",
        "moral": "Wisdom and patience will always win over speed and pride",
        "moral_hindi": "Gyaan aur sabr hamesha tez aur ghuroor par bhaari padta hai",
        "kids_hook": "Ganesha races around the world using a clever trick — kids love the twist ending!",
        "adult_hook": "The classic tortoise-and-hare lesson but in the most culturally rich, beautifully animated way.",
        "angle": "Wisdom Over Ego",
        "topic": "ganesha race story hindi kids animated",
        "keywords": ["ganesha story for kids hindi", "ganesh ji ki kahani animated", "wisdom story hindi mythology"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 3: DADI / NANI KI KAHANIYAN (Grandma Tales)
    # ══════════════════════════════════════════════════════
    {
        "title": "Dadi Ki Jadui Kahani: Sher Aur Chuha",
        "category": "dadi_kahani",
        "audience": "family",
        "format": "mini",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Dadi's Magic Story Book",
        "moral": "Never underestimate anyone — even the smallest can help the greatest",
        "moral_hindi": "Kisi ko bhi chota mat samjho — chota sa bhi sabse bade ki madad kar sakta hai",
        "kids_hook": "A tiny mouse saves a mighty lion — the reversal is thrilling and funny for kids!",
        "adult_hook": "This is THE story every Indian person heard from their grandmother. Pure nostalgia flood.",
        "angle": "Humility and Gratitude",
        "topic": "sher aur chuha dadi ki kahani hindi",
        "keywords": ["sher aur chuha story hindi", "dadi ki kahani animated", "lion and mouse story hindi kids"],
    },
    {
        "title": "Dadi Ki Kahani: Khargosh Aur Kachua",
        "category": "dadi_kahani",
        "audience": "family",
        "format": "short",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Magic Finish Line",
        "moral": "Slow and steady wins the race",
        "moral_hindi": "Dheere dheere chalne se bhi manzil milti hai",
        "kids_hook": "Colorful 3D animation of the classic race with a dramatic slow-motion finish!",
        "adult_hook": "A story every adult has heard but never seen THIS beautifully animated in Hindi. Pure joy.",
        "angle": "Patience and Persistence",
        "topic": "khargosh aur kachua dadi ki kahani hindi animated",
        "keywords": ["khargosh aur kachua kahani", "tortoise and hare hindi story", "dadi ki moral kahani kids"],
    },
    {
        "title": "Nani Ki Kahani: Pyaasi Kauwwa",
        "category": "dadi_kahani",
        "audience": "family",
        "format": "short",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Clever Crow's Stone",
        "moral": "Intelligence and effort together solve every problem",
        "moral_hindi": "Dimag aur mehnat saath mein har mushkil suljha dete hain",
        "kids_hook": "A thirsty crow drops stones into a pot to raise water — kids try to guess the solution first!",
        "adult_hook": "The first problem-solving story most Indians remember. Animated perfectly = millions of rewatches.",
        "angle": "Intelligence and Problem Solving",
        "topic": "pyaasa kauwwa nani ki kahani hindi animated",
        "keywords": ["pyaasa kauwwa story hindi kids", "thirsty crow animated hindi", "nani ki kahani moral story"],
    },
    {
        "title": "Dadi Aur Chintu: Wo Purani Kahaniyan",
        "category": "dadi_kahani",
        "audience": "lean_adult",
        "format": "long",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Dadi's Glowing Story Lamp",
        "moral": "Stories told with love are the greatest gift a grandparent gives",
        "moral_hindi": "Pyaar se sunai gayi kahaniyan sabse bada tohfa hain",
        "kids_hook": "Chintu asks Dadi for ONE more story at bedtime and she tells three — each with magical animation!",
        "adult_hook": "Deeply emotional. Adults who have lost grandparents cry watching this. Pure nostalgia and love.",
        "angle": "Family Bonds and Nostalgia",
        "topic": "dadi chintu story collection hindi animated",
        "keywords": ["dadi ki kahani chintu", "bedtime stories hindi animated", "grandma stories kids hindi emotional"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 4: REAL LIFE MAGIC (Relatable Everyday)
    # ══════════════════════════════════════════════════════
    {
        "title": "Chintu Ka Exam Ka Dar",
        "category": "real_life",
        "audience": "family",
        "format": "mini",
        "bad_habit": "giving up when things get hard",
        "bad_habit_hindi": "mushkil hone par haar maan lena",
        "magical_element": "Magical Pencil",
        "moral": "Hard work and self-belief beat exam fear every time",
        "moral_hindi": "Mehnat aur yakeen se har imtihan ka darr door hota hai",
        "kids_hook": "A magic pencil writes exam answers — but the twist is, it only works if Chintu studied first!",
        "adult_hook": "Every adult remembers exam anxiety. This story validates the fear AND shows the solution beautifully.",
        "angle": "Overcoming Fear",
        "topic": "exam fear story hindi kids moral animated",
        "keywords": ["exam dar story hindi kids", "imtihan ki kahani animated", "study motivation story kids hindi"],
    },
    {
        "title": "Chintu Ka Naya Dost",
        "category": "real_life",
        "audience": "family",
        "format": "mini",
        "bad_habit": "being too shy to make friends",
        "bad_habit_hindi": "sharm ke karan dost na banana",
        "magical_element": "Magic Compass (points to friendship)",
        "moral": "One small act of kindness can start a lifelong friendship",
        "moral_hindi": "Ek choti si meharbani zindagi bhar ki dosti ki shuruat kar sakti hai",
        "kids_hook": "A magical compass leads Chintu to the loneliest kid in school and magic happens when they meet!",
        "adult_hook": "Introversion and social anxiety are real. Adults see themselves in Chintu and feel seen.",
        "angle": "Friendship and Courage",
        "topic": "new friend story hindi kids moral animated",
        "keywords": ["dost banana ki kahani hindi", "friendship moral story kids", "shy kid friendship story hindi"],
    },
    {
        "title": "Chintu Ka Pehla Din School Mein",
        "category": "real_life",
        "audience": "family",
        "format": "long",
        "bad_habit": "being scared of new things",
        "bad_habit_hindi": "nayi cheezein dekh kar darna",
        "magical_element": "Magical School Bell",
        "moral": "Courage to try new things opens the door to wonderful adventures",
        "moral_hindi": "Nayi cheezein aazmaane ki himmat amazing adventures ka darwaza khol deti hai",
        "kids_hook": "The school bell rings and magical adventures begin on the very first day!",
        "adult_hook": "Every parent's emotional journey of their child's first day of school — seen through the child's eyes.",
        "angle": "Bravery and New Beginnings",
        "topic": "first day school story hindi kids animated",
        "keywords": ["pehla din school story hindi kids", "school adventure animated hindi", "first day school moral story"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 5: FAMILY FUNNY (Relatable Comedy)
    # ══════════════════════════════════════════════════════
    {
        "title": "Jab Chintu Ne Cooking Ki Koshish Ki!",
        "category": "family_funny",
        "audience": "family",
        "format": "short",
        "bad_habit": "not appreciating parent's hard work",
        "bad_habit_hindi": "maa baap ki mehnat ki kadr na karna",
        "magical_element": "Magic Recipe Book",
        "moral": "Appreciate the hard work your parents put in every day",
        "moral_hindi": "Maa baap ki roz ki mehnat ki kadr karo",
        "kids_hook": "Chintu tries to cook food and creates a hilarious disaster in the kitchen!",
        "adult_hook": "EVERY parent laughs at this — and kids see cooking for the first time as an adventure.",
        "angle": "Gratitude for Parents",
        "topic": "chintu cooking funny story hindi kids",
        "keywords": ["funny cooking story kids hindi", "kitchen disaster comedy cartoon", "maa ki mehnat story animated"],
    },
    {
        "title": "Papa Aur Chintu Ka Epic Road Trip",
        "category": "family_funny",
        "audience": "lean_adult",
        "format": "long",
        "bad_habit": "not spending quality time with family",
        "bad_habit_hindi": "family ke saath quality time nahi bitana",
        "magical_element": "Magical GPS (gives life directions)",
        "moral": "The best journeys happen when you switch off your phone and enjoy the ride",
        "moral_hindi": "Sabse achhi yatra woh hoti hai jab phone band kar ke raaste ka maza liya jaaye",
        "kids_hook": "Papa and Chintu go on a hilarious road trip full of funny wrong turns and surprises!",
        "adult_hook": "Hits every adult who works too much and misses quality family time. Emotional and funny together.",
        "angle": "Father-Child Bond",
        "topic": "papa chintu road trip funny story hindi",
        "keywords": ["papa aur chintu story hindi", "father son funny story animated", "family road trip story kids hindi"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 6: ANIMAL TALES (Universal Appeal)
    # ══════════════════════════════════════════════════════
    {
        "title": "Sher Ka Dil: Jungle Ka Raja Roya",
        "category": "animal_tales",
        "audience": "family",
        "format": "mini",
        "bad_habit": "using power to bully others",
        "bad_habit_hindi": "taaqat se doosron ko dara karna",
        "magical_element": "Forest Guardian's Magic Stone",
        "moral": "True strength is in kindness, not fear",
        "moral_hindi": "Sacchi taaqat daya mein hoti hai, darr mein nahi",
        "kids_hook": "The mightiest lion in the jungle cries — and kids are desperate to know why!",
        "adult_hook": "Powerful leaders who use fear vs. kindness — this allegory resonates deeply with adults.",
        "angle": "Kindness Over Power",
        "topic": "lion story hindi moral animated kids",
        "keywords": ["sher ki kahani hindi animated", "lion moral story kids", "jungle raja story hindi"],
    },
    {
        "title": "Bandar Ki Dukaan: Ek Funny Jungle Story",
        "category": "animal_tales",
        "audience": "family",
        "format": "short",
        "bad_habit": "being greedy",
        "bad_habit_hindi": "lalchi hona",
        "magical_element": "Magic Banana Tree",
        "moral": "Greed always leads to loss — share and you gain more",
        "moral_hindi": "Lalach hamesha nuksan karta hai — baanto toh zyada milta hai",
        "kids_hook": "A monkey opens a shop in the jungle and gives everything away for free — what happens next is hilarious!",
        "adult_hook": "A funny but sharp commentary on generosity vs. greed that adults find surprisingly profound.",
        "angle": "Generosity vs Greed",
        "topic": "monkey funny story hindi moral kids animated",
        "keywords": ["bandar ki kahani hindi kids", "monkey moral story animated hindi", "greedy monkey story kids"],
    },
    {
        "title": "Haathi Ka Naya Dost: Ek Pyaari Kahani",
        "category": "animal_tales",
        "audience": "family",
        "format": "mini",
        "bad_habit": "judging others by their size or appearance",
        "bad_habit_hindi": "kisi ko uski size ya dikhawat se judge karna",
        "magical_element": "Rainbow Bridge of Friendship",
        "moral": "Never judge a friend by their size — the smallest heart can be the biggest",
        "moral_hindi": "Dost ko size se mat aankho — sabse chota dil bhi sabse bada hota hai",
        "kids_hook": "A tiny mouse becomes best friends with the biggest elephant — and saves his life!",
        "adult_hook": "Don't judge a book by its cover — adults see the lesson in their own relationships.",
        "angle": "Friendship and Acceptance",
        "topic": "elephant mouse friendship story hindi animated kids",
        "keywords": ["haathi aur chuha dosti story", "elephant friendship moral story hindi", "small big friends story kids"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 7: MYSTERY / PUZZLE (Smart Stories)
    # ══════════════════════════════════════════════════════
    {
        "title": "Chintu Detective: Churaya Hua Khilona Kaun Laya?",
        "category": "mystery",
        "audience": "family",
        "format": "mini",
        "bad_habit": "blaming others without proof",
        "bad_habit_hindi": "bina saboot ke doosron par ilzaam lagana",
        "magical_element": "Magic Magnifying Glass",
        "moral": "Always find the truth before pointing fingers",
        "moral_hindi": "Kisi par ilzaam lagane se pehle sach pata karo",
        "kids_hook": "Chintu turns detective and kids try to solve the mystery BEFORE he does!",
        "adult_hook": "Teaches critical thinking and fair judgment — adults realize they make the same blame mistake.",
        "angle": "Critical Thinking and Fairness",
        "topic": "chintu detective mystery story hindi kids",
        "keywords": ["chintu detective story hindi", "mystery story kids hindi animated", "who took the toy story hindi"],
    },
    {
        "title": "Jadugar Ka Raaz: Kaun Tha Woh?",
        "category": "mystery",
        "audience": "lean_adult",
        "format": "long",
        "bad_habit": "",
        "bad_habit_hindi": "",
        "magical_element": "Magician's Secret Box",
        "moral": "True magic is not tricks — it is the love and hope we give each other",
        "moral_hindi": "Asli jaadu cheating nahi hoti — yeh woh pyaar aur umeed hai jo hum ek dusre ko dete hain",
        "kids_hook": "A mysterious magician visits the village and has a secret that nobody can figure out!",
        "adult_hook": "A twist ending that makes adults emotional — the magician's identity is a beautiful surprise.",
        "angle": "Hope and Love",
        "topic": "mystery magician story hindi animated long",
        "keywords": ["jadugar kahani hindi animated", "mystery story hindi adults kids", "magician twist ending story hindi"],
    },

    # ══════════════════════════════════════════════════════
    # CATEGORY 8: SEASONAL / FESTIVAL STORIES
    # ══════════════════════════════════════════════════════
    {
        "title": "Chintu Ki Diwali: Roshni Ka Jaadu",
        "category": "seasonal",
        "audience": "family",
        "format": "long",
        "bad_habit": "being selfish during festivals",
        "bad_habit_hindi": "tyohar mein swaarth karna",
        "magical_element": "Diya of Wishes",
        "moral": "True Diwali is not just lights outside but kindness in your heart",
        "moral_hindi": "Sacchi Diwali sirf bahar ki roshni nahi, dil mein mehrbani hai",
        "kids_hook": "A magical Diya grants three wishes — but Chintu must choose between selfishness and kindness!",
        "adult_hook": "The commercialization of festivals hits home. Adults feel the reminder to go back to the spirit of Diwali.",
        "angle": "Giving and Kindness",
        "topic": "diwali story hindi kids animated moral",
        "keywords": ["diwali kahani hindi kids animated", "festival moral story diwali", "chintu diwali story wonder"],
    },
    {
        "title": "Holi Ka Rang: Chintu Aur Uski Dushman",
        "category": "seasonal",
        "audience": "family",
        "format": "mini",
        "bad_habit": "holding grudges and not forgiving",
        "bad_habit_hindi": "gusse ko roke rakhna aur maafi na dena",
        "magical_element": "Holi Color of Forgiveness",
        "moral": "Holi washes away anger — forgive and celebrate with open arms",
        "moral_hindi": "Holi gusse ko dho deti hai — maaf karo aur khule dil se jashn manao",
        "kids_hook": "Chintu must play Holi with his biggest enemy at school — what happens is beautiful and funny!",
        "adult_hook": "Forgiveness is the hardest thing for adults too. Holi as a metaphor hits perfectly.",
        "angle": "Forgiveness",
        "topic": "holi story hindi kids moral animated",
        "keywords": ["holi moral story hindi kids", "holi festival story animated", "forgiveness story holi hindi"],
    },
    {
        "title": "Raksha Bandhan Ka Vaada: Chintu Aur Di",
        "category": "seasonal",
        "audience": "lean_adult",
        "format": "long",
        "bad_habit": "taking siblings for granted",
        "bad_habit_hindi": "bhai-behen ki qadr na karna",
        "magical_element": "Golden Rakhi Thread",
        "moral": "A sibling's love is the most precious gift — never take it for granted",
        "moral_hindi": "Bhai-behen ka pyaar sabse anmol tohfa hai — ise kabhi halke mat lo",
        "kids_hook": "A golden rakhi thread glows magical when tied — and grants the sister's deepest wish!",
        "bold_theme": "Raksha Bandhan",
        "adult_hook": "Raksha Bandhan nostalgia is massive in India. Adults cry and share this with their siblings.",
        "angle": "Sibling Bond",
        "topic": "raksha bandhan story hindi kids animated emotional",
        "keywords": ["raksha bandhan story hindi animated", "rakhi kahani kids emotional", "bhai behen bond story hindi"],
    },
    # ══════════════════════════════════════════════════════
    # CATEGORY 9: HORROR / SPOOKY STORIES
    # ══════════════════════════════════════════════════════
    {
        "title": "Chintu Aur Haunted Toy",
        "category": "horror",
        "audience": "family",
        "format": "short",
        "bad_habit": "taking things without permission",
        "bad_habit_hindi": "bina permission ke doosro ki cheez lena",
        "magical_element": "Haunted Toy",
        "moral": "Never take things that do not belong to you",
        "moral_hindi": "Dusro ki cheezein bina puche kabhi mat lo",
        "kids_hook": "A spooky old toy that giggles in the dark and floats when Chintu tries to hide it!",
        "adult_hook": "Spooky campfire mystery vibe that teaches integrity and boundaries.",
        "angle": "Integrity",
        "topic": "cozy horror kids story hindi",
        "keywords": ["scary story kids hindi", "bhoot ki kahani cartoon", "haunted toy moral story"],
    },
    {
        "title": "Chintu Aur Bhoot Bungalow",
        "category": "horror",
        "audience": "family",
        "format": "mini",
        "bad_habit": "going to dangerous places despite warnings",
        "bad_habit_hindi": "mana karne par bhi khatarnak jagah jana",
        "magical_element": "Glowing Old Key",
        "moral": "Listen to the advice of your parents for your safety",
        "moral_hindi": "Apne maa-baap ki salah mano apni suraksha ke liye",
        "kids_hook": "Spooky shadow puppets that talk to Chintu in the old haunted mansion!",
        "adult_hook": "A reminder of child curiosity vs parental protective instincts.",
        "angle": "Safety & Listening",
        "topic": "haunted house story hindi kids",
        "keywords": ["bhoot bungalow kahani", "haunted mansion story kids animated", "safety moral story hindi"],
    },
    {
        "title": "Chintu Aur Bolne Wala Kankal",
        "category": "horror",
        "audience": "family",
        "format": "long",
        "bad_habit": "fearing the dark and being superstitious",
        "bad_habit_hindi": "andhere se darna aur andhavishwas karna",
        "magical_element": "Talking Skeleton (friendly)",
        "moral": "Courage is not the absence of fear, but facing it",
        "moral_hindi": "Darr se darna band karo, uska samna karo",
        "kids_hook": "A funny, dancing skeleton in the closet that helps Chintu overcome his fear of the dark!",
        "adult_hook": "Helping kids overcome developmental fears of darkness and ghosts.",
        "angle": "Overcoming Fear",
        "topic": "spooky friendly story hindi kids",
        "keywords": ["skeleton funny story hindi", "darr bhagane ki kahani", "overcoming fear story kids"],
    },
]


# ─── Helper Functions ─────────────────────────────────────────────────────────

def get_story_seed(
    category: str | None = None,
    audience: str | None = None,
    fmt: str | None = None,
    exclude_titles: set[str] | None = None,
) -> dict | None:
    """Pick a random story seed, optionally filtered by category/audience/format."""
    pool = STORY_TOPIC_BANK.copy()
    if category:
        pool = [s for s in pool if s["category"] == category]
    if audience:
        pool = [s for s in pool if s.get("audience") in (audience, "family")]
    if fmt:
        pool = [s for s in pool if s["format"] == fmt]
    if exclude_titles:
        pool = [s for s in pool if s["title"].lower() not in {t.lower() for t in exclude_titles}]
    if not pool:
        pool = STORY_TOPIC_BANK  # fallback to full bank
    return random.choice(pool)


def filter_by_category(category: str) -> list[dict]:
    return [s for s in STORY_TOPIC_BANK if s["category"] == category]


def prioritize_stories(theme: str | None = None) -> list[dict]:
    """Rank stories by trending signal match — highest scores first."""
    ranked: list[tuple[int, int, dict]] = []
    for idx, story in enumerate(STORY_TOPIC_BANK):
        blob = " ".join(str(v).lower() for v in story.values())
        score = 0
        for signal in TRENDING_SIGNAL_TERMS:
            if any(kw in blob for kw in signal["keywords"]):
                score += int(signal["weight"])
        if theme:
            for word in theme.lower().split():
                if word in blob:
                    score += 3
        ranked.append((score, -idx, story))
    ranked.sort(reverse=True)
    return [item for _, _, item in ranked]


def get_random_magical_element(used_elements: set[str] | None = None) -> str:
    """Pick a fresh magical element not used before in this session."""
    available = [e for e in MAGICAL_ELEMENTS if e not in (used_elements or set())]
    if not available:
        available = MAGICAL_ELEMENTS
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


def sample_story_titles(items: list[dict], limit: int = 20) -> list[str]:
    return [item["title"] for item in items[:limit]]
