import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from config import VIDEO_DIR, get_config
from posting_schedule import get_daily_slots
from seo_generator import SeoPackage
from uploader import YouTubeUploader
from facebook_uploader import FacebookUploader

logging.basicConfig(level=logging.INFO)


def build_fallback_seo(video_path: Path) -> SeoPackage:
    stem = re.sub(r"^\d{8}_\d{6}_", "", video_path.stem)
    title_text = stem.replace("-", " ").replace("_", " ").strip()
    title_text = re.sub(r"\s+", " ", title_text).strip() or "DailyFitX Short"
    title = title_text.title()
    hashtags = [
        "#shorts",
        "#shortsfeed",
        "#fitness",
        "#fitnessmotivation",
        "#fitnessjourney",
        "#healthylifestyle",
        "#DailyFitX",
    ]
    return SeoPackage(
        title=title[:80],
        description=(
            f"{title}.\n\n"
            + " ".join(hashtags)
        ),
        tags=[
            title_text.lower(),
            "fitness shorts",
            "workout motivation",
            "DailyFitX",
            "youtube shorts",
        ],
        hashtags=hashtags,
        primary_keyword=title_text.lower(),
        language_code="en",
        audio_language_code="en",
        content_style="fitness",
    )


def append_orphan_video_records(history: list[dict]) -> int:
    known_paths = {
        str(Path(record["video_path"]).resolve())
        for record in history
        if record.get("video_path")
    }
    appended = 0
    for video_path in sorted(VIDEO_DIR.glob("*.mp4")):
        resolved = str(video_path.resolve())
        if resolved in known_paths:
            continue
        history.append(
            {
                "idea_title": video_path.stem,
                "idea": {
                    "idea_id": video_path.stem,
                    "title": video_path.stem,
                    "angle": "orphan-video-recovery",
                    "hook": "",
                    "topic": "Recovered local upload",
                    "audience_value": "Recovered local upload",
                    "source_prompt": "upload-all-orphan-recovery",
                    "created_at": "",
                },
                "script": {
                    "title": video_path.stem,
                    "hook": "",
                    "problem": "",
                    "insight": "",
                    "solution": "",
                    "cta": "",
                    "full_script": "",
                    "estimated_duration_seconds": 0,
                    "primary_keyword": video_path.stem,
                    "retention_note": "Recovered local video with fallback metadata.",
                },
                "seo": asdict(build_fallback_seo(video_path)),
                "audio_path": "",
                "video_path": str(video_path.resolve()),
                "subtitle_srt": "",
                "subtitle_json": "",
                "uploaded": False,
                "upload_response": None,
                "created_at": "",
                "recovered_for_upload": True,
            }
        )
        known_paths.add(resolved)
        appended += 1
    return appended


def reconcile_recovered_records(history: list[dict]) -> int:
    fixed = 0
    for record in history:
        if not record.get("recovered_for_upload"):
            continue
        if record.get("uploaded"):
            continue
        video_path_raw = record.get("video_path")
        upload_response = record.get("upload_response")
        scheduled_time = record.get("scheduled_time")
        if upload_response and scheduled_time:
            record["uploaded"] = True
            fixed += 1
            continue
        if video_path_raw and not Path(video_path_raw).exists():
            record["uploaded"] = True
            record["local_video_deleted"] = True
            record["skipped_because_missing_after_recovery"] = True
            fixed += 1
    return fixed


def cleanup_local_video(video_path: Path, record: dict) -> None:
    if not video_path.exists():
        return
    try:
        video_path.unlink()
        record["local_video_deleted"] = True
        print(f"Deleted local video: {video_path.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"Uploaded but could not delete local video {video_path.name}: {exc}")


def schedule_pending_uploads(videos_per_day: int = 3) -> int:
    import pytz
    from datetime import datetime, timedelta, time
    config = get_config()
    history_file = config.content_store
    if not history_file.exists():
        print("No content history found.")
        return 0

    history = json.loads(history_file.read_text("utf-8"))
    uploader = YouTubeUploader(config)
    fb_uploader = FacebookUploader(config)
    orphan_count = append_orphan_video_records(history)
    reconciled_count = reconcile_recovered_records(history)
    if orphan_count or reconciled_count:
        history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), "utf-8")
        if orphan_count:
            print(f"Recovered {orphan_count} local video(s) from output/videos for scheduling.")
        if reconciled_count:
            print(f"Reconciled {reconciled_count} recovered record(s) from previous interrupted runs.")
    
    tz = pytz.timezone(config.scheduler_timezone)
    now = datetime.now(tz)
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
        yt_done = record.get("uploaded", False)
        fb_done = record.get("fb_uploaded", False)
        
        # If both platforms are done, skip
        if yt_done and fb_done:
            continue
            
        # If FB isn't configured, and YT is done, skip
        if yt_done and not fb_uploader.is_configured():
            continue

        video_path = Path(record["video_path"])
        if not video_path.exists():
            print(f"File not found for upload: {video_path}")
            missing_files += 1
            continue

        seo = SeoPackage(**record["seo"])
        publish_at_utc = record.get("scheduled_time")

        if not publish_at_utc:
            # Find next slot
            next_slot = None
            temp_date = current_time_pointer.date()
            while next_slot is None:
                video_type = str(record.get("script", {}).get("video_type", "short")).lower()
                if video_type not in {"short", "long"}:
                    video_type = "short"
                slots = get_daily_slots(temp_date.weekday(), videos_per_day, video_type=video_type)
                for s_hour in slots:
                    candidate = tz.localize(datetime.combine(temp_date, time(hour=s_hour)))
                    if candidate > current_time_pointer:
                        next_slot = candidate
                        break
                if next_slot is None: temp_date += timedelta(days=1)

            publish_at_utc = next_slot.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
            record["scheduled_time"] = publish_at_utc
            current_time_pointer = next_slot + timedelta(minutes=10)

        made_progress = False

        if not yt_done:
            print(f"Scheduling '{seo.title}' for YouTube at {publish_at_utc}...")
            try:
                response = uploader.upload_short(video_path, seo, publish_at=publish_at_utc)
                record["uploaded"] = True
                record["upload_response"] = response
                made_progress = True
                print("YouTube scheduled successfully!")
            except Exception as e:
                print(f"Failed to schedule to YouTube for {seo.title}: {e}")

        if not fb_done and fb_uploader.is_configured():
            print(f"Scheduling '{seo.title}' for Facebook at {publish_at_utc}...")
            video_type = str(record.get("script", {}).get("video_type", "short")).lower()
            is_long = (video_type == "long")
            try:
                fb_res = fb_uploader.upload(video_path, seo, publish_at=publish_at_utc, is_long=is_long)
                record["fb_uploaded"] = True
                record["fb_upload_response"] = fb_res
                made_progress = True
                print("Facebook scheduled successfully!")
            except Exception as e:
                print(f"Failed to schedule to Facebook for {seo.title}: {e}")

        if made_progress:
            # Only clean up local video if YouTube is done (or if both are done)
            if record.get("uploaded", False) and (not fb_uploader.is_configured() or record.get("fb_uploaded", False)):
                cleanup_local_video(video_path, record)
            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), "utf-8")
            count_uploaded += 1

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
    schedule_pending_uploads(videos_per_day=3)




if __name__ == "__main__":
    main()
