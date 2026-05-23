"""
video_downloader.py
-------------------
Downloads free, high-quality, royalty-free fitness/gym/yoga video clips from:
  1. Coverr.co  (free, CC0, no signup needed)
  2. Pexels API (your existing key)

Organises clips into assets/localvideos/ matching the keyword tags
that video_generator.py uses for smart matching.

Run standalone:
    python video_downloader.py
Or imported by main.py if local library is small.
"""
from __future__ import annotations

import logging
import os
import time
import urllib.parse
import uuid
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)

LOCAL_VIDEO_DIR = Path(__file__).resolve().parent / "assets" / "localvideos"
BG_VIDEO_DIR    = Path(__file__).resolve().parent / "assets" / "backgrounds"
TARGET_LOCAL    = 40    # target for localvideos/ (exercise clips)
TARGET_BG       = 20    # target for backgrounds/ (cinematic b-roll)
REQUEST_TIMEOUT = 60

# ─── Coverr.co public API ────────────────────────────────────────────────────
# Coverr exposes a simple search API that returns MP4 URLs, no key needed.
COVERR_API = "https://coverr.co/api/videos/featured"
COVERR_SEARCH = "https://coverr.co/api/videos"

# Each tuple: (search_term, save_name_prefix, min_clips)
COVERR_QUERIES = [
    ("gym workout",         "gym",          3),
    ("running",             "running",      2),
    ("yoga",                "yoga",         3),
    ("push up",             "pushup",       2),
    ("squat",               "squat",        2),
    ("jump",                "jumpingjack",  2),
    ("fitness woman",       "fitness_w",    3),
    ("fitness man",         "fitness_m",    3),
    ("meditation",          "meditation",   2),
    ("stretching",          "stretch",      2),
    ("cycling",             "cycling",      2),
    ("abs workout",         "abs",          2),
    ("dumbbell",            "dumbbell",     2),
    ("kettlebell",          "kettlebell",   2),
    ("outdoor running",     "outdoor_run",  2),
    ("hiit workout",        "hiit",         2),
    ("home workout",        "home",         2),
    ("weight lifting",      "weightlift",   2),
    ("boxing",              "boxing",       1),
    ("swimming",            "swimming",     1),
]

# Pexels portrait fitness queries (for Shorts – vertical video)
PEXELS_QUERIES = [
    ("woman gym workout vertical",   "pexels_woman_gym",    "portrait", 3),
    ("man gym workout vertical",     "pexels_man_gym",      "portrait", 3),
    ("yoga woman vertical",          "pexels_yoga_w",       "portrait", 3),
    ("yoga man vertical",            "pexels_yoga_m",       "portrait", 2),
    ("running fitness vertical",     "pexels_running",      "portrait", 2),
    ("push up fitness",              "pexels_pushup",       "portrait", 2),
    ("squat fitness",                "pexels_squat",        "portrait", 2),
    ("meditation vertical",          "pexels_meditation",   "portrait", 2),
    ("home workout vertical",        "pexels_home",         "portrait", 3),
    ("fitness motivation",           "pexels_motivation",   "portrait", 3),
    ("abs workout",                  "pexels_abs",          "portrait", 2),
    ("hiit workout",                 "pexels_hiit",         "portrait", 2),
    ("stretching flexibility",       "pexels_stretch",      "portrait", 2),
    ("gym weight training",          "pexels_weights",      "portrait", 2),
]

PEXELS_BG_QUERIES = [
    ("cinematic nature sunrise",     "bg_sunrise",       "landscape", 2),
    ("gym interior",                 "bg_gym",           "landscape", 2),
    ("running trail",                "bg_trail",         "landscape", 2),
    ("motivation abstract",          "bg_abstract",      "landscape", 2),
]


def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len([f for f in directory.iterdir() if f.suffix.lower() in {".mp4", ".mov", ".mkv"}])


