from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import AppConfig
from main import run_pipeline


LOGGER = logging.getLogger(__name__)


def start_scheduler(config: AppConfig) -> None:
    scheduler = BlockingScheduler(timezone=config.scheduler_timezone)

    # Priorities based on best times to post:
    # Sunday: 7 p.m., 8 p.m., 5 p.m.
    # Monday: 8 p.m., 5 p.m., 6 p.m.
    # Tuesday: 8 p.m., 9 p.m., 7 p.m.
    # Wednesday: 7 p.m., 8 p.m., 9 p.m.
    # Thursday: 7 p.m., 8 p.m., 9 p.m.
    # Friday: 4 p.m., 6 p.m., 7 p.m.
    # Saturday: 7 p.m., 11 a.m., 6 p.m.
    schedules = {
        'sun': [19, 20, 17],
        'mon': [20, 17, 18],
        'tue': [20, 21, 19],
        'wed': [19, 20, 21],
        'thu': [19, 20, 21],
        'fri': [16, 18, 19],
        'sat': [19, 11, 18],
    }

    # Select up to config.daily_video_count hours per day
    for day, hours in schedules.items():
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
