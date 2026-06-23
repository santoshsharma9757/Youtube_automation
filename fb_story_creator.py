"""
fb_story_creator.py — Wonder Stories TV
=========================================
Creates a Facebook Story — a 1080×1920 portrait image with:
  • AI-generated Pixar-style scene image (same quality as posts)
  • Channel branding bar at top
  • Bold Hindi hook text at bottom
  • Follow CTA

Usage (via fb_content.py CLI):
    python fb_content.py create story --topic "Aaj ki seekh: Sacchi dosti"
    python fb_content.py create story --auto

Output:
    output/fb_content/stories/{date_slug}/
        story_card_raw.png  ← Clean AI image
        story_card.png      ← Final image with text overlay
        text.txt            ← Hook text
        metadata.json       ← Structured data
        status.json         ← Upload tracking
"""
from __future__ import annotations

import json
import logging
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import AppConfig, get_config

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOGGER = logging.getLogger(__name__)

FB_STORIES_DIR = Path("output/fb_content/stories")

# Story card dimensions — Facebook Story is 9:16 portrait
STORY_W, STORY_H = 1080, 1920


def _strip_emoji(text: str) -> str:
    """Remove emoji that Pillow cannot render with system fonts."""
    import re as _re
    return _re.sub(
        r'[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F900-\U0001FAFF\uFE00-\uFE0F\u200D\u20E3]+',
        '', text, flags=_re.UNICODE
    ).strip()


