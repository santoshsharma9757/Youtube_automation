import json
import logging
from pathlib import Path

from config import get_config
from seo_generator import SeoPackage
from uploader import YouTubeUploader

logging.basicConfig(level=logging.INFO)


def cleanup_local_video(video_path: Path, record: dict) -> None:
    if not video_path.exists():
        return
    try:
        video_path.unlink()
        record["local_video_deleted"] = True
        print(f"Deleted local video: {video_path.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"Uploaded but could not delete local video {video_path.name}: {exc}")


def build_daily_slots(videos_per_day: int) -> list[int]:
    if videos_per_day <= 1:
        return [12]
    if videos_per_day == 2:
        return [7, 19]
    if videos_per_day == 3:
        return [8, 14, 20]
    step = max(1, 12 // max(videos_per_day - 1, 1))
    start = 8
    slots = []
    for index in range(videos_per_day):
        hour = min(22, start + (index * step))
        if hour not in slots:
            slots.append(hour)
    return slots


def schedule_pending_uploads(videos_per_day: int = 2) -> int:
    import pytz
    from datetime import datetime, timedelta, time
    config = get_config()
    history_file = config.content_store
    if not history_file.exists():
        print("No content history found.")
        return 0

    history = json.loads(history_file.read_text("utf-8"))
    uploader = YouTubeUploader(config)
    
    tz = pytz.timezone(config.scheduler_timezone)
    now = datetime.now(tz)
    slots = build_daily_slots(videos_per_day)
    count_uploaded = 0
    missing_files = 0
    current_time_pointer = now + timedelta(minutes=30)

    existing_scheduled_times = []
    for record in history:
        scheduled_time = record.get("scheduled_time")
        if not scheduled_time:
            continue
        try:
            scheduled_dt = datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M:%SZ")
            scheduled_dt = pytz.UTC.localize(scheduled_dt).astimezone(tz)
            existing_scheduled_times.append(scheduled_dt)
        except ValueError:
            continue
    if existing_scheduled_times:
        current_time_pointer = max(current_time_pointer, max(existing_scheduled_times) + timedelta(minutes=10))

    for record in history:
        if not record.get("uploaded", False):
            video_path = Path(record["video_path"])
            if not video_path.exists():
                print(f"File not found for upload: {video_path}")
                missing_files += 1
                continue
                
            # Find the next available 7 AM or 7 PM slot
            next_slot = None
            temp_date = current_time_pointer.date()
            while next_slot is None:
                for s_hour in slots:
                    candidate = tz.localize(datetime.combine(temp_date, time(hour=s_hour)))
                    if candidate > current_time_pointer:
                        next_slot = candidate
                        break
                if next_slot is None: temp_date += timedelta(days=1)

            # Convert to UTC ISO for YouTube API
            publish_at_utc = next_slot.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
            seo = SeoPackage(**record["seo"])
            
            print(f"Scheduling '{seo.title}' for {next_slot.strftime('%Y-%m-%d %H:%M %Z')}...")
            try:
                response = uploader.upload_short(video_path, seo, publish_at=publish_at_utc)
                record["uploaded"] = True
                record["upload_response"] = response
                record["scheduled_time"] = publish_at_utc
                cleanup_local_video(video_path, record)
                history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), "utf-8")
                print("Scheduled successfully!")
                count_uploaded += 1
                current_time_pointer = next_slot + timedelta(minutes=10)
            except Exception as e:
                print(f"Failed to schedule {seo.title}: {e}")

    if count_uploaded == 0 and missing_files == 0:
        print("No new videos to schedule.")
    elif count_uploaded == 0 and missing_files > 0:
        print(f"No videos were scheduled because {missing_files} pending record(s) are missing their video files.")
    else:
        print(f"Successfully scheduled {count_uploaded} videos.")
        if missing_files:
            print(f"Skipped {missing_files} pending record(s) because the video files were missing.")
    return count_uploaded


def main():
    schedule_pending_uploads(videos_per_day=2)

if __name__ == "__main__":
    main()
