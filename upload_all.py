import json
import logging
import os
import re
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timedelta, time, timezone
import requests
import pytz
from googleapiclient.discovery import build

ACTIVE_CHANNEL = os.getenv("CHANNEL", "stories").lower().strip()

from config import VIDEO_DIR, get_config
from posting_schedule import get_daily_slots
from kids_seo_generator import KidsSeoPackage as SeoPackage
from uploader import YouTubeUploader
from facebook_uploader import FacebookUploader

logging.basicConfig(level=logging.INFO)


def build_fallback_seo(video_path: Path) -> SeoPackage:
    """Fallback SEO for orphan videos recovered from disk — Wonder Stories TV branding."""
    stem = re.sub(r"^\d{8}_\d{6}_", "", video_path.stem)
    title_text = stem.replace("-", " ").replace("_", " ").strip()
    title_text = re.sub(r"\s+", " ", title_text).strip() or "Wonder Stories TV"
    title = title_text.title()
    hashtags = [
        "#shorts",
        "#WonderStoriesTV",
        "#HindiMoralStory",
        "#BacchonKiKahani",
        "#AnimatedStory",
        "#KidsStory",
    ]
    return SeoPackage(
        title=title[:80],
        description=(
            f"{title}.\n\n"
            + " ".join(hashtags)
        ),
        tags=[
            title_text.lower(),
            "hindi moral story",
            "bacchon ki kahani",
            "wonder stories tv",
            "animated story hindi",
        ],
        hashtags=hashtags,
        primary_keyword=title_text.lower(),
        language_code="hi",
        audio_language_code="hi",
        content_style="family_story",
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
    # 1. Delete final video file
    if video_path.exists():
        try:
            video_path.unlink()
            record["local_video_deleted"] = True
            print(f"Deleted local video: {video_path.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"Uploaded but could not delete local video {video_path.name}: {exc}")

    # 2. Delete input clips folder
    input_folder = Path("input/clips") / video_path.stem
    if input_folder.exists():
        import shutil
        import time
        for _ in range(5):
            try:
                shutil.rmtree(input_folder)
                print(f"Deleted input folder: {input_folder.name}")
                break
            except Exception:
                time.sleep(0.5)

    # 2b. Delete prompts text file
    prompts_file = Path("output/veo_prompts") / f"{video_path.stem}.txt"
    if prompts_file.exists():
        try:
            prompts_file.unlink()
            print(f"Deleted prompts file: {prompts_file.name}")
        except Exception as exc:
            print(f"Could not delete prompts file {prompts_file.name}: {exc}")

    # 3. Delete intermediate generated resources (audio, subtitles)
    for key in ("audio_path", "subtitle_srt", "subtitle_json"):
        path_str = record.get(key)
        if path_str:
            path = Path(path_str)
            if path.exists():
                try:
                    path.unlink()
                    print(f"Deleted intermediate local resource ({key}): {path.name}")
                except Exception as exc:
                    print(f"Could not delete intermediate resource {path.name}: {exc}")


def sync_scheduled_times_from_platforms(history: list[dict], tz, config) -> int:
    """
    Syncs scheduled publish times from Facebook Graph API and YouTube API
    with the local content history file so that local database stays 100% in sync
    with manual scheduling shifts done on the platforms.
    """
    def clean_for_match(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum())
    synced_count = 0
    
    # 1. Sync from Facebook Graph API
    if config.facebook_page_id and config.facebook_access_token:
        try:
            print("Syncing scheduled times from Facebook Graph API...")
            fb_url = f"https://graph.facebook.com/v19.0/{config.facebook_page_id}/scheduled_posts"
            params = {
                "fields": "id,message,scheduled_publish_time",
                "access_token": config.facebook_access_token,
                "limit": 100
            }
            res = requests.get(fb_url, params=params, timeout=15)
            res.raise_for_status()
            fb_data = res.json().get("data", [])
            
            for fb_item in fb_data:
                fb_time_stamp = fb_item.get("scheduled_publish_time")
                fb_message = fb_item.get("message", "")
                if not fb_time_stamp or not fb_message:
                    continue
                
                # Convert Unix timestamp to UTC ISO format string (used in history)
                fb_dt_utc = datetime.fromtimestamp(fb_time_stamp, timezone.utc)
                fb_time_str = fb_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                
                # Try to find matching record in local history
                for record in history:
                    # Match by idea_title or seo title
                    title_to_match = record.get("idea_title", "")
                    seo_title = record.get("seo", {}).get("title", "")
                    
                    match_found = False
                    clean_fb = clean_for_match(fb_message)
                    clean_idea = clean_for_match(title_to_match)
                    clean_seo = clean_for_match(seo_title)
                    
                    if clean_idea and clean_idea in clean_fb:
                        match_found = True
                    elif clean_seo and clean_seo in clean_fb:
                        match_found = True
                    
                    if match_found:
                        old_time = record.get("scheduled_time")
                        if old_time != fb_time_str:
                            record["scheduled_time"] = fb_time_str
                            record["fb_uploaded"] = True
                            record["uploaded"] = True  # Align YouTube to prevent re-uploading
                            synced_count += 1
                            print(f"Sync: Updated '{title_to_match or seo_title}' schedule time to {fb_time_str} (from Facebook)")
        except Exception as exc:
            print(f"Warning: Facebook schedule sync failed: {exc}")
            
    # 2. Sync from YouTube API (if credentials and token are valid)
    try:
        uploader = YouTubeUploader(config)
        token_path = Path(config.youtube_token_file)
        if token_path.exists():
            print("Syncing scheduled times from YouTube API...")
            youtube = build("youtube", "v3", credentials=uploader._load_credentials())
            # Get uploads playlist
            ch_res = youtube.channels().list(part="contentDetails", mine=True).execute()
            uploads_playlist_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            
            # List recent playlist items (last 50 uploads)
            pl_res = youtube.playlistItems().list(
                part="snippet,status",
                playlistId=uploads_playlist_id,
                maxResults=50
            ).execute()
            
            video_ids = []
            for item in pl_res.get("items", []):
                v_id = item["snippet"]["resourceId"]["videoId"]
                video_ids.append(v_id)
                
            if video_ids:
                # Fetch details to get publishAt time for scheduled videos
                v_res = youtube.videos().list(
                    part="snippet,status",
                    id=",".join(video_ids)
                ).execute()
                
                for v_item in v_res.get("items", []):
                    publish_at = v_item.get("status", {}).get("publishAt")
                    if publish_at:
                        # YouTube publishAt comes as '2026-06-04T13:30:00Z'
                        # Normalize to '2026-06-04T13:30:00Z' format
                        yt_time_str = publish_at
                        if ".000Z" in yt_time_str:
                            yt_time_str = yt_time_str.replace(".000", "")
                        
                        yt_title = v_item["snippet"].get("title", "")
                        
                        for record in history:
                            title_to_match = record.get("idea_title", "")
                            seo_title = record.get("seo", {}).get("title", "")
                            
                            match_found = False
                            clean_yt = clean_for_match(yt_title)
                            clean_idea = clean_for_match(title_to_match)
                            clean_seo = clean_for_match(seo_title)
                            
                            if clean_idea and clean_idea in clean_yt:
                                match_found = True
                            elif clean_seo and clean_seo in clean_yt:
                                match_found = True
                                
                            if match_found:
                                old_time = record.get("scheduled_time")
                                if old_time != yt_time_str:
                                    record["scheduled_time"] = yt_time_str
                                    record["uploaded"] = True
                                    synced_count += 1
                                    print(f"Sync: Updated '{title_to_match or seo_title}' schedule time to {yt_time_str} (from YouTube)")
    except Exception as exc:
        print(f"Warning: YouTube schedule sync failed: {exc}")
        
    return synced_count


def schedule_pending_uploads(videos_per_day: int = 3) -> int:
    config = get_config()
    history_file = config.content_store
    if not history_file.exists():
        print("No content history found.")
        return 0

    history = json.loads(history_file.read_text("utf-8"))
    tz = pytz.timezone(config.scheduler_timezone)
    
    # Synchronize scheduled times from Facebook/YouTube before deciding next upload slots
    synced = sync_scheduled_times_from_platforms(history, tz, config)
    
    uploader = YouTubeUploader(config)
    fb_uploader = FacebookUploader(config)
    orphan_count = append_orphan_video_records(history)
    reconciled_count = reconcile_recovered_records(history)
    if orphan_count or reconciled_count or synced:
        history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), "utf-8")
        if synced:
            print(f"Successfully synchronized {synced} scheduled times from online platforms to local history database.")
        if orphan_count:
            print(f"Recovered {orphan_count} local video(s) from output/videos for scheduling.")
        if reconciled_count:
            print(f"Reconciled {reconciled_count} recovered record(s) from previous interrupted runs.")
    
    now = datetime.now(tz)
    count_uploaded = 0
    missing_files = 0
    current_time_pointer = now + timedelta(minutes=30)

    existing_scheduled_times = []
    for record in history:
        # Only treat it as a taken slot if it was actually uploaded successfully on at least one platform
        if not record.get("uploaded", False) and not record.get("fb_uploaded", False):
            continue
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

        v_path_str = record.get("video_path", "")
        if not v_path_str:
            continue
            
        video_path = Path(v_path_str)
        if not video_path.is_file():
            print(f"File not found for upload: {video_path}")
            missing_files += 1
            continue

        seo = SeoPackage.from_dict(record["seo"])
        publish_at_utc = record.get("scheduled_time")
        is_immediate = (publish_at_utc == "IMMEDIATE")

        if not publish_at_utc and not is_immediate:
            # Find next slot
            next_slot = None
            temp_date = current_time_pointer.date()
            while next_slot is None:
                video_type = str(record.get("script", {}).get("video_type", "short")).lower()
                if video_type not in {"short", "long"}:
                    video_type = "short"
                slots = get_daily_slots(temp_date.weekday(), videos_per_day, video_type=video_type, channel=ACTIVE_CHANNEL)
                for s_hour in slots:
                    s_minute = 0
                    candidate = tz.localize(datetime.combine(temp_date, time(hour=s_hour, minute=s_minute)))
                    if candidate > current_time_pointer:
                        next_slot = candidate
                        break
                if next_slot is None: temp_date += timedelta(days=1)

            publish_at_utc = next_slot.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
            record["scheduled_time"] = publish_at_utc
            current_time_pointer = next_slot + timedelta(minutes=10)

        if is_immediate:
            publish_at_utc = None

        made_progress = False

        if not yt_done:
            safe_title = seo.title.encode("ascii", "replace").decode("ascii")
            print(f"Scheduling '{safe_title}' for YouTube at {publish_at_utc}...")
            try:
                response = uploader.upload_short(video_path, seo, publish_at=publish_at_utc)
                record["uploaded"] = True
                record["upload_response"] = response
                made_progress = True
                print("YouTube scheduled successfully!")
            except Exception as e:
                print(f"Failed to schedule to YouTube for {seo.title}: {e}")

        if not fb_done and fb_uploader.is_configured():
            safe_title = seo.title.encode("ascii", "replace").decode("ascii")
            print(f"Scheduling '{safe_title}' for Facebook at {publish_at_utc}...")
            video_type = str(record.get("script", {}).get("video_type", "short")).lower()
            # is_long = True for all non-short videos (mini, long, series) — only short goes as Reels
            is_long = video_type != "short"
            # Pass the pre-generated facebook_description if available in the record
            fb_desc = record.get("seo", {}).get("facebook_description", "")
            try:
                fb_res = fb_uploader.upload(
                    video_path,
                    seo,
                    publish_at=publish_at_utc,
                    is_long=is_long,
                    facebook_description=fb_desc,
                )
                record["fb_uploaded"] = True
                record["fb_upload_response"] = fb_res
                made_progress = True
                print(f"Facebook {'Video' if is_long else 'Reel'} scheduled successfully!")
            except Exception as e:
                print(f"Failed to schedule to Facebook for {seo.title}: {e}")

        if made_progress:
            # Only clean up local video if YouTube is done (or if both are done)
            if record.get("uploaded", False) and (not fb_uploader.is_configured() or record.get("fb_uploaded", False)):
                cleanup_local_video(video_path, record)
            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), "utf-8")
            count_uploaded += 1
        else:
            # If both failed, reset scheduled_time so it doesn't block future slots or get saved as an occupied date
            record["scheduled_time"] = None

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