class FBStoryCreator:
    """Creates a Facebook Story card with Pixar-style AI image + text overlay."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or get_config()
        FB_STORIES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def create(self, topic: str) -> Path:
        """
        Full pipeline: topic → AI hook text → AI image → story card.
        Returns the story directory path.
        """
        LOGGER.info("📱 Creating Facebook Story for topic: %s", topic)

        slug = _slugify(topic)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        story_dir = FB_STORIES_DIR / f"{date_str}_{slug}"
        story_dir.mkdir(parents=True, exist_ok=True)

        channel_name = getattr(self.config, "channel_name", "Wonder Stories TV")

        # Step 1: Generate story hook text + image prompt via LLM
        hook_data = self._generate_hook(topic, channel_name)
        LOGGER.info("✅ Story hook generated via %s", hook_data.get("provider", "unknown"))

        # Step 2: Generate Pixar-style background image
        raw_path = story_dir / "story_card_raw.png"
        image_prompt = hook_data.get("image_prompt", "")
        self._generate_image(image_prompt, raw_path)

        # Step 3: Apply text overlay to create final story card
        card_path = story_dir / "story_card.png"
        _apply_story_overlay(
            image_path=raw_path,
            output_path=card_path,
            hook_hinglish=(hook_data.get("hook_hinglish") or hook_data.get("hook_hindi", "")),
            hook_english=hook_data.get("hook_english", ""),
            channel_name=channel_name,
        )
        LOGGER.info("✅ Story card saved → %s", card_path)

        # Step 4: Save text + metadata
        (story_dir / "text.txt").write_text(
            (hook_data.get("hook_hinglish") or hook_data.get("hook_hindi", ""))
            + "\n" + hook_data.get("hook_english", ""),
            encoding="utf-8"
        )
        metadata = {
            "topic": topic,
            "hook_hinglish": (hook_data.get("hook_hinglish") or hook_data.get("hook_hindi", "")),
            "hook_english": hook_data.get("hook_english", ""),
            "image_prompt": image_prompt,
            "card_path": str(card_path.resolve()),
            "raw_path": str(raw_path.resolve()),
            "provider": hook_data.get("provider", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (story_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (story_dir / "status.json").write_text(
            json.dumps({"uploaded": False, "upload_response": None}, indent=2),
            encoding="utf-8"
        )

        _print_box(f"STORY CREATED -> {story_dir.resolve()}")
        print(f"\nHook: {hook_data.get('hook_hinglish') or hook_data.get('hook_hindi', '')}")
        return story_dir

    # ── LLM hook generation ───────────────────────────────────────────────────

    def _generate_hook(self, topic: str, channel_name: str) -> dict:
        prompt = _build_story_prompt(topic, channel_name)
        for runner in (
            self._try_openai_hook,
            self._try_gemini_hook,
        ):
            result = runner(prompt)
            if result:
                return result
        LOGGER.warning("All LLM providers failed — using fallback story hook")
        return _fallback_hook(topic)

    def _try_openai_hook(self, prompt: str) -> dict | None:
        if not self.config.openai_api_key:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.config.openai_api_key)
            resp = client.chat.completions.create(
                model=self.config.openai_model,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            data["provider"] = f"openai:{self.config.openai_model}"
            return data
        except Exception as exc:
            LOGGER.warning("OpenAI story hook failed: %s", exc)
            return None

    def _try_gemini_hook(self, prompt: str) -> dict | None:
        if not self.config.gemini_api_key:
            return None
        try:
            from google import genai
            client = genai.Client(api_key=self.config.gemini_api_key)
            resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            raw = getattr(resp, "text", "") or ""
            raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data = json.loads(raw)
            data["provider"] = "gemini:gemini-2.0-flash"
            return data
        except Exception as exc:
            LOGGER.warning("Gemini story hook failed: %s", exc)
            return None

    # ── Image generation (same fallback chain as posts) ───────────────────────

    def _generate_image(self, image_prompt: str, save_path: Path) -> None:
        """Generate Pixar-style portrait image using the same model chain as posts."""

        if not image_prompt:
            image_prompt = (
                "Pixar 3D animation style, adorable Indian boy Chintu "
                "(age 6-7, red kurta, big curious eyes) in a magical colorful scene. "
                "Portrait/vertical composition. Warm vibrant colors, soft lighting. "
                "Family-friendly. No text."
            )

        # Make prompt portrait-friendly
        portrait_prompt = (
            f"{image_prompt} "
            "Portrait/vertical orientation. Centered subject with room at top and bottom. "
            "Cinematic vertical composition suitable for a 9:16 story format."
        )

        if self.config.openai_api_key:
            for model, size in [
                ("gpt-image-1", "1024x1792"),
                ("gpt-image-1", "1024x1024"),
                ("dall-e-2",    "1024x1024"),
            ]:
                if self._try_openai_image(portrait_prompt, save_path, model, size):
                    return

        if self.config.gemini_api_key:
            if self._try_gemini_image(portrait_prompt, save_path):
                return

        LOGGER.error("All image providers failed — saving placeholder")
        _create_placeholder(save_path)

    def _try_openai_image(self, prompt: str, save_path: Path, model: str, size: str) -> bool:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.config.openai_api_key)
            LOGGER.info("🖼️  Story image: trying %s (%s)...", model, size)

            kwargs: dict = {"model": model, "prompt": prompt, "n": 1, "size": size}
            if model == "gpt-image-1":
                kwargs["quality"] = "high"

            resp = client.images.generate(**kwargs)
            item = resp.data[0]

            if getattr(item, "url", None):
                urllib.request.urlretrieve(item.url, save_path)
                LOGGER.info("✅ Story image saved via %s", model)
                return True
            elif getattr(item, "b64_json", None):
                import base64
                save_path.write_bytes(base64.b64decode(item.b64_json))
                LOGGER.info("✅ Story image saved via %s (base64)", model)
                return True
        except Exception as exc:
            LOGGER.warning("Story image %s failed: %s", model, exc)
        return False

    def _try_gemini_image(self, prompt: str, save_path: Path) -> bool:
        try:
            from google import genai
            from google.genai import types
            LOGGER.info("🖼️  Story image: trying Gemini Imagen...")
            client = genai.Client(api_key=self.config.gemini_api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                ),
            )
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    import base64
                    img_bytes = part.inline_data.data
                    if isinstance(img_bytes, str):
                        img_bytes = base64.b64decode(img_bytes)
                    save_path.write_bytes(img_bytes)
                    LOGGER.info("✅ Story image saved via Gemini Imagen")
                    return True
        except Exception as exc:
            LOGGER.warning("Gemini Imagen story failed: %s", exc)
        return False


# ── Story card overlay ────────────────────────────────────────────────────────

def _apply_story_overlay(
    image_path: Path,
    output_path: Path,
    hook_hinglish: str,
    hook_english: str,
    channel_name: str,
) -> None:
    """
    Apply portrait text overlay on the story image using Hinglish text.
      TOP: channel branding bar
      BOTTOM: Hinglish hook (Impact font) + English subtitle + CTA
    """
    from PIL import Image, ImageDraw, ImageFont

    # Open and resize to portrait 1080×1920
    img = Image.open(image_path).convert("RGB")
    # Smart crop/fit to 9:16
    orig_w, orig_h = img.size
    target_ratio = STORY_H / STORY_W  # 16/9 ≈ 1.778
    orig_ratio = orig_h / orig_w

    if orig_ratio < target_ratio:
        # Image is wider than 9:16 — fit height, crop width
        new_h = STORY_H
        new_w = int(new_h / orig_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        x_off = (new_w - STORY_W) // 2
        img = img.crop((x_off, 0, x_off + STORY_W, STORY_H))
    else:
        # Image is taller — fit width, crop height
        new_w = STORY_W
        new_h = int(new_w * orig_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        y_off = (new_h - STORY_H) // 2
        y_off = max(0, y_off - int(STORY_H * 0.05))  # bias upward slightly
        img = img.crop((0, y_off, STORY_W, y_off + STORY_H))

    img = img.convert("RGBA")
    overlay = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── Fonts: all Latin, no Devanagari needed (Hinglish text) ──────────────
    impact_p = next((p for p in [
        Path("C:/Windows/Fonts/impact.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ] if p.exists()), None)
    arial_p = next((p for p in [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/impact.ttf"),
    ] if p.exists()), impact_p)

    def load(path, size):
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            return ImageFont.load_default()

    brand_font = load(arial_p,  52)
    hook_font  = load(impact_p, 96)
    sub_font   = load(arial_p,  52)
    cta_font   = load(arial_p,  44)

    W, H = STORY_W, STORY_H

    # ── TOP branding bar ───────────────────────────────────────────────────────
    top_h = int(H * 0.10)
    for y in range(top_h):
        alpha = int(220 * (1 - y / top_h))
        draw.rectangle([0, y, W, y + 1], fill=(10, 5, 30, alpha))

    # Yellow dot accents
    dot_r = 12
    for dx in [60, W - 60]:
        draw.ellipse([dx - dot_r, top_h // 2 - dot_r,
                      dx + dot_r, top_h // 2 + dot_r], fill=(255, 210, 0, 240))

    brand_text = f"~ {channel_name} ~"
    _draw_story_centered(draw, brand_text, y=top_h // 2 - 26,
                         font=brand_font, fill=(255, 220, 50),
                         stroke_fill=(0, 0, 0), stroke_width=2, width=W)

    # ── BOTTOM panel (big gradient) ───────────────────────────────────────────
    panel_h   = int(H * 0.45)
    panel_top = H - panel_h

    for y in range(panel_h):
        alpha = int(245 * (y / panel_h) ** 0.45)
        draw.rectangle([0, panel_top + y, W, panel_top + y + 1],
                       fill=(8, 3, 25, alpha))

    # Orange accent line at top of panel
    draw.rectangle([0, panel_top, W, panel_top + 6], fill=(255, 140, 0, 240))

    # ── Hinglish hook text (Impact uppercase — bold and punchy) ──────────────
    clean_hook = _strip_emoji(hook_hinglish.strip()).upper()

    # Word wrap for portrait (max 14 chars/line)
    words = clean_hook.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= 14:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    line_gap = 100
    text_start = panel_top + int(H * 0.03)
    for i, line in enumerate(lines[:4]):
        _draw_story_centered(draw, line, y=text_start + i * line_gap,
                             font=hook_font, fill=(255, 255, 255),
                             stroke_fill=(0, 0, 0), stroke_width=4, width=W)

    # ── English subtitle ──────────────────────────────────────────────────────
    clean_sub = _strip_emoji(hook_english.strip())
    if len(clean_sub) > 55:
        clean_sub = clean_sub[:52] + "..."
    sub_y = text_start + len(lines[:4]) * line_gap + int(H * 0.025)
    _draw_story_centered(draw, clean_sub, y=sub_y,
                         font=sub_font, fill=(255, 230, 130),
                         stroke_fill=(0, 0, 0), stroke_width=2, width=W)

    # ── CTA ───────────────────────────────────────────────────────────────────────
    cta_text = f"Follow Karo >> {channel_name}"
    cta_y    = H - 80
    _draw_story_centered(draw, cta_text, y=cta_y,
                         font=cta_font, fill=(200, 220, 255),
                         stroke_fill=(0, 0, 0), stroke_width=1, width=W)

    # ── Compose and save ──────────────────────────────────────────────────────
    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG", quality=95)


def _draw_story_centered(
    draw, text: str, y: int, font, fill, width: int,
    stroke_fill=None, stroke_width: int = 0,
) -> None:
    """Draw text centered horizontally."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * 20
    x = max(20, (width - tw) // 2)
    draw.text((x, y), text, font=font, fill=fill,
              stroke_fill=stroke_fill, stroke_width=stroke_width)


# ── LLM prompt builder ────────────────────────────────────────────────────────

def _build_story_prompt(topic: str, channel_name: str) -> str:
    return f"""You are creating Facebook Story content for "{channel_name}" — a popular Hindi kids story page.

Topic: "{topic}"

Create a SHORT, PUNCHY story hook. Return ONLY valid JSON:

{{
  "hook_hinglish": "2-3 SHORT lines of ROMANIZED HINDI (Hinglish). English letters that sound like Hindi. Each line max 14 chars. Examples: 'Kya Tumne Kabhi', 'Aisa Kiya?', 'Sacchi Dosti Ka', 'Matlab Kya Hai?'. NO Devanagari.",
  "hook_english": "1 short English subtitle line. Max 50 characters. Curiosity-building.",
  "image_prompt": "Detailed Pixar 3D animation image prompt: adorable Indian boy Chintu (age 6-7, red kurta, big curious eyes) in a vivid scene related to '{topic}'. Portrait composition. Warm colors, cinematic soft lighting, family-friendly, no text in image. At least 60 words."
}}

Rules:
- hook_hinglish: Romanized Hindi only (e.g. 'Kya Tumhara Bachcha\nYahi Karta Hai?') — NO Devanagari
- hook_english: casual, intriguing, makes viewer want to follow
- image_prompt: portrait-friendly, vibrant, Pixar quality
"""


def _fallback_hook(topic: str) -> dict:
    return {
        "hook_hinglish": "Nayi Kahani\nAa Rahi Hai\nJude Raho!",
        "hook_english": "A new story is coming. Don't miss it!",
        "image_prompt": (
            f"Pixar 3D animation style, adorable Indian boy Chintu "
            f"(age 6-7, red kurta, big curious eyes, chubby cheeks) in a magical colorful scene "
            f"related to '{topic}'. Portrait orientation. Warm vibrant colors, "
            f"soft cinematic lighting. Family-friendly. No text."
        ),
        "provider": "fallback",
    }


def _create_placeholder(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (STORY_W, STORY_H), color=(30, 15, 60))
        draw = ImageDraw.Draw(img)
        for y in range(STORY_H):
            alpha = y / STORY_H
            r = int(30 * (1 - alpha) + 80 * alpha)
            g = int(15 * (1 - alpha) + 20 * alpha)
            b = int(60 * (1 - alpha) + 120 * alpha)
            draw.line([(0, y), (STORY_W, y)], fill=(r, g, b))
        img.save(path, "PNG")
    except Exception:
        path.write_bytes(b"")


def _slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value[:60] or "story"


def _print_box(msg: str) -> None:
    border = "=" * (len(msg) + 4)
    text = f"\n+{border}+\n|  {msg}  |\n+{border}+\n"
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        print(text)


# ── Standalone usage ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    topic = " ".join(sys.argv[1:]) or "Chintu ne seekha sacchi dosti ka matlab"
    creator = FBStoryCreator()
    story_dir = creator.create(topic)
    print(f"\nStory ready in: {story_dir.resolve()}")
