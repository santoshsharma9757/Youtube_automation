from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from gtts import gTTS
from moviepy import AudioClip, AudioFileClip, ColorClip, CompositeAudioClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_audioclips, concatenate_videoclips
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

CHANNEL_NAME = "360 Nepal Explained"
BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "assets" / "videos"
AUDIO_DIR = BASE_DIR / "assets" / "audio"
OUTPUT_DIR = BASE_DIR / "output"
FINAL_VIDEO = OUTPUT_DIR / "final_video.mp4"
SCRIPT_JSON = OUTPUT_DIR / "script.json"
SEO_JSON = OUTPUT_DIR / "seo.json"
SUMMARY_JSON = OUTPUT_DIR / "run_summary.json"
VIDEO_SIZE = (1080, 1920)
FPS = 24
PAUSE = 0.22
MAX_CLIP_DURATION = 2.8
HOOK_WORD_LIMIT = 8
CATEGORIES = {"history", "mystery", "politics", "culture", "education"}
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "563492ad6f9170000100000111f0f211bf054f57ae80182582d40855")
YT_CLIENT = Path(os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", BASE_DIR.parent / "client_secret.json"))
YT_TOKEN = Path(os.getenv("YOUTUBE_TOKEN_FILE", BASE_DIR.parent / "youtube_token.json"))
YT_CATEGORY = os.getenv("YOUTUBE_CATEGORY_ID", "25")
YT_PRIVACY = os.getenv("YOUTUBE_PRIVACY_STATUS", "public")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
FALLBACKS = {
    "history": ["palace corridor", "historic archive", "ancient temple"],
    "mystery": ["dark corridor", "night silhouette", "shadow face"],
    "politics": ["government building", "protest crowd", "news studio"],
    "culture": ["Nepal festival", "temple prayer", "traditional dance"],
    "education": ["library books", "student notebook", "map closeup"],
}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/Nirmala.ttf",
    "C:/Windows/Fonts/NirmalaB.ttf",
    "C:/Windows/Fonts/mangal.ttf",
    "C:/Windows/Fonts/Kokila.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def log(msg: str) -> None:
    print(f"[DEBUG] {msg}")


def ensure_dirs() -> None:
    for path in (VIDEO_DIR, AUDIO_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ai_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return OpenAI(api_key=key)


def sdur(clip, duration):
    return clip.with_duration(duration) if hasattr(clip, "with_duration") else clip.set_duration(duration)


def saudio(clip, audio):
    return clip.with_audio(audio) if hasattr(clip, "with_audio") else clip.set_audio(audio)


def spos(clip, pos):
    return clip.with_position(pos) if hasattr(clip, "with_position") else clip.set_position(pos)


def sopacity(clip, value):
    return clip.with_opacity(value) if hasattr(clip, "with_opacity") else clip.set_opacity(value)


def sresize(clip, value):
    return clip.resized(value) if hasattr(clip, "resized") else clip.resize(value)


def svolume(clip, value):
    return clip.with_volume_scaled(value) if hasattr(clip, "with_volume_scaled") else clip.volumex(value)


def subclip(clip, start, end):
    return clip.subclipped(start, end) if hasattr(clip, "subclipped") else clip.subclip(start, end)


def font(size: int):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def default_emotion(category: str) -> str:
    return {
        "history": "informative",
        "mystery": "dark",
        "politics": "shock",
        "culture": "inspiring",
        "education": "informative",
    }.get(category, "informative")


def category_queries(category: str, visual_type: str | None = None) -> list[str]:
    primary = FALLBACKS.get(visual_type or category, [])
    secondary = FALLBACKS.get(category, [])
    return [*primary, *secondary, "cinematic light", "dramatic closeup"]


def tighten_line(text: str, limit: int = 10) -> str:
    words = text.replace("\n", " ").split()
    if len(words) <= limit:
        return " ".join(words).strip()
    return " ".join(words[:limit]).strip()


def hookify(text: str) -> str:
    text = tighten_line(text, HOOK_WORD_LIMIT)
    if "?" in text or "!" in text:
        return text
    if "..." in text:
        return text + " ?"
    return text + "..."


def normalize_scenes(scenes: list[dict], category: str) -> list[dict]:
    normalized = []
    for idx, scene in enumerate(scenes):
        line = tighten_line(str(scene.get("line", "")).strip(), 10)
        if not line:
            continue
        normalized.append(
            {
                "line": hookify(line) if idx == 0 else line,
                "keywords": list(scene.get("keywords") or category_queries(category)[:2]),
                "emotion": str(scene.get("emotion") or default_emotion(category)).lower(),
                "visual_type": str(scene.get("visual_type") or category).lower(),
            }
        )
    if normalized and "?" not in normalized[-1]["line"]:
        normalized[-1]["line"] = normalized[-1]["line"].rstrip("।!") + " ... आखिर सत्य के हो?"
    return normalized


def generate_script(topic: str, category: str) -> list[dict]:
    client = ai_client()
    prompt = (
        "Return JSON only in this shape: {\"scenes\":[{\"line\":\"...\",\"keywords\":[\"...\",\"...\"],\"emotion\":\"dark\",\"visual_type\":\"mystery\"}]}. "
        "Write 10 to 14 cinematic Nepali scenes for a 30 to 40 second YouTube Short. "
        "Every line must feel spoken, natural, emotional, and under 10 words. "
        "The first line must be instantly shocking or irresistible. "
        "No line should feel explanatory or slow. Each line must push curiosity forward. "
        "Final line must end in a question that triggers comments or debate. "
        "Visual keywords must strongly match the meaning and emotion. "
        f"Topic: {topic}. Category: {category}. Channel: {CHANNEL_NAME}."
    )
    res = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=1.0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    data = json.loads(res.choices[0].message.content)
    scenes = normalize_scenes(data.get("scenes", data), category)
    if not scenes:
        raise RuntimeError("No valid scenes generated")
    dump_json(SCRIPT_JSON, scenes)
    return scenes


def fallback_description(topic: str, category: str) -> str:
    return (
        f"{topic} को यो सिनेम्याटिक Shorts मा Nepal को {category} कथालाई छोटो तर दमदार ढंगले प्रस्तुत गरिएको छ।\n\n"
        f"यो विषयमा तपाईंको विचार के छ? comment मा लेख्नुहोस्, र यस्तै दमदार Nepali Shorts का लागि {CHANNEL_NAME} subscribe गर्नुहोस्।"
    )


def generate_seo(topic: str, category: str) -> dict:
    client = ai_client()
    prompt = (
        "Return JSON only with keys title, description, hashtags, keywords. "
        "Title in Nepali, max 60 chars, very high CTR, curiosity-driven. "
        "Description 2-3 short paragraphs with CTA and channel name 360 Nepal Explained. "
        "Hashtags 10-15. Keywords 8-10. Topic and category must fit Nepal audience. "
        f"Topic: {topic}. Category: {category}."
    )
    res = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.85,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    data = json.loads(res.choices[0].message.content)
    seo = {
        "title": str(data.get("title", topic)).strip()[:60],
        "description": str(data.get("description", fallback_description(topic, category))).strip(),
        "hashtags": [str(x).strip() for x in data.get("hashtags", []) if str(x).strip()],
        "keywords": [str(x).strip() for x in data.get("keywords", []) if str(x).strip()],
    }
    if not seo["hashtags"]:
        seo["hashtags"] = ["#nepal", "#nepali", "#shorts", "#360NepalExplained", f"#{category}"]
    if not seo["keywords"]:
        seo["keywords"] = [topic, f"Nepal {category}", "Nepali shorts", CHANNEL_NAME]
    dump_json(SEO_JSON, seo)
    return seo


def pexels_search(query: str) -> dict | None:
    response = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": PEXELS_KEY},
        params={"query": query, "per_page": 12, "orientation": "portrait", "size": "large"},
        timeout=30,
    )
    response.raise_for_status()
    best, score = None, -1
    for video in response.json().get("videos", []):
        w, h = int(video.get("width") or 0), int(video.get("height") or 0)
        if not w or not h:
            continue
        s = (6000 if h > w else 0) + h + int(video.get("duration") or 0) * 10
        if s > score:
            best, score = video, s
    return best


def best_file(video: dict) -> str | None:
    link, score = None, -1
    for item in video.get("video_files", []):
        w, h = int(item.get("width") or 0), int(item.get("height") or 0)
        if not w or not h:
            continue
        s = (6000 if h > w else 0) + (1200 if h >= 1280 else 0) + h
        if s > score:
            link, score = item.get("link"), s
    return link


def fetch_video(keyword, index: int, category: str, visual_type: str | None = None) -> Path | None:
    queries = []
    if isinstance(keyword, str):
        queries.append(keyword)
    else:
        merged = " ".join([str(x).strip() for x in keyword if str(x).strip()])
        if merged:
            queries.append(merged)
        queries.extend([str(x).strip() for x in keyword if str(x).strip()])
    queries.extend(category_queries(category, visual_type))
    out = VIDEO_DIR / f"video_{index}.mp4"
    for query in queries:
        if not query:
            continue
        try:
            log(f"Pexels search: {query}")
            video = pexels_search(query)
            if not video:
                continue
            link = best_file(video)
            if not link:
                continue
            with requests.get(link, stream=True, timeout=60) as response:
                response.raise_for_status()
                with out.open("wb") as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            return out
        except Exception as exc:
            log(f"Pexels failed for '{query}': {exc}")
    return None


def generate_audio(text: str, index: int) -> Path:
    out = AUDIO_DIR / f"audio_{index}.mp3"
    gTTS(text=text, lang="ne", slow=False).save(str(out))
    return out


def make_wave_clip(duration: float, func, volume: float = 1.0) -> AudioClip:
    def frame(t):
        tt = np.asarray(t, dtype=float)
        data = volume * func(tt)
        if np.isscalar(t):
            value = float(data)
            return [value, value]
        data = np.asarray(data, dtype=float)
        return np.column_stack((data, data))
    return AudioClip(frame, duration=duration, fps=44100)


def silence_clip(duration: float) -> AudioClip:
    return AudioClip(lambda t: [0.0, 0.0] if np.isscalar(t) else np.zeros((len(np.asarray(t)), 2)), duration=duration, fps=44100)


def whoosh_sfx(duration: float = 0.24) -> AudioClip:
    def func(tt):
        env = np.clip(tt / max(duration, 0.001), 0, 1)
        return np.sin(2 * math.pi * (220 + 980 * env) * tt) * (1 - env)
    return make_wave_clip(duration, func, 0.12)


def boom_sfx(duration: float = 0.42) -> AudioClip:
    def func(tt):
        env = np.exp(-7 * tt)
        return (np.sin(2 * math.pi * 48 * tt) + 0.35 * np.sin(2 * math.pi * 96 * tt)) * env
    return make_wave_clip(duration, func, 0.2)


def music_clip(duration: float, category: str) -> AudioClip:
    freqs = {
        "mystery": (52.0, 79.0, 0.32),
        "history": (73.4, 110.0, 0.18),
        "culture": (196.0, 294.0, 0.24),
        "politics": (110.0, 165.0, 0.45),
        "education": (146.8, 220.0, 0.20),
    }
    f1, f2, pulse = freqs.get(category, (73.4, 110.0, 0.2))
    def func(tt):
        return 0.08 * np.sin(2 * math.pi * f1 * tt) + 0.05 * np.sin(2 * math.pi * f2 * tt + 0.8) + 0.03 * np.sin(2 * math.pi * pulse * tt)
    return make_wave_clip(duration, func, 1.0)


def subtitle_clip(text: str, duration: float):
    img = Image.new("RGBA", (980, 420), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font(68)
    words = text.split()
    highlights = set(sorted((w.strip("।?!,;:…\"") for w in words if len(w) >= 4), key=len, reverse=True)[:2])
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if draw.textbbox((0, 0), test, font=fnt, stroke_width=5)[2] <= 880 or not current:
            current.append(word)
        else:
            lines.append(current)
            current = [word]
    if current:
        lines.append(current)
    lines = lines[:3]
    metrics, total_h = [], 0
    for line_words in lines:
        bbox = draw.textbbox((0, 0), " ".join(line_words), font=fnt, stroke_width=5)
        line_w, line_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        metrics.append((line_words, line_w, line_h))
        total_h += line_h + 18
    if metrics:
        total_h -= 18
    max_w = max((m[1] for m in metrics), default=0)
    pad = 34
    box = ((980 - max_w) // 2 - pad, (420 - total_h) // 2 - pad, (980 + max_w) // 2 + pad, (420 + total_h) // 2 + pad)
    draw.rounded_rectangle(box, radius=30, fill=(0, 0, 0, 175))
    y = (420 - total_h) / 2
    for line_words, line_w, line_h in metrics:
        x = (980 - line_w) / 2
        for word in line_words:
            color = (255, 219, 88) if word.strip("।?!,;:…\"") in highlights else (255, 255, 255)
            ww = draw.textbbox((0, 0), word, font=fnt, stroke_width=5)[2]
            draw.text((x, y), word, font=fnt, fill=color, stroke_width=5, stroke_fill="black")
            x += ww + draw.textbbox((0, 0), " ", font=fnt, stroke_width=5)[2]
        y += line_h + 18
    clip = ImageClip(np.array(img))
    return spos(sdur(clip, duration), ("center", 1365))


def fit_vertical(clip):
    target = VIDEO_SIZE[0] / VIDEO_SIZE[1]
    ratio = clip.w / clip.h
    if ratio > target:
        clip = sresize(clip, VIDEO_SIZE[1] / clip.h)
        x1 = max(0, int(clip.w / 2 - VIDEO_SIZE[0] / 2))
        return clip.cropped(x1=x1, y1=0, x2=x1 + VIDEO_SIZE[0], y2=VIDEO_SIZE[1]) if hasattr(clip, "cropped") else clip.crop(x1=x1, y1=0, x2=x1 + VIDEO_SIZE[0], y2=VIDEO_SIZE[1])
    clip = sresize(clip, VIDEO_SIZE[0] / clip.w)
    y1 = max(0, int(clip.h / 2 - VIDEO_SIZE[1] / 2))
    return clip.cropped(x1=0, y1=y1, x2=VIDEO_SIZE[0], y2=y1 + VIDEO_SIZE[1]) if hasattr(clip, "cropped") else clip.crop(x1=0, y1=y1, x2=VIDEO_SIZE[0], y2=y1 + VIDEO_SIZE[1])

def extend_video(clip, duration: float):
    if clip.duration >= duration:
        return subclip(clip, 0, duration)
    loops = int(math.ceil(duration / max(clip.duration, 0.1)))
    log(f"Looping source clip {loops}x")
    return subclip(concatenate_videoclips([clip] * loops, method="compose"), 0, duration)


def generated_bg(duration: float, category: str, emotion: str):
    palette = {
        "history": (44, 28, 18),
        "mystery": (12, 14, 22),
        "politics": (18, 24, 34),
        "culture": (90, 46, 20),
        "education": (20, 48, 58),
    }
    base = sdur(ColorClip(size=VIDEO_SIZE, color=palette.get(category, (18, 18, 22))), duration)
    if emotion in {"dark", "suspense"}:
        return CompositeVideoClip([base, sopacity(sdur(ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)), duration), 0.2)], size=VIDEO_SIZE)
    if emotion == "shock":
        return CompositeVideoClip([base, sopacity(sdur(ColorClip(size=VIDEO_SIZE, color=(255, 255, 255)), min(0.12, duration)), 0.18)], size=VIDEO_SIZE)
    if emotion == "inspiring":
        return CompositeVideoClip([base, sopacity(sdur(ColorClip(size=VIDEO_SIZE, color=(255, 220, 150)), duration), 0.07)], size=VIDEO_SIZE)
    return base


def render_brand_badge():
    img = Image.new("RGBA", (760, 118), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, 760, 118), radius=28, fill=(0, 0, 0, 120))
    draw.text((36, 28), CHANNEL_NAME, font=font(44), fill=(255, 255, 255), stroke_width=2, stroke_fill="black")
    return img


