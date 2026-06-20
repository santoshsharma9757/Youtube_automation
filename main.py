from __future__ import annotations

import argparse
import json
import logging
import sys
import re
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from config import AUDIO_DIR, DATA_DIR, VIDEO_DIR, get_config
from upload_all import schedule_pending_uploads
from uploader import YouTubeUploader

LOGGER = logging.getLogger(__name__)


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


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


# ═══════════════════════════════════════════════════════════════════════════════
#  WONDER STORIES TV  –  Chintu Stories Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_kids_pipeline(
    short_count: int = 1,
    long_count: int = 0,
    upload: bool = False,
    videos_per_day: int = 1,
    kids_mode: str = "veo",
    made_for_kids: bool | None = None,
    video_format: str | None = None,
    category: str | None = None,
    topic: str | None = None,
    no_voice: bool = False,
    local_tts: bool = False,
) -> list[dict]:
    """
    Wonder Stories TV – AI Kids Animation pipeline:
      1. Generate story ideas (Chintu + magical element + moral)
      2. LLM generates a 4-scene (Short) or 8-scene (Long) story JSON plan
      3. Saves prompts to prompts.txt and plan/metadata.json to input/clips/{base_name}/
      4. Waits for user to place manually generated videos/images
      5. Synthesizes Edge TTS audio dynamically
      6. Assembles the final video (subtitles, transitions, etc.)
      7. Uploads to YouTube + Facebook
    """
    from kids_idea_generator import KidsIdeaGenerator, KidsStoryIdea
    from kids_story_generator import KidsStoryGenerator
    from kids_tts import KidsTTSEngine
    from kids_video_assembler import KidsVideoAssembler
    from kids_seo_generator import KidsSeoGenerator

    config = get_config()

    kids_ideas_store   = config.ideas_store
    kids_content_store = config.content_store

    idea_gen    = KidsIdeaGenerator(config)
    story_gen   = KidsStoryGenerator(config)
    tts_engine  = KidsTTSEngine(config, force_local=local_tts)
    assembler   = KidsVideoAssembler(config)
    seo_gen     = KidsSeoGenerator(config)
    yt_uploader = YouTubeUploader(config)

    content_history: list[dict] = read_json(kids_content_store)
    used_titles = {item.get("idea_title", "").lower() for item in content_history}
    results: list[dict] = []

    is_kids = made_for_kids if made_for_kids is not None else False

    # Determine formats to generate
    ideas_to_gen = []
    if video_format:
        count = short_count if short_count > 0 else 1
        ideas_to_gen.append((video_format, count))
    else:
        if short_count > 0:
            ideas_to_gen.append(("short", short_count))
        if long_count > 0:
            ideas_to_gen.append(("long", long_count))

    all_ideas = []
    if topic:
        from story_topics import STORY_TOPIC_BANK
        import uuid
        matched_seed = None
        for seed in STORY_TOPIC_BANK:
            seed_title = seed["title"]
            if topic.lower() in seed_title.lower():
                matched_seed = seed
                break

        if matched_seed:
            if video_format:
                fmt_name = video_format
            elif long_count > 0:
                fmt_name = "long"
            elif short_count > 0:
                fmt_name = "short"
            else:
                fmt_name = matched_seed.get("format", "short")
            title = matched_seed["title"]
            adult_hook_text = matched_seed.get("adult_hook", "")
            kids_hook_text  = matched_seed.get("kids_hook", "")

            idea = KidsStoryIdea(
                idea_id=str(uuid.uuid4()),
                title=title,
                bad_habit=matched_seed.get("bad_habit", ""),
                bad_habit_hindi=matched_seed.get("bad_habit_hindi", ""),
                magical_element=(
                    ""
                    if (category or matched_seed.get("category", "")) in {"real_life", "family_funny"}
                    else matched_seed.get("magical_element", "")
                ),
                moral=matched_seed.get("moral", ""),
                moral_hindi=matched_seed.get("moral_hindi", ""),
                angle=matched_seed.get("angle", "Moral Story"),
                topic=matched_seed.get("topic", ""),
                audience_value=matched_seed.get("audience_value", adult_hook_text),
                source_prompt="static-topic-force",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=fmt_name,
                category=category or matched_seed.get("category", "magical_adventure"),
                adult_hook=adult_hook_text,
                kids_hook=kids_hook_text,
                made_for_kids=is_kids,
            )
            idea_gen.save_new_ideas([idea], ideas_store=kids_ideas_store)
            all_ideas = [idea]
        else:
            LOGGER.error("Forced topic '%s' not found in STORY_TOPIC_BANK!", topic)
            return []
    else:
        for fmt_name, count in ideas_to_gen:
            raw_ideas = idea_gen.generate_ideas(
                count=count * 3,
                video_type=fmt_name,
                ideas_store=kids_ideas_store,
                made_for_kids=is_kids,
                category=category,
            )
            saved    = idea_gen.save_new_ideas(raw_ideas, ideas_store=kids_ideas_store)
            selected = [i for i in saved if i.title.lower() not in used_titles][:count]
            if category:
                selected = [replace(i, category=category) for i in selected]
            all_ideas.extend(selected)

    for idea in all_ideas:
        LOGGER.info("Processing story: '%s' (type=%s)", idea.title, idea.video_type)

        try:
            plan = story_gen.generate_story(idea, kids_mode=kids_mode)
            
            clean_title = plan.story_metadata.get("title", idea.title)
            base_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slugify(clean_title)}"

            folder_path = Path("input/clips") / base_name
            folder_path.mkdir(parents=True, exist_ok=True)

            # Build prompt text per scene
            clean_prompts = []
            for scene in plan.scenes:
                num      = scene["scene_number"]
                gen_type = scene["generation_type"]
                expected = f"{num}.mp4" if gen_type == "AI_VIDEO" else f"{num}_image.png"
                clean_prompts.append(
                    f"🔥 SCENE {num} - {gen_type} (Expected file: {expected})\n"
                    f"Voiceover (Hindi): {scene.get('voiceover_hindi', '')}\n"
                    f"Prompt:\n{scene.get('ai_prompt', '')}\n"
                    f"--------------------------------------------------\n"
                )

            prompts_text = "\n".join(clean_prompts)

            # Append thumbnail generation prompts for long videos
            thumb_title_dev = plan.story_metadata.get("thumbnail_title_devanagari")
            thumb_prompt = plan.story_metadata.get("thumbnail_prompt")
            if idea.video_type == "long" and thumb_title_dev and thumb_prompt:
                thumbnail_section = (
                    f"\n\n==================================================\n"
                    f"🎨 THUMBNAIL GENERATION (Expected file: thumbnail.png)\n"
                    f"==================================================\n"
                    f"Suggested Text on Thumbnail (Hindi Devanagari): {thumb_title_dev}\n"
                    f"Prompt:\n{thumb_prompt}\n"
                    f"--------------------------------------------------\n"
                )
                prompts_text += thumbnail_section

            seo = seo_gen.generate(idea, plan)
            if made_for_kids is not None:
                seo.made_for_kids = made_for_kids

            # Append YouTube/FB metadata to the prompt text file for easy copy-pasting
            youtube_section = (
                f"\n\n==================================================\n"
                f"📺 UPLOAD METADATA (YouTube & Facebook)\n"
                f"==================================================\n"
                f"▶ YouTube Title:\n{seo.title}\n\n"
                f"▶ YouTube Description:\n{seo.description}\n\n"
                f"▶ Tags:\n{', '.join(seo.tags)}\n\n"
                f"▶ Hashtags:\n{' '.join(seo.hashtags)}\n\n"
                f"▶ Facebook Description:\n{getattr(seo, 'facebook_description', seo.description)}\n"
                f"--------------------------------------------------\n"
            )
            prompts_text += youtube_section

            prompts_dir = Path("output/veo_prompts")
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompts_file_path = prompts_dir / f"{base_name}.txt"
            prompts_file_path.write_text(prompts_text, encoding="utf-8")
            (folder_path / "plan.json").write_text(plan.raw_json, encoding="utf-8")

            # Pre-synthesize TTS for image mode
            if kids_mode != "veo" and not no_voice:
                for scene in plan.scenes:
                    text = scene.get("voiceover_hindi", "").strip()
                    if text:
                        try:
                            tts_engine.synthesize_scene(
                                text, folder_path / f"scene_{scene['scene_number']}.mp3"
                            )
                        except Exception as e:
                            LOGGER.warning("TTS pre-synth failed for scene %s: %s", scene["scene_number"], e)

            metadata = {
                "title":                seo.title,
                "description":          seo.description,
                "tags":                 seo.tags,
                "hashtags":             seo.hashtags,
                "primary_keyword":      seo.primary_keyword,
                "language_code":        seo.language_code,
                "audio_language_code":  seo.audio_language_code,
                "content_style":        seo.content_style,
                "kids_mode":            kids_mode,
                "idea_as_dict":         asdict(idea),
                "made_for_kids":        seo.made_for_kids,
                "facebook_description": getattr(seo, "facebook_description", ""),
            }
            (folder_path / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            safe_print(f"\n==================================================")
            safe_print(f"[PROMPTS GENERATED FOR: {idea.title}]")
            safe_print(f"==================================================")
            safe_print(prompts_text)
            safe_print(f"Prompts saved → {prompts_file_path.resolve()}")
            safe_print(f"Plan saved    → {folder_path.resolve()}")
            safe_print(f"==================================================\n")

            record = {
                "idea_title":    idea.title,
                "idea":          asdict(idea),
                "story_plan":    json.loads(plan.raw_json),
                "seo":           asdict(seo),
                "audio_path":    "",
                "video_path":    "",
                "subtitle_srt":  "",
                "subtitle_json": "",
                "uploaded":      False,
                "upload_response": None,
                "channel":       "kids",
                "created_at":    datetime.now(timezone.utc).isoformat(),
                "script":        {"video_type": idea.video_type, "title": idea.title},
            }

            existing_idx = next(
                (i for i, r in enumerate(content_history) if r.get("idea_title") == idea.title),
                None,
            )
            if existing_idx is not None:
                content_history[existing_idx] = record
            else:
                content_history.append(record)

            used_titles.add(idea.title.lower())
            results.append(record)
            LOGGER.info("Prompts and metadata saved for '%s'", idea.title)

        except Exception as exc:
            LOGGER.exception("Pipeline failed for '%s': %s", idea.title, exc)
            continue

    write_json(kids_content_store, content_history)
    return results


# ───────────────────────────────────────────────────────────────────────────────
#  STITCH  –  assemble manually placed clips into final video
# ───────────────────────────────────────────────────────────────────────────────

def run_stitch() -> list[dict]:
    """Scans input/clips/ for completed folders and assembles final videos."""
    from kids_tts import KidsTTSEngine
    from kids_video_assembler import KidsVideoAssembler
    from kids_idea_generator import KidsStoryIdea
    from kids_story_generator import KidsStoryPlan
    from kids_seo_generator import KidsSeoPackage

    config = get_config()
    tts_engine = KidsTTSEngine(config)
    assembler  = KidsVideoAssembler(config)

    kids_content_store = config.content_store
    content_history    = read_json(kids_content_store)

    folders = sorted(
        [d for d in Path("input/clips").iterdir() if d.is_dir() and d.name != "temp_audio"]
    ) if Path("input/clips").exists() else []

    if not folders:
        LOGGER.info("No story folders found in input/clips/.")
        return []

    for folder in folders:
        plan_file = folder / "plan.json"
        meta_file = folder / "metadata.json"
        if not plan_file.exists() or not meta_file.exists():
            LOGGER.warning("Skipping '%s': plan.json or metadata.json missing.", folder.name)
            continue

        try:
            plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
            meta_data = json.loads(meta_file.read_text(encoding="utf-8"))

            # Verify all scene files are present
            missing_files = []
            for s in plan_data.get("scenes", []):
                num      = s["scene_number"]
                gen_type = s["generation_type"]
                if gen_type == "AI_VIDEO":
                    if not any((folder / f"{num}{ext}").exists() for ext in [".mp4", ".mov", ".avi"]):
                        missing_files.append(f"{num}.mp4")
                else:
                    valid_names = [
                        f"{num}_image.png", f"{num}_image.jpg", f"{num}_image.jpeg", f"{num}_image.webp",
                        f"{num}.png", f"{num}.jpg", f"{num}.jpeg", f"{num}.webp"
                    ]
                    found = any((folder / p).exists() for p in valid_names)
                    if not found:
                        missing_files.append(f"{num}.png/jpg")

            if missing_files:
                LOGGER.info("Folder '%s' not ready – missing images for scenes: %s", folder.name, missing_files)
                continue

            LOGGER.info("Stitching '%s'…", folder.name)

            idea_dict = meta_data.get("idea_as_dict", {})
            idea = KidsStoryIdea(
                idea_id=idea_dict.get("idea_id", ""),
                title=idea_dict.get("title", ""),
                bad_habit=idea_dict.get("bad_habit", ""),
                bad_habit_hindi=idea_dict.get("bad_habit_hindi", ""),
                magical_element=idea_dict.get("magical_element", ""),
                moral=idea_dict.get("moral", ""),
                moral_hindi=idea_dict.get("moral_hindi", ""),
                angle=idea_dict.get("angle", ""),
                topic=idea_dict.get("topic", ""),
                audience_value=idea_dict.get("audience_value", ""),
                source_prompt=idea_dict.get("source_prompt", ""),
                created_at=idea_dict.get("created_at", ""),
                video_type=idea_dict.get("video_type", "short"),
                language=idea_dict.get("language", "hindi"),
                category=idea_dict.get("category", "magical_adventure"),
                adult_hook=idea_dict.get("adult_hook", ""),
                kids_hook=idea_dict.get("kids_hook", ""),
            )

            plan = KidsStoryPlan(
                story_metadata=plan_data["story_metadata"],
                scenes=plan_data["scenes"],
                audio_effects_config=plan_data.get("audio_effects_config", {}),
                raw_json=json.dumps(plan_data),
            )

            video_path = VIDEO_DIR / f"{folder.name}.mp4"
            assembler.assemble_from_folder(
                input_dir=folder,
                plan=plan,
                tts_engine=tts_engine,
                idea=idea,
                output_path=video_path,
            )

            record = {
                "idea_title":    idea.title,
                "idea":          asdict(idea),
                "story_plan":    plan_data,
                "seo": {
                    "title":                meta_data["title"],
                    "description":          meta_data["description"],
                    "tags":                 meta_data["tags"],
                    "hashtags":             meta_data["hashtags"],
                    "primary_keyword":      meta_data["primary_keyword"],
                    "language_code":        meta_data["language_code"],
                    "audio_language_code":  meta_data["audio_language_code"],
                    "content_style":        meta_data["content_style"],
                    "made_for_kids":        meta_data.get("made_for_kids", False),
                    "facebook_description": meta_data.get("facebook_description", ""),
                },
                "audio_path":    "",
                "video_path":    str(video_path.resolve()),
                "subtitle_srt":  "",
                "subtitle_json": "",
                "uploaded":      False,
                "upload_response": None,
                "channel":       "kids",
                "created_at":    datetime.now(timezone.utc).isoformat(),
                "script":        {"video_type": idea.video_type, "title": idea.title},
            }

            existing_idx = next(
                (i for i, r in enumerate(content_history) if r.get("idea_title") == idea.title),
                None,
            )
            if existing_idx is not None:
                content_history[existing_idx] = record
            else:
                content_history.append(record)

            write_json(kids_content_store, content_history)
            LOGGER.info("Stitched '%s' → %s", folder.name, video_path)

        except Exception as e:
            LOGGER.exception("Failed to process folder '%s': %s", folder.name, e)

    return []


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wonder Stories TV – Chintu Stories automation pipeline"
    )
    parser.add_argument("--count", nargs="?", const=1, default=1, type=int,
                        help="Number of short videos to generate (default: 1).")
    parser.add_argument("--long-count", type=int, default=0,
                        help="Number of long videos to generate.")
    parser.add_argument("--short", action="store_true",
                        help="Force short format (sets long-count to 0).")
    parser.add_argument("--long", action="store_true",
                        help="Force long format (sets short count to 0).")
    parser.add_argument("--upload", action="store_true",
                        help="Upload / schedule generated videos to YouTube + Facebook.")
    parser.add_argument("--schedule", action="store_true",
                        help="Start APScheduler (runs daily at 2:30 PM IST).")
    parser.add_argument("--topic", type=str,
                        help="Force a specific story topic from STORY_TOPIC_BANK (partial title match).")
    parser.add_argument("--schedule-upload", action="store_true",
                        help="After generation, schedule all pending local videos.")
    parser.add_argument("--videos-per-day", type=int, default=1,
                        help="How many videos to schedule per day (default: 1).")
    parser.add_argument("--stitch", "--stitch-kids", action="store_true", dest="stitch_kids",
                        help="Stitch manually placed video/image clips into final video.")
    parser.add_argument("--deploy", "--deploy-kids", action="store_true", dest="deploy_kids",
                        help="Schedule stitched videos sitting in output/final_videos/.")
    parser.add_argument("--image", action="store_true",
                        help="Generate image-based story (4 image scenes, ~30s).")
    parser.add_argument("--no-voice", action="store_true",
                        help="Skip generating voiceovers/TTS files during prompt generation to save costs.")
    parser.add_argument("--local-tts", action="store_true",
                        help="Use local Edge TTS only (skip ElevenLabs). Free, unlimited — ideal for testing.")
    parser.add_argument("--children", "--kids", action="store_true", dest="children",
                        help="Mark video as 'Made for Kids' in YouTube metadata.")
    parser.add_argument("--normal", action="store_true", dest="normal",
                        help="Mark video as 'Not Made for Kids' in YouTube metadata.")
    parser.add_argument("--format", type=str, choices=["short", "long"],
                        default=None, help="Video format: short | long.")
    parser.add_argument("--category", type=str, choices=[
                            "magical_adventure", "mythology", "dadi_kahani",
                            "real_life", "family_funny", "animal_tales",
                            "mystery", "seasonal", "horror",
                        ], default=None, help="Story category.")

    args = parser.parse_args()

    if args.long:
        args.long_count = args.count
        args.count = 0
    elif args.short:
        args.long_count = 0

    return args


