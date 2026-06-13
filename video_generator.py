"""
video_generator.py  –  DailyFitX  (Upgraded for max viewer retention)
======================================================================
Key upgrades vs previous version:
  • CapCut-style word-by-word subtitles with bold highlight + pop animation
  • Cinematic dark-gradient overlay on ALL footage (makes stock look premium)
  • Smart progress bar at bottom (drives watch-time completion)
  • Intro hook card: first 1.8s = full-screen hook text only → stops scroll
  • Multi-layer visual cuts: 2-3s per clip (faster = higher retention)
  • Colour-graded badge system & title card
  • Smarter local video matching (50+ clips library)
  • Pexels + Pixabay fallback with better queries
"""
from __future__ import annotations

import logging
import math
import random
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import urllib.parse
import uuid
import time
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

from config import AppConfig
from script_generator import VideoScript
from subtitle_generator import SubtitleArtifact


LOGGER = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
SHORTS_W, SHORTS_H = 1080, 1920
LONG_W,   LONG_H   = 1920, 1080

# Viral keywords shown in yellow instead of white
VIRAL_KEYWORDS = {
    "workout", "gym", "fitness", "muscle", "discipline", "mindset", "grind",
    "power", "strength", "success", "motivation", "beast", "hard", "work",
    "stop", "fail", "win", "growth", "results", "believe", "impossible",
    "routine", "secret", "truth", "money", "rich", "wealth", "healthy",
    "yoga", "meditation", "breath", "diet", "protein", "fat", "loss",
    "energy", "sleep", "gut", "fast", "cardio", "run", "squat", "push",
}


class VideoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    # ═══════════════════════════════════════════════════════════════════════
    #  PUBLIC ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════════

    def create_video(
        self,
        script: VideoScript,
        audio_path: Path,
        subtitles: SubtitleArtifact,
        output_path: Path,
    ) -> Path:
        LOGGER.info("Creating video at %s", output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        is_long = getattr(script, "video_type", "short") == "long"
        vid_w   = LONG_W   if is_long else SHORTS_W
        vid_h   = LONG_H   if is_long else SHORTS_H

        # ── Audio (voice only — no background music) ──────────────────────
        final_audio = AudioFileClip(str(audio_path))
        total_dur   = final_audio.duration

        # ── Visual layers ─────────────────────────────────────────────────
        background  = self._build_base_visual(script, total_dur, vid_w, vid_h)
        overlay     = self._build_cinematic_overlay(total_dur, vid_w, vid_h)
        intro_card  = self._build_intro_hook_card(script, total_dur, vid_w, vid_h)
        title_clip  = self._build_title_clip(script, total_dur, vid_w, vid_h)
        sub_clips   = self._build_capcut_subtitles(subtitles.segments, total_dur, script, vid_w, vid_h)
        progress    = self._build_progress_bar(total_dur, vid_w, vid_h)

        layers = [background, overlay]
        if intro_card:
            layers.append(intro_card)
        if title_clip:
            layers.append(title_clip)
        layers.extend(sub_clips)
        if progress:
            layers.append(progress)

        final = CompositeVideoClip(layers, size=(vid_w, vid_h))
        final = final.with_audio(final_audio)

        temp_audio_path = output_path.parent / f"{output_path.stem}_temp_audio.mp4"
        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(temp_audio_path),
            threads=4,
            ffmpeg_params=["-movflags", "+faststart", "-crf", "22"],
            logger=None,
        )
        return output_path

    # ═══════════════════════════════════════════════════════════════════════
    #  BACKGROUND VIDEO
    # ═══════════════════════════════════════════════════════════════════════

    def _build_base_visual(self, script: VideoScript, duration: float, vid_w: int, vid_h: int):
        return self._build_pexels_background(script, duration, vid_w, vid_h)

    def _build_pexels_background(self, script, duration, vid_w, vid_h):
        is_long = vid_w == LONG_W
        queries = self._build_visual_queries(script)
        clips   = []
        # Aim for a cut every 2.0 to 3.0s for Shorts (medium/fast), every 3.0 to 4.0s for Long
        target_clips = max(3, int(duration / (3.5 if is_long else 2.5)))

        # 1. Try to fetch fresh Pexels/Pixabay clips matching the topic queries
        for query in queries:
            if len(clips) >= target_clips:
                break
            path = self._fetch_pexels_video(query, is_long=is_long)
            if path is None:
                path = self._fetch_pixabay_video(query)
            if path and path.exists():
                try:
                    clip = VideoFileClip(str(path)).without_audio()
                    
                    # Snappy pacing (medium/fast cut duration)
                    cut_dur = random.uniform(3.0, 4.0) if is_long else random.uniform(2.0, 3.0)
                    if clip.duration > cut_dur:
                        start_t = random.uniform(0.0, clip.duration - cut_dur)
                        clip = clip.subclipped(start_t, start_t + cut_dur)
                    
                    clip = self._fit_clip(clip, vid_w, vid_h)
                    clip = self._apply_ken_burns(clip)
                    clips.append(clip)
                except Exception as exc:
                    LOGGER.warning("Clip load failed: %s", exc)

        # 2. Fallback/Fill: If we don't have enough clips, pull from the cached backgrounds
        if len(clips) < target_clips:
            bg_dir = self.config.background_assets_dir
            if bg_dir.exists():
                cached_files = [
                    p for p in bg_dir.iterdir()
                    if p.suffix.lower() in {".mp4", ".mov", ".mkv"}
                ]
                if cached_files:
                    random.shuffle(cached_files)
                    for path in cached_files:
                        if len(clips) >= target_clips:
                            break
                        try:
                            clip = VideoFileClip(str(path)).without_audio()
                            
                            # Snappy pacing (medium/fast cut duration)
                            cut_dur = random.uniform(3.0, 4.0) if is_long else random.uniform(2.0, 3.0)
                            if clip.duration > cut_dur:
                                start_t = random.uniform(0.0, clip.duration - cut_dur)
                                clip = clip.subclipped(start_t, start_t + cut_dur)
                            
                            clip = self._fit_clip(clip, vid_w, vid_h)
                            clip = self._apply_ken_burns(clip)
                            clips.append(clip)
                        except Exception as exc:
                            pass

        if not clips:
            return self._gradient_fallback(script, duration, vid_w, vid_h)
        return self._loop_clips_to_duration(clips, duration)

    # ═══════════════════════════════════════════════════════════════════════
    #  CINEMATIC OVERLAY  (dark gradient top + bottom)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_cinematic_overlay(self, duration: float, vid_w: int, vid_h: int):
        """Adds a dark vignette/gradient overlay so text always pops."""
        img = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        # Top gradient (for title / hook text area)
        for y in range(int(vid_h * 0.35)):
            alpha = int(180 * (1 - y / (vid_h * 0.35)))
            draw.line([(0, y), (vid_w, y)], fill=(0, 0, 0, alpha))

        # Bottom gradient (for subtitle area)
        bottom_start = int(vid_h * 0.55)
        for y in range(bottom_start, vid_h):
            alpha = int(200 * ((y - bottom_start) / (vid_h - bottom_start)))
            draw.line([(0, y), (vid_w, y)], fill=(0, 0, 0, alpha))

        arr = np.array(img)
        return ImageClip(arr, duration=duration)

    # ═══════════════════════════════════════════════════════════════════════
    #  INTRO HOOK CARD  – stops scroll in first 2 seconds
    # ═══════════════════════════════════════════════════════════════════════

    def _build_intro_hook_card(self, script: VideoScript, duration: float, vid_w: int, vid_h: int):
        if duration < 3:
            return None
        hook_text = script.hook.strip()
        if not hook_text:
            return None

        # Shorten to first punchy line
        first_line = hook_text.split(".")[0].split("!")[0].split("?")[0].strip()
        words = first_line.split()
        display = " ".join(words[:8]).upper()
        if not display:
            return None

        is_long = vid_w == LONG_W
        card_w  = int(vid_w * 0.9)

        img = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        # Accent bar
        accent = self._style_accent(script)
        bar_h = 6
        bar_y = int(vid_h * 0.42)
        draw.rectangle([(int(vid_w * 0.05), bar_y), (int(vid_w * 0.95), bar_y + bar_h)], fill=accent["primary"])

        # Hook text
        font_size = 72 if is_long else 82
        font = self._load_font(font_size)
        wrapped = self._wrap_text(display, font, card_w - 60)

        # Shadow
        self._draw_text_shadow(draw, (vid_w // 2, int(vid_h * 0.44) + bar_h + 10), wrapped, font, anchor="ma")
        draw.multiline_text(
            (vid_w // 2, int(vid_h * 0.44) + bar_h + 10),
            wrapped,
            font=font,
            fill=accent["text"],
            align="center",
            anchor="ma",
            stroke_width=5,
            stroke_fill="#000000",
            spacing=12,
        )

        # Sub-label: "SWIPE UP" or emoji pulse
        sub_font = self._load_font(34)
        draw.text(
            (vid_w // 2, int(vid_h * 0.75)),
            "👇 WATCH TILL END 👇",
            font=sub_font,
            fill=(255, 255, 255, 220),
            anchor="mm",
            stroke_width=3,
            stroke_fill="#000000",
        )

        arr = np.array(img)
        clip = ImageClip(arr).with_duration(min(2.2, duration * 0.12))

        # Fade out
        clip = clip.with_effects([vfx.CrossFadeOut(0.4)])
        return clip

    # ═══════════════════════════════════════════════════════════════════════
    #  CAPCUT-STYLE WORD-BY-WORD SUBTITLES  ← BIGGEST RETENTION BOOST
    # ═══════════════════════════════════════════════════════════════════════

    def _build_capcut_subtitles(
        self,
        segments: list[dict],
        total_duration: float,
        script: VideoScript,
        vid_w: int,
        vid_h: int,
    ) -> list:
        """
        Renders word-by-word subtitles in CapCut/TikTok style:
        - 1–3 words shown at a time (very fast word flashes)
        - Current segment highlighted in bright yellow / accent color
        - Bold black stroke for readability on ANY background
        - Bounce/pop-in animation per word
        """
        is_long  = vid_w == LONG_W
        accent   = self._style_accent(script)

        # Sub-zone vertical position (bottom safe area)
        sub_y_center = int(vid_h * 0.82) if is_long else int(vid_h * 0.80)
        card_max_w   = int(vid_w * 0.86)

        font_size    = 70 if is_long else 76
        font         = self._load_font(font_size)

        clips = []
        for seg in segments:
            text  = seg.get("text", "").strip()
            if not text:
                continue
            start = float(seg.get("start", 0))
            end   = min(float(seg.get("end", start + 1.5)), total_duration)
            if end <= start:
                continue

            words   = text.upper().split()
            seg_dur = end - start

            # Split words into micro-groups of 2
            groups = [words[i:i+2] for i in range(0, len(words), 2)]
            if not groups:
                continue
            group_dur = max(seg_dur / len(groups), 0.18)

            for gi, group in enumerate(groups):
                group_text = " ".join(group)
                group_start = start + gi * group_dur
                group_end   = min(group_start + group_dur, end)
                if group_end <= group_start:
                    continue

                # Decide color: yellow for viral keywords, white otherwise
                is_viral = any(w.lower() in VIRAL_KEYWORDS for w in group)
                txt_color = accent["highlight"] if is_viral else "#FFFFFF"

                card = self._render_capcut_word_card(
                    text=group_text,
                    font=font,
                    max_width=card_max_w,
                    text_color=txt_color,
                    is_viral=is_viral,
                )

                clip = (
                    ImageClip(card)
                    .with_start(group_start)
                    .with_duration(group_end - group_start)
                    .with_position(("center", sub_y_center - card.shape[0] // 2))
                )

                # Pop-in scale animation
                try:
                    clip = clip.resized(lambda t: min(1.0, 0.75 + t * 2.0))
                except Exception:
                    pass

                clips.append(clip)

        return clips

    def _render_capcut_word_card(
        self,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
        text_color: str,
        is_viral: bool,
    ) -> np.ndarray:
        """Renders a single word-group subtitle card with thick stroke."""
        padding = 16
        stroke  = 7

        # Measure text
        tmp = Image.new("RGBA", (max_width + 200, 400), (0, 0, 0, 0))
        d   = ImageDraw.Draw(tmp)
        bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw   = bbox[2] - bbox[0] + padding * 2
        th   = bbox[3] - bbox[1] + padding * 2
        tw   = min(tw, max_width + 40)
        th   = max(th, 60)

        img  = Image.new("RGBA", (int(tw), int(th)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        # Optional pill background for viral words
        if is_viral:
            draw.rounded_rectangle(
                (0, 0, tw - 1, th - 1),
                radius=18,
                fill=(20, 20, 20, 160),
            )

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

    # ═══════════════════════════════════════════════════════════════════════
    #  PROGRESS BAR
    # ═══════════════════════════════════════════════════════════════════════

    def _build_progress_bar(self, duration: float, vid_w: int, vid_h: int):
        """Thin animated bar at the very bottom – proven to increase completion rate."""
        bar_h  = 5
        bar_y  = vid_h - bar_h - 2
        accent = (250, 204, 21, 255)   # yellow

        def make_frame(t: float) -> np.ndarray:
            progress = min(t / duration, 1.0)
            img = Image.new("RGBA", (vid_w, bar_h), (50, 50, 50, 120))
            draw = ImageDraw.Draw(img)
            draw.rectangle([(0, 0), (int(vid_w * progress), bar_h)], fill=accent)
            return np.array(img)

        # Build it as a sequence of frames rendered at keyframes
        # Use a simple ImageClip that repositions over time via with_position
        frames = []
        keyframe_count = max(int(duration * 5), 30)   # 5fps is enough for progress bar
        for i in range(keyframe_count):
            t = i * duration / keyframe_count
            frames.append(make_frame(t))

        # Concatenate tiny clips
        bar_clips = []
        kf_dur = duration / keyframe_count
        for i, frame in enumerate(frames):
            c = (
                ImageClip(frame)
                .with_start(i * kf_dur)
                .with_duration(kf_dur)
                .with_position(("left", bar_y))
            )
            bar_clips.append(c)

        return CompositeVideoClip(bar_clips, size=(vid_w, bar_h)).with_position(("left", bar_y))

    # ═══════════════════════════════════════════════════════════════════════
    #  TITLE / OVERLAY TEXT  (top of screen, first 3s)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_title_clip(self, script: VideoScript, duration: float, vid_w: int, vid_h: int):
        title = (getattr(script, "overlay_text", "") or script.title).strip()
        if not title:
            return None
        # Clean to max 5 words
        words = re.sub(r"[^\w\s?!]", " ", title).split()
        display = " ".join(words[:5]).strip()
        if not display:
            return None

        is_long = vid_w == LONG_W
        accent  = self._style_accent(script)
        font_size = 42 if is_long else 38

        card = self._render_text_card(
            text=display,
            width=int(vid_w * 0.75),
            font_size=font_size,
            text_color=accent["text"],
            bg_color=(0, 0, 0, 0),
            stroke_color="#000000",
            stroke_width=3,
            padding=8,
        )
        y_pos = 80 if is_long else 110
        clip_dur = min(duration, 3.5)
        clip = (
            ImageClip(card)
            .with_position(("center", y_pos))
            .with_duration(clip_dur)
        )
        try:
            clip = clip.with_effects([vfx.CrossFadeIn(0.3)])
        except Exception:
            pass
        return clip

    # ═══════════════════════════════════════════════════════════════════════
    # Background music removed

    # ═══════════════════════════════════════════════════════════════════════
    #  PEXELS / PIXABAY FETCH
    # ═══════════════════════════════════════════════════════════════════════

    def _build_visual_queries(self, script: VideoScript) -> list[str]:
        style = self._visual_style(script)
        keyword = (script.primary_keyword or "gym motivation").strip()
        title_tokens = re.sub(r"[^a-zA-Z0-9\s]", " ", script.title).split()
        title_phrase = " ".join(title_tokens[:5]).strip()

        if style == "yoga":
            base = [
                f"{keyword} yoga flow",
                f"{title_phrase} yoga stretch",
                "woman yoga sunrise vertical",
                "man yoga breathing vertical",
                "yoga meditation portrait",
                "yoga posture woman",
                "calm yoga stretch",
                "mindful meditation",
            ]
        elif style in ("diet", "health"):
            base = [
                f"{keyword} healthy lifestyle",
                "healthy food fitness",
                "woman wellness workout vertical",
                "man wellness fitness",
                "nutrition healthy eating",
                "fitness lifestyle motivation",
            ]
        else:
            base = [
                f"{keyword} cinematic workout",
                f"{keyword} athlete gym",
                f"{title_phrase} fitness",
                "woman gym workout vertical",
                "man gym workout vertical",
                "female fitness intense",
                "male fitness intense",
                "home workout motivation",
                "hiit fitness motivation",
                "gym training athlete",
            ]

        deduped: list[str] = []
        for item in base:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if cleaned and cleaned.lower() not in {v.lower() for v in deduped}:
                deduped.append(cleaned)
        random.shuffle(deduped)
        return deduped[:8]

    def _fetch_pexels_video(self, query: str, is_long: bool = False) -> Path | None:
        if not self.config.pexels_api_key:
            return None
        try:
            orientation = "landscape" if is_long else "portrait"
            url = (
                f"https://api.pexels.com/videos/search"
                f"?query={urllib.parse.quote(query)}"
                f"&orientation={orientation}&size=medium&per_page=15"
            )
            resp = requests.get(url, headers={"Authorization": self.config.pexels_api_key}, timeout=15)
            if resp.status_code == 200:
                videos = resp.json().get("videos", [])
                if videos:
                    choice = random.choice(videos[:min(len(videos), 10)])
                    files  = choice.get("video_files", [])
                    # Prefer 720p–1080p (fast + good quality)
                    hd = [f for f in files if 720 <= f.get("height", 0) <= 1920]
                    best = (
                        hd[0] if hd
                        else sorted(files, key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)[0]
                        if files else None
                    )
                    if best:
                        dl   = requests.get(best["link"], timeout=45)
                        out  = self.config.background_assets_dir / f"pexels_{uuid.uuid4().hex[:6]}.mp4"
                        out.write_bytes(dl.content)
                        return out
        except Exception as exc:
            LOGGER.warning("Pexels fetch failed for '%s': %s", query, exc)
        return None

    def _fetch_pixabay_video(self, query: str, is_long: bool = False) -> Path | None:
        if not self.config.pixabay_api_key:
            return None
        try:
            url = (
                f"https://pixabay.com/api/videos/"
                f"?key={self.config.pixabay_api_key}"
                f"&q={urllib.parse.quote(query)}&video_type=film&per_page=10"
            )
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    choice = random.choice(hits[:min(len(hits), 8)])
                    best   = choice["videos"].get("large", {}).get("url") or choice["videos"].get("medium", {}).get("url")
                    if best:
                        dl  = requests.get(best, timeout=60)
                        out = self.config.background_assets_dir / f"pixabay_{uuid.uuid4().hex[:6]}.mp4"
                        out.write_bytes(dl.content)
                        return out
        except Exception as exc:
            LOGGER.warning("Pixabay fetch failed for '%s': %s", query, exc)
        return None

    # ═══════════════════════════════════════════════════════════════════════


    def _iter_background_assets(self) -> Iterable[Path]:
        bg_dir = self.config.background_assets_dir
        if not bg_dir.exists():
            return []
        assets = [
            p for p in bg_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".mkv"}
        ]
        random.shuffle(assets)
        return assets[:8]

    # ═══════════════════════════════════════════════════════════════════════
    #  CLIP HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _fit_clip(clip, vid_w: int, vid_h: int):
        try:
            # Speed up the clip playback by 1.3x to make the action snappy and energetic
            clip = clip.multiply_speed(1.3)
        except Exception:
            pass
        clip = clip.resized(height=vid_h)
        if clip.w < vid_w:
            clip = clip.resized(width=vid_w)
        clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=vid_w, height=vid_h)
        return clip

    @staticmethod
    def _apply_ken_burns(clip, zoom_rate: float = 0.015):
        """Slow zoom-in Ken Burns effect – makes static clips dynamic."""
        try:
            clip = clip.resized(lambda t: 1.0 + zoom_rate * t)
        except Exception:
            pass
        return clip

    @staticmethod
    def _loop_clips_to_duration(clips: list, duration: float):
        if not clips:
            return None
        sequence = list(clips)
        total = sum(c.duration for c in sequence)
        while total < duration:
            sequence.extend(clips)
            total += sum(c.duration for c in clips)
        combined = concatenate_videoclips(sequence, method="compose")
        return combined.subclipped(0, duration)

    def _gradient_fallback(self, script, duration, vid_w, vid_h):
        arr = self._render_gradient_background(script, vid_w, vid_h)
        return ImageClip(arr, duration=duration)

    # ═══════════════════════════════════════════════════════════════════════
    #  RENDERING HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _render_gradient_background(self, script: VideoScript, vid_w: int, vid_h: int) -> np.ndarray:
        accent = self._style_accent(script)
        img    = Image.new("RGBA", (vid_w, vid_h), "#091a2f")
        draw   = ImageDraw.Draw(img, "RGBA")
        # Radial glow spots
        draw.ellipse((vid_w - 360, 80,  vid_w + 60,  540), fill=(*accent["glow1"], 60))
        draw.ellipse((-80,         300, 300,          660), fill=(*accent["glow2"], 55))
        return np.array(img)

    def _render_text_card(
        self,
        text: str,
        width: int,
        font_size: int,
        text_color: str,
        bg_color: tuple,
        stroke_color: str,
        stroke_width: int,
        padding: int,
    ) -> np.ndarray:
        font    = self._load_font(font_size)
        wrapped = self._wrap_text(text, font, width - padding * 2)
        temp    = Image.new("RGBA", (width, 2000), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(temp)
        bbox    = draw.multiline_textbbox(
            (padding, padding), wrapped, font=font, spacing=10, align="center", stroke_width=stroke_width
        )
        height  = int(bbox[3] - bbox[1] + padding * 2)
        height  = max(height, 40)
        img     = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(img, "RGBA")
        if bg_color and len(bg_color) == 4 and bg_color[3] > 0:
            draw.rounded_rectangle((0, 0, width, height), radius=22, fill=bg_color)
        draw.multiline_text(
            (width / 2, padding), wrapped, font=font,
            fill=text_color, spacing=10, align="center", anchor="ma",
            stroke_width=stroke_width, stroke_fill=stroke_color,
        )
        return np.array(img)

    @staticmethod
    def _draw_text_shadow(draw, pos, text, font, anchor="mm", offset=4, alpha=140):
        sx, sy = pos[0] + offset, pos[1] + offset
        draw.multiline_text(
            (sx, sy), text, font=font,
            fill=(0, 0, 0, alpha), anchor=anchor, align="center",
        )

    def _render_badge(self, text: str, fill: tuple, text_color: str) -> np.ndarray:
        font = self._load_alt_font(28)
        tmp  = Image.new("RGBA", (500, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tmp, "RGBA")
        bbox = draw.textbbox((24, 18), text, font=font)
        w    = int(bbox[2] - bbox[0] + 48)
        h    = int(bbox[3] - bbox[1] + 34)
        img  = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        draw.rounded_rectangle((0, 0, w, h), radius=h // 2, fill=fill)
        draw.text((w / 2, h / 2), text, font=font, fill=text_color, anchor="mm")
        return np.array(img)

    # ═══════════════════════════════════════════════════════════════════════
    #  FONT LOADERS
    # ═══════════════════════════════════════════════════════════════════════

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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

    def _load_alt_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for candidate in [
            Path("C:/Windows/Fonts/seguisb.ttf"),
            Path("C:/Windows/Fonts/segoesc.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]:
            if candidate.exists():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except Exception:
                    continue
        return self._load_font(size)

    # ═══════════════════════════════════════════════════════════════════════
    #  TEXT UTILITIES
    # ═══════════════════════════════════════════════════════════════════════

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        lines: list[str] = []
        for paragraph in text.splitlines():
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = words[0]
            for word in words[1:]:
                test = f"{current} {word}"
                if self._text_width(test, font) <= max_width:
                    current = test
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return "\n".join(lines)

    @staticmethod
    def _text_width(text: str, font: ImageFont.ImageFont) -> int:
        try:
            left, _, right, _ = font.getbbox(text)
            return int(right - left)
        except Exception:
            return len(text) * 14   # fallback estimate

    # ═══════════════════════════════════════════════════════════════════════
    #  STYLE HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _visual_style(script: VideoScript) -> str:
        blob = f"{script.title} {script.primary_keyword} {script.full_script}".lower()
        yoga_terms   = {"yoga", "asana", "breath", "pranayam", "pranayama", "mobility", "meditation", "stretch"}
        diet_terms   = {"diet", "food", "protein", "calories", "fat loss", "weight loss", "eating", "meal", "nutrition"}
        health_terms = {"health", "gut", "digestion", "bloating", "sleep", "fatigue", "energy", "skin"}
        if any(t in blob for t in yoga_terms):   return "yoga"
        if any(t in blob for t in diet_terms):   return "diet"
        if any(t in blob for t in health_terms): return "health"
        return "fitness"

    @staticmethod
    def _style_accent(script: VideoScript) -> dict:
        style = VideoGenerator._visual_style(script)
        if style == "yoga":
            return {
                "primary":   (14, 165, 233, 255),    # sky blue
                "text":      "#f0f9ff",
                "highlight": "#fde68a",
                "glow1":     (14, 165, 233),
                "glow2":     (16, 185, 129),
            }
        if style in ("diet", "health"):
            return {
                "primary":   (16, 185, 129, 255),    # emerald
                "text":      "#f0fdf4",
                "highlight": "#fde68a",
                "glow1":     (16, 185, 129),
                "glow2":     (5, 150, 105),
            }
        # fitness / default – hot orange/red
        return {
            "primary":   (249, 115, 22, 255),
            "text":      "#fff7ed",
            "highlight": "#facc15",
            "glow1":     (220, 38, 38),
            "glow2":     (249, 115, 22),
        }

    @staticmethod
    def _is_romanized_script(script: VideoScript) -> bool:
        payload = f"{script.title} {script.full_script}"
        return all(ord(c) < 128 for c in payload)

    # ═══════════════════════════════════════════════════════════════════════
    #  LEGACY HELPERS (kept for backward compatibility with other modules)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_subtitle_clips(self, segments, duration, script):
        """Legacy – now routed to CapCut subtitles."""
        is_long = getattr(script, "video_type", "short") == "long"
        vid_w   = LONG_W if is_long else SHORTS_W
        vid_h   = LONG_H if is_long else SHORTS_H
        return self._build_capcut_subtitles(segments, duration, script, vid_w, vid_h)

    # Legacy background music method removed

    @staticmethod
    def _limit_subtitle_lines(text: str, max_words_per_line: int = 4) -> str:
        words = text.split()
        if not words:
            return ""
        lines = [
            " ".join(words[i:i + max_words_per_line])
            for i in range(0, len(words), max_words_per_line)
        ]
        return "\n".join(lines[:2])