def beat_opacity(duration: float, fade: float = 0.16):
    def opacity(t):
        left = min(max(t / max(fade, 0.001), 0.0), 1.0)
        right = min(max((duration - t) / max(fade, 0.001), 0.0), 1.0)
        return max(0.0, min(left, right, 1.0))
    return opacity


def color_overlay(duration: float, color: tuple[int, int, int], opacity: float):
    return sopacity(sdur(ColorClip(size=VIDEO_SIZE, color=color), duration), opacity)


def style_visual(clip, emotion: str, duration: float, beat_index: int):
    zoom_base = {"dark": 0.05, "suspense": 0.06, "shock": 0.1, "informative": 0.04, "inspiring": 0.035}.get(emotion, 0.05)
    direction = -1 if beat_index % 2 else 1
    def zoom_fn(t):
        return 1 + zoom_base * (0.35 + t / max(duration, 0.1))
    clip = sresize(clip, zoom_fn)
    if hasattr(clip, "crop") or hasattr(clip, "cropped"):
        shift = 36 * direction
        x1 = max(0, int((clip.w - VIDEO_SIZE[0]) / 2 + shift))
        y1 = max(0, int((clip.h - VIDEO_SIZE[1]) / 2))
        x2 = x1 + VIDEO_SIZE[0]
        y2 = y1 + VIDEO_SIZE[1]
        clip = clip.cropped(x1=x1, y1=y1, x2=x2, y2=y2) if hasattr(clip, "cropped") else clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
    layers = [clip]
    if emotion == "dark":
        layers.append(color_overlay(duration, (0, 0, 0), 0.28))
        layers.append(color_overlay(duration, (18, 28, 46), 0.08))
    elif emotion == "suspense":
        layers.append(color_overlay(duration, (0, 0, 0), 0.18))
        layers.append(color_overlay(duration, (16, 22, 36), 0.05))
    elif emotion == "shock":
        layers.append(color_overlay(duration, (0, 0, 0), 0.14))
        layers.append(sopacity(sdur(ColorClip(size=VIDEO_SIZE, color=(255, 255, 255)), min(0.1, duration)), 0.2))
    elif emotion == "inspiring":
        layers.append(color_overlay(duration, (255, 215, 120), 0.06))
    else:
        layers.append(color_overlay(duration, (0, 0, 0), 0.08))
    styled = CompositeVideoClip(layers, size=VIDEO_SIZE)
    return styled


