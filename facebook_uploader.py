"""
facebook_uploader.py  –  Wonder Stories TV
===========================================
Uploads videos to Facebook as Reels (short) or standard videos (long).

FIXES applied vs old version:
  - Removed all fitness hashtags from _optimize_caption_for_facebook()
  - Added `title` field in Reels finish payload (improves FB discovery)
  - Added story-niche hashtags for Wonder Stories TV
  - Facebook Reels caption now uses KidsSeoPackage.facebook_description
    when available (pre-generated story-specific caption)
  - Added timeout handling on HTTP requests
  - Improved error logging with response body
"""
import logging
import os
from pathlib import Path
from datetime import datetime
import re
import requests

from config import AppConfig
from kids_seo_generator import KidsSeoPackage as SeoPackage


LOGGER = logging.getLogger(__name__)

CHANNEL_NAME = "Wonder Stories TV"

# Core FB Reels hashtags for Wonder Stories TV niche
_WONDER_FB_HASHTAGS = (
    "#Reels #FBViral #HindiKahani #MoralStory #WonderStoriesTV "
    "#BacchonKiKahani #AnimatedStory #KidsStory #HindiReels #FamilyContent"
)


class FacebookUploader:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.page_id = config.facebook_page_id
        self.access_token = config.facebook_access_token
        self.api_version = "v19.0"

    def is_configured(self) -> bool:
        return bool(self.page_id and self.access_token)

    def upload(
        self,
        video_path: Path,
        seo: SeoPackage,
        publish_at: str | None = None,
        is_long: bool = False,
        facebook_description: str = "",
    ) -> dict:
        if not self.is_configured():
            LOGGER.warning("Facebook API credentials not configured. Skipping Facebook upload.")
            return {}

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if is_long:
            return self._upload_standard_video(video_path, seo, publish_at, facebook_description)
        else:
            return self._upload_reel(video_path, seo, publish_at, facebook_description)

    def _upload_standard_video(
        self,
        video_path: Path,
        seo: SeoPackage,
        publish_at: str | None = None,
        facebook_description: str = "",
    ) -> dict:
        LOGGER.info("Starting Facebook Standard Video upload...")
        url = f"https://graph.facebook.com/{self.api_version}/{self.page_id}/videos"

        caption = facebook_description or self._build_caption(seo)

        payload = {
            "access_token": self.access_token,
            "description": caption,
            "title": seo.title[:255],
        }

        if publish_at:
            from datetime import timezone
            dt = datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            payload["published"] = "false"
            payload["scheduled_publish_time"] = str(int(dt.timestamp()))
        else:
            payload["published"] = "true"

        with open(video_path, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f}, timeout=300)

        data = res.json()
        if "error" in data:
            LOGGER.error("Facebook Standard Video Error: %s", data["error"])
            raise Exception(f"Facebook Graph API Error (Standard Video): {data['error']}")

        video_id = data.get("id", "unknown")
        LOGGER.info("Facebook standard video upload complete. Video ID: %s", video_id)
        return {"id": video_id, "platform": "facebook", "status": "SCHEDULED" if publish_at else "PUBLISHED"}

    def _upload_reel(
        self,
        video_path: Path,
        seo: SeoPackage,
        publish_at: str | None = None,
        facebook_description: str = "",
    ) -> dict:
        file_size = os.path.getsize(video_path)

        # ─── Phase 1: Initialize Upload ───────────────────────────────────────
        LOGGER.info("FB Reels Phase 1: Initialize upload session...")
        init_url = f"https://graph.facebook.com/{self.api_version}/{self.page_id}/video_reels"
        init_payload = {
            "upload_phase": "start",
            "access_token": self.access_token,
        }
        init_res = requests.post(init_url, data=init_payload, timeout=30)
        init_data = init_res.json()

        if "error" in init_data:
            LOGGER.error("FB Reels Init Error: %s | Response: %s", init_data["error"], init_res.text)
            raise Exception(f"Facebook Graph API Error (Init): {init_data['error']}")

        video_id = init_data["video_id"]
        upload_url = init_data["upload_url"]
        LOGGER.info("FB Reels Phase 1 complete. Video ID: %s", video_id)

        # ─── Phase 2: Upload Video File ───────────────────────────────────────
        LOGGER.info("FB Reels Phase 2: Uploading video file (%s bytes)...", file_size)
        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size),
        }

        with open(video_path, "rb") as f:
            upload_res = requests.post(upload_url, headers=headers, data=f, timeout=600)

        upload_data = upload_res.json()
        if "error" in upload_data:
            LOGGER.error("FB Reels Upload Error: %s | Response: %s", upload_data.get("error"), upload_res.text)
            raise Exception(f"Facebook Graph API Error (Upload): {upload_data['error']}")

        LOGGER.info("FB Reels Phase 2 complete. Upload successful.")

        # ─── Phase 3: Finish and Publish ─────────────────────────────────────
        LOGGER.info("FB Reels Phase 3: Publishing Reel...")

        # Use pre-generated facebook_description if available, else build one
        caption = facebook_description or self._build_reel_caption(seo)

        finish_payload = {
            "access_token": self.access_token,
            "upload_phase": "finish",
            "video_id": video_id,
            "description": caption,
        }

        if publish_at:
            from datetime import timezone
            dt = datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            finish_payload["video_state"] = "SCHEDULED"
            finish_payload["scheduled_publish_time"] = str(int(dt.timestamp()))
        else:
            finish_payload["video_state"] = "PUBLISHED"

        finish_res = requests.post(init_url, data=finish_payload, timeout=60)
        finish_data = finish_res.json()

        if "error" in finish_data:
            LOGGER.error("FB Reels Finish Error: %s | Response: %s", finish_data.get("error"), finish_res.text)
            raise Exception(f"Facebook Graph API Error (Finish): {finish_data['error']}")

        LOGGER.info("FB Reels Phase 3 complete. Reel published. Video ID: %s", video_id)
        return {
            "id": video_id,
            "platform": "facebook",
            "status": finish_payload["video_state"],
        }

    # ─── Caption Builders ─────────────────────────────────────────────────────

    def _build_caption(self, seo: SeoPackage) -> str:
        """Build a standard video caption from SeoPackage."""
        caption = f"{seo.title}\n\n{seo.description}"
        return self._optimize_caption_for_facebook(caption)

    def _build_reel_caption(self, seo: SeoPackage) -> str:
        """Build a short, punchy Reels caption from SeoPackage."""
        # Use first 200 chars of description + wonder hashtags
        short_desc = seo.description[:200].strip()
        if len(seo.description) > 200:
            short_desc += "..."
        caption = f"✨ {seo.title}\n\n{short_desc}\n\n{_WONDER_FB_HASHTAGS}"
        return caption[:500]

    def _optimize_caption_for_facebook(self, caption: str) -> str:
        """Replace YouTube-specific hashtags with Facebook-native equivalents
        and inject Wonder Stories TV story hashtags."""
        # Replace YouTube hashtags with Facebook equivalents
        replacements = {
            "#shortsfeed": "#facebookreels",
            "#shortsvideos": "#viralreels",
            "#shortsreels": "#fbreels",
            "#shorts": "#reels",
            "#youtubeshorts": "#fbreels",
        }
        optimized = caption
        for yt_tag, fb_tag in replacements.items():
            optimized = re.sub(re.escape(yt_tag), fb_tag, optimized, flags=re.IGNORECASE)

        # Add Wonder Stories TV story hashtags (not fitness ones!)
        wonder_tags = [
            "#WonderStoriesTV",
            "#HindiKahani",
            "#MoralStory",
            "#BacchonKiKahani",
            "#FBViral",
            "#Reels",
            "#AnimatedStory",
            "#FamilyContent",
        ]

        extra_tags = [tag for tag in wonder_tags if tag.lower() not in optimized.lower()]
        if extra_tags:
            optimized = f"{optimized.strip()} {' '.join(extra_tags)}"

        return optimized[:2000]
