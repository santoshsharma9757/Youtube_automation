from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from main import run_pipeline


LOGGER = logging.getLogger(__name__)


def start_scheduler(config: AppConfig) -> None:
    scheduler = BlockingScheduler(timezone=config.scheduler_timezone)

    # Morning Peak: 7:00 AM
    scheduler.add_job(
        func=lambda: run_pipeline(video_count=config.daily_video_count, upload=config.upload_enabled),
        trigger=CronTrigger(hour=7, minute=0),
        id="morning_shorts_pipeline",
        max_instances=1,
        replace_existing=True,
    )

    # Evening Peak: 7:00 PM (19:00)
    scheduler.add_job(
        func=lambda: run_pipeline(video_count=config.daily_video_count, upload=config.upload_enabled),
        trigger=CronTrigger(hour=19, minute=0),
        id="evening_shorts_pipeline",
        max_instances=1,
        replace_existing=True,
    )

    LOGGER.info(
        "Scheduler started for timezone=%s, daily_video_count=%s",
        config.scheduler_timezone,
        config.daily_video_count,
    )
    scheduler.start()
