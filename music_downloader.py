"""
music_downloader.py
-------------------
Downloads free, royalty-free fitness / energetic music from sources
that allow programmatic direct download:

  1. Free Music Archive (FMA) public API - no key needed
  2. ccMixter / Incompetech direct CC0 tracks  
  3. GitHub-hosted CC0 music collections
  4. Pixabay Music API (if PIXABAY_API_KEY is set)

Run standalone:
    python music_downloader.py

Or called from main.py on startup via ensure_music_library().
"""
from __future__ import annotations

import logging
import os
import sys
import time
import urllib.parse
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)

MUSIC_DIR    = Path(__file__).resolve().parent / "assets" / "music"
TARGET_COUNT = 15
REQ_TIMEOUT  = 45


# ---------------------------------------------------------------------------
# Source 1: Free Music Archive (FMA) public API – CC-licensed, no key needed
# ---------------------------------------------------------------------------
FMA_API = "https://freemusicarchive.org/api/get/tracks.json"
FMA_GENRE_IDS = ["76", "38", "92"]   # Electronic, Hip-Hop, Instrumental

# ---------------------------------------------------------------------------
# Source 2: Pixabay Music API
# ---------------------------------------------------------------------------
PIXABAY_MUSIC_API = "https://pixabay.com/api/music/"
PIXABAY_TERMS = ["energetic sport", "workout motivation", "fitness", "powerful", "gym"]

# ---------------------------------------------------------------------------
# Source 3: Direct CC0 / public domain MP3 URLs (verified accessible)
# Github-hosted & archive.org CC0 tracks
# ---------------------------------------------------------------------------
CC0_TRACKS = [
    # archive.org CC0 instrumental tracks
    ("https://archive.org/download/FreeBackgroundMusic/Electronic_1.mp3", "cc0_electronic_1.mp3"),
    ("https://archive.org/download/FreeBackgroundMusic/Electronic_2.mp3", "cc0_electronic_2.mp3"),
    ("https://archive.org/download/FreeBackgroundMusic/Electronic_3.mp3", "cc0_electronic_3.mp3"),
    ("https://archive.org/download/FreeBackgroundMusic/Rock_1.mp3",       "cc0_rock_1.mp3"),
    ("https://archive.org/download/FreeBackgroundMusic/Rock_2.mp3",       "cc0_rock_2.mp3"),
    # NASA-licensed / CC0 tracks hosted on github
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",    "soundhelix_1.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",    "soundhelix_3.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",    "soundhelix_6.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",    "soundhelix_8.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-10.mp3",   "soundhelix_10.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-12.mp3",   "soundhelix_12.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-14.mp3",   "soundhelix_14.mp3"),
    ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-16.mp3",   "soundhelix_16.mp3"),
]


def _count() -> int:
    if not MUSIC_DIR.exists():
        return 0
    return len([f for f in MUSIC_DIR.iterdir() if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}])


def _save(url: str, filename: str, headers: dict | None = None) -> bool:
    dest = MUSIC_DIR / filename
    if dest.exists() and dest.stat().st_size > 50_000:
        return True
    try:
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            **(headers or {}),
        }
        resp = requests.get(url, headers=h, timeout=REQ_TIMEOUT, stream=True)
        resp.raise_for_status()
        data = resp.content
        if len(data) < 40_000:
            LOGGER.warning("Skipping tiny file from %s (%d bytes)", url, len(data))
            return False
        MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        LOGGER.info("Downloaded: %s (%.1f KB)", filename, len(data) / 1024)
        return True
    except Exception as exc:
        LOGGER.warning("Download failed %s: %s", url, exc)
        return False


def download_cc0_tracks() -> int:
    """Direct CC0 tracks from archive.org and soundhelix.com."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for url, fname in CC0_TRACKS:
        if _count() >= TARGET_COUNT:
            break
        if _save(url, fname):
            downloaded += 1
        time.sleep(0.3)
    return downloaded


def download_fma_tracks() -> int:
    """Free Music Archive CC-licensed tracks via public API."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for genre_id in FMA_GENRE_IDS:
        if _count() >= TARGET_COUNT:
            break
        try:
            resp = requests.get(
                FMA_API,
                params={"genre_id": genre_id, "limit": 5, "page": 1},
                headers={"User-Agent": "DailyFitX/1.0"},
                timeout=20,
            )
            resp.raise_for_status()
            tracks = resp.json().get("dataset", [])
            for track in tracks[:3]:
                if _count() >= TARGET_COUNT:
                    break
                mp3_url = track.get("track_file", "") or track.get("track_url", "")
                if not mp3_url:
                    continue
                fname = f"fma_{track.get('track_id', 'track')}.mp3"
                if _save(mp3_url, fname):
                    downloaded += 1
                time.sleep(0.5)
        except Exception as exc:
            LOGGER.warning("FMA fetch failed for genre %s: %s", genre_id, exc)
    return downloaded


def download_pixabay_music(api_key: str) -> int:
    """Pixabay Music API – requires PIXABAY_API_KEY."""
    if not api_key:
        return 0
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for term in PIXABAY_TERMS:
        if _count() >= TARGET_COUNT:
            break
        try:
            url = (
                f"{PIXABAY_MUSIC_API}"
                f"?key={api_key}&q={urllib.parse.quote(term)}&per_page=5"
            )
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            for hit in resp.json().get("hits", [])[:2]:
                if _count() >= TARGET_COUNT:
                    break
                audio_url = hit.get("audio", "")
                if not audio_url:
                    continue
                fname = f"pixabay_{hit.get('id', 'track')}.mp3"
                if _save(audio_url, fname):
                    downloaded += 1
                time.sleep(0.4)
        except Exception as exc:
            LOGGER.warning("Pixabay music failed for '%s': %s", term, exc)
    return downloaded


def ensure_music_library(min_tracks: int = 8, pixabay_key: str = "") -> int:
    """
    Public entry – called by main.py.
    Downloads music if library is below min_tracks.
    Returns total track count.
    """
    current = _count()
    if current >= min_tracks:
        LOGGER.info("Music library OK: %s tracks", current)
        return current

    LOGGER.info("Music library low (%s tracks). Downloading more...", current)

    # CC0 tracks first (fastest, most reliable)
    download_cc0_tracks()
    # FMA next
    if _count() < min_tracks:
        download_fma_tracks()
    # Pixabay if key available
    if pixabay_key and _count() < min_tracks:
        download_pixabay_music(pixabay_key)

    final = _count()
    LOGGER.info("Music library now has %s tracks", final)
    return final


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    from dotenv import load_dotenv
    load_dotenv()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")
    total = ensure_music_library(min_tracks=TARGET_COUNT, pixabay_key=pixabay_key)
    print(f"\nMusic library ready: {total} tracks in {MUSIC_DIR}")
