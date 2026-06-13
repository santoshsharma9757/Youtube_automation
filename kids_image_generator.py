"""
kids_image_generator.py  –  Chintu Stories Channel
====================================================
Generates AI scene images for each scene using OpenAI DALL-E 3.
All images are 3D Pixar-style animation quality.

- AI_VIDEO scenes      → portrait 1024×1792 (9:16 Shorts) or landscape 1792×1024
- IMAGE_FOR_ZOOM scenes → same resolution (displayed with zoom effect)
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

import requests

from config import AppConfig
from kids_story_generator import KidsStoryPlan

LOGGER = logging.getLogger(__name__)

# DALL-E 3 supports these sizes only
PORTRAIT_SIZE  = "1024x1792"   # 9:16 — Shorts
LANDSCAPE_SIZE = "1792x1024"   # 16:9 — Long form


class KidsImageGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.config.openai_api_key)
            except Exception as exc:
                LOGGER.error("Failed to init OpenAI client: %s", exc)
                raise
        return self._client

    def generate_scene_images(
        self,
        plan: KidsStoryPlan,
        output_dir: Path,
        is_long: bool = False,
    ) -> dict[int, Path]:
        """
        Generate one image per scene.
        Returns: {scene_number: image_path}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        size     = LANDSCAPE_SIZE if is_long else PORTRAIT_SIZE
        results: dict[int, Path] = {}

        for scene in plan.scenes:
            scene_num = scene["scene_number"]
            prompt    = scene.get("ai_prompt", "")
            ext       = "png"
            out_path  = output_dir / f"scene{scene_num}.{ext}"

            if out_path.exists():
                LOGGER.info("Scene %s image already exists, reusing: %s", scene_num, out_path)
                results[scene_num] = out_path
                continue

            LOGGER.info("Generating image for scene %s (type=%s)", scene_num, scene["generation_type"])

            # Truncate prompt to DALL-E limit (4000 chars)
            prompt = prompt[:3900].strip()

            img_path = self._generate_dalle(prompt, out_path, size)
            if img_path:
                results[scene_num] = img_path
            else:
                # Fallback: create a gradient placeholder image
                fallback = self._create_gradient_fallback(scene_num, output_dir)
                results[scene_num] = fallback

            # Rate limit: DALL-E 3 is ~5 images/min on tier 1
            time.sleep(13)

        return results

    def _generate_dalle(self, prompt: str, out_path: Path, size: str) -> Path | None:
        try:
            client = self._get_client()
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality="standard",
                n=1,
                response_format="url",
            )
            url = response.data[0].url
            # Download the image
            img_response = requests.get(url, timeout=60)
            img_response.raise_for_status()
            out_path.write_bytes(img_response.content)
            LOGGER.info("DALL-E 3 image saved: %s", out_path)
            return out_path
        except Exception as exc:
            LOGGER.error("DALL-E 3 generation failed for scene: %s", exc)
            return None

    def _create_gradient_fallback(self, scene_num: int, output_dir: Path) -> Path:
        """Create a colorful gradient placeholder if DALL-E fails."""
        try:
            from PIL import Image, ImageDraw
            import numpy as np

            w, h = 1024, 1792
            img  = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(img)

            # Cheerful gradient colors per scene
            scene_colors = [
                [(255, 200, 100), (255, 100, 50)],   # orange warm
                [(100, 200, 255), (50, 100, 200)],   # blue cool
                [(150, 255, 150), (50, 200, 100)],   # green magic
                [(255, 200, 255), (200, 100, 255)],  # purple celebration
            ]
            colors = scene_colors[(scene_num - 1) % 4]
            for y in range(h):
                ratio = y / h
                r = int(colors[0][0] * (1 - ratio) + colors[1][0] * ratio)
                g = int(colors[0][1] * (1 - ratio) + colors[1][1] * ratio)
                b = int(colors[0][2] * (1 - ratio) + colors[1][2] * ratio)
                draw.line([(0, y), (w, y)], fill=(r, g, b))

            # Add scene number text
            try:
                from PIL import ImageFont
                font = ImageFont.load_default()
                draw.text((w // 2, h // 2), f"Scene {scene_num}", fill=(255, 255, 255), anchor="mm", font=font)
            except Exception:
                pass

            out_path = output_dir / f"scene{scene_num}.png"
            img.save(str(out_path))
            LOGGER.info("Created gradient fallback for scene %s: %s", scene_num, out_path)
            return out_path

        except Exception as exc:
            LOGGER.error("Gradient fallback creation failed: %s", exc)
            # Last resort: tiny 1-pixel blank image
            out_path = output_dir / f"scene{scene_num}.png"
            out_path.write_bytes(b"")
            return out_path
