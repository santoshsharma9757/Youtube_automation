from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from config import AUDIO_DIR, DATA_DIR, VIDEO_DIR, get_config
from idea_generator import IdeaGenerator, VideoIdea, canonicalize_text, canonicalize_title
from manual_content import build_manual_content
from script_generator import ScriptGenerator
from seo_generator import SeoGenerator
from subtitle_generator import SubtitleGenerator
from tts import TextToSpeechEngine
from upload_all import schedule_pending_uploads
from uploader import YouTubeUploader
from video_generator import VideoGenerator


LOGGER = logging.getLogger(__name__)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value[:80] or "video"


def read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: list[dict]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cleanup_local_video(video_path: Path, record: dict | None = None) -> None:
    if not video_path.exists():
        return
    try:
        video_path.unlink()
        LOGGER.info("Deleted local video after successful upload: %s", video_path)
        if record is not None:
            record["local_video_deleted"] = True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not delete local video '%s': %s", video_path, exc)


def select_fresh_ideas(
    generator: IdeaGenerator,
    count: int,
    theme: str | None = None,
    language: str = "hinglish",
) -> list[VideoIdea]:
    ideas = generator.save_new_ideas(
        generator.generate_ideas(count=60, theme=theme, language=language)
    )
    if len(ideas) < count:
        LOGGER.warning("Only %s fresh ideas available for requested count=%s", len(ideas), count)
    return ideas[:count]


