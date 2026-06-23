"""
fb_post_creator.py — Chintu Wonder World
=========================================
Generates an attractive Facebook Post consisting of:
  1. An AI-written caption (Hindi hook + body + CTA + hashtags)
  2. A Pixar-style Chintu image generated via DALL-E 3

Usage (via fb_content.py CLI):
    python fb_content.py create post --topic "Chintu ne aaj seekha ki sach bolna chahiye"

Output:
    output/fb_content/posts/{date_slug}/
        image.png       ← DALL-E generated image
        caption.txt     ← Full Facebook caption
        metadata.json   ← All structured data
        status.json     ← Upload tracking
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

# Force UTF-8 console output on Windows — prevents cp1252 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import AppConfig, get_config

LOGGER = logging.getLogger(__name__)

# ── Output directory ──────────────────────────────────────────────────────────
FB_POSTS_DIR = Path("output/fb_content/posts")

# ── Hashtag pool for Wonder Stories TV posts ─────────────────────────────────
_POST_HASHTAGS = (
    "#WonderStoriesTV #HindiKahani #BacchonKiKahani #MoralStory #AnimatedStory "
    "#KidsIndia #FamilyContent #HindiStories #ChildrensStories "
    "#NaitikShiksha #Kahani #FBViral #IndianKids #Cartoons #KidsVideo"
)


class FBPostCreator:
    """Creates a Facebook post with AI-generated caption and image."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or get_config()
        FB_POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def create(self, topic: str) -> Path:
        """
        Full pipeline: topic → caption + image + text overlay → saved post folder.
        Returns the post directory path.
        """
        LOGGER.info("🎨 Creating Facebook post for topic: %s", topic)

        slug = _slugify(topic)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        post_dir = FB_POSTS_DIR / f"{date_str}_{slug}"
        post_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Generate caption
        caption_data = self._generate_caption(topic)
        LOGGER.info("✅ Caption generated via %s", caption_data.get("provider", "unknown"))

        # Step 2: Generate image
        image_path = post_dir / "image_raw.png"
        image_url = self._generate_image(caption_data["image_prompt"], image_path)
        LOGGER.info("✅ Raw image saved → %s", image_path)

        # Step 3: Add text overlay (Hinglish romanized text on image)
        final_image_path = post_dir / "image.png"
        try:
            # headline_overlay / moral_overlay = Hinglish from AI
            h_overlay = (caption_data.get("headline_overlay") or
                         caption_data.get("headline", "")).strip()
            m_overlay = (caption_data.get("moral_overlay") or
                         caption_data.get("moral", "")).strip()
            _add_text_overlay(
                image_path=image_path,
                output_path=final_image_path,
                headline=h_overlay,
                moral=m_overlay,
                config=self.config,
            )
            LOGGER.info("✅ Text overlay applied → %s", final_image_path)
        except Exception as exc:
            LOGGER.warning("Text overlay failed (%s) — using raw image", exc)
            import shutil
            shutil.copy(image_path, final_image_path)

        # Step 4: Save caption text
        caption_text = caption_data["full_caption"]
        (post_dir / "caption.txt").write_text(caption_text, encoding="utf-8")

        # Step 5: Save full metadata
        metadata = {
            "topic": topic,
            "headline": caption_data.get("headline", ""),
            "headline_overlay": caption_data.get("headline_overlay", ""),
            "body_hindi": caption_data.get("body_hindi", ""),
            "body_english": caption_data.get("body_english", ""),
            "moral": caption_data.get("moral", ""),
            "moral_overlay": caption_data.get("moral_overlay", ""),
            "cta": caption_data.get("cta", ""),
            "hashtags": caption_data.get("hashtags", ""),
            "full_caption": caption_text,
            "image_prompt": caption_data.get("image_prompt", ""),
            "image_url": image_url or "",
            "image_path": str(image_path.resolve()),
            "provider": caption_data.get("provider", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (post_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (post_dir / "status.json").write_text(
            json.dumps({"uploaded": False, "upload_response": None}, indent=2), encoding="utf-8"
        )

        _print_box(f"POST CREATED → {post_dir.resolve()}")
        print(f"\nCAPTION PREVIEW:\n{'='*60}")
        sys.stdout.write(caption_text[:500] + "...\n")
        print(f"{'='*60}")

        return post_dir

    # ── Caption generation ────────────────────────────────────────────────────

    def _generate_caption(self, topic: str) -> dict:
        """Call LLM to generate structured caption data."""
        prompt = _build_caption_prompt(topic, getattr(self.config, 'channel_name', 'Wonder Stories TV'))

        # Try providers in priority order
        for runner in (
            self._try_openai_caption,
            self._try_gemini_caption,
            self._try_deepseek_caption,
        ):
            result = runner(prompt)
            if result:
                return result

        # Hard fallback
        LOGGER.warning("All LLM providers failed — using built-in fallback caption")
        return _fallback_caption(topic)

    def _try_openai_caption(self, prompt: str) -> dict | None:
        if not self.config.openai_api_key:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.config.openai_api_key)
            resp = client.chat.completions.create(
                model=self.config.openai_model,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.85,
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            data["provider"] = f"openai:{self.config.openai_model}"
            data["full_caption"] = _assemble_caption(data)
            return data
        except Exception as exc:
            LOGGER.warning("OpenAI caption failed: %s", exc)
            return None

    def _try_gemini_caption(self, prompt: str) -> dict | None:
        if not self.config.gemini_api_key:
            return None
        try:
            from google import genai
            import re as _re
            client = genai.Client(api_key=self.config.gemini_api_key)
            resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            raw = getattr(resp, "text", "") or ""
            # Strip markdown code fences
            raw = _re.sub(r"```json\s*|\s*```", "", raw).strip()
            data = json.loads(raw)
            data["provider"] = "gemini:gemini-2.0-flash"
            data["full_caption"] = _assemble_caption(data)
            return data
        except Exception as exc:
            LOGGER.warning("Gemini caption failed: %s", exc)
            return None

    def _try_deepseek_caption(self, prompt: str) -> dict | None:
        if not self.config.deepseek_api_key:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.config.deepseek_api_key,
                base_url=self.config.deepseek_base_url,
            )
            resp = client.chat.completions.create(
                model=self.config.deepseek_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return only valid JSON matching the requested schema."},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            data["provider"] = f"deepseek:{self.config.deepseek_model}"
            data["full_caption"] = _assemble_caption(data)
            return data
        except Exception as exc:
            LOGGER.warning("DeepSeek caption failed: %s", exc)
            return None

    # ── Image generation ──────────────────────────────────────────────────────

    def _generate_image(self, image_prompt: str, save_path: Path) -> str | None:
        """
        Generate image with a fallback chain:
          1. OpenAI gpt-image-1  (newest, best quality)
          2. OpenAI dall-e-2     (widely available fallback)
          3. Gemini Imagen       (free fallback using Gemini API)
        Returns image URL/source label, or None on total failure.
        """
        # Try OpenAI models first
        if self.config.openai_api_key:
            for model, size in [
                ("gpt-image-1", "1024x1024"),
                ("dall-e-2",    "1024x1024"),
            ]:
                url = self._try_openai_image(image_prompt, save_path, model, size)
                if url:
                    return url

        # Try Gemini Imagen as final fallback
        if self.config.gemini_api_key:
            result = self._try_gemini_image(image_prompt, save_path)
            if result:
                return result

        LOGGER.error("❌ All image providers failed — saving placeholder")
        _create_placeholder_image(save_path, "Image generation failed\nCheck your API keys")
        return None

    def _try_openai_image(
        self, prompt: str, save_path: Path, model: str, size: str
    ) -> str | None:
        """Try one OpenAI image model. Returns URL on success, None on failure."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.config.openai_api_key)
            LOGGER.info("🖼️  Trying OpenAI image model: %s ...", model)

            kwargs: dict = {
                "model": model,
                "prompt": prompt,
                "n": 1,
            }
            # gpt-image-1 uses 'size'; dall-e-2 also uses 'size'
            # gpt-image-1 supports quality='high'; dall-e-2 does not
            kwargs["size"] = size
            if model == "gpt-image-1":
                kwargs["quality"] = "high"

            resp = client.images.generate(**kwargs)

            # gpt-image-1 may return base64 instead of URL
            item = resp.data[0]
            if getattr(item, "url", None):
                LOGGER.info("Downloading image from %s ...", model)
                urllib.request.urlretrieve(item.url, save_path)
                LOGGER.info("✅ Image saved via %s", model)
                return item.url
            elif getattr(item, "b64_json", None):
                import base64
                LOGGER.info("Decoding base64 image from %s ...", model)
                save_path.write_bytes(base64.b64decode(item.b64_json))
                LOGGER.info("✅ Image saved via %s (base64)", model)
                return f"{model}:base64"
            else:
                LOGGER.warning("%s returned no image data", model)
                return None

        except Exception as exc:
            LOGGER.warning("OpenAI %s failed: %s", model, exc)
            return None

    def _try_gemini_image(self, prompt: str, save_path: Path) -> str | None:
        """Try Gemini Imagen as image generation fallback."""
        try:
            from google import genai
            from google.genai import types
            LOGGER.info("🖼️  Trying Gemini Imagen as fallback...")
            client = genai.Client(api_key=self.config.gemini_api_key)

            # Enhance prompt for Gemini Imagen
            full_prompt = (
                f"Generate a high-quality Pixar 3D animation style illustration. "
                f"{prompt} "
                f"Style: vibrant colors, soft cinematic lighting, family-friendly, "
                f"professional animation quality. No text or watermarks in the image."
            )

            response = client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                ),
            )

            # Extract image bytes from response
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    import base64
                    img_bytes = part.inline_data.data
                    # inline_data.data may already be bytes or base64 string
                    if isinstance(img_bytes, str):
                        img_bytes = base64.b64decode(img_bytes)
                    save_path.write_bytes(img_bytes)
                    LOGGER.info("✅ Image saved via Gemini Imagen")
                    return "gemini:imagen"

            LOGGER.warning("Gemini Imagen returned no image data")
            return None

        except Exception as exc:
            LOGGER.warning("Gemini Imagen failed: %s", exc)
            return None



# ── Caption helpers ───────────────────────────────────────────────────────────

def _build_caption_prompt(topic: str, channel_name: str = "Wonder Stories TV") -> str:
    return f"""You are a creative social media manager for "{channel_name}" —
a popular Hindi animated kids story Facebook page. Create an ATTRACTIVE, VIRAL Facebook post.

Topic/Idea: "{topic}"

Return ONLY a valid JSON object with these exact keys:

{{
  "headline_overlay": "Short catchy hook for the IMAGE — written in ROMANIZED HINDI (Hinglish). English letters that sound like Hindi. Max 8 words. Example: 'Kya Sacchi Dosti Hoti Hai?', 'Dhruv Tara Jaisa Sapna Dekho', 'Jab Chintu Ne Kuch Seekha'. NO Devanagari script.",
  "moral_overlay": "One-line moral for the IMAGE — in ROMANIZED HINDI (Hinglish). English letters. Example: 'Sacchi Dosti Mein Dhoka Nahi Hota.', 'Mehnat Ka Phal Meetha Hota Hai.' Max 10 words. NO Devanagari.",
  "headline": "Eye-catching Hindi headline for the POST CAPTION (Devanagari + emoji ok). Max 15 words.",
  "body_hindi": "Main content in Hindi Devanagari (3-5 sentences). Tell a mini moral story or insight. Make parents feel something. Use relatable scenarios.",
  "body_english": "1-2 sentences in English that amplify the message for reach.",
  "moral": "One-line moral lesson in Hindi Devanagari for the post caption (with emoji).",
  "cta": "Call to action in Hindi — ask parents to share/comment/tag. Max 2 lines.",
  "hashtags": "15-20 relevant hashtags mixing Hindi content + kids + India + family tags",
  "image_prompt": "A detailed image prompt: Pixar 3D animation style, adorable Indian boy named Chintu (age 6-7, wearing a red kurta, big curious eyes, chubby cheeks) in a vivid scene that represents the topic '{topic}'. Warm, vibrant colors. Soft cinematic lighting. Family-friendly. No text in image. At least 60 words."
}}

Rules:
- headline_overlay: romanized Hindi (Hinglish) ONLY — like 'Sacchi Dosti', 'Pyaar Ka Matlab' — NO Devanagari
- moral_overlay: romanized Hindi (Hinglish) ONLY — like 'Mehnat Ka Phal Meetha Hota Hai' — NO Devanagari
- headline and body: can use Hindi Devanagari for the Facebook post text
- Body should make parents stop scrolling — use relatable parenting moments
- CTA must ask people to TAG another parent
- All text must be appropriate for a kids channel
- image_prompt must be vivid and detailed (at least 60 words)
"""


def _assemble_caption(data: dict) -> str:
    """Combine all parts into one final Facebook caption string."""
    parts = []

    headline = data.get("headline", "").strip()
    if headline:
        parts.append(headline)

    body_hindi = data.get("body_hindi", "").strip()
    if body_hindi:
        parts.append(f"\n{body_hindi}")

    body_english = data.get("body_english", "").strip()
    if body_english:
        parts.append(f"\n{body_english}")

    moral = data.get("moral", "").strip()
    if moral:
        parts.append(f"\n{moral}")

    cta = data.get("cta", "").strip()
    if cta:
        parts.append(f"\n{cta}")

    hashtags = data.get("hashtags", _POST_HASHTAGS).strip()
    if hashtags:
        parts.append(f"\n\n{hashtags}")

    return "\n".join(parts)


def _fallback_caption(topic: str) -> dict:
    """Built-in fallback when all LLM providers fail."""
    headline = f"✨ {topic[:60]}"
    body_hindi = (
        "Chintu Wonder World में आपका स्वागत है! 🌟\n"
        "हर कहानी में एक सीख छुपी होती है।\n"
        "अपने बच्चों के साथ इस सफर का हिस्सा बनें।"
    )
    moral = "🌟 Aaj ki Seekh: हर मुश्किल में एक रास्ता होता है।"
    cta = "💬 अपने दोस्तों को TAG करें और यह message share करें! ❤️🔁"
    return {
        "headline_overlay": f"Naya Safar: {topic[:40]}",
        "moral_overlay": "Har Mushkil Mein Ek Rasta Hota Hai.",
        "headline": headline,
        "body_hindi": body_hindi,
        "body_english": "Every story has a lesson. Join Chintu on his amazing journey!",
        "moral": "Har mushkil mein ek rasta hota hai.",
        "cta": cta,
        "hashtags": _POST_HASHTAGS,
        "image_prompt": (
            f"Pixar 3D animation style, adorable Indian boy named Chintu "
            f"(age 6-7, red kurta, big curious eyes) in a colorful magical scene "
            f"related to '{topic}'. Warm vibrant colors, soft lighting, family-friendly."
        ),
        "full_caption": "\n".join([headline, body_hindi, moral, cta, _POST_HASHTAGS]),
        "provider": "fallback",
    }

def _strip_emoji(text: str) -> str:
    """Remove emoji characters that Pillow cannot render from standard system fonts."""
    import re
    return re.sub(
        r'[\U0001F000-\U0001FFFF'
        r'\U00002600-\U000027BF'
        r'\U0001F900-\U0001FAFF'
        r'\uFE00-\uFE0F'
        r'\u200D'
        r'\u20E3]+',
        '', text, flags=re.UNICODE
    ).strip()


def _add_text_overlay(
    image_path: Path,
    output_path: Path,
    headline: str,
    moral: str,
    config,
) -> None:
    """
    Composites a professional text overlay on the generated post image.
    Uses Hinglish (romanized Hindi) with Impact/Arial fonts — no font issues.
      TOP bar:    channel branding
      BOTTOM:     Hinglish headline (Impact, uppercase) + moral + CTA
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGBA")
    W, H = img.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    channel_name = getattr(config, "channel_name", "Wonder Stories TV")

    # All Latin fonts — Impact for bold headlines, Arial Bold for body
    impact_p = next((p for p in [
        Path("C:/Windows/Fonts/impact.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/ariblk.ttf"),
    ] if p.exists()), None)
    arial_p = next((p for p in [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/impact.ttf"),
    ] if p.exists()), impact_p)

    size_brand = max(28, W // 28)
    size_title = max(44, W // 15)
    size_moral = max(26, W // 34)
    size_cta   = max(22, W // 40)

    def load(path, size):
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            return ImageFont.load_default()

    brand_font = load(arial_p,  size_brand)
    title_font = load(impact_p, size_title)
    moral_font = load(arial_p,  size_moral)
    cta_font   = load(arial_p,  size_cta)

    # TOP branding bar (dark gradient)
    top_h = int(H * 0.10)
    for y in range(top_h):
        alpha = int(215 * (1 - y / top_h))
        draw.rectangle([0, y, W, y + 1], fill=(15, 8, 40, alpha))

    dot_r = max(8, W // 90)
    for dx in [int(W * 0.06), int(W * 0.94)]:
        draw.ellipse([dx - dot_r, top_h // 2 - dot_r,
                      dx + dot_r, top_h // 2 + dot_r], fill=(255, 210, 0, 230))

    brand_text = f"~ {channel_name} ~"
    _draw_centered(draw, brand_text, y=top_h // 2 - size_brand // 2,
                   font=brand_font, fill=(255, 220, 50),
                   stroke_fill=(0, 0, 0), stroke_width=2, width=W)

    # BOTTOM gradient panel
    panel_h   = int(H * 0.42)
    panel_top = H - panel_h
    for y in range(panel_h):
        alpha = int(240 * (y / panel_h) ** 0.50)
        draw.rectangle([0, panel_top + y, W, panel_top + y + 1],
                       fill=(10, 3, 28, alpha))
    draw.rectangle([0, panel_top, W, panel_top + 5], fill=(255, 140, 0, 230))

    # Headline: Hinglish uppercase in Impact font
    clean_headline = _strip_emoji(headline.strip()).upper()
    words = clean_headline.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= 22:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    text_y   = panel_top + int(H * 0.04)
    line_gap = size_title + 4
    for i, line in enumerate(lines[:3]):
        _draw_centered(draw, line, y=text_y + i * line_gap,
                       font=title_font, fill=(255, 255, 255),
                       stroke_fill=(0, 0, 0), stroke_width=3, width=W)

    # Moral: Hinglish in quotes, yellow
    moral_clean = _strip_emoji(moral.strip())
    if not moral_clean.startswith('"'):
        moral_clean = f'"{moral_clean}"'
    if len(moral_clean) > 65:
        moral_clean = moral_clean[:62] + '..."'
    moral_y = text_y + len(lines[:3]) * line_gap + int(H * 0.025)
    _draw_centered(draw, moral_clean, y=moral_y,
                   font=moral_font, fill=(255, 230, 60),
                   stroke_fill=(0, 0, 0), stroke_width=2, width=W)

    # CTA: clean English
    cta_text = f"Follow Karo >> {channel_name}"
    cta_y    = H - size_cta - int(H * 0.03)
    _draw_centered(draw, cta_text, y=cta_y,
                   font=cta_font, fill=(200, 225, 255),
                   stroke_fill=(0, 0, 0), stroke_width=1, width=W)

    # Compose and save
    result = Image.alpha_composite(img, overlay).convert("RGB")
    result.save(output_path, "PNG", quality=95)


def _draw_centered(
    draw, text: str, y: int, font, fill, width: int,
    stroke_fill=None, stroke_width: int = 0,
) -> None:
    """Draw text centered horizontally at y position."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * (font.size if hasattr(font, "size") else 20)
    x = max(10, (width - tw) // 2)
    if stroke_fill and stroke_width:
        draw.text((x, y), text, font=font, fill=fill,
                  stroke_fill=stroke_fill, stroke_width=stroke_width)
    else:
        draw.text((x, y), text, font=font, fill=fill)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    return value[:60] or "post"


def _print_box(msg: str) -> None:
    border = "=" * (len(msg) + 4)
    text = f"\n+{border}+\n|  {msg}  |\n+{border}+\n"
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        print(text)


def _create_placeholder_image(path: Path, message: str) -> None:
    """Create a simple placeholder image using Pillow if image generation fails."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1024, 1024), color=(30, 30, 60))
        draw = ImageDraw.Draw(img)
        draw.text((512, 512), message, fill=(255, 200, 50), anchor="mm")
        img.save(path)
    except Exception:
        path.write_bytes(b"")  # empty file fallback


# ── Standalone usage ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from config import setup_logging
    setup_logging()
    topic = " ".join(sys.argv[1:]) or "Chintu ne aaj seekha ki jhooth bolne se dost duur ho jaate hain"
    creator = FBPostCreator()
    post_dir = creator.create(topic)
    print(f"\n✅ Post ready in: {post_dir.resolve()}")
