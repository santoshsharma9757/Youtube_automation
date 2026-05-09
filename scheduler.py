from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from main import run_pipeline
from posting_schedule import DAY_NAME_TO_WEEKDAY, SHORTS_POSTING_SLOTS


LOGGER = logging.getLogger(__name__)


def start_scheduler(config: AppConfig) -> None:
    scheduler = BlockingScheduler(timezone=config.scheduler_timezone)

    # Select up to config.daily_video_count hours per day
    for day, weekday in DAY_NAME_TO_WEEKDAY.items():
        hours = SHORTS_POSTING_SLOTS[weekday]
        selected_hours = hours[:config.daily_video_count]

        for idx, hour in enumerate(selected_hours):
            scheduler.add_job(
                func=lambda: run_pipeline(short_count=1, upload=config.upload_enabled),
                trigger=CronTrigger(day_of_week=day, hour=hour, minute=0),
                id=f"{day}_shorts_pipeline_{idx}",
                max_instances=1,
                replace_existing=True,
            )

    LOGGER.info(
        "Scheduler started for timezone=%s, daily_video_count=%s",
        config.scheduler_timezone,
        config.daily_video_count,
    )
    scheduler.start()