def run_pipeline(
    short_count: int = 1,
    long_count: int = 0,
    upload: bool = False,
    topic: str | None = None,
    theme: str | None = None,
    language: str = "hinglish",
    test_long: bool = False,
    use_pexels: bool = False,
) -> list[dict]:
    config = get_config()
    config.use_pexels_for_shorts = use_pexels or bool(config.pexels_api_key)
    total_count = short_count + long_count
    if total_count < 1 or total_count > 30:
        raise ValueError("Total video count must be between 1 and 30.")

    idea_generator = IdeaGenerator(config)
    script_generator = ScriptGenerator(config)
    tts_engine = TextToSpeechEngine(config)
    subtitle_generator = SubtitleGenerator(config)
    video_generator = VideoGenerator(config)
    seo_generator = SeoGenerator(config)
    uploader = YouTubeUploader(config)

    content_history = read_json(config.content_store)
    processed_signatures = {
        (
            canonicalize_title(item.get("idea_title", "")),
            canonicalize_text(item.get("idea", {}).get("topic", "")),
            canonicalize_text(item.get("idea", {}).get("hook", "")),
        )
        for item in content_history
    }
    results: list[dict] = []

    if topic:
        manual_package = build_manual_content(topic)
        if manual_package:
            ideas_to_process = [
                VideoIdea(
                    idea_id=slugify(manual_package.script.title),
                    title=manual_package.script.title,
                    angle=topic,
                    hook=manual_package.script.hook,
                    topic=topic,
                    audience_value="Manual topic-driven explainer content",
                    source_prompt="manual-topic",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    language_preference=language,
                    theme_hint=theme or topic,
                )
            ]
        else:
            ideas_to_process = [
                VideoIdea(
                    idea_id=slugify(topic),
                    title=topic.strip(),
                    angle=topic,
                    hook="",
                    topic=topic,
                    audience_value="Deliver a beautiful, high-retention Hindi-English short on this exact topic",
                    source_prompt="manual-topic-script-generator",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    language_preference=language,
                    theme_hint=theme or topic,
                )
            ]
    else:
        ideas_to_process = select_fresh_ideas(idea_generator, total_count, theme=theme, language=language)

    if not topic and long_count > 0:
        actual_long_count = min(long_count, len(ideas_to_process))
        for i in range(len(ideas_to_process) - actual_long_count, len(ideas_to_process)):
            ideas_to_process[i] = replace(ideas_to_process[i], video_type="long")
    
    if test_long and ideas_to_process:
        ideas_to_process[0] = replace(ideas_to_process[0], video_type="long")

    for idea in ideas_to_process:
        idea_signature = (
            canonicalize_title(idea.title),
            canonicalize_text(idea.topic),
            canonicalize_text(idea.hook),
        )
        if not topic and idea_signature in processed_signatures:
            LOGGER.info("Skipping already produced content for title '%s'", idea.title)
            continue

        base_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slugify(idea.title)}"
        try:
            manual_package = build_manual_content(topic) if topic else None
            script = manual_package.script if manual_package else script_generator.generate_script(idea)
            is_long = getattr(idea, "video_type", "short") == "long"
            min_dur = 80 if is_long else 31
            script = replace(
                script,
                full_script=script_generator._extend_script_if_needed(script.full_script, idea),
                estimated_duration_seconds=max(min_dur, int(script.estimated_duration_seconds)),
            )
            audio_path = tts_engine.synthesize(script.full_script, AUDIO_DIR / f"{base_name}.mp3")
            if manual_package:
                manual_segments = [
                    {"start": segment.start, "end": segment.end, "text": segment.text}
                    for segment in manual_package.segments
                ]
                subtitles = subtitle_generator.generate_from_segments(manual_segments, base_name)
            else:
                subtitles = subtitle_generator.generate(audio_path, base_name, script=script)
            video_path = video_generator.create_video(
                script=script,
                audio_path=audio_path,
                subtitles=subtitles,
                output_path=VIDEO_DIR / f"{base_name}.mp4",
            )
            seo = manual_package.seo if manual_package else seo_generator.generate(script)
            upload_response = uploader.upload_short(video_path, seo) if upload else None
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Pipeline failed for idea '%s': %s", idea.title, exc)
            continue

        record = {
            "idea_title": idea.title,
            "idea": asdict(idea),
            "script": asdict(script),
            "seo": asdict(seo),
            "audio_path": str(audio_path),
            "video_path": str(video_path),
            "subtitle_srt": str(subtitles.srt_path),
            "subtitle_json": str(subtitles.json_path),
            "uploaded": bool(upload_response),
            "upload_response": upload_response,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if upload_response:
            cleanup_local_video(video_path, record)
        content_history.append(record)
        processed_signatures.add(idea_signature)
        results.append(record)
        LOGGER.info("Finished content package for '%s'", idea.title)

    write_json(config.content_store, content_history)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated YouTube Shorts generation pipeline")
    parser.add_argument(
        "--count",
        nargs="?",
        const=2,
        default=2,
        type=int,
        help="Number of short videos to generate. If passed without a value, defaults to 2.",
    )
    parser.add_argument(
        "--long-count",
        type=int,
        default=0,
        help="Number of long videos to generate.",
    )
    parser.add_argument("--use-pexels", action="store_true", help="Use Pexels API for short videos instead of local files")
    parser.add_argument("--upload", action="store_true", help="Upload generated videos to YouTube")
    parser.add_argument("--schedule", action="store_true", help="Start APScheduler instead of running once")
    parser.add_argument("--topic", type=str, help="Create one manual topic-driven Short")
    parser.add_argument("--theme", type=str, help="Bias automatic ideas toward a niche or topic family")
    parser.add_argument(
        "--language",
        type=str,
        choices=["english", "hindi", "hinglish"],
        default="hinglish",
        help="Preferred output language style for auto-generated videos",
    )
    parser.add_argument(
        "--schedule-upload",
        action="store_true",
        help="After generation, schedule all pending local videos for future YouTube publish slots",
    )
    parser.add_argument(
        "--videos-per-day",
        type=int,
        default=2,
        help="How many videos to schedule per day when using --schedule-upload",
    )
    parser.add_argument("--test-long", action="store_true", help="Generate a long video for testing")
    parser.add_argument(
        "legacy_command",
        nargs="?",
        choices=["count"],
        help=argparse.SUPPRESS,
    )
    parser.add_argument("legacy_value", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.legacy_command == "count":
        if args.legacy_value is None:
            args.count = 2
            return args
        try:
            args.count = int(args.legacy_value)
        except ValueError as exc:
            raise SystemExit("`count` must be followed by a whole number.") from exc

    return args


def main() -> None:
    args = parse_args()
    if args.schedule:
        from scheduler import start_scheduler

        start_scheduler(get_config())
        return

    results = run_pipeline(
        short_count=args.count,
        long_count=args.long_count,
        upload=args.upload,
        topic=args.topic,
        theme=args.theme,
        language=args.language,
        test_long=args.test_long,
        use_pexels=args.use_pexels,
    )
    if args.schedule_upload:
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Scheduled %s pending videos after generation", scheduled)
    LOGGER.info("Pipeline finished with %s generated videos", len(results))


if __name__ == "__main__":
    main()
