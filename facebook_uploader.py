import logging
import os
from pathlib import Path
from datetime import datetime
import re
import requests

from config import AppConfig
from seo_generator import SeoPackage


LOGGER = logging.getLogger(__name__)


class FacebookUploader:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.page_id = config.facebook_page_id
        self.access_token = config.facebook_access_token
        self.api_version = "v19.0"

    def is_configured(self) -> bool:
        return bool(self.page_id and self.access_token)

    def upload(self, video_path: Path, seo: SeoPackage, publish_at: str | None = None, is_long: bool = False) -> dict:
        if not self.is_configured():
            LOGGER.warning("Facebook API credentials not configured. Skipping Facebook upload.")
            return {}

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if is_long:
            return self._upload_standard_video(video_path, seo, publish_at)
        else:
            return self._upload_reel(video_path, seo, publish_at)

    def _upload_standard_video(self, video_path: Path, seo: SeoPackage, publish_at: str | None = None) -> dict:
        LOGGER.info("Starting Facebook Standard Video upload...")
        url = f"https://graph.facebook.com/{self.api_version}/{self.page_id}/videos"
        caption = seo.description
        if not caption.strip().lower().startswith(seo.title.strip().lower()[:20]):
            caption = f"{seo.title}\n\n{seo.description}"
        caption = self._optimize_caption_for_facebook(caption, seo.content_style)
        
        payload = {
            "access_token": self.access_token,
            "description": caption,
        }
        
        if publish_at:
            from datetime import timezone
            dt = datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            unix_timestamp = int(dt.timestamp())
            payload["published"] = "false"
            payload["scheduled_publish_time"] = str(unix_timestamp)
        else:
            payload["published"] = "true"

        with open(video_path, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f})
            data = res.json()

        if "error" in data:
            raise Exception(f"Facebook Graph API Error (Standard Video): {data['error']}")
            
        video_id = data.get("id", "unknown")
        LOGGER.info("Facebook upload complete with video id %s", video_id)
        return {"id": video_id, "platform": "facebook", "status": "SCHEDULED" if publish_at else "PUBLISHED"}

    def _upload_reel(self, video_path: Path, seo: SeoPackage, publish_at: str | None = None) -> dict:
        file_size = os.path.getsize(video_path)

        # ---------------------------------------------------------
        # Phase 1: Initialize Upload
        # ---------------------------------------------------------
        LOGGER.info("Starting Facebook Reels upload phase 1 (Initialize)...")
        init_url = f"https://graph.facebook.com/{self.api_version}/{self.page_id}/video_reels"
        init_payload = {
            "upload_phase": "start",
            "access_token": self.access_token
        }
        init_res = requests.post(init_url, data=init_payload)
        init_data = init_res.json()

        if "error" in init_data:
            raise Exception(f"Facebook Graph API Error (Init): {init_data['error']}")

        video_id = init_data["video_id"]
        upload_url = init_data["upload_url"]

        # ---------------------------------------------------------
        # Phase 2: Upload Video File
        # ---------------------------------------------------------
        LOGGER.info("Starting Facebook Reels upload phase 2 (Upload File)...")
        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size)
        }
        
        with open(video_path, "rb") as f:
            upload_res = requests.post(upload_url, headers=headers, data=f)
            upload_data = upload_res.json()
            if "error" in upload_data:
                 raise Exception(f"Facebook Graph API Error (Upload): {upload_data['error']}")

        # ---------------------------------------------------------
        # Phase 3: Finish and Publish/Schedule
        # ---------------------------------------------------------
        LOGGER.info("Starting Facebook Reels upload phase 3 (Publish/Schedule)...")
        
        # Combine title and description for FB Reels caption
        caption = seo.description
        if not caption.strip().lower().startswith(seo.title.strip().lower()[:20]):
            caption = f"{seo.title}\n\n{seo.description}"
        caption = self._optimize_caption_for_facebook(caption, seo.content_style)

        finish_payload = {
            "access_token": self.access_token,
            "upload_phase": "finish",
            "video_id": video_id,
            "description": caption
        }

        if publish_at:
            # publish_at comes as ISO string like '2026-05-24T20:00:00Z'
            from datetime import timezone
            dt = datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            unix_timestamp = int(dt.timestamp())
            finish_payload["video_state"] = "SCHEDULED"
            finish_payload["scheduled_publish_time"] = str(unix_timestamp)
        else:
            finish_payload["video_state"] = "PUBLISHED"

        finish_res = requests.post(init_url, data=finish_payload)
        finish_data = finish_res.json()

        if "error" in finish_data:
            raise Exception(f"Facebook Graph API Error (Finish): {finish_data['error']}")

        LOGGER.info("Facebook upload complete with video id %s", video_id)
        return {"id": video_id, "platform": "facebook", "status": finish_payload["video_state"]}

    def _optimize_caption_for_facebook(self, caption: str, content_style: str) -> str:
        # Replace YouTube-specific hashtags with Facebook-native Reels hashtags
        replacements = {
            "#shortsfeed": "#facebookreels",
            "#shortsvideos": "#viralreels",
            "#shortsreels": "#fbreels",
            "#shorts": "#reels",
        }
        optimized = caption
        for yt_tag, fb_tag in replacements.items():
            # Perform case-insensitive replacement
            optimized = re.sub(re.escape(yt_tag), fb_tag, optimized, flags=re.IGNORECASE)
            
        # Add high-retention general and niche-specific FB Reels hashtags if not present
        fb_tags = ["#reels", "#fbviral", "#trendingreels"]
        if content_style == "yoga":
            fb_tags.extend(["#yogareels", "#mindfulness"])
        elif content_style == "fat_loss":
            fb_tags.extend(["#weightlossjourney", "#fitnessreels"])
        elif content_style == "strength":
            fb_tags.extend(["#gymreels", "#workoutmotivation"])
        elif content_style == "health":
            fb_tags.extend(["#healthtips", "#wellness"])
        else:
            fb_tags.extend(["#fitnessreels", "#workout"])
            
        # Append tags that are not already in the caption
        extra_tags = []
        for tag in fb_tags:
            if tag.lower() not in optimized.lower():
                extra_tags.append(tag)
                
        if extra_tags:
            optimized = f"{optimized.strip()} {' '.join(extra_tags)}"
            
        return optimized