def build_visual_beat(source_path: Path | None, duration: float, emotion: str, category: str, beat_index: int, beat_count: int):
    try:
        if source_path and source_path.exists():
            source = fit_vertical(VideoFileClip(str(source_path)))
            source = extend_video(source, max(duration + beat_index * 0.08, duration))
            offset_room = max(source.duration - duration, 0)
            start = min(offset_room, beat_index * 0.18)
            beat = subclip(source, start, start + duration)
        else:
            beat = generated_bg(duration, category, emotion)
    except Exception as exc:
        log(f"Visual fallback used: {exc}")
        beat = generated_bg(duration, category, emotion)
    beat = style_visual(beat, emotion, duration, beat_index)
    if beat_count > 1 and beat_index % 2 == 1:
        flash = sopacity(sdur(ColorClip(size=VIDEO_SIZE, color=(255, 255, 255)), min(0.06, duration)), 0.08)
        beat = CompositeVideoClip([beat, flash], size=VIDEO_SIZE)
    return sdur(beat, duration)


def scene_sfx(duration: float, emotion: str, beat_count: int):
    layers = []
    for i in range(max(0, beat_count - 1)):
        whoosh = whoosh_sfx().with_start((i + 1) * MAX_CLIP_DURATION - 0.04) if hasattr(whoosh_sfx(), "with_start") else whoosh_sfx().set_start((i + 1) * MAX_CLIP_DURATION - 0.04)
        layers.append(whoosh)
    if emotion in {"shock", "dark"}:
        boom = boom_sfx().with_start(0.02) if hasattr(boom_sfx(), "with_start") else boom_sfx().set_start(0.02)
        layers.append(boom)
    return layers