def _save_video(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 100_000:
        return True
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
        data = resp.content
        if len(data) < 80_000:
            return False
        dest.write_bytes(data)
        LOGGER.info("Saved video: %s (%.1f MB)", dest.name, len(data) / 1_048_576)
        return True
    except Exception as exc:
        LOGGER.warning("Failed to download %s → %s: %s", url, dest.name, exc)
        return False


def _coverr_search(query: str, max_clips: int = 4) -> list[str]:
    """Returns a list of MP4 download URLs from Coverr."""
    try:
        resp = requests.get(
            COVERR_SEARCH,
            params={"keywords": query, "page": 1, "per_page": max_clips},
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        urls: list[str] = []
        # Coverr response format: {"hits": [{"coverr_url": "...", "mp4_url": "..."}]}
        for item in data.get("hits", [])[:max_clips]:
            mp4 = item.get("mp4_url") or item.get("coverr_url") or ""
            if mp4 and mp4.endswith(".mp4"):
                urls.append(mp4)
        return urls
    except Exception as exc:
        LOGGER.warning("Coverr search failed for '%s': %s", query, exc)
        return []


def download_coverr_videos(target: int = TARGET_LOCAL) -> int:
    """Download fitness clips from Coverr.co."""
    LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for query, prefix, min_clips in COVERR_QUERIES:
        if _count_files(LOCAL_VIDEO_DIR) >= target:
            break
        urls = _coverr_search(query, max_clips=min_clips + 1)
        for i, url in enumerate(urls[:min_clips]):
            dest = LOCAL_VIDEO_DIR / f"{prefix}_{i+1:02d}.mp4"
            if dest.exists():
                continue
            if _save_video(url, dest):
                downloaded += 1
            time.sleep(0.8)
    LOGGER.info("Coverr: downloaded %s clips", downloaded)
    return downloaded


def download_pexels_videos(api_key: str, target_local: int = TARGET_LOCAL, target_bg: int = TARGET_BG) -> int:
    """Download fitness clips from Pexels using existing API key."""
    if not api_key:
        LOGGER.warning("No PEXELS_API_KEY – skipping Pexels video download")
        return 0

    LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    BG_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": api_key}
    downloaded = 0

    def _fetch_pexels(query: str, orientation: str, prefix: str, count: int, dest_dir: Path) -> int:
        nonlocal downloaded
        got = 0
        try:
            url = (
                f"https://api.pexels.com/videos/search"
                f"?query={urllib.parse.quote(query)}"
                f"&orientation={orientation}&size=medium&per_page={count + 3}"
            )
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            import random
            random.shuffle(videos)
            for v in videos[:count]:
                files = v.get("video_files", [])
                # Prefer 720p–1080p
                hd = [f for f in files if 720 <= f.get("height", 0) <= 1920]
                best = hd[0] if hd else (sorted(files, key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)[0] if files else None)
                if not best:
                    continue
                dest = dest_dir / f"{prefix}_{v['id']}.mp4"
                if _save_video(best["link"], dest):
                    got += 1
                    downloaded += 1
                time.sleep(0.5)
        except Exception as exc:
            LOGGER.warning("Pexels batch download failed for '%s': %s", query, exc)
        return got

    # Local (portrait) clips
    for query, prefix, orientation, count in PEXELS_QUERIES:
        if _count_files(LOCAL_VIDEO_DIR) >= target_local:
            break
        _fetch_pexels(query, orientation, prefix, count, LOCAL_VIDEO_DIR)

    # Background (landscape) clips
    for query, prefix, orientation, count in PEXELS_BG_QUERIES:
        if _count_files(BG_VIDEO_DIR) >= target_bg:
            break
        _fetch_pexels(query, orientation, prefix, count, BG_VIDEO_DIR)

    LOGGER.info("Pexels: downloaded %s clips total", downloaded)
    return downloaded


def ensure_video_library(
    min_local: int = 20,
    min_bg: int = 8,
    pexels_key: str = "",
) -> tuple[int, int]:
    """
    Public entry point – called by main.py on startup.
    Returns (local_count, bg_count).
    """
    local_count = _count_files(LOCAL_VIDEO_DIR)
    bg_count    = _count_files(BG_VIDEO_DIR)

    if local_count < min_local or bg_count < min_bg:
        LOGGER.info(
            "Video library low (local=%s, bg=%s). Downloading more…",
            local_count, bg_count,
        )
        download_coverr_videos(target=min_local)
        if pexels_key:
            download_pexels_videos(pexels_key, target_local=min_local, target_bg=min_bg)

    local_count = _count_files(LOCAL_VIDEO_DIR)
    bg_count    = _count_files(BG_VIDEO_DIR)
    LOGGER.info("Video library: local=%s, bg=%s", local_count, bg_count)
    return local_count, bg_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    from dotenv import load_dotenv
    load_dotenv()
    pexels_key = os.getenv("PEXELS_API_KEY", "")
    local, bg = ensure_video_library(min_local=40, min_bg=15, pexels_key=pexels_key)
    print(f"\n✅ Video library ready: {local} local clips, {bg} background clips")
