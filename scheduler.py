from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from main import run_pipeline

LOGGER = logging.getLogger(__name__)

# ─── Channel routing (mirrors main.py) ────────────────────────────────────────
ACTIVE_CHANNEL = os.getenv("CHANNEL", "stories").lower().strip()


def start_scheduler(config: AppConfig) -> None:
    scheduler = BlockingScheduler(timezone=config.scheduler_timezone)

    if ACTIVE_CHANNEL in ("kids", "stories"):
        # ── Chintu Stories: single daily job at 2:30 PM IST ───────────────────
        scheduler.add_job(
            func=lambda: run_pipeline(
                short_count=config.daily_video_count,
                long_count=0,
                upload=config.upload_enabled,
                videos_per_day=config.daily_video_count,
            ),
            trigger=CronTrigger(hour=14, minute=30),   # 14:30 = 2:30 PM IST
            id="kids_chintu_daily",
            max_instances=1,
            replace_existing=True,
        )
        LOGGER.info(
            "Chintu Stories scheduler started — runs daily at 14:30 %s",
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
                    func=lambda: run_pipeline(short_count=1, upload=config.upload_enabled),
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

    scheduler.start()
