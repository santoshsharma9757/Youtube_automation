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
from music_downloader import ensure_music_library
from script_generator import ScriptGenerator
from seo_generator import SeoGenerator, SeoPackage
from subtitle_generator import SubtitleGenerator
from tts import TextToSpeechEngine
from upload_all import schedule_pending_uploads
from uploader import YouTubeUploader
from video_downloader import ensure_video_library
from video_generator import VideoGenerator
from moviepy import VideoFileClip, concatenate_videoclips

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
    veo_prompt: bool = False,
    stitch_veo: bool = False,
    deploy_veo: bool = False,
    videos_per_day: int = 3,
) -> list[dict]:
    config = get_config()
    total_count = short_count + long_count

    if stitch_veo:
        LOGGER.info("Stitching manually generated Veo clips...")
        veo_dir = Path("input/veo_clips")
        metadata_file = veo_dir / "metadata.json"
        
        if not metadata_file.exists():
            LOGGER.error("metadata.json not found in %s! Cannot stitch without SEO metadata.", veo_dir)
            return []
            
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        clips_paths = sorted([p for p in veo_dir.glob("*.mp4")])
        
        if not clips_paths:
            LOGGER.error("No .mp4 files found in %s!", veo_dir)
            return []
            
        LOGGER.info("Found %s clips to combine.", len(clips_paths))
        try:
            clips = [VideoFileClip(str(p)) for p in clips_paths]
            final_clip = concatenate_videoclips(clips, method="compose")
            
            output_dir = Path("output/final_videos")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"veo_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            
            LOGGER.info("Rendering combined video...")
            final_clip.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                fps=30,
                threads=4,
                logger=None,
            )
            for c in clips:
                c.close()
            final_clip.close()
            
            metadata["final_video_path"] = str(output_path)
            metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            
            LOGGER.info("Stitching complete! You can preview the final video here: %s", output_path)
            LOGGER.info("When you are ready, run the deploy command: python main.py --deploy-veo")
            
        except Exception as exc:
            LOGGER.error("Failed to stitch Veo clips: %s", exc)
        return []

    if deploy_veo:
        LOGGER.info("Deploying stitched Veo video...")
        veo_dir = Path("input/veo_clips")
        metadata_file = veo_dir / "metadata.json"
        
        if not metadata_file.exists():
            LOGGER.error("metadata.json not found in %s! Cannot deploy without SEO metadata.", veo_dir)
            return []
            
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        if "final_video_path" not in metadata:
            LOGGER.error("Final video path not found in metadata! Please run --stitch-veo first.")
            return []
            
        output_path = Path(metadata["final_video_path"])
        if not output_path.exists():
            LOGGER.error("Final video file not found at %s! Please run --stitch-veo again.", output_path)
            return []
            
        try:
            seo = SeoPackage(
                title=metadata["seo_title"],
                description=metadata["seo_description"],
                tags=metadata["seo_tags"],
                hashtags=metadata.get("seo_tags", [])[:5],
                primary_keyword=metadata.get("seo_tags", [""])[0] if metadata.get("seo_tags") else "video",
                language_code="hi",
                audio_language_code="hi",
            )
            record = {
                "idea_title": metadata.get("seo_title", "Veo Video"),
                "idea": {},
                "script": {"video_type": "short"},
                "seo": asdict(seo),
                "audio_path": "",
                "video_path": str(output_path.resolve()),
                "subtitle_srt": "",
                "subtitle_json": "",
                "uploaded": False,
                "upload_response": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            content_history = read_json(config.content_store)
            content_history.append(record)
            write_json(config.content_store, content_history)
            
            LOGGER.info("Scheduling combined Veo video to YouTube...")
            from upload_all import schedule_pending_uploads
            schedule_pending_uploads(videos_per_day=videos_per_day)
            
            LOGGER.info("Scheduling process complete. Cleaning up %s...", veo_dir)
            # Remove original clips
            clips_paths = sorted([p for p in veo_dir.glob("*.mp4")])
            for p in clips_paths:
                p.unlink()
                
            if "prompt_path" in metadata:
                Path(metadata["prompt_path"]).unlink(missing_ok=True)
            metadata_file.unlink()
            LOGGER.info("Veo deployment finished successfully!")
            
        except Exception as exc:
            LOGGER.error("Failed to deploy Veo video: %s", exc)
        return []

    if total_count < 1 or total_count > 30:
        raise ValueError("Total video count must be between 1 and 30.")

    # ── Auto-populate asset libraries if they are thin ─────────────────────
    try:
        ensure_music_library(min_tracks=8, pixabay_key=config.pixabay_api_key)
    except Exception as _dl_exc:
        LOGGER.warning("Music library check failed (non-fatal): %s", _dl_exc)
    try:
        ensure_video_library(min_local=20, min_bg=8, pexels_key=config.pexels_api_key)
    except Exception as _dl_exc:
        LOGGER.warning("Video library check failed (non-fatal): %s", _dl_exc)

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
    short_visual_index = 0
    current_short_visual_mode = "unknown"

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
            if veo_prompt:
                # Veo Prompt Mode: Skip actual video generation
                veo_data = script_generator.generate_veo_prompt(idea)
                
                veo_dir = Path("output/veo_prompts")
                veo_dir.mkdir(parents=True, exist_ok=True)
                veo_path = veo_dir / f"{base_name}.txt"
                
                # Format perfectly for the user to copy/paste
                clean_prompt = (
                    "🔥 CLIP 1 PROMPT (Copy to Veo):\n"
                    f"{veo_data.get('clip_1_prompt', '')}\n\n"
                    "--------------------------------------------------\n\n"
                    "🔥 CLIP 2 PROMPT (Copy to Veo):\n"
                    f"{veo_data.get('clip_2_prompt', '')}\n\n"
                    "--------------------------------------------------\n\n"
                    "🔥 CLIP 3 PROMPT (Copy to Veo):\n"
                    f"{veo_data.get('clip_3_prompt', '')}\n\n"
                    "--------------------------------------------------\n\n"
                    "🔥 CLIP 4 PROMPT (Copy to Veo):\n"
                    f"{veo_data.get('clip_4_prompt', '')}\n"
                )
                
                veo_path.write_text(clean_prompt, encoding="utf-8")
                LOGGER.info("Saved Veo Prompt to %s", veo_path)
                
                input_dir = Path("input/veo_clips")
                input_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = input_dir / "metadata.json"
                veo_data["prompt_path"] = str(veo_path.resolve())
                metadata_path.write_text(json.dumps(veo_data, indent=2, ensure_ascii=False), encoding="utf-8")
                LOGGER.info("Saved SEO metadata to %s", metadata_path)
                
                record = {
                    "idea_title": idea.title,
                    "idea": asdict(idea),
                    "veo_prompt_path": str(veo_path.resolve()),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                results.append(record)
                continue

            manual_package = build_manual_content(topic) if topic else None
            script = manual_package.script if manual_package else script_generator.generate_script(idea)
            is_long = getattr(idea, "video_type", "short") == "long"
            # Minimum 50s for Shorts (45-60s performs best on YouTube algorithm)
            min_dur = 80 if is_long else 50
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
            if not is_long:
                short_visual_index += 1
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
            "short_visual_mode": current_short_visual_mode,
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
        default=3,
        help="How many videos to schedule per day when using --schedule-upload",
    )
    parser.add_argument("--veo-prompt", action="store_true", help="Generate text prompts for Google Veo instead of rendering videos")
    parser.add_argument("--stitch-veo", action="store_true", help="Combine Veo clips so you can preview the final video before deploying")
    parser.add_argument("--deploy-veo", action="store_true", help="Upload the combined Veo video from --stitch-veo to YouTube")
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
        veo_prompt=args.veo_prompt,
        stitch_veo=args.stitch_veo,
        deploy_veo=args.deploy_veo,
        videos_per_day=args.videos_per_day,
    )
    if args.schedule_upload:
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Scheduled %s pending videos after generation", scheduled)
    LOGGER.info("Pipeline finished with %s generated videos", len(results))


if __name__ == "__main__":
    main()
