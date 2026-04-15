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
        background_clip = self._build_base_visual(script=script, duration=audio_clip.duration)
        subtitle_clips = self._build_subtitle_clips(subtitles.segments, audio_clip.duration, script=script)
        title_clip = self._build_title_clip(script.title, audio_clip.duration)
        extra_clips = self._build_story_clips(script, audio_clip.duration)

        final = CompositeVideoClip([background_clip, title_clip, *extra_clips, *subtitle_clips], size=(1080, 1920))
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
        local_video_clip = self._build_local_video_background(script=script, duration=duration)
        if local_video_clip is not None:
            return local_video_clip

        return self._build_background(duration)

    def _build_local_video_background(self, script: VideoScript, duration: float):
        assets = self._match_local_video_assets(script)
        if not assets:
            return None

        clips = []
        for asset in assets:
            clip = VideoFileClip(str(asset))
            clip = clip.without_audio()
            clip = clip.resized(height=1920)
            if clip.w < 1080:
                clip = clip.resized(width=1080)
            clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=1080, height=1920)
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
                f"{keyword} sunrise yoga portrait",
                f"{title_phrase} yoga flow vertical",
                "woman yoga breathing portrait",
                "calm yoga stretch cinematic",
                "mindful meditation body flow",
                "yoga posture healing vertical",
            ]
        else:
            candidates = [
                f"{keyword} cinematic workout",
                f"{keyword} athlete training",
                f"{title_phrase} gym",
                f"{title_phrase} fitness motivation",
                "intense workout motivation",
                "athlete training vertical",
            ]
        deduped: list[str] = []
        for item in candidates:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if cleaned and cleaned.lower() not in {value.lower() for value in deduped}:
                deduped.append(cleaned)
        random.shuffle(deduped)
        return deduped[:4]

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

    def _fetch_pexels_video(self, query: str) -> Path | None:
        if not self.config.pexels_api_key: return None
        try:
            LOGGER.info("Fetching video from Pexels for query: %s", query)
            url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&orientation=portrait&size=large"
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

    def _fetch_pixabay_video(self, query: str) -> Path | None:
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

    def _build_background(self, duration: float):
        assets = list(self._iter_background_assets())
        if not assets:
            LOGGER.warning("No background assets found, using designed fallback card")
            frame = self._render_gradient_background()
            return ImageClip(frame, duration=duration)

        clips = []
        slice_duration = max(duration / max(len(assets), 1), 3)
        for asset in assets:
            if asset.suffix.lower() in {".mp4", ".mov", ".mkv"}:
                clip = VideoFileClip(str(asset))
                clip = clip.subclipped(0, min(slice_duration, clip.duration))
            else:
                clip = ImageClip(str(asset), duration=slice_duration)
            clip = clip.resized(height=1920)
            if clip.w < 1080:
                clip = clip.resized(width=1080)
            clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=1080, height=1920)
            clips.append(clip.with_duration(slice_duration).crossfadein(0.2))

        combined = concatenate_videoclips(clips, method="compose")
        return combined.subclipped(0, duration)

    def _build_subtitle_clips(self, segments: list[dict], duration: float, script: VideoScript) -> list:
        subtitle_clips = []
        keywords = {
            "workout",
            "gym",
            "fitness",
            "muscle",
            "discipline",
            "mindset",
            "grind",
            "power",
            "strength",
            "success",
        }
        for segment in segments:
            text = segment.get("text", "").strip()
            if not text:
                continue
            color = "#facc15" if any(keyword in text for keyword in keywords) else "white"
            is_romanized = self._is_romanized_script(script)
            clip = ImageClip(
                self._render_text_card(
                    text=text,
                    width=960,
                    font_size=54 if is_romanized else 56,
                    text_color=color,
                    bg_color=(9, 15, 23, 185) if is_romanized else (7, 16, 31, 205),
                    stroke_color="#05111f",
                    stroke_width=2,
                    padding=28,
                )
            )
            clip = clip.with_start(segment["start"]).with_end(min(segment["end"], duration))
            base_y = 1460 if is_romanized else 1380
            clip = clip.with_position(lambda t, base_y=base_y: ("center", base_y + max(0, int(40 - (t * 140)))))
            subtitle_clips.append(clip)
        return subtitle_clips

    def _build_title_clip(self, title: str, duration: float):
        title_text = ImageClip(
            self._render_text_card(
                text=title,
                width=920,
                font_size=74,
                text_color="#f8fafc",
                bg_color=(180, 32, 44, 235),
                stroke_color="#7f1d1d",
                stroke_width=2,
                padding=26,
            )
        )
        return title_text.with_position(("center", 180)).with_duration(min(duration, 4))

    def _build_story_clips(self, script: VideoScript, duration: float) -> list:
        clips = []
        beats = self._story_beats(script, duration)
        accent = self._accent_palette(script)
        for index, beat in enumerate(beats):
            card = ImageClip(
                self._render_text_card(
                    text=beat["text"],
                    width=820,
                    font_size=52 if beat["kind"] == "hook" else 46,
                    text_color=accent["text"],
                    bg_color=beat["bg"],
                    stroke_color=accent["stroke"],
                    stroke_width=2,
                    padding=26,
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
                tag = (
                    tag.with_start(beat["start"])
                    .with_end(beat["end"])
                    .with_position((90 if index % 2 == 0 else 720, 1040 + (index * 46)))
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

    def _render_gradient_background(self) -> np.ndarray:
        image = Image.new("RGBA", (1080, 1920), "#091a2f")
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((50, 70, 1030, 1850), radius=42, fill=(14, 30, 57, 255))
        draw.ellipse((760, 120, 1120, 480), fill=(32, 76, 150, 70))
        draw.ellipse((-80, 300, 260, 640), fill=(202, 34, 52, 70))
        draw.rounded_rectangle((80, 980, 1000, 1300), radius=36, fill=(255, 255, 255, 14))
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
        beats = [
            {
                "kind": "hook",
                "label": "Stop Scroll" if style == "fitness" else "Pause & Breathe",
                "text": script.hook,
                "start": 0.0,
                "end": min(4.2, duration),
                "position": ("center", 510),
                "bg": (168, 34, 34, 215) if style == "fitness" else (14, 116, 144, 205),
            },
            {
                "kind": "problem",
                "label": "Why It Fails" if style == "fitness" else "What You Feel",
                "text": script.problem,
                "start": min(4.0, duration),
                "end": min(11.0, duration),
                "position": ("center", 900),
                "bg": (15, 23, 42, 198),
            },
            {
                "kind": "insight",
                "label": "Truth",
                "text": script.insight,
                "start": min(11.0, duration),
                "end": min(19.5, duration),
                "position": ("center", 720),
                "bg": (88, 28, 135, 194) if style == "fitness" else (30, 64, 175, 190),
            },
            {
                "kind": "solution",
                "label": "Do This",
                "text": script.solution,
                "start": min(19.5, duration),
                "end": min(duration - 3.0, max(24.0, duration * 0.82)),
                "position": ("center", 1080),
                "bg": (21, 128, 61, 194) if style == "fitness" else (13, 148, 136, 188),
            },
            {
                "kind": "cta",
                "label": "Follow",
                "text": script.cta,
                "start": max(0.0, duration - 4.0),
                "end": duration,
                "position": ("center", 1260),
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
