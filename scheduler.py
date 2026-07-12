from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from main import run_kids_pipeline

LOGGER = logging.getLogger(__name__)

# ─── Channel routing (mirrors main.py) ────────────────────────────────────────
ACTIVE_CHANNEL = os.getenv("CHANNEL", "stories").lower().strip()

FB_CONTENT_DIR = Path("output/fb_content")
FB_POSTS_DIR   = FB_CONTENT_DIR / "posts"
FB_STORIES_DIR = FB_CONTENT_DIR / "stories"


def run_scheduled_fb_post(config: AppConfig) -> None:
    """
    Scheduled job to publish a Facebook post.
    1. Checks if there is any pending post in output/fb_content/posts/ with an image.
    2. If yes, uploads the oldest pending post.
    3. If no, automatically generates a new post template (using --auto).
    """
    try:
        from fb_social_uploader import FBSocialUploader
        from fb_post_creator import FBPostCreator
        from fb_content import _pick_auto_topic

        uploader = FBSocialUploader(config)

        pending_folders = []
        if FB_POSTS_DIR.exists():
            for folder in sorted(FB_POSTS_DIR.iterdir()):
                if not folder.is_dir():
                    continue
                # Only consider pending if the image asset is already placed
                image_exists = (folder / "image.png").exists() or (folder / "image.jpg").exists()
                if not image_exists:
                    continue

                status_file = folder / "status.json"
                is_uploaded = False
                if status_file.exists():
                    try:
                        status = json.loads(status_file.read_text(encoding="utf-8"))
                        is_uploaded = bool(status.get("uploaded"))
                    except Exception:
                        pass
                if not is_uploaded:
                    pending_folders.append(folder)

        if pending_folders:
            LOGGER.info("Scheduled FB Post Job: Found %d pending posts with assets. Uploading the oldest: %s", len(pending_folders), pending_folders[0].name)
            uploader._check_config()
            result = uploader.upload_post_dir(pending_folders[0])
            LOGGER.info("Scheduled FB Post Job: Upload successful! ID: %s", result.get("id"))
        else:
            LOGGER.info("Scheduled FB Post Job: No pending posts with assets found. Auto-generating a new post template...")
            topic = _pick_auto_topic()
            creator = FBPostCreator(config)
            post_dir = creator.create(topic)
            LOGGER.info("Scheduled FB Post Job: Auto-generated post template in %s. Please place image.png in it.", post_dir)
            
    except Exception:
        LOGGER.exception("Error during scheduled Facebook post execution")


def run_scheduled_fb_story(config: AppConfig) -> None:
    """
    Scheduled job to publish a Facebook story.
    1. Checks if there is any pending story in output/fb_content/stories/ with a story card.
    2. If yes, uploads the oldest pending story.
    3. If no, automatically generates a new story template (using --auto).
    """
    try:
        from fb_social_uploader import FBSocialUploader
        from fb_story_creator import FBStoryCreator
        from fb_content import _pick_auto_topic

        uploader = FBSocialUploader(config)

        pending_folders = []
        if FB_STORIES_DIR.exists():
            for folder in sorted(FB_STORIES_DIR.iterdir()):
                if not folder.is_dir():
                    continue
                # Only consider pending if the story card asset is already placed
                card_exists = (folder / "story_card.png").exists()
                if not card_exists:
                    continue

                status_file = folder / "status.json"
                is_uploaded = False
                if status_file.exists():
                    try:
                        status = json.loads(status_file.read_text(encoding="utf-8"))
                        is_uploaded = bool(status.get("uploaded"))
                    except Exception:
                        pass
                if not is_uploaded:
                    pending_folders.append(folder)

        if pending_folders:
            LOGGER.info("Scheduled FB Story Job: Found %d pending stories with assets. Uploading the oldest: %s", len(pending_folders), pending_folders[0].name)
            uploader._check_config()
            result = uploader.upload_story_dir(pending_folders[0])
            LOGGER.info("Scheduled FB Story Job: Upload successful! ID: %s", result.get("id"))
        else:
            LOGGER.info("Scheduled FB Story Job: No pending stories with assets found. Auto-generating a new story template...")
            topic = _pick_auto_topic()
            creator = FBStoryCreator(config)
            story_dir = creator.create(topic)
            LOGGER.info("Scheduled FB Story Job: Auto-generated story template in %s. Please place story_card.png in it.", story_dir)
            
    except Exception:
        LOGGER.exception("Error during scheduled Facebook story execution")



def start_scheduler(config: AppConfig) -> None:
    scheduler = BlockingScheduler(timezone=config.scheduler_timezone)

    if ACTIVE_CHANNEL in ("kids", "stories"):
        # ── Chintu Stories: single daily job at 2:30 PM IST ───────────────────
        scheduler.add_job(
            func=lambda: run_kids_pipeline(
                short_count=config.daily_video_count,
                long_count=0,
                upload=config.upload_enabled,
                videos_per_day=config.daily_video_count,
            ),
            trigger=CronTrigger(hour=13, minute=30),   # 13:30 = 1:30 PM IST
            id="kids_chintu_daily",
            max_instances=1,
            replace_existing=True,
        )
        LOGGER.info(
            "Chintu Stories scheduler started — runs daily at 13:30 %s",
            config.scheduler_timezone,
        )
    else:
        # ── Fitness channel: original multi-slot schedule ─────────────────────
        from posting_schedule import DAY_NAME_TO_WEEKDAY, SHORTS_POSTING_SLOTS

        for day, weekday in DAY_NAME_TO_WEEKDAY.items():
            hours = SHORTS_POSTING_SLOTS[weekday]
            selected_hours = hours[: config.daily_video_count]
            for idx, hour in enumerate(selected_hours):
                scheduler.add_job(
                    func=lambda: run_kids_pipeline(short_count=1, upload=config.upload_enabled),
                    trigger=CronTrigger(day_of_week=day, hour=hour, minute=0),
                    id=f"{day}_fitness_shorts_{idx}",
                    max_instances=1,
                    replace_existing=True,
                )
        LOGGER.info(
            "Fitness scheduler started — timezone=%s, daily_video_count=%s",
            config.scheduler_timezone,
            config.daily_video_count,
        )

    # ── Facebook Content Studio scheduling ────────────────────────────────────
    # 3 Posts per day: 10:00 AM, 3:00 PM, 8:00 PM
    post_hours = [10, 15, 20]
    for idx, hour in enumerate(post_hours):
        scheduler.add_job(
            func=lambda: run_scheduled_fb_post(config),
            trigger=CronTrigger(hour=hour, minute=0),
            id=f"fb_post_daily_{hour}",
            max_instances=1,
            replace_existing=True,
        )
    
    # 1 Story per day: 12:00 PM (Noon)
    scheduler.add_job(
        func=lambda: run_scheduled_fb_story(config),
        trigger=CronTrigger(hour=12, minute=0),
        id="fb_story_daily",
        max_instances=1,
        replace_existing=True,
    )
    
    LOGGER.info(
        "Facebook Content Studio scheduler loaded — 3 posts/day at %s, 1 story/day at 12:00 (%s)",
        post_hours,
        config.scheduler_timezone,
    )

    scheduler.start()