def main() -> None:
    args = parse_args()
    config = get_config()
    LOGGER.info("Wonder Stories TV pipeline starting…")

    # ── Scheduler ──────────────────────────────────────────────────────────────
    if args.schedule:
        from scheduler import start_scheduler
        start_scheduler(config)
        return

    # ── Stitch manually placed clips ───────────────────────────────────────────
    if args.stitch_kids:
        run_stitch()
        return

    # ── Deploy / schedule ──────────────────────────────────────────────────────
    if args.deploy_kids or (
        args.upload and not any(arg in sys.argv for arg in ["--count", "--long-count"])
    ):
        LOGGER.info("Scheduling stitched videos for upload…")
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Scheduled %s video(s).", scheduled)
        return

    # ── Determine made_for_kids override ───────────────────────────────────────
    cli_made_for_kids: bool | None = None
    if args.children:
        cli_made_for_kids = True
    elif args.normal:
        cli_made_for_kids = False

    # ── Generate ───────────────────────────────────────────────────────────────
    results = run_kids_pipeline(
        short_count=args.count,
        long_count=args.long_count,
        upload=args.upload,
        videos_per_day=args.videos_per_day,
        kids_mode="images" if args.image else "veo",
        made_for_kids=cli_made_for_kids,
        video_format=args.format,
        category=args.category,
        topic=args.topic,
        no_voice=args.no_voice,
        local_tts=args.local_tts,
    )

    if args.schedule_upload:
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Scheduled %s pending video(s) after generation.", scheduled)

    LOGGER.info("Pipeline finished — %s story/stories generated.", len(results))


if __name__ == "__main__":
    main()