def process_scene(video: Path | None, audio: Path, emotion: str, subtitle: str, category: str):
    voice = AudioFileClip(str(audio))
    silence = silence_clip(PAUSE)
    audio_clip = concatenate_audioclips([voice, silence])
    duration = audio_clip.duration
    beat_count = max(1, int(math.ceil(duration / MAX_CLIP_DURATION)))
    beat_duration = duration / beat_count
    beats = [build_visual_beat(video, beat_duration, emotion, category, i, beat_count) for i in range(beat_count)]
    visual = concatenate_videoclips(beats, method="compose") if len(beats) > 1 else beats[0]
    visual = sdur(visual, duration)
    brand = spos(sdur(ImageClip(np.array(render_brand_badge())), duration), ("center", 88))
    subs = subtitle_clip(subtitle, duration)
    base = sdur(ColorClip(size=VIDEO_SIZE, color=(8, 8, 8)), duration)
    scene = CompositeVideoClip([base, visual, brand, subs], size=VIDEO_SIZE)
    fx_layers = scene_sfx(duration, emotion, beat_count)
    mixed_audio = CompositeAudioClip([audio_clip, *fx_layers]) if fx_layers else audio_clip
    return saudio(scene, mixed_audio), duration


def create_final_video(scenes: list[dict], category: str) -> Path:
    clips, durations = [], []
    for i, scene in enumerate(scenes):
        clip, dur = process_scene(VIDEO_DIR / f"video_{i}.mp4", AUDIO_DIR / f"audio_{i}.mp3", scene["emotion"], scene["line"], category)
        clips.append(clip)
        durations.append(dur)
    final = concatenate_videoclips(clips, method="compose")
    final_audio = CompositeAudioClip([svolume(final.audio, 1.0), svolume(music_clip(sum(durations), category), 0.15)])
    final = saudio(final, final_audio)
    kwargs = {"filename": str(FINAL_VIDEO), "fps": FPS, "codec": "libx264", "audio_codec": "aac"}
    if "logger" in final.write_videofile.__code__.co_varnames:
        kwargs["logger"] = None
    final.write_videofile(**kwargs)
    for clip in clips:
        clip.close()
    final.close()
    return FINAL_VIDEO


