from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from config import AUDIO_DIR, DATA_DIR, VIDEO_DIR, get_config
from idea_generator import IdeaGenerator, VideoIdea, canonicalize_text, canonicalize_title
from script_generator import ScriptGenerator
from seo_generator import SeoPackage
from upload_all import schedule_pending_uploads
from uploader import YouTubeUploader
from moviepy import VideoFileClip, concatenate_videoclips

LOGGER = logging.getLogger(__name__)

# ─── Channel routing ──────────────────────────────────────────────────────────
# Set CHANNEL=kids in .env to activate the Chintu Stories kids animation pipeline.
# Set CHANNEL=fitness (or leave blank) to use the original fitness pipeline.
ACTIVE_CHANNEL = os.getenv("CHANNEL", "fitness").lower().strip()


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        import sys
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


# ═══════════════════════════════════════════════════════════════════════════════
#  KIDS PIPELINE  (Chintu Stories)
# ═══════════════════════════════════════════════════════════════════════════════

def run_kids_pipeline(
    short_count: int = 1,
    long_count: int = 0,
    upload: bool = False,
    videos_per_day: int = 1,
    kids_mode: str = "veo",
) -> list[dict]:
    """
    Semi-manual AI Kids Animation pipeline:
      1. Generate story ideas (Chintu + magical element + moral)
      2. LLM generates a 4-scene (Short) or 8-scene (Long) story JSON plan
      3. Saves prompts to prompts.txt and plan/metadata.json to input/kids_clips/{base_name}/
      4. Waits for user to place manually generated videos/images
      5. Synthesizes Edge TTS audio dynamically
      6. Assembles the final video (subtitles, transitions, etc.)
      7. Uploads to YouTube + Facebook
    """
    from kids_idea_generator import KidsIdeaGenerator
    from kids_story_generator import KidsStoryGenerator
    from kids_tts import KidsTTSEngine
    from kids_video_assembler import KidsVideoAssembler
    from kids_seo_generator import KidsSeoGenerator, KidsSeoPackage

    config = get_config()

    # ── Kids-specific data stores ────────────────────────────────────────────
    kids_ideas_store   = DATA_DIR / "kids_ideas.json"
    kids_content_store = DATA_DIR / "kids_content_history.json"

    idea_gen    = KidsIdeaGenerator(config)
    story_gen   = KidsStoryGenerator(config)
    tts_engine  = KidsTTSEngine(config)
    assembler   = KidsVideoAssembler(config)
    seo_gen     = KidsSeoGenerator(config)
    yt_uploader = YouTubeUploader(config)

    content_history: list[dict] = read_json(kids_content_store)
    used_titles = {item.get("idea_title", "").lower() for item in content_history}
    results: list[dict] = []

    # Generate ideas for Shorts
    short_ideas = []
    if short_count > 0:
        raw_ideas = idea_gen.generate_ideas(count=short_count * 3, video_type="short", ideas_store=kids_ideas_store)
        saved     = idea_gen.save_new_ideas(raw_ideas, ideas_store=kids_ideas_store)
        short_ideas = [i for i in saved if i.title.lower() not in used_titles][:short_count]

    # Generate ideas for Longs
    long_ideas = []
    if long_count > 0:
        raw_ideas = idea_gen.generate_ideas(count=long_count * 3, video_type="long", ideas_store=kids_ideas_store)
        saved     = idea_gen.save_new_ideas(raw_ideas, ideas_store=kids_ideas_store)
        long_ideas = [i for i in saved if i.title.lower() not in used_titles][:long_count]

    all_ideas = short_ideas + long_ideas

    for idea in all_ideas:
        is_long   = idea.video_type == "long"
        base_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slugify(idea.title)}"

        LOGGER.info("Processing kids story: '%s' (type=%s)", idea.title, idea.video_type)

        try:
            # ── Step 1: Generate story plan ───────────────────────────────────
            plan = story_gen.generate_story(idea, kids_mode=kids_mode)

            # ── Step 2: Create directory and save prompt/plan metadata ────────
            parent_dir = "input/clips"
            folder_path = Path(parent_dir) / base_name
            folder_path.mkdir(parents=True, exist_ok=True)

            # Generate prompts text
            clean_prompts = []
            for scene in plan.scenes:
                num = scene["scene_number"]
                gen_type = scene["generation_type"]
                k = num
                expected = f"{k}.mp4" if gen_type == "AI_VIDEO" else f"{k}_image.png"
                clean_prompts.append(
                    f"🔥 SCENE {num} - {gen_type} (Expected file: {expected})\n"
                    f"Voiceover (Hindi): {scene.get('voiceover_hindi', '')}\n"
                    f"Prompt:\n{scene.get('ai_prompt', '')}\n"
                    f"--------------------------------------------------\n"
                )

            prompts_text = "\n".join(clean_prompts)
            
            # Save prompts directly to output/veo_prompts/
            prompts_dir = Path("output/veo_prompts")
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompts_file_path = prompts_dir / f"{base_name}.txt"
            prompts_file_path.write_text(prompts_text, encoding="utf-8")
            
            (folder_path / "plan.json").write_text(plan.raw_json, encoding="utf-8")

            # Pre-synthesize TTS scene audios for lip-syncing/preview support (ONLY for image mode)
            if kids_mode != "veo":
                for scene in plan.scenes:
                    num = scene["scene_number"]
                    text = scene.get("voiceover_hindi", "").strip()
                    if text:
                        try:
                            tts_engine.synthesize_scene(text, folder_path / f"scene_{num}.mp3")
                        except Exception as e:
                            LOGGER.warning("Could not pre-synthesize TTS for scene %s: %s", num, e)

            # Generate SEO
            seo = seo_gen.generate(idea, plan)
            metadata = {
                "title": seo.title,
                "description": seo.description,
                "tags": seo.tags,
                "hashtags": seo.hashtags,
                "primary_keyword": seo.primary_keyword,
                "language_code": seo.language_code,
                "audio_language_code": seo.audio_language_code,
                "content_style": seo.content_style,
                "kids_mode": kids_mode,
                "idea_as_dict": asdict(idea),
            }
            (folder_path / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

            # Print prompts clearly on console
            safe_print(f"\n==================================================")
            safe_print(f"[KIDS PROMPTS GENERATED FOR: {idea.title}]")
            safe_print(f"==================================================")
            safe_print(prompts_text)
            safe_print(f"Saved prompts to {prompts_file_path.resolve()} and plan to {folder_path.resolve()}")
            safe_print(f"==================================================\n")

            # Save record of prompt generation (so we know it's generated)
            record = {
                "idea_title": idea.title,
                "idea": asdict(idea),
                "story_plan": json.loads(plan.raw_json),
                "seo": asdict(seo),
                "audio_path": "",
                "video_path": "",
                "subtitle_srt": "",
                "subtitle_json": "",
                "uploaded": False,
                "upload_response": None,
                "channel": "kids",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "script": {"video_type": idea.video_type, "title": idea.title},
            }
            # Reconstruct and update record in-place if it exists, otherwise append
            existing_idx = None
            for idx, r in enumerate(content_history):
                if r.get("idea_title") == idea.title:
                    existing_idx = idx
                    break
            if existing_idx is not None:
                content_history[existing_idx] = record
            else:
                content_history.append(record)
            used_titles.add(idea.title.lower())
            results.append(record)
            LOGGER.info("Successfully generated prompts and saved metadata for '%s'", idea.title)

        except Exception as exc:
            LOGGER.exception("Kids pipeline failed for idea '%s': %s", idea.title, exc)
            continue

    write_json(kids_content_store, content_history)
    return results


def _cleanup_local(video_path: Path, audio_path: Path) -> None:
    for p in (video_path, audio_path):
        if p and p.exists():
            try:
                p.unlink()
                LOGGER.info("Deleted local file after upload: %s", p.name)
            except Exception as exc:
                LOGGER.warning("Could not delete %s: %s", p, exc)


# ═══════════════════════════════════════════════════════════════════════════
#  FITNESS PIPELINE  (original — unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def build_fallback_veo_metadata() -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "seo_title": f"10 Minute Full Body Fitness Burn | Home Workout #{timestamp}",
        "seo_description": (
            "Quick full-body fitness session to boost energy, build strength, and stay consistent. "
            "Perfect for a home workout routine with simple movements, strong focus, and fat-burning intensity. "
            "Train smart, stay active, and keep pushing your fitness goals."
        ),
        "seo_tags": [
            "fitness",
            "home workout",
            "full body workout",
            "fat burn",
            "exercise motivation",
            "strength training",
            "healthy lifestyle",
        ],
    }


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
    if video_path.exists():
        try:
            video_path.unlink()
            LOGGER.info("Deleted local video after successful upload: %s", video_path)
            if record is not None:
                record["local_video_deleted"] = True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not delete local video '%s': %s", video_path, exc)

    if record is not None:
        for key in ("audio_path", "subtitle_srt", "subtitle_json"):
            path_str = record.get(key)
            if path_str:
                path = Path(path_str)
                if path.exists():
                    try:
                        path.unlink()
                        LOGGER.info("Deleted intermediate local resource (%s): %s", key, path.name)
                    except Exception as exc:
                        LOGGER.warning("Could not delete intermediate resource '%s': %s", path_str, exc)


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
    videos_per_day: int = 1,
    stitch_kids: bool = False,
    kids_mode: str = "veo",
) -> list[dict]:
    """
    Routes to the correct pipeline based on the CHANNEL env var.

    CHANNEL=kids   → run_kids_pipeline()
    CHANNEL=fitness → original fitness pipeline (unchanged)
    """
    if ACTIVE_CHANNEL == "kids":
        if stitch_kids:
            LOGGER.info("Scanning for manually generated kids clips to stitch...")
            folders = []
            p_path = Path("input/clips")
            if p_path.exists():
                folders.extend([d for d in p_path.iterdir() if d.is_dir() and d.name != "temp_audio"])

            if not folders:
                LOGGER.info("No kids story folders found in input/clips/.")
                return []

            from kids_tts import KidsTTSEngine
            from kids_video_assembler import KidsVideoAssembler
            from kids_idea_generator import KidsStoryIdea
            from kids_story_generator import KidsStoryPlan
            from seo_generator import SeoPackage

            config = get_config()
            tts_engine = KidsTTSEngine(config)
            assembler = KidsVideoAssembler(config)

            kids_content_store = DATA_DIR / "kids_content_history.json"
            content_history = read_json(kids_content_store)

            for folder in folders:
                plan_file = folder / "plan.json"
                meta_file = folder / "metadata.json"
                if not plan_file.exists() or not meta_file.exists():
                    LOGGER.warning("Skipping folder %s: plan.json or metadata.json is missing.", folder.name)
                    continue

                try:
                    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))

                    # Verify files are present
                    missing_files = []
                    kids_mode_meta = meta_data.get("kids_mode")
                    use_sequential = (kids_mode_meta is not None)

                    for s in plan_data.get("scenes", []):
                        num = s["scene_number"]
                        gen_type = s["generation_type"]
                        k = num if use_sequential else (num + 1) // 2
                        if gen_type == "AI_VIDEO":
                            if not any((folder / f"{k}{ext}").exists() for ext in [".mp4", ".mov", ".avi"]):
                                missing_files.append(f"{k}.mp4")
                        else:
                            if not any((folder / f"{k}_image{ext}").exists() for ext in [".png", ".jpg", ".jpeg"]):
                                missing_files.append(f"{k}_image.png")

                    if missing_files:
                        LOGGER.info("Folder '%s' is not ready yet. Missing files: %s", folder.name, missing_files)
                        continue

                    LOGGER.info("Stitching folder '%s'...", folder.name)

                    # Reconstruct KidsStoryIdea
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
                    )

                    # Reconstruct KidsStoryPlan
                    plan = KidsStoryPlan(
                        story_metadata=plan_data["story_metadata"],
                        scenes=plan_data["scenes"],
                        audio_effects_config=plan_data.get("audio_effects_config", {}),
                        raw_json=json.dumps(plan_data),
                    )

                    video_path = VIDEO_DIR / f"{folder.name}.mp4"

                    # Assemble
                    assembler.assemble_from_folder(
                        input_dir=folder,
                        plan=plan,
                        tts_engine=tts_engine,
                        idea=idea,
                        output_path=video_path,
                    )

                    # Upload
                    upload_response = None
                    if upload:
                        LOGGER.info("Uploading assembled kids video to YouTube...")
                        yt_uploader = YouTubeUploader(config)
                        yt_seo = SeoPackage(
                            title=meta_data["title"],
                            description=meta_data["description"],
                            tags=meta_data["tags"],
                            hashtags=meta_data["hashtags"],
                            primary_keyword=meta_data["primary_keyword"],
                            language_code=meta_data["language_code"],
                            audio_language_code=meta_data["audio_language_code"],
                            content_style=meta_data["content_style"],
                        )
                        upload_response = yt_uploader.upload_short(video_path, yt_seo)

                    # Create record
                    record = {
                        "idea_title": idea.title,
                        "idea": asdict(idea),
                        "story_plan": plan_data,
                        "seo": {
                            "title": meta_data["title"],
                            "description": meta_data["description"],
                            "tags": meta_data["tags"],
                            "hashtags": meta_data["hashtags"],
                            "primary_keyword": meta_data["primary_keyword"],
                            "language_code": meta_data["language_code"],
                            "audio_language_code": meta_data["audio_language_code"],
                            "content_style": meta_data["content_style"],
                        },
                        "audio_path": "",
                        "video_path": str(video_path.resolve()),
                        "subtitle_srt": "",
                        "subtitle_json": "",
                        "uploaded": bool(upload_response),
                        "upload_response": upload_response,
                        "channel": "kids",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "script": {"video_type": idea.video_type, "title": idea.title},
                    }

                    # Clean up local files only if uploaded successfully
                    if upload_response:
                        try:
                            import shutil
                            shutil.rmtree(folder, ignore_errors=True)
                        except Exception as e:
                            LOGGER.warning("Could not delete folder %s: %s", folder, e)
                        try:
                            video_path.unlink()
                        except:
                            pass

                    # Reconstruct and update record in-place if it exists, otherwise append
                    existing_idx = None
                    for idx, r in enumerate(content_history):
                        if r.get("idea_title") == idea.title:
                            existing_idx = idx
                            break
                    if existing_idx is not None:
                        content_history[existing_idx] = record
                    else:
                        content_history.append(record)
                    write_json(kids_content_store, content_history)
                    LOGGER.info("Successfully stitched and processed '%s'!", folder.name)

                except Exception as e:
                    LOGGER.exception("Failed to process folder %s: %s", folder.name, e)

            return []

        LOGGER.info("CHANNEL=kids: routing to Chintu Stories kids animation pipeline")
        return run_kids_pipeline(
            short_count=short_count,
            long_count=long_count,
            upload=upload,
            videos_per_day=videos_per_day,
            kids_mode=kids_mode,
        )

    # ── Original fitness pipeline ──────────────────────────────────────────────
    config = get_config()
    total_count = short_count + long_count

    if stitch_veo:
        LOGGER.info("Stitching manually generated Veo clips...")
        veo_dir = Path("input/veo_clips")
        metadata_file = veo_dir / "metadata.json"
        fallback_metadata = build_fallback_veo_metadata()

        if not metadata_file.exists():
            metadata = fallback_metadata
            metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            LOGGER.warning("metadata.json not found in %s. Created fallback fitness SEO metadata.", veo_dir)
        else:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

        metadata.setdefault("seo_title", fallback_metadata["seo_title"])
        metadata.setdefault("seo_description", fallback_metadata["seo_description"])
        metadata.setdefault("seo_tags", fallback_metadata["seo_tags"])
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
                str(output_path), codec="libx264", audio_codec="aac",
                fps=30, threads=4, logger=None,
            )
            for c in clips:
                c.close()
            final_clip.close()

            metadata["final_video_path"] = str(output_path)
            metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            LOGGER.info("Stitching complete! Preview: %s", output_path)
            LOGGER.info("When ready, run: python main.py --deploy-veo")
        except Exception as exc:
            LOGGER.error("Failed to stitch Veo clips: %s", exc)
        return []

    if deploy_veo:
        LOGGER.info("Deploying stitched Veo video...")
        veo_dir = Path("input/veo_clips")
        metadata_file = veo_dir / "metadata.json"

        if not metadata_file.exists():
            LOGGER.error("metadata.json not found in %s!", veo_dir)
            return []

        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        fallback_metadata = build_fallback_veo_metadata()
        metadata.setdefault("seo_title", fallback_metadata["seo_title"])
        metadata.setdefault("seo_description", fallback_metadata["seo_description"])
        metadata.setdefault("seo_tags", fallback_metadata["seo_tags"])
        if "final_video_path" not in metadata:
            LOGGER.error("Final video path not found in metadata! Run --stitch-veo first.")
            return []

        output_path = Path(metadata["final_video_path"])
        if not output_path.exists():
            LOGGER.error("Final video file not found at %s!", output_path)
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
            schedule_pending_uploads(videos_per_day=videos_per_day)

            LOGGER.info("Cleaning up %s...", veo_dir)
            for p in sorted(veo_dir.glob("*.mp4")):
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
    idea_generator    = IdeaGenerator(config)
    script_generator  = ScriptGenerator(config)
    uploader          = YouTubeUploader(config)

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
            veo_data = script_generator.generate_veo_prompt(idea)
            
            # Print prompts clearly on console
            safe_print(f"\n==================================================")
            safe_print(f"[VEO PROMPT GENERATED FOR: {idea.title}]")
            safe_print(f"==================================================")
            safe_print(f"CLIP 1 PROMPT:\n{veo_data.get('clip_1_prompt', '')}\n")
            safe_print(f"CLIP 2 PROMPT:\n{veo_data.get('clip_2_prompt', '')}\n")
            safe_print(f"CLIP 3 PROMPT:\n{veo_data.get('clip_3_prompt', '')}\n")
            safe_print(f"CLIP 4 PROMPT:\n{veo_data.get('clip_4_prompt', '')}\n")
            safe_print(f"SEO Title: {veo_data.get('seo_title', '')}")
            safe_print(f"SEO Description: {veo_data.get('seo_description', '')}")
            safe_print(f"==================================================\n")

            veo_dir  = Path("output/veo_prompts")
            veo_dir.mkdir(parents=True, exist_ok=True)
            veo_path = veo_dir / f"{base_name}.txt"
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

            if veo_prompt:
                results.append(record)
                continue

            import sys
            if not sys.stdin.isatty():
                LOGGER.info("Non-interactive terminal detected. Skipping manual clip input wait.")
                clips_paths = sorted([p for p in input_dir.glob("*.mp4")])
                if not clips_paths:
                    LOGGER.warning("No clips found in input/veo_clips/ for non-interactive run. Prompt saved; skipping stitch/upload.")
                    results.append(record)
                    continue
            else:
                LOGGER.info("Waiting for scene inputs in input/veo_clips/...")
                while True:
                    val = input("\n-> Generate the 4 clips in Google Veo using the prompts above,\n"
                                "place them in 'input/veo_clips/' as .mp4 files,\n"
                                "and press Enter to stitch and upload (or type 'skip' to skip this idea): ").strip()
                    if val.lower() == 'skip':
                        LOGGER.info("Skipped idea: %s", idea.title)
                        clips_paths = []
                        break
                    clips_paths = sorted([p for p in input_dir.glob("*.mp4")])
                    if not clips_paths:
                        safe_print("[ERROR] No .mp4 files found in input/veo_clips/. Please place the clips there first!")
                        continue
                    break

            if not clips_paths:
                results.append(record)
                continue

            safe_print(f"[STITCH] Found {len(clips_paths)} clips. Stitching...")
            clips = [VideoFileClip(str(p)) for p in clips_paths]
            final_clip = concatenate_videoclips(clips, method="compose")

            output_dir = Path("output/final_videos")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"veo_final_{base_name}.mp4"

            LOGGER.info("Rendering combined video...")
            final_clip.write_videofile(
                str(output_path), codec="libx264", audio_codec="aac",
                fps=30, threads=4, logger=None,
            )
            for c in clips:
                c.close()
            final_clip.close()
            LOGGER.info("Stitching complete! Output: %s", output_path)

            seo = SeoPackage(
                title=veo_data["seo_title"],
                description=veo_data["seo_description"],
                tags=veo_data["seo_tags"],
                hashtags=veo_data.get("seo_tags", [])[:5],
                primary_keyword=veo_data.get("seo_tags", [""])[0] if veo_data.get("seo_tags") else "video",
                language_code="hi",
                audio_language_code="hi",
            )

            upload_response = None
            if upload:
                LOGGER.info("Uploading combined Veo video to YouTube...")
                upload_response = uploader.upload_short(output_path, seo)

            record.update({
                "script": {"video_type": idea.video_type, "title": idea.title},
                "seo": asdict(seo),
                "audio_path": "",
                "video_path": str(output_path.resolve()),
                "subtitle_srt": "",
                "subtitle_json": "",
                "uploaded": bool(upload_response),
                "upload_response": upload_response,
            })

            if upload_response:
                try:
                    output_path.unlink()
                    LOGGER.info("Deleted local final video after successful upload: %s", output_path)
                except Exception as e:
                    LOGGER.warning("Could not delete final video: %s", e)

            for p in clips_paths:
                try:
                    p.unlink()
                except:
                    pass
            metadata_path.unlink(missing_ok=True)

            content_history.append(record)
            processed_signatures.add(idea_signature)
            results.append(record)
            LOGGER.info("Finished content package for '%s'", idea.title)
        except Exception as exc:
            LOGGER.exception("Pipeline failed for idea '%s': %s", idea.title, exc)
            continue

    write_json(config.content_store, content_history)
    return results


