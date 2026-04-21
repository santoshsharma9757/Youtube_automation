from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from openai import OpenAI

from config import AppConfig


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LlmResult:
    text: str
    provider: str
    model: str


class LlmFallbackClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def generate_text(self, prompt: str) -> LlmResult:
        for runner in (
            self._try_openai,
            self._try_gemini_flash_20,
            self._try_gemini_flash_15,
            self._try_deepseek,
        ):
            result = runner(prompt)
            if result:
                return result
        raise RuntimeError("No LLM provider succeeded.")

    def generate_json(self, prompt: str) -> tuple[dict, LlmResult]:
        result = self.generate_text(prompt)
        return self._parse_json(result.text), result

    def _try_openai(self, prompt: str) -> LlmResult | None:
        if not self.config.openai_api_key:
            return None
        try:
            client = OpenAI(api_key=self.config.openai_api_key)
            response = client.chat.completions.create(
                model=self.config.openai_model,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content or ""
            return LlmResult(text=text, provider="openai", model=self.config.openai_model)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("OpenAI failed (%s)", exc)
            return None

    def _try_gemini_flash_20(self, prompt: str) -> LlmResult | None:
        return self._try_gemini(prompt, "gemini-2.0-flash", "gemini")

    def _try_gemini_flash_15(self, prompt: str) -> LlmResult | None:
        return self._try_gemini(prompt, "gemini-1.5-flash", "gemini")

    def _try_gemini(self, prompt: str, model: str, provider: str) -> LlmResult | None:
        if not self.config.gemini_api_key:
            return None
        try:
            from google import genai

            gemini_client = genai.Client(api_key=self.config.gemini_api_key)
            gemini_response = gemini_client.models.generate_content(model=model, contents=prompt)
            text = getattr(gemini_response, "text", "") or ""
            if not text:
                return None
            return LlmResult(text=text, provider=provider, model=model)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("%s failed (%s)", model, exc)
            return None

    def _try_deepseek(self, prompt: str) -> LlmResult | None:
        if not self.config.deepseek_api_key:
            return None
        try:
            client = OpenAI(api_key=self.config.deepseek_api_key, base_url=self.config.deepseek_base_url)
            response = client.chat.completions.create(
                model=self.config.deepseek_model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "Return only valid JSON that matches the user's requested schema.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content or ""
            return LlmResult(text=text, provider="deepseek", model=self.config.deepseek_model)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("DeepSeek failed (%s)", exc)
            return None

    @staticmethod
    def _parse_json(raw_text: str) -> dict:
        raw_text = (raw_text or "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw_text)


def build_json_with_fallback(
    client: LlmFallbackClient,
    prompt: str,
    fallback_factory: Callable[[], dict],
    fallback_label: str,
) -> tuple[dict, str]:
    try:
        payload, result = client.generate_json(prompt)
        return payload, f"{result.provider}:{result.model}"
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("All LLM providers failed, using %s fallback: %s", fallback_label, exc)
        return fallback_factory(), fallback_label
