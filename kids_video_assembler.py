"""
kids_video_assembler.py  –  Chintu Stories Channel
===================================================
Assembles the final video from:
  1. User-generated scene videos and images (MP4/PNG/JPG) placed in input/kids_clips/{folder}/
  2. Edge TTS Hindi voiceover dynamically synthesized per scene
  3. CapCut-style Hindi subtitles (word-by-word, bold, stroke)

AI_VIDEO scenes   → User-provided MP4 video, fitted/cropped and extended via freeze-frame if shorter than voiceover
IMAGE_FOR_ZOOM scenes → User-provided image, zoomed gently (Ken Burns) to match voiceover duration

Output:
  - Shorts: 9:16 (1080×1920)
  - Long:   16:9 (1920×1080)
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
    vfx,
    VideoFileClip,
    CompositeAudioClip,
)

from config import AppConfig
from kids_story_generator import KidsStoryPlan
from kids_idea_generator import KidsStoryIdea

LOGGER = logging.getLogger(__name__)

# ─── Canvas sizes ─────────────────────────────────────────────────────────────
SHORTS_W, SHORTS_H = 1080, 1920
LONG_W,   LONG_H   = 1920, 1080

# ─── Viral keywords highlighted in yellow ─────────────────────────────────────
KIDS_VIRAL_KEYWORDS = {
    "chintu", "maa", "jaadu", "magic", "magical", "pyaar", "seekha",
    "promise", "happy", "khushi", "dost", "sach", "jhooth", "galat",
    "sahi", "paani", "accha", "bura", "lesson", "moral", "sikhna",
}


class KidsVideoAssembler:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def assemble(
        self,
        plan: KidsStoryPlan,
        scene_images: dict[int, Path],   # {scene_number: image_path}
        audio_path: Path,                # combined Hindi TTS audio
        idea: KidsStoryIdea,
        output_path: Path,
    ) -> Path:
        """
        [Legacy method kept for backward compatibility if needed]
        Full pipeline: images + audio → final MP4.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        is_long = idea.video_type == "long"
        vid_w   = LONG_W   if is_long else SHORTS_W
        vid_h   = LONG_H   if is_long else SHORTS_H

        LOGGER.info("Assembling kids video: %s (%s)", output_path.name, idea.video_type)

        # ── 1. Build per-scene video clips from images ─────────────────────────
        scene_clips = []
        for scene in plan.scenes:
            num      = scene["scene_number"]
            gen_type = scene["generation_type"]
            dur      = float(scene["duration_seconds"])
            img_path = scene_images.get(num)

            if img_path and img_path.exists() and img_path.stat().st_size > 10:
                clip = self._image_to_clip(img_path, dur, vid_w, vid_h, gen_type)
            else:
                LOGGER.warning("Image missing for scene %s, using gradient fallback", num)
                clip = self._gradient_clip(num, dur, vid_w, vid_h)
            scene_clips.append(clip)

        # Concatenate all scene clips
        video_base = concatenate_videoclips(scene_clips, method="compose")
        total_dur  = video_base.duration

        # ── 2. Audio (voice only — no background music) ───────────────────────
        final_audio = self._load_voice(audio_path, total_dur)

        # ── 3. Overlay layers ──────────────────────────────────────────────────
        overlay   = self._build_gradient_overlay(total_dur, vid_w, vid_h)
        title_card = self._build_title_card(idea, total_dur, vid_w, vid_h)
        sub_clips  = self._build_subtitle_clips(plan.scenes, total_dur, vid_w, vid_h)
        progress   = self._build_progress_bar(total_dur, vid_w, vid_h)

        layers: list = [video_base, overlay]
        if title_card:
            layers.append(title_card)
        layers.extend(sub_clips)
        if progress:
            layers.append(progress)

        final = CompositeVideoClip(layers, size=(vid_w, vid_h))
        final = final.with_audio(final_audio)

        temp_audio = output_path.parent / f"{output_path.stem}_tmp_audio.m4a"
        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(temp_audio),
            remove_temp=False,
            threads=4,
            ffmpeg_params=["-movflags", "+faststart", "-crf", "21"],
            logger=None,
        )

        for clip in scene_clips:
            clip.close()
        video_base.close()
        final_audio.close()
        final.close()

        if temp_audio.exists():
            import time
            for _ in range(5):
                try:
                    temp_audio.unlink()
                    break
                except Exception:
                    time.sleep(0.5)

        LOGGER.info("Kids video assembled: %s", output_path)
        return output_path

    def assemble_from_folder(
        self,
        input_dir: Path,
        plan: KidsStoryPlan,
        tts_engine: "KidsTTSEngine",
        idea: KidsStoryIdea,
        output_path: Path,
    ) -> Path:
        """
        Dynamically stitches manual videos and images from a folder.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        is_long = idea.video_type == "long"
        vid_w   = LONG_W   if is_long else SHORTS_W
        vid_h   = LONG_H   if is_long else SHORTS_H

        LOGGER.info("Assembling kids video from folder: %s (%s)", input_dir, idea.video_type)

        # Detect kids_mode from metadata.json to know if we use sequential indexes
        kids_mode = None
        meta_path = input_dir / "metadata.json"
        if meta_path.exists():
            try:
                import json
                meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                kids_mode = meta_data.get("kids_mode")
            except Exception:
                pass
        
        use_sequential = (kids_mode is not None)

        # 1. Map scenes and find the corresponding files
        scene_files = {}
        for scene in plan.scenes:
            num = scene["scene_number"]
            gen_type = scene["generation_type"]
            k = num if use_sequential else (num + 1) // 2

            if gen_type == "AI_VIDEO":
                # look for k.mp4, k.mov, k.avi
                video_found = None
                for ext in [".mp4", ".mov", ".avi"]:
                    test_path = input_dir / f"{k}{ext}"
                    if test_path.exists():
                        video_found = test_path
                        break
                if not video_found:
                    raise FileNotFoundError(f"Missing required video file for Scene {num} in {input_dir}: {k}.mp4")
                scene_files[num] = (video_found, "video")
            else:
                # look for k_image.png, k_image.jpg, k_image.jpeg, or k.png, k.jpg, k.jpeg
                image_found = None
                for ext in [".png", ".jpg", ".jpeg"]:
                    for pattern in [f"{k}_image{ext}", f"{k}{ext}"]:
                        test_path = input_dir / pattern
                        if test_path.exists():
                            image_found = test_path
                            break
                    if image_found:
                        break
                if not image_found:
                    raise FileNotFoundError(f"Missing required image file for Scene {num} in {input_dir}: {k}_image.png or {k}.png")
                scene_files[num] = (image_found, "image")

        # 2. Synthesize individual scene voiceovers and determine durations
        audio_temp_dir = input_dir / "temp_audio"
        audio_temp_dir.mkdir(parents=True, exist_ok=True)

        scene_clips = []
        raw_video_clips = []
        audio_clips = []
        current_t = 0.0

        for scene in plan.scenes:
            num = scene["scene_number"]
            text = scene.get("voiceover_hindi", "").strip()
            file_path, asset_type = scene_files[num]

            use_video_audio = False
            raw_clip = None

            # 2a. If it's a video, load it first and check if it has audio
            if asset_type == "video":
                try:
                    raw_clip = VideoFileClip(str(file_path))
                    raw_video_clips.append(raw_clip)
                    video_dur = raw_clip.duration
                    if raw_clip.audio is not None:
                        use_video_audio = True
                except Exception as exc:
                    LOGGER.error("Could not load video file %s: %s", file_path, exc)
                    raise

            # 2b. Synthesize TTS only if we are not using the video's built-in audio
            tts_dur = 0.0
            tts_path = audio_temp_dir / f"scene_{num}.mp3"
            
            if not use_video_audio:
                parent_tts = input_dir / f"scene_{num}.mp3"
                if parent_tts.exists():
                    import shutil
                    try:
                        shutil.copy2(parent_tts, tts_path)
                    except Exception as exc:
                        LOGGER.warning("Could not copy pre-generated TTS for scene %s: %s", num, exc)
                
                if not tts_path.exists() or tts_path.stat().st_size == 0:
                    tts_engine.synthesize_scene(text, tts_path)

                if not tts_path.exists() or tts_path.stat().st_size == 0:
                    tts_dur = 13.0 if is_long else (6.0 if kids_mode == "veo" else 6.0)
                    LOGGER.warning("TTS failed for scene %s, using fallback duration %s", num, tts_dur)
                else:
                    try:
                        temp_audio = AudioFileClip(str(tts_path))
                        tts_dur = temp_audio.duration
                        temp_audio.close()
                    except Exception as exc:
                        LOGGER.warning("Could not read TTS duration, using fallback: %s", exc)
                        tts_dur = 13.0 if is_long else (6.0 if kids_mode == "veo" else 6.0)

            # 2c. Build visual and audio tracks for the scene
            if asset_type == "video":
                if use_video_audio:
                    scene_dur = video_dur
                    resized_clip = self._fit_video_clip(raw_clip, vid_w, vid_h)
                    scene_clip = resized_clip.subclipped(0, scene_dur)
                    if scene_clip.audio is not None:
                        audio_clips.append(scene_clip.audio.with_start(current_t))
                else:
                    # Strip audio, use TTS fallback
                    stripped_raw_clip = raw_clip.without_audio()
                    scene_dur = max(video_dur, tts_dur + 0.5)
                    resized_clip = self._fit_video_clip(stripped_raw_clip, vid_w, vid_h)
                    
                    if video_dur < scene_dur:
                        last_frame = resized_clip.get_frame(video_dur - 0.05)
                        freeze_dur = scene_dur - video_dur
                        freeze_clip = ImageClip(last_frame, duration=freeze_dur)
                        scene_clip = concatenate_videoclips([resized_clip, freeze_clip], method="compose")
                    else:
                        scene_clip = resized_clip.subclipped(0, scene_dur)
                        
                    if tts_path.exists() and tts_path.stat().st_size > 0:
                        try:
                            tts_audio_clip = AudioFileClip(str(tts_path)).with_start(current_t)
                            audio_clips.append(tts_audio_clip)
                        except Exception as exc:
                            LOGGER.warning("Could not load scene tts audio: %s", exc)
            else:
                # For Image
                scene_dur = tts_dur + 0.5
                scene_clip = self._image_to_clip(file_path, scene_dur, vid_w, vid_h, "IMAGE_FOR_ZOOM")
                if tts_path.exists() and tts_path.stat().st_size > 0:
                    try:
                        tts_audio_clip = AudioFileClip(str(tts_path)).with_start(current_t)
                        audio_clips.append(tts_audio_clip)
                    except Exception as exc:
                        LOGGER.warning("Could not load scene tts audio: %s", exc)

            # Update scene duration dynamically
            scene["duration_seconds"] = scene_dur
            scene_clips.append(scene_clip)
            current_t += scene_dur

        total_dur = current_t

        # 3. Concatenate base visual track
        video_base = concatenate_videoclips(scene_clips, method="compose")

        # 4. Compose final audio track
        final_audio = CompositeAudioClip(audio_clips)

        # 5. Overlays (cinematic gradient, title card, subtitles, progress bar)
        overlay   = self._build_gradient_overlay(total_dur, vid_w, vid_h)
        title_card = self._build_title_card(idea, total_dur, vid_w, vid_h)
        sub_clips  = self._build_subtitle_clips(plan.scenes, total_dur, vid_w, vid_h)
        progress   = self._build_progress_bar(total_dur, vid_w, vid_h)

        layers: list = [video_base, overlay]
        if title_card:
            layers.append(title_card)
        layers.extend(sub_clips)
        if progress:
            layers.append(progress)

        final = CompositeVideoClip(layers, size=(vid_w, vid_h))
        final = final.with_audio(final_audio)

        temp_audio = output_path.parent / f"{output_path.stem}_tmp_audio.m4a"
        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(temp_audio),
            remove_temp=False,
            threads=4,
            ffmpeg_params=["-movflags", "+faststart", "-crf", "21"],
            logger=None,
        )

        # Clean up moviepy clips
        for clip in scene_clips:
            clip.close()
        video_base.close()
        for r_clip in raw_video_clips:
            r_clip.close()
        for a_clip in audio_clips:
            a_clip.close()
        final_audio.close()
        final.close()

        # Clean up temp audio file
        if temp_audio.exists():
            import time
            for _ in range(5):
                try:
                    temp_audio.unlink()
                    break
                except Exception:
                    time.sleep(0.5)

        # Clean up temp audio dir
        try:
            import shutil
            shutil.rmtree(audio_temp_dir, ignore_errors=True)
        except Exception as exc:
            LOGGER.warning("Failed to clean up temp audio dir: %s", exc)

        LOGGER.info("Assembled kids video successfully: %s", output_path)
        return output_path

    # ═══════════════════════════════════════════════════════════════════════════
    #  IMAGE → VIDEO CLIP
    # ═══════════════════════════════════════════════════════════════════════════

    def _image_to_clip(
        self,
        img_path: Path,
        duration: float,
        vid_w: int,
        vid_h: int,
        gen_type: str,
    ):
        """Convert a DALL-E image to a video clip with motion effects."""
        try:
            pil_img = Image.open(str(img_path)).convert("RGB")
            pil_img = self._cover_crop(pil_img, vid_w, vid_h)
            arr = np.array(pil_img)

            clip = ImageClip(arr, duration=duration)

            if gen_type == "AI_VIDEO":
                clip = self._apply_ken_burns(clip, duration, vid_w, vid_h, style="pan-zoom")
            else:
                clip = self._apply_ken_burns(clip, duration, vid_w, vid_h, style="zoom-in")

            return clip
        except Exception as exc:
            LOGGER.warning("Image clip creation failed for %s: %s", img_path, exc)
            return self._gradient_clip(1, duration, vid_w, vid_h)

    def _apply_ken_burns(self, clip, duration: float, vid_w: int, vid_h: int, style: str = "zoom-in"):
        """
        AI_VIDEO   → Ken Burns: slow zoom + diagonal pan (feels like a moving scene)
        IMAGE_ZOOM → Simple slow zoom-in from 1.0 → 1.12
        """
        try:
            # Retrieve base frame and convert to PIL Image once outside make_frame for performance
            base_frame = clip.get_frame(0)
            pil_base = Image.fromarray(base_frame)

            if style == "pan-zoom":
                zoom_start = 1.08
                zoom_end   = 1.18
                pan_dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)]
                px, py = random.choice(pan_dirs)
                max_pan_x = int(vid_w * 0.06) * px
                max_pan_y = int(vid_h * 0.04) * py

                def make_frame(t: float):
                    ratio  = t / max(duration, 1.0)
                    zoom   = zoom_start + (zoom_end - zoom_start) * ratio
                    ox     = int(max_pan_x * ratio)
                    oy     = int(max_pan_y * ratio)
                    new_w  = int(vid_w * zoom)
                    new_h  = int(vid_h * zoom)
                    pil    = pil_base.resize((new_w, new_h), Image.BILINEAR)
                    cx     = (new_w - vid_w) // 2 + ox
                    cy     = (new_h - vid_h) // 2 + oy
                    cx     = max(0, min(cx, new_w - vid_w))
                    cy     = max(0, min(cy, new_h - vid_h))
                    cropped = pil.crop((cx, cy, cx + vid_w, cy + vid_h))
                    return np.array(cropped)

                from moviepy import VideoClip
                return VideoClip(make_frame, duration=duration)

            else:  # zoom-in
                zoom_start = 1.0
                zoom_end   = 1.12

                def make_frame_zoom(t: float):
                    ratio = t / max(duration, 1.0)
                    zoom  = zoom_start + (zoom_end - zoom_start) * ratio
                    new_w = int(vid_w * zoom)
                    new_h = int(vid_h * zoom)
                    pil   = pil_base.resize((new_w, new_h), Image.BILINEAR)
                    cx    = (new_w - vid_w) // 2
                    cy    = (new_h - vid_h) // 2
                    cropped = pil.crop((cx, cy, cx + vid_w, cy + vid_h))
                    return np.array(cropped)

                from moviepy import VideoClip
                return VideoClip(make_frame_zoom, duration=duration)

        except Exception as exc:
            LOGGER.warning("Ken Burns effect failed: %s", exc)
            return clip

    @staticmethod
    def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Resize image to cover the canvas, then center-crop."""
        img_ratio    = img.width / img.height
        target_ratio = target_w / target_h
        if img_ratio > target_ratio:
            new_h = target_h
            new_w = int(img.width * (target_h / img.height))
        else:
            new_w = target_w
            new_h = int(img.height * (target_w / img.width))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))

    @staticmethod
    def _fit_video_clip(clip, vid_w: int, vid_h: int):
        """Resizes a VideoClip to cover target_w x target_h, cropping if necessary."""
        clip = clip.resized(height=vid_h)
        if clip.w < vid_w:
            clip = clip.resized(width=vid_w)
        clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=vid_w, height=vid_h)
        return clip

    # ═══════════════════════════════════════════════════════════════════════════
    #  GRADIENT FALLBACK CLIP
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _gradient_clip(scene_num: int, duration: float, vid_w: int, vid_h: int):
        scene_colors = [
            (255, 180, 80),   # warm orange
            (80, 180, 255),   # sky blue
            (100, 220, 120),  # grass green
            (220, 140, 255),  # celebration purple
        ]
        color = scene_colors[(scene_num - 1) % 4]
        return ColorClip(size=(vid_w, vid_h), color=color, duration=duration)

    # ═══════════════════════════════════════════════════════════════════════════
    #  AUDIO HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _load_voice(audio_path: Path, total_dur: float) -> AudioFileClip:
        try:
            clip = AudioFileClip(str(audio_path))
            if clip.duration > total_dur:
                clip = clip.subclipped(0, total_dur)
            return clip
        except Exception as exc:
            LOGGER.warning("Could not load voice audio %s: %s", audio_path, exc)
            from moviepy import AudioClip
            return AudioClip(lambda t: [0], duration=total_dur)

    # ═══════════════════════════════════════════════════════════════════════════
    #  CINEMATIC GRADIENT OVERLAY
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_gradient_overlay(duration: float, vid_w: int, vid_h: int) -> ImageClip:
        img  = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        for y in range(int(vid_h * 0.25)):
            alpha = int(150 * (1 - y / (vid_h * 0.25)))
            draw.line([(0, y), (vid_w, y)], fill=(0, 0, 0, alpha))
        bottom_start = int(vid_h * 0.60)
        for y in range(bottom_start, vid_h):
            alpha = int(180 * ((y - bottom_start) / (vid_h - bottom_start)))
            draw.line([(0, y), (vid_w, y)], fill=(0, 0, 0, alpha))
        return ImageClip(np.array(img), duration=duration)

    # ═══════════════════════════════════════════════════════════════════════════
    #  TITLE CARD  (top, first 3 s)
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_title_card(self, idea: KidsStoryIdea, total_dur: float, vid_w: int, vid_h: int):
        title    = idea.title[:50]
        font_sz  = 52 if vid_w == LONG_W else 58
        font     = self._load_font(font_sz)
        wrapped  = self._wrap_text(title.upper(), font, int(vid_w * 0.85))

        img  = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        y_pos = 60 if vid_w == LONG_W else 80
        draw.multiline_text(
            (vid_w // 2, y_pos),
            wrapped,
            font=font,
            fill="#FFE066",
            align="center",
            anchor="ma",
            stroke_width=6,
            stroke_fill="#1a1a1a",
            spacing=8,
        )

        clip = (
            ImageClip(np.array(img))
            .with_duration(min(3.5, total_dur * 0.15))
        )
        try:
            clip = clip.with_effects([vfx.CrossFadeIn(0.3), vfx.CrossFadeOut(0.4)])
        except Exception:
            pass
        return clip

    # ═══════════════════════════════════════════════════════════════════════════
    #  CAPCUT-STYLE HINDI SUBTITLES
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_subtitle_clips(
        self,
        scenes: list[dict],
        total_dur: float,
        vid_w: int,
        vid_h: int,
    ) -> list:
        """
        Render Hindi voiceover text as word-by-word CapCut-style subtitles.
        Distributes words evenly across each scene's duration.
        """
        clips  = []
        cursor = 0.0

        for scene in scenes:
            text     = scene.get("voiceover_hindi", "").strip()
            dur      = float(scene["duration_seconds"])
            scene_start = cursor
            cursor  += dur

            if not text:
                continue

            words  = text.split()
            if not words:
                continue

            groups    = [words[i:i+2] for i in range(0, len(words), 2)]
            group_dur = dur / max(len(groups), 1)

            for gi, group in enumerate(groups):
                group_text  = " ".join(group).upper()
                g_start     = scene_start + gi * group_dur
                g_end       = min(g_start + group_dur, scene_start + dur)
                if g_end <= g_start:
                    continue

                is_keyword = any(w.lower() in KIDS_VIRAL_KEYWORDS for w in group)
                txt_color  = "#FFE066" if is_keyword else "#FFFFFF"

                card = self._render_word_card(group_text, vid_w, txt_color, is_keyword)
                y_pos = int(vid_h * 0.82) - card.shape[0] // 2

                clip = (
                    ImageClip(card)
                    .with_start(g_start)
                    .with_duration(g_end - g_start)
                    .with_position(("center", y_pos))
                )
                try:
                    clip = clip.resized(lambda t: min(1.0, 0.78 + t * 2.2))
                except Exception:
                    pass
                clips.append(clip)

        return clips

    def _render_word_card(
        self,
        text: str,
        vid_w: int,
        text_color: str,
        is_keyword: bool,
    ) -> np.ndarray:
        font    = self._load_font(72 if vid_w == LONG_W else 78)
        padding = 18
        stroke  = 8

        tmp  = Image.new("RGBA", (vid_w, 300), (0, 0, 0, 0))
        d    = ImageDraw.Draw(tmp)
        bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw   = min(int(bbox[2] - bbox[0]) + padding * 2, vid_w - 40)
        th   = max(int(bbox[3] - bbox[1]) + padding * 2, 70)

        img  = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        if is_keyword:
            draw.rounded_rectangle((0, 0, tw - 1, th - 1), radius=20, fill=(20, 20, 20, 170))

        draw.text(
            (tw // 2, th // 2),
            text,
            font=font,
            fill=text_color,
            anchor="mm",
            stroke_width=stroke,
            stroke_fill="#000000",
        )
        return np.array(img)

    # ═══════════════════════════════════════════════════════════════════════════
    #  PROGRESS BAR
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_progress_bar(duration: float, vid_w: int, vid_h: int):
        bar_h  = 6
        bar_y  = vid_h - bar_h - 2
        accent = (255, 224, 102, 255)

        def make_frame(t: float):
            progress = min(t / duration, 1.0)
            img      = Image.new("RGBA", (vid_w, bar_h), (60, 60, 60, 100))
            draw     = ImageDraw.Draw(img)
            draw.rectangle([(0, 0), (int(vid_w * progress), bar_h)], fill=accent)
            return np.array(img)

        from moviepy import VideoClip
        return VideoClip(make_frame, duration=duration).with_position(("left", bar_y))

    # ═══════════════════════════════════════════════════════════════════════════
    #  FONT HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _load_font(self, size: int) -> ImageFont.ImageFont:
        if self.config.font_file.exists():
            try:
                return ImageFont.truetype(str(self.config.font_file), size=size)
            except Exception:
                pass
        for candidate in [
            Path("C:/Windows/Fonts/impact.ttf"),
            Path("C:/Windows/Fonts/ariblk.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]:
            if candidate.exists():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        lines:   list[str] = []
        words    = text.split()
        if not words:
            return text
        current  = words[0]
        for word in words[1:]:
            test = f"{current} {word}"
            try:
                w = font.getlength(test)
            except Exception:
                w = len(test) * 14
            if w <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return "\n".join(lines)