# ═══════════════════════════════════════════════════════════════════════════
#  CLI ARGS
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YouTube automation pipeline (CHANNEL=kids or CHANNEL=fitness)"
    )
    parser.add_argument("--count", nargs="?", const=1, default=1, type=int,
                        help="Number of short videos to generate.")
    parser.add_argument("--long-count", type=int, default=0,
                        help="Number of long videos to generate.")
    parser.add_argument("--short", action="store_true",
                        help="Treat --count as short video count (set long-count to 0).")
    parser.add_argument("--long", action="store_true",
                        help="Treat --count as long video count (set short count to 0).")
    parser.add_argument("--upload", action="store_true",
                        help="Upload generated videos to YouTube + Facebook.")
    parser.add_argument("--schedule", action="store_true",
                        help="Start APScheduler (runs at 2:30 PM IST daily for kids channel).")
    parser.add_argument("--topic", type=str, help="[Fitness only] Create one manual topic-driven Short.")
    parser.add_argument("--theme", type=str, help="[Fitness only] Bias ideas toward a niche.")
    parser.add_argument("--language", type=str, choices=["english", "hindi", "hinglish"],
                        default="hinglish", help="[Fitness only] Preferred language.")
    parser.add_argument("--schedule-upload", action="store_true",
                        help="After generation, schedule all pending local videos.")
    parser.add_argument("--videos-per-day", type=int, default=1,
                        help="How many videos to schedule per day.")
    parser.add_argument("--veo-prompt", action="store_true",
                        help="[Fitness only] Generate Veo prompts instead of rendering.")
    parser.add_argument("--stitch-veo", action="store_true",
                        help="[Fitness only] Combine Veo clips for preview.")
    parser.add_argument("--deploy-veo", action="store_true",
                        help="[Fitness only] Upload combined Veo video to YouTube.")
    parser.add_argument("--test-long", action="store_true",
                        help="[Fitness only] Generate a long video for testing.")
    
    # Kids Semi-Manual Flags
    parser.add_argument("--stitch", "--stitch-kids", action="store_true", dest="stitch_kids",
                        help="[Kids only] Stitch manually generated video/image clips.")
    parser.add_argument("--deploy-kids", action="store_true",
                        help="[Kids only] Upload stitched kids videos sitting in output/final_videos.")
    parser.add_argument("--image", action="store_true",
                        help="[Kids only] Generate image-based story (4 image scenes, 25-35s) instead of default veo video story (3 scenes, max 18s).")
    parser.add_argument("--videos", action="store_true",
                        help="[Kids only] Generate video-based story (3 video scenes, max 18s) (default).")

    parser.add_argument("legacy_command", nargs="?", choices=["count"], help=argparse.SUPPRESS)
    parser.add_argument("legacy_value", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.legacy_command == "count":
        args.count = int(args.legacy_value) if args.legacy_value else 1

    if args.long:
        args.long_count = args.count
        args.count = 0
    elif args.short:
        args.long_count = 0

    return args


def main() -> None:
    args = parse_args()
    LOGGER.info("Active channel: %s", ACTIVE_CHANNEL.upper())

    if args.schedule:
        from scheduler import start_scheduler
        start_scheduler(get_config())
        return

    # Kids specific flags
    if getattr(args, "stitch_kids", False):
        run_pipeline(stitch_kids=True, upload=args.upload, videos_per_day=args.videos_per_day)
        return

    # Check if --upload was run alone on kids channel (acts as deploy)
    if ACTIVE_CHANNEL == "kids" and args.upload and not any(arg in sys.argv for arg in ["--count", "--long-count"]):
        LOGGER.info("Deploying/Scheduling stitched kids videos...")
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Completed deployment. Scheduled %s kids videos.", scheduled)
        return

    if getattr(args, "deploy_kids", False):
        LOGGER.info("Deploying/Scheduling stitched kids videos...")
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Completed deployment. Scheduled %s kids videos.", scheduled)
        return

    results = run_pipeline(
        short_count=args.count,
        long_count=args.long_count,
        upload=args.upload,
        topic=getattr(args, "topic", None),
        theme=getattr(args, "theme", None),
        language=getattr(args, "language", "hinglish"),
        test_long=getattr(args, "test_long", False),
        veo_prompt=getattr(args, "veo_prompt", False),
        stitch_veo=getattr(args, "stitch_veo", False),
        deploy_veo=getattr(args, "deploy_veo", False),
        videos_per_day=args.videos_per_day,
        stitch_kids=getattr(args, "stitch_kids", False),
        kids_mode="images" if getattr(args, "image", False) else "veo",
    )
    if args.schedule_upload:
        scheduled = schedule_pending_uploads(videos_per_day=args.videos_per_day)
        LOGGER.info("Scheduled %s pending videos after generation", scheduled)
    LOGGER.info("Pipeline finished — %s video(s) generated (channel=%s)", len(results), ACTIVE_CHANNEL)


if __name__ == "__main__":
    main()
