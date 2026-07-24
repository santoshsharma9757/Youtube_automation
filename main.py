from __future__ import annotations

import argparse
import json
import logging
import sys
import re
from dataclasses import asdict
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


CATEGORY_ALIASES = {
    "bagwan_stories": "bhagwan_stories",
}


def normalize_story_category(category: str | None) -> str | None:
    if category is None:
        return None
    return CATEGORY_ALIASES.get(category, category)


# ═══════════════════════════════════════════════════════════════════════════════
#  WONDER STORIES TV  –  Viral Hindi Stories Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_stories_pipeline(
    short_count: int = 1,
    long_count: int = 0,
    upload: bool = False,
    videos_per_day: int = 1,
    mode: str = "image",           # "image" | "video"
    category: str | None = None,
    topic: str | None = None,
    no_voice: bool = False,
    local_tts: bool = False,
) -> list[dict]:
    """
    Wonder Stories TV – Viral Hindi Stories Pipeline:
      1. Generate story ideas (Mystery, Horror, Thriller, Crime, Karma, etc.)
      2. LLM generates complete Hindi script + scene image prompts
      3. Script saved → ElevenLabs Raunak TTS voiceover synthesized
      4. Scene image prompts saved for manual generation
      5. User places images → Stitch (--stitch) → Upload (--deploy)
    """
    from story_idea_generator import IdeaGenerator, StoryIdea
    from story_generator import StoryGenerator
    from tts_engine import TTSEngine
    from video_assembler import VideoAssembler
    from seo_generator import SeoGenerator

    config = get_config()
    category = normalize_story_category(category)

    ideas_store   = config.ideas_store
    content_store = config.content_store

    idea_gen   = IdeaGenerator(config)
    story_gen  = StoryGenerator(config)
    tts_engine = TTSEngine(config, force_local=local_tts)
    assembler  = VideoAssembler(config)
    seo_gen    = SeoGenerator(config)
    yt_uploader = YouTubeUploader(config)

    content_history: list[dict] = read_json(content_store)
    used_titles = {item.get("idea_title", "").lower() for item in content_history}
    results: list[dict] = []

    # Determine formats to generate
    ideas_to_gen = []
    if short_count > 0:
        ideas_to_gen.append(("short", short_count))
    if long_count > 0:
        ideas_to_gen.append(("long", long_count))

    all_ideas: list[StoryIdea] = []

    if topic:
        from story_topics import STORY_TOPIC_BANK
        import uuid
        matched_seed = None
        for seed in STORY_TOPIC_BANK:
            if topic.lower() in seed["title"].lower():
                matched_seed = seed
                break

        if matched_seed:
            fmt_name = "long" if long_count > 0 else "short"
            idea = StoryIdea(
                idea_id=str(uuid.uuid4()),
                title=matched_seed["title"],
                hook=matched_seed.get("hook", ""),
                hook_hindi=matched_seed.get("hook_hindi", ""),
                core_conflict=matched_seed.get("core_conflict", ""),
                twist=matched_seed.get("twist", ""),
                moral=matched_seed.get("moral", ""),
                moral_hindi=matched_seed.get("moral_hindi", ""),
                angle=matched_seed.get("angle", "Story"),
                topic=matched_seed.get("topic", ""),
                audience_hook=matched_seed.get("audience_hook", ""),
                source_prompt="static-topic-force",
                created_at=datetime.now(timezone.utc).isoformat(),
                video_type=fmt_name,
                category=normalize_story_category(category or matched_seed.get("category", "mystery_stories")) or "mystery_stories",
            )
            idea_gen.save_new_ideas([idea], ideas_store=ideas_store)
            all_ideas = [idea]
        else:
            LOGGER.error("Forced topic '%s' not found in STORY_TOPIC_BANK!", topic)
            return []
    else:
        for fmt_name, count in ideas_to_gen:
            if category is not None:
                raw_ideas = idea_gen.generate_ideas(
                    count=count * 3,
                    video_type=fmt_name,
                    ideas_store=ideas_store,
                    category=category,
                )
                saved    = idea_gen.save_new_ideas(raw_ideas, ideas_store=ideas_store)
                selected = [i for i in saved if i.title.lower() not in used_titles][:count]
                all_ideas.extend(selected)
            else:
                # Enforce 50/50 split on the actually selected ideas
                import random
                insp_cats = ["karma_stories", "moral_stories", "real_life_facts", "bhagwan_stories"]
                susp_cats = ["horror_stories", "mystery_stories", "suspense_stories", "crime_stories", "psychological", "thriller_stories", "shocking_facts", "dark_facts"]
                
                if count == 1:
                    target_cats = [random.choice(insp_cats) if random.random() < 0.5 else random.choice(susp_cats)]
                else:
                    n_insp = count // 2
                    n_susp = count - n_insp
                    if count % 2 != 0 and random.random() < 0.5:
                        n_insp, n_susp = n_susp, n_insp
                    
                    target_cats = []
                    for _ in range(n_insp):
                        target_cats.append(random.choice(insp_cats))
                    for _ in range(n_susp):
                        target_cats.append(random.choice(susp_cats))
                    random.shuffle(target_cats)
                
                # Generate specifically for each target category slot
                for target_cat in target_cats:
                    raw_ideas = idea_gen.generate_ideas(
                        count=3,
                        video_type=fmt_name,
                        ideas_store=ideas_store,
                        category=target_cat,
                    )
                    saved = idea_gen.save_new_ideas(raw_ideas, ideas_store=ideas_store)
                    selected = [i for i in saved if i.title.lower() not in used_titles]
                    if not selected:
                        selected = [i for i in raw_ideas if i.title.lower() not in used_titles]
                    
                    if selected:
                        all_ideas.append(selected[0])
                    else:
                        all_ideas.append(raw_ideas[0])

    for idea in all_ideas:
        effective_mode = mode
        if idea.video_type == "long" and mode == "video":
            effective_mode = "image"
            LOGGER.warning("Long video-to-video is disabled; using image mode for '%s'.", idea.title)

        LOGGER.info("Processing story: '%s' (type=%s, mode=%s)", idea.title, idea.video_type, effective_mode)

        try:
            plan = story_gen.generate_story(idea, mode=effective_mode)

            clean_title = plan.story_metadata.get("title", idea.title)
            base_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slugify(clean_title)}"

            folder_path = Path("input/clips") / base_name
            folder_path.mkdir(parents=True, exist_ok=True)

            # ── Build scene prompt text ──────────────────────────────────────
            clean_prompts = []
            char_desc = plan.story_metadata.get("character_appearance", "").strip()
            if char_desc:
                clean_prompts.append(
                    f"👤 CHARACTER APPEARANCE REFERENCE:\n"
                    f"{char_desc}\n"
                    f"==================================================\n"
                )
            for scene in plan.scenes:
                num      = scene["scene_number"]
                gen_type = scene["generation_type"]
                expected = scene.get("expected_file", f"{num}_image.png")
                beat     = scene.get("scene_beat", "")
                clean_prompts.append(
                    f"📌 SCENE {num} [{beat}] — {gen_type} (Expected file: {expected})\n"
                    f"Voiceover (Hindi): {scene.get('voiceover_hindi', '')}\n"
                    f"Voiceover (Hinglish): {scene.get('voiceover_hinglish', '')}\n"
                    f"Image Prompt:\n{scene.get('ai_prompt', '')}\n"
                    f"--------------------------------------------------\n"
                )

            prompts_text = "\n".join(clean_prompts)

            # ── Thumbnail section (long videos) ──────────────────────────────
            thumb_title_dev = plan.story_metadata.get("thumbnail_title_hindi")
            thumb_prompt = plan.story_metadata.get("thumbnail_prompt")
            if idea.video_type == "long" and thumb_title_dev and thumb_prompt:
                prompts_text += (
                    f"\n\n==================================================\n"
                    f"🎨 THUMBNAIL (Expected file: thumbnail.png)\n"
                    f"==================================================\n"
                    f"Thumbnail Title (Hindi): {thumb_title_dev}\n"
                    f"Prompt:\n{thumb_prompt}\n"
                    f"--------------------------------------------------\n"
                )

            seo = seo_gen.generate(idea, plan)

            # ── YouTube/FB metadata section ──────────────────────────────────
            prompts_text += (
                f"\n\n==================================================\n"
                f"📺 UPLOAD METADATA (YouTube)\n"
                f"==================================================\n"
                f"▶ YouTube Title:\n{seo.title}\n\n"
                f"▶ YouTube Description:\n{seo.description}\n\n"
                f"▶ Tags:\n{', '.join(seo.tags)}\n\n"
                f"▶ Hashtags:\n{' '.join(seo.hashtags)}\n\n"
                f"▶ Facebook/Reels Caption:\n{seo.facebook_description}\n"
                f"--------------------------------------------------\n"
            )

            prompts_dir = Path("output/veo_prompts")
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompts_file_path = prompts_dir / f"{base_name}.txt"
            prompts_file_path.write_text(prompts_text, encoding="utf-8")
            (folder_path / "plan.json").write_text(plan.raw_json, encoding="utf-8")

            # ── Clean Zapi-only image prompts file (one prompt per block) ────
            # This file has ONLY the image prompts — no voiceover, no headers.
            # Use this file directly in Zapi Flow / Midjourney batch tools.
            zapi_prompts = []
            for scene in plan.scenes:
                prompt_text = scene.get("ai_prompt", "").strip()
                if prompt_text:
                    zapi_prompts.append(prompt_text)
            # Add thumbnail prompt if long video
            thumb_prompt_clean = plan.story_metadata.get("thumbnail_prompt", "").strip()
            if idea.video_type == "long" and thumb_prompt_clean:
                zapi_prompts.append(f"[THUMBNAIL] {thumb_prompt_clean}")
            zapi_file_path = prompts_dir / f"{base_name}_zapi_prompts.txt"
            zapi_file_path.write_text("\n\n".join(zapi_prompts), encoding="utf-8")

            # ── Pre-synthesize TTS voiceover for image mode ──────────────────
            if effective_mode == "image" and not no_voice:
                for scene in plan.scenes:
                    text = scene.get("voiceover_hindi", "").strip()
                    if text:
                        try:
                            tts_engine.synthesize_scene(
                                text,
                                folder_path / f"scene_{scene['scene_number']}.mp3",
                                voice_hint=scene.get("voice_hint", "narrator_dramatic"),
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
                "mode":                 effective_mode,
                "idea_as_dict":         asdict(idea),
                "made_for_kids":        False,
                "facebook_description": seo.facebook_description,
            }
            (folder_path / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            safe_print(f"\n==================================================")
            safe_print(f"[STORY GENERATED: {idea.title}]")
            safe_print(f"  Category: {idea.category} | Format: {idea.video_type} | Mode: {effective_mode}")
            safe_print(f"  Scenes: {len(plan.scenes)} | Est. Duration: {plan.story_metadata.get('estimated_duration_seconds', '?')}s")
            if char_desc:
                safe_print(f"  Character Reference: {char_desc}")
            safe_print(f"==================================================")
            safe_print(prompts_text)
            safe_print(f"")
            safe_print(f"  Full Prompts  → {prompts_file_path.resolve()}")
            safe_print(f"  ZAPI FLOW     → {zapi_file_path.resolve()}  ← USE THIS IN ZAPI")
            safe_print(f"  Clips Folder  → {folder_path.resolve()}")
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
                "channel":       "stories",
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

    write_json(content_store, content_history)
    return results


# ───────────────────────────────────────────────────────────────────────────────
#  STITCH  –  assemble manually placed clips into final video
# ───────────────────────────────────────────────────────────────────────────────

def run_stitch() -> list[dict]:
    """Scans input/clips/ for completed folders and assembles final videos."""
    from tts_engine import TTSEngine
    from video_assembler import VideoAssembler
    from story_idea_generator import StoryIdea
    from story_generator import StoryPlan
    from seo_generator import SeoPackage

    config = get_config()
    tts_engine = TTSEngine(config)
    assembler  = VideoAssembler(config)

    content_store   = config.content_store
    content_history = read_json(content_store)

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
            import re

            def has_matching_file(k_val, allowed_exts):
                if not folder.exists():
                    return False
                for f in folder.iterdir():
                    if not f.is_file():
                        continue
                    if f.suffix.lower() not in allowed_exts:
                        continue
                    m = re.match(r'^(\d+)', f.stem)
                    if m and int(m.group(1)) == k_val:
                        return True
                return False

            # Check if the folder contains sequential scene assets
            has_seq_files = False
            for ext in [".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".avi"]:
                if (folder / f"4{ext}").exists() or (folder / f"4_image{ext}").exists():
                    has_seq_files = True
                    break
            if not has_seq_files:
                for f in folder.iterdir():
                    if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".avi"]:
                        m = re.match(r'^(\d+)', f.stem)
                        if m and int(m.group(1)) == 4:
                            has_seq_files = True
                            break

            kids_mode = None
            meta_path = folder / "metadata.json"
            if meta_path.exists():
                try:
                    meta_data_json = json.loads(meta_path.read_text(encoding="utf-8"))
                    kids_mode = meta_data_json.get("kids_mode")
                except Exception:
                    pass
            use_sequential = (kids_mode is not None) or has_seq_files

            for s in plan_data.get("scenes", []):
                num      = s["scene_number"]
                gen_type = s["generation_type"]
                
                k_seq = num
                k_legacy = num if use_sequential else (num + 1) // 2
                
                if gen_type == "AI_VIDEO":
                    found = (has_matching_file(k_seq, [".mp4", ".mov", ".avi"]) or 
                             has_matching_file(k_legacy, [".mp4", ".mov", ".avi"]))
                    if not found:
                        missing_files.append(f"{num}.mp4")
                else:
                    found = (has_matching_file(k_seq, [".png", ".jpg", ".jpeg", ".webp"]) or 
                             has_matching_file(k_legacy, [".png", ".jpg", ".jpeg", ".webp"]))
                    if not found:
                        missing_files.append(f"{num}.png/jpg")

            if missing_files:
                LOGGER.info("Folder '%s' not ready — missing scene files: %s", folder.name, missing_files)
                continue

            LOGGER.info("Stitching '%s'…", folder.name)

            idea_dict = meta_data.get("idea_as_dict", {})
            idea = StoryIdea(
                idea_id=idea_dict.get("idea_id", ""),
                title=idea_dict.get("title", ""),
                hook=idea_dict.get("hook", ""),
                hook_hindi=idea_dict.get("hook_hindi", ""),
                core_conflict=idea_dict.get("core_conflict", ""),
                twist=idea_dict.get("twist", ""),
                moral=idea_dict.get("moral", ""),
                moral_hindi=idea_dict.get("moral_hindi", ""),
                angle=idea_dict.get("angle", ""),
                topic=idea_dict.get("topic", ""),
                audience_hook=idea_dict.get("audience_hook", ""),
                source_prompt=idea_dict.get("source_prompt", ""),
                created_at=idea_dict.get("created_at", ""),
                video_type=idea_dict.get("video_type", "short"),
                language=idea_dict.get("language", "hindi"),
                category=idea_dict.get("category", "mystery_stories"),
            )

            plan = StoryPlan(
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
                    "made_for_kids":        False,
                    "facebook_description": meta_data.get("facebook_description", ""),
                },
                "audio_path":    "",
                "video_path":    str(video_path.resolve()),
                "subtitle_srt":  "",
                "subtitle_json": "",
                "uploaded":      False,
                "upload_response": None,
                "channel":       "stories",
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

            write_json(content_store, content_history)
            LOGGER.info("Stitched '%s' → %s", folder.name, video_path)

        except Exception as e:
            LOGGER.exception("Failed to process folder '%s': %s", folder.name, e)

    return []


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wonder Stories TV – Viral Hindi Stories automation pipeline"
    )
    parser.add_argument("--count", nargs="?", const=1, default=1, type=int,
                        help="Number of short videos to generate (default: 1).")
    parser.add_argument("--long-count", type=int, default=0,
                        help="Number of long videos to generate.")
    parser.add_argument("--short", action="store_true",
                        help="Force short format.")
    parser.add_argument("--long", action="store_true",
                        help="Force long format.")
    parser.add_argument("--upload", action="store_true",
                        help="Upload / schedule generated videos to YouTube.")
    parser.add_argument("--schedule", action="store_true",
                        help="Start APScheduler (runs daily at 2:30 PM IST).")
    parser.add_argument("--topic", type=str,
                        help="Force a specific story topic (partial title match).")
    parser.add_argument("--schedule-upload", action="store_true",
                        help="After generation, schedule all pending local videos.")
    parser.add_argument("--videos-per-day", type=int, default=1,
                        help="How many videos to schedule per day (default: 1).")
    parser.add_argument("--stitch", action="store_true",
                        help="Stitch manually placed video/image clips into final video.")
    parser.add_argument("--deploy", action="store_true",
                        help="Schedule stitched videos sitting in output/final_videos/.")
    parser.add_argument("--mode", type=str, choices=["image", "video"], default="image",
                        help="Generation mode: image (image-to-video) | video (video-to-video for short stories only). Long stories will auto-fall back to image mode.")
    parser.add_argument("--no-voice", action="store_true",
                        help="Skip generating voiceovers/TTS files during prompt generation.")
    parser.add_argument("--local-tts", action="store_true",
                        help="Use local Edge TTS only (skip ElevenLabs). Free, unlimited.")
    parser.add_argument("--category", type=str, choices=[
                            "mystery_stories", "shocking_facts", "suspense_stories",
                            "dark_facts", "psychological", "thriller_stories",
                            "horror_stories", "crime_stories", "karma_stories",
                            "real_life_facts", "moral_stories", "bhagwan_stories",
                            "bagwan_stories", "inspirational_stories",
                            "motivational_stories",
                        ], default=None, help="Story category.")

    args = parser.parse_args()
    args.category = normalize_story_category(args.category)

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
    if args.stitch:
        run_stitch()
        return

    # ── Deploy / schedule ──────────────────────────────────────────────────────
    if args.deploy or (
        args.upload and not any(arg in sys.argv for arg in ["--count", "--long-count"])
    ):
        LOGGER.info("Scheduling stitched videos for upload…")
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Scheduled %s video(s).", scheduled)
        return

    # ── Generate ───────────────────────────────────────────────────────────────
    results = run_stories_pipeline(
        short_count=args.count,
        long_count=args.long_count,
        upload=args.upload,
        videos_per_day=args.videos_per_day,
        mode=args.mode,
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
