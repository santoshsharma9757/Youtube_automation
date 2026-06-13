from __future__ import annotations

# ── Fitness channel posting slots (unchanged) ──────────────────────────────────
SHORTS_POSTING_SLOTS: dict[int, list[int]] = {
    0: [20, 17, 18],  # Monday: 8 p.m., 5 p.m., 6 p.m.
    1: [20, 21, 19],  # Tuesday: 8 p.m., 9 p.m., 7 p.m.
    2: [19, 20, 21],  # Wednesday: 7 p.m., 8 p.m., 9 p.m.
    3: [19, 20, 21],  # Thursday: 7 p.m., 8 p.m., 9 p.m.
    4: [16, 18, 19],  # Friday: 4 p.m., 6 p.m., 7 p.m.
    5: [19, 11, 18],  # Saturday: 7 p.m., 11 a.m., 6 p.m.
    6: [19, 20, 17],  # Sunday: 7 p.m., 8 p.m., 5 p.m.
}

LONG_FORM_POSTING_SLOTS: dict[int, list[int]] = {
    0: [9, 22, 7],    # Monday: 9 a.m., 10 p.m., 7 a.m.
    1: [9, 11, 8],    # Tuesday: 9 a.m., 11 a.m., 8 a.m.
    2: [7, 15, 17],   # Wednesday: 7 a.m., 3 p.m., 5 p.m.
    3: [17, 18, 7],   # Thursday: 5 p.m., 6 p.m., 7 a.m.
    4: [12, 11, 15],  # Friday: 12 p.m., 11 a.m., 3 p.m.
    5: [12, 10, 15],  # Saturday: 12 p.m., 10 a.m., 3 p.m.
    6: [10, 9, 12],   # Sunday: 10 a.m., 9 a.m., 12 p.m.
}

# ── Kids channel: 2:30 PM every day (hour=14, minute=30 set in scheduler.py) ──
# All slots point to hour 14 so upload_all.py slot logic also uses 2 PM if needed
KIDS_POSTING_SLOTS: dict[int, list[int]] = {
    0: [14],  # Monday
    1: [14],  # Tuesday
    2: [14],  # Wednesday
    3: [14],  # Thursday
    4: [14],  # Friday
    5: [14],  # Saturday
    6: [14],  # Sunday
}

DAY_NAME_TO_WEEKDAY: dict[str, int] = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def get_daily_slots(
    weekday: int,
    videos_per_day: int,
    video_type: str = "short",
    channel: str = "fitness",
) -> list[int]:
    if channel == "kids":
        slots = KIDS_POSTING_SLOTS.get(weekday, [14])
    elif video_type == "long":
        slots = LONG_FORM_POSTING_SLOTS.get(weekday, SHORTS_POSTING_SLOTS[0])
    else:
        slots = SHORTS_POSTING_SLOTS.get(weekday, SHORTS_POSTING_SLOTS[0])
    return sorted(slots[:videos_per_day])
