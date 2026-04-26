from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import urllib.parse
import uuid
import time
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
    vfx,
    afx,
)

from config import AppConfig
from script_generator import VideoScript
from subtitle_generator import SubtitleArtifact


LOGGER = logging.getLogger(__name__)


class VideoGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def create_video(
        self,
        script: VideoScript,
        audio_path: Path,
        subtitles: SubtitleArtifact,
        output_path: Path,
    ) -> Path:
        LOGGER.info("Creating vertical video at %s", output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        audio_clip = AudioFileClip(str(audio_path))
        
        bg_music_path = self._get_random_background_music()
        if bg_music_path:
            LOGGER.info("Adding background music: %s", bg_music_path.name)
            try:
                music_clip = AudioFileClip(str(bg_music_path)).with_volume_scaled(0.2)
                if music_clip.duration < audio_clip.duration:
                    import math
                    repeats = math.ceil(audio_clip.duration / max(music_clip.duration, 1.0))
                    music_clip = concatenate_audioclips([music_clip] * repeats)
                music_clip = music_clip.subclipped(0, audio_clip.duration)
                audio_clip = CompositeAudioClip([audio_clip, music_clip])
            except Exception as e:
                LOGGER.warning("Could not add background music: %s", e)

        background_clip = self._build_base_visual(script=script, duration=audio_clip.duration)
        subtitle_clips = self._build_subtitle_clips(subtitles.segments, audio_clip.duration, script=script)
        title_clip = self._build_title_clip(script, audio_clip.duration)
        extra_clips = self._build_story_clips(script, audio_clip.duration)

        is_long = getattr(script, 'video_type', 'short') == 'long'
        vid_w = 1920 if is_long else 1080
        vid_h = 1080 if is_long else 1920

        final = CompositeVideoClip([background_clip, title_clip, *subtitle_clips], size=(vid_w, vid_h))
        final = final.with_audio(audio_clip)

        final.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            ffmpeg_params=["-movflags", "+faststart"],
            logger=None,
        )
        return output_path

    def _build_base_visual(self, script: VideoScript, duration: float):
        is_long = getattr(script, 'video_type', 'short') == 'long'
        
        if is_long or getattr(self.config, 'use_pexels_for_shorts', False):
            return self._build_pexels_background(script, duration)

        local_video_clip = self._build_local_video_background(script=script, duration=duration)
        if local_video_clip is not None:
            return local_video_clip

        return self._build_background(script, duration)

    def _build_local_video_background(self, script: VideoScript, duration: float):
        assets = self._match_local_video_assets(script)
        if not assets:
            return None

        is_long = getattr(script, 'video_type', 'short') == 'long'
        vid_w = 1920 if is_long else 1080
        vid_h = 1080 if is_long else 1920

        clips = []
        for asset in assets:
            clip = VideoFileClip(str(asset))
            clip = clip.without_audio()
            clip = clip.resized(height=vid_h)
            if clip.w < vid_w:
                clip = clip.resized(width=vid_w)
            clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=vid_w, height=vid_h)
            clips.append(clip)

        if not clips:
            return None

        sequence = list(clips)
        total_duration = sum(clip.duration for clip in sequence)
        base_duration = max(total_duration, 0.1)
        while total_duration < duration:
            sequence.extend(clips)
            total_duration += base_duration

        combined = concatenate_videoclips(sequence, method="compose")
        return combined.subclipped(0, duration)

    def _build_visual_queries(self, script: VideoScript) -> list[str]:
        visual_style = self._visual_style(script)
        title_tokens = re.sub(r"[^a-zA-Z0-9\s]", " ", script.title).split()
        title_phrase = " ".join(title_tokens[:5]).strip()
        keyword = (script.primary_keyword or "gym motivation").strip()
        if visual_style == "yoga":
            candidates = [
                f"{keyword} sunrise yoga",
                f"{title_phrase} yoga flow",
                "woman yoga breathing portrait",
                "man yoga breathing portrait",
                "woman yoga breathing",
                "man yoga stretch",
                "calm yoga stretch cinematic",
                "mindful meditation body flow",
                "meditation portrait breathing",
                "yoga posture healing",
            ]
        else:
            candidates = [
                f"{keyword} cinematic workout",
                f"{keyword} athlete training",
                f"{title_phrase} gym",
                f"{title_phrase} fitness motivation",
                "female fitness workout portrait",
                "male fitness workout portrait",
                "woman home workout vertical",
                "man home workout vertical",
                "intense workout motivation",
                "athlete training",
            ]
        deduped: list[str] = []
        for item in candidates:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if cleaned and cleaned.lower() not in {value.lower() for value in deduped}:
                deduped.append(cleaned)
        random.shuffle(deduped)
        return deduped[:5]

    def _build_pexels_background(self, script: VideoScript, duration: float):
        queries = self._build_visual_queries(script)
        clips = []
        is_long = getattr(script, 'video_type', 'short') == 'long'
        vid_w = 1920 if is_long else 1080
        vid_h = 1080 if is_long else 1920
        
        for query in queries:
            path = self._fetch_pexels_video(query, is_long=is_long)
            if path is None:
                path = self._fetch_pixabay_video(query)
            if path and path.exists():
                clip = VideoFileClip(str(path)).without_audio()
                clip = clip.resized(height=vid_h)
                if clip.w < vid_w:
                    clip = clip.resized(width=vid_w)
                clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=vid_w, height=vid_h)
                
                # Dynamic zoom for engagement
                try:
                    clip = clip.resized(lambda t: 1.0 + (0.02 * t))
                except:
                    pass
                    
                clips.append(clip)
            if len(clips) >= (4 if is_long else 2):
                break
                
        if not clips:
            LOGGER.warning("Pexels failed to return videos, falling back to static background")
            return self._build_background(script, duration)
            
        sequence = list(clips)
        total_duration = sum(clip.duration for clip in sequence)
        base_duration = max(total_duration, 0.1)
        
        while total_duration < duration:
            sequence.extend(clips)
            total_duration += base_duration
            
        combined = concatenate_videoclips(sequence, method="compose")
        return combined.subclipped(0, duration)

    def _generate_veo_video(self, prompt: str) -> Path | None:
        if not self.config.gemini_api_key: return None
        try:
            from google import genai
            client = genai.Client(api_key=self.config.gemini_api_key)
            LOGGER.info("Starting Veo video generation (may take a few minutes)...")
            operation = client.models.generate_videos(
                model="veo-3.1-generate-preview",
                prompt=f"Cinematic vertical video, fitness and workout motivation: {prompt}",
            )
            for _ in range(60):
                if operation.done: break
                time.sleep(10)
                
            if operation.result and getattr(operation.result, "generated_videos", None):
                uri = operation.result.generated_videos[0].video.uri
                if uri:
                    resp = requests.get(uri, timeout=60)
                    out = self.config.background_assets_dir / f"veo_{uuid.uuid4().hex[:6]}.mp4"
                    out.write_bytes(resp.content)
                    return out
        except Exception as e:
            LOGGER.warning("Veo generation failed, falling back: %s", e)
        return None

    def _fetch_pexels_video(self, query: str, is_long: bool = False) -> Path | None:
        if not self.config.pexels_api_key: return None
        try:
            orientation = "landscape" if is_long else "portrait"
            LOGGER.info("Fetching %s video from Pexels for query: %s", orientation, query)
            url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&orientation={orientation}&size=large"
            headers = {"Authorization": self.config.pexels_api_key}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                videos = resp.json().get("videos", [])
                if videos:
                    import random
                    # Pick from a wider slice so repeated topics do not keep reusing the same clip.
                    v_choice = random.choice(videos[: min(len(videos), 12)])
                    files = v_choice.get("video_files", [])
                    if files:
                        # Prefer HD (1080p) over 4K for speed and rendering stability
                        hds = [f for f in files if f.get("height", 0) >= 1280 or f.get("width", 0) >= 720]
                        best = hds[0] if hds else sorted(files, key=lambda x: x.get("width", 0)*x.get("height", 0), reverse=True)[0]
                        
                        LOGGER.info("Downloading Pexels video (res: %sx%s)", best.get("width"), best.get("height"))
                        dl = requests.get(best["link"], timeout=30)
                        out = self.config.background_assets_dir / f"pexels_{uuid.uuid4().hex[:6]}.mp4"
                        out.write_bytes(dl.content)
                        return out
        except Exception as e:
            LOGGER.warning("Pexels fetch failed: %s", e)
        return None

    def _fetch_pixabay_video(self, query: str, is_long: bool = False) -> Path | None:
        if not self.config.pixabay_api_key: return None
        try:
            LOGGER.info("Fetching video from Pixabay for query: %s", query)
            url = f"https://pixabay.com/api/videos/?key={self.config.pixabay_api_key}&q={urllib.parse.quote(query)}&video_type=film"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    import random
                    # Pick from a wider slice so repeated topics do not keep reusing the same clip.
                    v_choice = random.choice(hits[: min(len(hits), 12)])
                    best = v_choice["videos"]["large"]["url"]
                    dl = requests.get(best, timeout=60)
                    out = self.config.background_assets_dir / f"pixabay_{uuid.uuid4().hex[:6]}.mp4"
                    out.write_bytes(dl.content)
                    return out
        except Exception as e:
            LOGGER.warning("Pixabay fetch failed: %s", e)
        return None

    def _build_background(self, script: VideoScript, duration: float):
        assets = list(self._iter_background_assets())
        if not assets:
            LOGGER.warning("No background assets found, using designed fallback card")
            frame = self._render_gradient_background(script)
            return ImageClip(frame, duration=duration)

        is_long = getattr(script, 'video_type', 'short') == 'long'
        vid_w = 1920 if is_long else 1080
        vid_h = 1080 if is_long else 1920

        clips = []
        # Faster cuts (1.5-2.2s) increase retention for Shorts
        slice_duration = max(duration / max(len(assets), 1), 1.8)
        for asset in assets:
            if asset.suffix.lower() in {".mp4", ".mov", ".mkv"}:
                clip = VideoFileClip(str(asset))
                clip = clip.subclipped(0, min(slice_duration, clip.duration))
            else:
                clip = ImageClip(str(asset), duration=slice_duration)
            clip = clip.resized(height=vid_h)
            if clip.w < vid_w:
                clip = clip.resized(width=vid_w)
            clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=vid_w, height=vid_h)
            
            # Add a slow zoom-in effect (Ken Burns) for more dynamic visuals
            try:
                clip = clip.resized(lambda t: 1.0 + (0.02 * t))
            except:
                pass
            clips.append(clip.with_duration(slice_duration).crossfadein(0.2))

        combined = concatenate_videoclips(clips, method="compose")
        return combined.subclipped(0, duration)

    def _build_subtitle_clips(self, segments: list[dict], duration: float, script: VideoScript) -> list:
        subtitle_clips = []
        for segment in segments:
            text = segment.get("text", "").strip()
            if not text:
                continue
            
            # Expanded viral keyword list for more dynamic highlighting
            viral_keywords = {
                "workout", "gym", "fitness", "muscle", "discipline", "mindset", "grind", 
                "power", "strength", "success", "motivation", "beast", "hard", "work",
                "stop", "fail", "win", "growth", "results", "believe", "impossible",
                "routine", "secret", "truth", "money", "rich", "wealth", "healthy",
            }
            
            color = "#facc15" if any(kw in text.lower() for kw in viral_keywords) else "white"
            is_romanized = self._is_romanized_script(script)
            is_long = getattr(script, 'video_type', 'short') == 'long'
            
            # Create the text card
            card = self._render_text_card(
                text=text.upper(), # Uppercase is more impactful for viral videos
                width=1400 if is_long else 960,
                font_size=68 if is_romanized else 70, # Bold and large
                text_color=color,
                bg_color=(0, 0, 0, 0),
                stroke_color="#000000",
                stroke_width=5, # Heavier stroke for impact
                padding=10,
            )
            
            clip = ImageClip(card)
            duration_seg = min(segment["end"], duration) - segment["start"]
            clip = clip.with_start(segment["start"]).with_duration(duration_seg)
            
            # Positioning
            # Move subtitles to a balanced spot: above the bottom but strictly below the middle (middle is 960)
            base_y = 1200 if is_romanized else 1150
            if is_long:
                base_y = 750 if is_romanized else 700
            
            # 1. Rising Animation
            # 2. Pop-in Scaling Animation (Dynamic resize from 0.8 to 1.0 in first 0.15s)
            def anim(t):
                # Vertical position rise
                y = base_y + max(0, int(30 - (t * 150)))
                return ("center", y)
            
            def scale_anim(t):
                if t < 0.12:
                    return 0.8 + (t * 1.66) # 0.8 -> 1.0
                return 1.0
            
            clip = clip.with_position(anim)
            # MoviePy 2.x uses resize differently, applying it as a transformation
            try:
                clip = clip.transformed_by_time(lambda img, t: clip.get_frame(t), apply_to=[]) # Placeholder for complex transforms if needed
                # For simplicity in MoviePy 2.0 with the current setup:
                clip = clip.resized(lambda t: scale_anim(t))
            except:
                pass # Fallback to static if dynamic resize fails
                
            subtitle_clips.append(clip)
        return subtitle_clips

    def _build_title_clip(self, script: VideoScript, duration: float):
        title = (getattr(script, "overlay_text", "") or script.title).strip()
        
        # Extract emojis from the full title to preserve them
        emojis = "".join(re.findall(r"[\U00010000-\U0010ffff\u2600-\u27ff]", title))
        
        # Limit top text to 3-5 words
        title_words = [w for w in title.split() if not any(c in emojis for c in w)]
        short_title = " ".join(title_words[:4])
        
        # Re-attach emojis (existing or fallback)
        if not emojis:
            emojis = "🔥💪" # Fallback viral emojis
        
        final_title = f"{short_title} {emojis}".strip()
        
        is_long = getattr(script, "video_type", "short") == "long"
        title_text = ImageClip(
            self._render_text_card(
                text=final_title,
                width=1100 if is_long else 760,
                font_size=54 if is_long else 42,
                text_color="#f8fafc",
                bg_color=(0, 0, 0, 0),
                stroke_color="#000000",
                stroke_width=3,
                padding=10,
            )
        )
        y_pos = 80 if is_long else 130
        clip_duration = min(duration, 5.5 if is_long else 6.5)
        return title_text.with_position(("center", y_pos)).with_duration(clip_duration)

    def _build_story_clips(self, script: VideoScript, duration: float) -> list:
        clips = []
        is_long = getattr(script, 'video_type', 'short') == 'long'
        beats = self._story_beats(script, duration)
        accent = self._accent_palette(script)
        for index, beat in enumerate(beats):
            card = ImageClip(
                self._render_text_card(
                    text=beat["text"],
                    width=1200 if is_long else 820,
                    font_size=52 if beat["kind"] == "hook" else 46,
                    text_color=accent["text"],
                    bg_color=(0, 0, 0, 0),
                    stroke_color="#000000",
                    stroke_width=3,
                    padding=10,
                )
            )
            card = (
                card.with_start(beat["start"])
                .with_end(beat["end"])
                .with_position(beat["position"])
            )
            clips.append(card)

            if beat["kind"] == "hook":
                pulse = ImageClip(
                    self._render_badge(
                        beat["label"],
                        fill=accent["badge_fill"],
                        text_color=accent["badge_text"],
                    )
                )
                pulse = (
                    pulse.with_start(beat["start"])
                    .with_end(min(beat["start"] + 2.8, beat["end"]))
                    .with_position(("center", 360))
                )
                clips.append(pulse)
            else:
                tag = ImageClip(
                    self._render_badge(
                        beat["label"],
                        fill=accent["tag_fill"],
                        text_color=accent["badge_text"],
                    )
                )
                offset_y = -400 if is_long else 0
                tag_x = (200 if index % 2 == 0 else 1400) if is_long else (90 if index % 2 == 0 else 720)
                tag = (
                    tag.with_start(beat["start"])
                    .with_end(beat["end"])
                    .with_position((tag_x, 1040 + (index * 46) + offset_y))
                )
                clips.append(tag)
        return clips

    def _iter_background_assets(self) -> Iterable[Path]:
        if not self.config.background_assets_dir.exists():
            return []
        assets = [
            path
            for path in self.config.background_assets_dir.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".mkv"}
        ]
        random.shuffle(assets)
        return assets[:5]

    def _match_local_video_assets(self, script: VideoScript) -> list[Path]:
        if not self.config.local_video_assets_dir.exists():
            return []

        available = {
            path.stem.lower(): path
            for path in self.config.local_video_assets_dir.iterdir()
            if path.suffix.lower() in {".mp4", ".mov", ".mkv"}
        }
        if not available:
            return []

        blob = f"{script.title} {script.primary_keyword} {script.full_script}".lower()
        priority_groups = [
            ({"run", "running", "jog", "walk", "stamina", "cardio"}, ["running", "jumpingjack"]),
            ({"pushup", "push-up", "chest", "upper body"}, ["pushup", "bicep", "shoulderpress"]),
            ({"pullup", "pull-up", "back", "lats"}, ["pullup", "bicep"]),
            ({"squat", "legs", "leg", "quad", "glute"}, ["squat", "legpress", "running"]),
            ({"shoulder", "delts", "press"}, ["shoulderpress", "bicep"]),
            ({"bicep", "arm", "arms", "curl"}, ["bicep", "pushup"]),
            ({"yoga", "breath", "breathing", "mobility", "stretch", "recovery", "stress", "calm"}, ["yoga_cobrapose"]),
            ({"warmup", "warm-up", "fat loss", "weight loss", "hiit"}, ["jumpingjack", "running", "squat"]),
        ]

        matched_names: list[str] = []
        for keywords, names in priority_groups:
            if any(keyword in blob for keyword in keywords):
                for name in names:
                    if name in available:
                        return [available[name]] # Return just the very best match to loop it

        # Fallback to random if no match
        remaining = list(available.keys())
        random.shuffle(remaining)
        return [available[remaining[0]]] if remaining else []

    def _get_random_background_music(self) -> Path | None:
        if not hasattr(self.config, 'music_dir') or not self.config.music_dir.exists():
            return None
        music_files = [p for p in self.config.music_dir.iterdir() if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}]
        if not music_files:
            return None
        import random
        return random.choice(music_files)

    def _render_gradient_background(self, script: VideoScript) -> np.ndarray:
        is_long = getattr(script, 'video_type', 'short') == 'long'
        vid_w = 1920 if is_long else 1080
        vid_h = 1080 if is_long else 1920
        image = Image.new("RGBA", (vid_w, vid_h), "#091a2f")
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((50, 70, vid_w - 50, vid_h - 70), radius=42, fill=(14, 30, 57, 255))
        draw.ellipse((vid_w - 320, 120, vid_w + 40, 480), fill=(32, 76, 150, 70))
        draw.ellipse((-80, 300, 260, 640), fill=(202, 34, 52, 70))
        draw.rounded_rectangle((80, vid_h - 940, vid_w - 80, vid_h - 620), radius=36, fill=(255, 255, 255, 14))
        return np.array(image)

    def _render_badge(self, text: str, fill: tuple[int, int, int, int], text_color: str) -> np.ndarray:
        font = self._load_alt_font(30)
        temp = Image.new("RGBA", (500, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temp, "RGBA")
        bbox = draw.textbbox((24, 18), text, font=font)
        width = int(bbox[2] - bbox[0] + 48)
        height = int(bbox[3] - bbox[1] + 34)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((0, 0, width, height), radius=height // 2, fill=fill)
        draw.text((width / 2, height / 2), text, font=font, fill=text_color, anchor="mm")
        return np.array(image)



    def _render_sticky_note(self, heading: str, body: str, color: tuple[int, int, int, int]) -> np.ndarray:
        width = 360
        height = 360
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((0, 0, width, height), radius=18, fill=color, outline=(0, 0, 0, 35), width=2)
        head_font = self._load_alt_font(34)
        body_font = self._load_alt_font(30)
        draw.text((24, 24), heading, font=head_font, fill="#111827")
        wrapped = self._wrap_text(body, body_font, width - 48)
        draw.multiline_text((24, 88), wrapped, font=body_font, fill="#111827", spacing=10)
        return np.array(image)

    def _render_handwritten_card(
        self,
        text: str,
        width: int,
        font_size: int,
        text_color: str,
        bg_color: tuple[int, int, int, int],
        line_color: str,
        padding: int,
    ) -> np.ndarray:
        font = self._load_alt_font(font_size)
        wrapped = self._wrap_text(text, font, width - (padding * 2))
        temp = Image.new("RGBA", (width, 1200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temp)
        bbox = draw.multiline_textbbox((padding, padding), wrapped, font=font, spacing=14)
        height = int(bbox[3] - bbox[1] + padding * 2)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((0, 0, width, height), radius=22, fill=bg_color)
        for y in range(padding + 42, height - padding, 58):
            draw.line((padding, y, width - padding, y), fill=line_color, width=2)
        draw.multiline_text((padding, padding), wrapped, font=font, fill=text_color, spacing=14)
        return np.array(image)



    @staticmethod
    def _fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
        image = image.copy()
        image.thumbnail((width, height))
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        x = (width - image.width) // 2
        y = (height - image.height) // 2
        canvas.alpha_composite(image, dest=(x, y))
        return canvas

    def _render_text_card(
        self,
        text: str,
        width: int,
        font_size: int,
        text_color: str,
        bg_color: tuple[int, int, int, int],
        stroke_color: str,
        stroke_width: int,
        padding: int,
    ) -> np.ndarray:
        font = self._load_font(font_size)
        wrapped = self._wrap_text(text, font, width - (padding * 2))
        temp = Image.new("RGBA", (width, 2000), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temp)
        bbox = draw.multiline_textbbox(
            (padding, padding),
            wrapped,
            font=font,
            spacing=10,
            align="center",
            stroke_width=stroke_width,
        )
        height = int(bbox[3] - bbox[1] + padding * 2)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        if bg_color and bg_color[3] > 0:
            draw.rounded_rectangle((0, 0, width, height), radius=26, fill=bg_color)
        draw.multiline_text(
            (width / 2, padding),
            wrapped,
            font=font,
            fill=text_color,
            spacing=10,
            align="center",
            anchor="ma",
            stroke_width=stroke_width,
            stroke_fill=stroke_color,
        )
        return np.array(image)

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if self.config.font_file.exists():
            return ImageFont.truetype(str(self.config.font_file), size=size)
        return ImageFont.load_default()

    def _load_alt_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            Path("C:/Windows/Fonts/seguisb.ttf"),
            Path("C:/Windows/Fonts/segoesc.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=size)
        return self._load_font(size)

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
        left, _, right, _ = font.getbbox(text)
        return int(right - left)

    @staticmethod
    def _is_romanized_script(script: VideoScript) -> bool:
        payload = f"{script.title} {script.full_script}"
        return all(ord(char) < 128 for char in payload)

    @staticmethod
    def _visual_style(script: VideoScript) -> str:
        blob = f"{script.title} {script.primary_keyword} {script.full_script}".lower()
        yoga_terms = {"yoga", "asana", "breath", "pranayam", "pranayama", "mobility", "meditation", "stretch"}
        return "yoga" if any(term in blob for term in yoga_terms) else "fitness"

    def _story_beats(self, script: VideoScript, duration: float) -> list[dict]:
        style = self._visual_style(script)
        
        # Calculate dynamic timings based on percentages of typical script structure
        # Hook: ~10%, Problem: ~15%, Insight: ~20%, Solution: ~45%, CTA: ~10%
        t_hook = min(duration * 0.1, 5.0)
        t_prob = min(t_hook + duration * 0.15, 12.0)
        t_insight = min(t_prob + duration * 0.20, 25.0)
        t_solution = max(duration - 4.0, t_insight + 5.0)
        
        is_long = getattr(script, "video_type", "short") == "long"
        y_offset = -400 if is_long else 0
        
        beats = [
            {
                "kind": "hook",
                "label": "Stop Scroll" if style == "fitness" else "Pause & Breathe",
                "text": script.hook,
                "start": 0.0,
                "end": t_hook,
                "position": ("center", 510 + y_offset),
                "bg": (168, 34, 34, 215) if style == "fitness" else (14, 116, 144, 205),
            },
            {
                "kind": "problem",
                "label": "Why It Fails" if style == "fitness" else "What You Feel",
                "text": script.problem,
                "start": max(0.0, t_hook - 0.2),
                "end": t_prob,
                "position": ("center", 900 + y_offset),
                "bg": (15, 23, 42, 198),
            },
            {
                "kind": "insight",
                "label": "Truth",
                "text": script.insight,
                "start": t_prob,
                "end": t_insight,
                "position": ("center", 720 + y_offset),
                "bg": (88, 28, 135, 194) if style == "fitness" else (30, 64, 175, 190),
            },
            {
                "kind": "solution",
                "label": "Do This",
                "text": script.solution,
                "start": t_insight,
                "end": t_solution,
                "position": ("center", 1080 + y_offset),
                "bg": (21, 128, 61, 194) if style == "fitness" else (13, 148, 136, 188),
            },
            {
                "kind": "cta",
                "label": "Follow",
                "text": script.cta,
                "start": max(0.0, duration - 4.0),
                "end": duration,
                "position": ("center", 1260 + y_offset),
                "bg": (245, 158, 11, 212),
            },
        ]
        return [beat for beat in beats if beat["end"] - beat["start"] >= 1.0 and beat["text"].strip()]

    def _accent_palette(self, script: VideoScript) -> dict[str, tuple[int, int, int, int] | str]:
        if self._visual_style(script) == "yoga":
            return {
                "text": "#f8fafc",
                "stroke": "#082f49",
                "badge_fill": (255, 255, 255, 225),
                "tag_fill": (12, 74, 110, 215),
                "badge_text": "#082f49",
            }
        return {
            "text": "#f8fafc",
            "stroke": "#111827",
            "badge_fill": (250, 204, 21, 235),
            "tag_fill": (127, 29, 29, 220),
            "badge_text": "#111827",
        }