def yt_credentials() -> Credentials:
    creds = Credentials.from_authorized_user_file(str(YT_TOKEN), SCOPES) if YT_TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(YT_CLIENT), SCOPES)
        creds = flow.run_local_server(port=0)
        YT_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_to_youtube(video_path: Path, seo: dict) -> dict:
    youtube = build("youtube", "v3", credentials=yt_credentials())
    desc = seo["description"].strip()
    tags = " ".join(seo["hashtags"])
    if tags:
        desc = f"{desc}\n\n{tags}".strip()
    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": seo["title"],
                "description": desc,
                "tags": seo["keywords"],
                "categoryId": YT_CATEGORY,
                "defaultLanguage": "ne",
                "defaultAudioLanguage": "ne",
            },
            "status": {"privacyStatus": YT_PRIVACY, "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp


def run_pipeline(topic: str, category: str, upload: bool = True) -> dict:
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
    ensure_dirs()
    scenes = generate_script(topic, category)
    seo = generate_seo(topic, category)
    for i, scene in enumerate(scenes):
        video = fetch_video(scene["keywords"], i, category, scene["visual_type"])
        if video is None:
            fallback = VIDEO_DIR / f"video_{i}.mp4"
            if fallback.exists():
                fallback.unlink()
        generate_audio(scene["line"], i)
    final_video = create_final_video(scenes, category)
    upload_resp = upload_to_youtube(final_video, seo) if upload else None
    summary = {
        "channel": CHANNEL_NAME,
        "topic": topic,
        "category": category,
        "script_path": str(SCRIPT_JSON),
        "seo_path": str(SEO_JSON),
        "video_path": str(final_video),
        "upload_response": upload_resp,
    }
    dump_json(SUMMARY_JSON, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-generate and upload cinematic Nepali YouTube Shorts")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    parser.add_argument("--skip-upload", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(args.topic, args.category, upload=not args.skip_upload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
