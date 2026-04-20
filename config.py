from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = OUTPUT_DIR / "data"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "videos"
SUBTITLE_DIR = OUTPUT_DIR / "subtitles"
LOG_DIR = OUTPUT_DIR / "logs"
WINDOWS_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/impact.ttf"),
    Path("C:/Windows/Fonts/ariblk.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
]


def ensure_directories() -> None:
    for directory in (
        ASSETS_DIR,
        OUTPUT_DIR,
        DATA_DIR,
        AUDIO_DIR,
        VIDEO_DIR,
        SUBTITLE_DIR,
        LOG_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


ensure_directories()


def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_file = LOG_DIR / "automation.log"

    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


@dataclass(slots=True)
class AppConfig:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5-mini"))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    deepseek_base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.getenv("ELEVENLABS_VOICE_ID", ""))
    youtube_client_secrets_file: str = field(
        default_factory=lambda: os.getenv("YOUTUBE_CLIENT_SECRET_FILE", os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json"))
    )
    youtube_token_file: str = field(default_factory=lambda: os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json"))
    youtube_api_key: str = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY", ""))
    youtube_category_id: str = field(default_factory=lambda: os.getenv("YOUTUBE_CATEGORY_ID", "26"))  # 26=Howto & Style fits workout, yoga, and explainer-style fitness shorts better than Sports
    default_privacy_status: str = field(default_factory=lambda: os.getenv("YOUTUBE_PRIVACY_STATUS", "public"))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    pexels_api_key: str = field(default_factory=lambda: os.getenv("PEXELS_API_KEY", ""))
    pixabay_api_key: str = field(default_factory=lambda: os.getenv("PIXABAY_API_KEY", ""))
    whisper_model_size: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL_SIZE", "base"))
    ffmpeg_binary: Optional[str] = field(default_factory=lambda: os.getenv("FFMPEG_BINARY"))
    background_assets_dir: Path = field(default_factory=lambda: ASSETS_DIR / "backgrounds")
    local_video_assets_dir: Path = field(default_factory=lambda: ASSETS_DIR / "localvideos")
    content_images_dir: Path = field(default_factory=lambda: ASSETS_DIR / "content images")
    music_dir: Path = field(default_factory=lambda: ASSETS_DIR / "music")
    font_file: Path = field(default_factory=lambda: resolve_font_path())
    subtitle_store_dir: Path = field(default_factory=lambda: SUBTITLE_DIR)
    scheduler_timezone: str = field(default_factory=lambda: os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata"))
    daily_video_count: int = field(default_factory=lambda: int(os.getenv("DAILY_VIDEO_COUNT", "1")))
    upload_enabled: bool = field(default_factory=lambda: os.getenv("UPLOAD_ENABLED", "false").lower() == "true")
    use_pexels_for_shorts: bool = field(default=False)

    ideas_store: Path = field(default_factory=lambda: DATA_DIR / "ideas.json")
    content_store: Path = field(default_factory=lambda: DATA_DIR / "content_history.json")
    seo_store: Path = field(default_factory=lambda: DATA_DIR / "seo_history.json")


def get_config() -> AppConfig:
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    return AppConfig()


def resolve_font_path() -> Path:
    bundled = ASSETS_DIR / "fonts" / "NotoSansDevanagari-Bold.ttf"
    if bundled.exists():
        return bundled
    for candidate in WINDOWS_FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    return bundled
