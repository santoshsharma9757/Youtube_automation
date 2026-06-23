"""
fb_social_uploader.py — Chintu Wonder World
============================================
Handles uploading Facebook content to the Chintu Wonder World page:

  • Posts   → POST /{page-id}/photos  (image + caption)
  • Stories → POST /{page-id}/photo_stories  (story card)
  • Reels   → 3-phase resumable upload to /{page-id}/video_reels

Usage (via fb_content.py CLI):
    python fb_content.py upload post [--dir path/to/post_dir]
    python fb_content.py upload story [--dir path/to/story_dir]
    python fb_content.py upload reel [--dir path/to/reel_dir]
    python fb_content.py upload all

Tracking:
    Each content folder has a status.json that tracks upload state.
    Already-uploaded items are skipped unless --force is used.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import AppConfig, get_config, YOUTUBE_COMMUNITY_DIR

LOGGER = logging.getLogger(__name__)

# Content output base dirs
FB_CONTENT_DIR = Path("output/fb_content")
FB_POSTS_DIR   = FB_CONTENT_DIR / "posts"
FB_STORIES_DIR = FB_CONTENT_DIR / "stories"
FB_REELS_DIR   = FB_CONTENT_DIR / "reels"

_API_VER = "v19.0"
_BASE_URL = f"https://graph.facebook.com/{_API_VER}"


class FBSocialUploader:
    """Uploads Facebook posts, stories, and reels via Graph API."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or get_config()
        self.page_id = self.config.facebook_page_id
        self.token   = self.config.facebook_access_token

    def is_configured(self) -> bool:
        return bool(self.page_id and self.token)

    def _check_config(self) -> None:
        if not self.is_configured():
            raise RuntimeError(
                "Facebook credentials not configured.\n"
                "Set FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN in your .env file."
            )

    # ── Upload ALL pending ────────────────────────────────────────────────────

    def upload_all_pending(self, content_type: str = "all", force: bool = False) -> dict:
        """Upload all pending (not yet uploaded) content of given type."""
        self._check_config()
        results = {"posts": [], "stories": [], "reels": []}

        if content_type in ("all", "post"):
            results["posts"] = self._upload_pending_from_dir(
                FB_POSTS_DIR, self.upload_post_dir, "post", force
            )
        if content_type in ("all", "story"):
            results["stories"] = self._upload_pending_from_dir(
                FB_STORIES_DIR, self.upload_story_dir, "story", force
            )
        if content_type in ("all", "reel"):
            results["reels"] = self._upload_pending_from_dir(
                FB_REELS_DIR, self.upload_reel_dir, "reel", force
            )

        total = len(results["posts"]) + len(results["stories"]) + len(results["reels"])
        _print_box(f"UPLOAD COMPLETE — {total} item(s) uploaded")
        return results

    def _upload_pending_from_dir(
        self, base_dir: Path, upload_fn, label: str, force: bool
    ) -> list[dict]:
        if not base_dir.exists():
            LOGGER.info("No %s output directory found: %s", label, base_dir)
            return []

        uploaded = []
        folders = sorted(base_dir.iterdir()) if base_dir.exists() else []
        for folder in folders:
            if not folder.is_dir():
                continue
            status_file = folder / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text(encoding="utf-8"))
                if status.get("uploaded") and not force:
                    LOGGER.info("Skipping already uploaded %s (cleaning up folder): %s", label, folder.name)
                    self._cleanup_uploaded_dir(folder, label)
                    continue
            try:
                result = upload_fn(folder)
                uploaded.append({"folder": str(folder), "result": result})
                LOGGER.info("✅ Uploaded %s: %s", label, folder.name)
            except Exception as exc:
                LOGGER.error("❌ Failed to upload %s %s: %s", label, folder.name, exc)
        return uploaded

    def _cleanup_uploaded_dir(self, folder: Path, label: str) -> None:
        """Copies post to youtube_community if needed, and deletes the local folder."""
        if label == "post":
            image_path = folder / "image.png"
            if not image_path.exists():
                jpg = folder / "image.jpg"
                if jpg.exists():
                    image_path = jpg
            
            caption_file = folder / "caption.txt"
            
            if image_path.exists():
                try:
                    import shutil
                    dest_dir = YOUTUBE_COMMUNITY_DIR / folder.name
                    if not dest_dir.exists():
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(image_path, dest_dir / image_path.name)
                        if caption_file.exists():
                            shutil.copy2(caption_file, dest_dir / "caption.txt")
                        meta_file = folder / "metadata.json"
                        if meta_file.exists():
                            shutil.copy2(meta_file, dest_dir / "metadata.json")
                        LOGGER.info("✅ Copied post files to youtube_community during cleanup → %s", dest_dir.name)
                except Exception as exc:
                    LOGGER.warning("Could not copy files to youtube_community: %s", exc)
                    
        # Delete local folder
        try:
            import shutil
            shutil.rmtree(folder)
            LOGGER.info("🗑️ Cleaned up and deleted already uploaded folder: %s", folder.name)
        except Exception as exc:
            LOGGER.warning("Could not delete directory %s: %s", folder, exc)

    # ── POST upload ───────────────────────────────────────────────────────────

    def upload_post_dir(self, post_dir: Path) -> dict:
        """Upload a Facebook photo post from a post directory."""
        post_dir = Path(post_dir)
        image_path = post_dir / "image.png"
        if not image_path.exists():
            # Try jpg
            jpg = post_dir / "image.jpg"
            if jpg.exists():
                image_path = jpg
            else:
                raise FileNotFoundError(f"No image found in {post_dir}")

        caption_file = post_dir / "caption.txt"
        caption = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""

        result = self.upload_post(image_path=image_path, caption=caption)
        
        # Copy to YouTube Community Posts folder
        try:
            import shutil
            dest_dir = YOUTUBE_COMMUNITY_DIR / post_dir.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image_path, dest_dir / image_path.name)
            if caption_file.exists():
                shutil.copy2(caption_file, dest_dir / "caption.txt")
            meta_file = post_dir / "metadata.json"
            if meta_file.exists():
                shutil.copy2(meta_file, dest_dir / "metadata.json")
            LOGGER.info("✅ Copied post files to youtube_community → %s", dest_dir.name)
        except Exception as exc:
            LOGGER.warning("Could not copy files to youtube_community: %s", exc)

        # Clean up (delete local FB post directory)
        try:
            import shutil
            shutil.rmtree(post_dir)
            LOGGER.info("🗑️ Deleted local post folder: %s", post_dir.name)
        except Exception as exc:
            LOGGER.warning("Could not delete post directory %s: %s", post_dir, exc)

        return result

    def upload_post(self, image_path: Path, caption: str = "") -> dict:
        """
        Upload a photo post to Facebook page.
        POST /{page-id}/photos
        """
        self._check_config()
        url = f"{_BASE_URL}/{self.page_id}/photos"
        LOGGER.info("📤 Uploading Facebook Post: %s", image_path.name)

        payload = {
            "access_token": self.token,
            "caption": caption[:63206],  # FB caption limit
            "published": "true",
        }

        with open(image_path, "rb") as f:
            resp = requests.post(url, data=payload, files={"source": f}, timeout=120)

        data = resp.json()
        if "error" in data:
            LOGGER.error("Post upload error: %s | Response: %s", data["error"], resp.text)
            raise Exception(f"Facebook Post API Error: {data['error']}")

        post_id = data.get("post_id") or data.get("id", "unknown")
        LOGGER.info("✅ Post published! Post ID: %s", post_id)
        return {
            "platform": "facebook",
            "type": "post",
            "id": post_id,
            "status": "PUBLISHED",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── STORY upload ──────────────────────────────────────────────────────────

    def upload_story_dir(self, story_dir: Path) -> dict:
        """Upload a Facebook story from a story directory."""
        story_dir = Path(story_dir)
        card_path = story_dir / "story_card.png"
        if not card_path.exists():
            raise FileNotFoundError(f"No story_card.png found in {story_dir}")

        result = self.upload_story(image_path=card_path)

        # Clean up (delete local FB story directory)
        try:
            import shutil
            shutil.rmtree(story_dir)
            LOGGER.info("🗑️ Deleted local story folder: %s", story_dir.name)
        except Exception as exc:
            LOGGER.warning("Could not delete story directory %s: %s", story_dir, exc)

        return result

    def upload_story(self, image_path: Path) -> dict:
        """
        Upload a photo story to Facebook page.
        Phase 1: Upload photo (unpublished) → get photo_id
        Phase 2: POST /{page-id}/photo_stories with photo_id
        """
        self._check_config()
        LOGGER.info("📤 Uploading Facebook Story: %s", image_path.name)

        # Phase 1: Upload photo to get photo_id
        photo_url = f"{_BASE_URL}/{self.page_id}/photos"
        payload_p1 = {
            "access_token": self.token,
            "published": "false",
        }
        with open(image_path, "rb") as f:
            resp1 = requests.post(photo_url, data=payload_p1, files={"source": f}, timeout=120)

        data1 = resp1.json()
        if "error" in data1:
            LOGGER.error("Story photo upload error: %s", data1["error"])
            raise Exception(f"Facebook Story Photo Upload Error: {data1['error']}")

        photo_id = data1.get("id")
        if not photo_id:
            raise Exception(f"No photo_id returned from Facebook: {data1}")
        LOGGER.info("Phase 1 complete. Photo ID: %s", photo_id)

        # Phase 2: Create the story
        story_url = f"{_BASE_URL}/{self.page_id}/photo_stories"
        payload_p2 = {
            "access_token": self.token,
            "photo_id": photo_id,
        }
        resp2 = requests.post(story_url, data=payload_p2, timeout=60)
        data2 = resp2.json()

        if "error" in data2:
            LOGGER.error("Story creation error: %s | Response: %s", data2["error"], resp2.text)
            raise Exception(f"Facebook Story Creation Error: {data2['error']}")

        story_id = data2.get("story_fbid") or data2.get("id", "unknown")
        LOGGER.info("✅ Story published! Story ID: %s", story_id)
        return {
            "platform": "facebook",
            "type": "story",
            "id": story_id,
            "photo_id": photo_id,
            "status": "PUBLISHED",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── REEL upload ───────────────────────────────────────────────────────────

    def upload_reel_dir(self, reel_dir: Path) -> dict:
        """Upload a Facebook Reel from a reel directory."""
        reel_dir = Path(reel_dir)
        reel_path = reel_dir / "reel.mp4"
        if not reel_path.exists():
            raise FileNotFoundError(f"No reel.mp4 found in {reel_dir}")

        caption_file = reel_dir / "caption.txt"
        caption = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""

        result = self.upload_reel(video_path=reel_path, caption=caption)
        _mark_uploaded(reel_dir, result)
        return result

    def upload_reel(self, video_path: Path, caption: str = "") -> dict:
        """
        Upload a video as a Facebook Reel via 3-phase resumable upload.
        Phase 1: Initialize upload session
        Phase 2: Upload video bytes
        Phase 3: Finish and publish
        """
        self._check_config()
        file_size = os.path.getsize(video_path)
        reels_url = f"{_BASE_URL}/{self.page_id}/video_reels"

        # ─ Phase 1: Initialize ────────────────────────────────────────────────
        LOGGER.info("🎬 Reel Phase 1: Initialize... (file: %s, %d bytes)", video_path.name, file_size)
        resp1 = requests.post(
            reels_url,
            data={"upload_phase": "start", "access_token": self.token},
            timeout=30,
        )
        data1 = resp1.json()
        if "error" in data1:
            raise Exception(f"Reel Init Error: {data1['error']}")

        video_id  = data1["video_id"]
        upload_url = data1["upload_url"]
        LOGGER.info("Phase 1 OK — video_id: %s", video_id)

        # ─ Phase 2: Upload bytes ──────────────────────────────────────────────
        LOGGER.info("🎬 Reel Phase 2: Uploading %d bytes...", file_size)
        with open(video_path, "rb") as f:
            resp2 = requests.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {self.token}",
                    "offset": "0",
                    "file_size": str(file_size),
                },
                data=f,
                timeout=600,
            )
        data2 = resp2.json()
        if "error" in data2:
            raise Exception(f"Reel Upload Error: {data2['error']}")
        LOGGER.info("Phase 2 OK — Upload complete.")

        # ─ Phase 3: Publish ───────────────────────────────────────────────────
        LOGGER.info("🎬 Reel Phase 3: Publishing...")
        resp3 = requests.post(
            reels_url,
            data={
                "access_token": self.token,
                "upload_phase": "finish",
                "video_id": video_id,
                "description": caption[:500],
                "video_state": "PUBLISHED",
            },
            timeout=60,
        )
        data3 = resp3.json()
        if "error" in data3:
            raise Exception(f"Reel Publish Error: {data3['error']}")

        LOGGER.info("✅ Reel published! Video ID: %s", video_id)
        return {
            "platform": "facebook",
            "type": "reel",
            "id": video_id,
            "status": "PUBLISHED",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mark_uploaded(content_dir: Path, upload_result: dict) -> None:
    """Write upload result to status.json in the content directory."""
    status = {
        "uploaded": True,
        "upload_response": upload_result,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    (content_dir / "status.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _print_box(msg: str) -> None:
    border = "═" * (len(msg) + 4)
    print(f"\n╔{border}╗\n║  {msg}  ║\n╚{border}╝\n")


# ── Standalone usage ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from config import setup_logging
    setup_logging()
    uploader = FBSocialUploader()
    uploader.upload_all_pending()
