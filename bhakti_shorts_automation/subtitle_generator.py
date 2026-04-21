from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from config import AppConfig
from script_generator import VideoScript


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SubtitleArtifact:
    srt_path: Path
    json_path: Path
    segments: list[dict[str, Any]]


class SubtitleGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def generate(self, audio_path: Path, base_name: str, script: VideoScript | None = None) -> SubtitleArtifact:
        LOGGER.info("Transcribing audio for subtitles (using heuristic chunking): %s", audio_path)
        
        # Audio duration
        from moviepy import AudioFileClip
        try:
            audio_clip = AudioFileClip(str(audio_path))
            duration = audio_clip.duration
            audio_clip.close()
        except:
            duration = script.estimated_duration_seconds if script else 30

        segments = self._heuristic_chunking(base_name, script, duration)
        result_dict = {"segments": segments}

        json_path = self.config.subtitle_store_dir / f"{base_name}.json"
        srt_path = self.config.subtitle_store_dir / f"{base_name}.srt"

        json_path.write_text(json.dumps(result_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        srt_path.write_text(self._to_srt(segments), encoding="utf-8")
        return SubtitleArtifact(srt_path=srt_path, json_path=json_path, segments=segments)

    def _heuristic_chunking(self, base_name: str, script: VideoScript | None = None, duration: float = 30.0) -> list[dict]:
        text = script.full_script if script else "Discipline is doing what needs to be done, even when you don't feel like it."
        words = text.split()
        segments = []
        words_per_segment = max(2, len(words) // (int(duration) // 2 or 1))
        duration_per_segment = max(duration / (len(words) / words_per_segment or 1), 0.5)
        
        for i in range(0, len(words), words_per_segment):
            chunk = " ".join(words[i : i + words_per_segment])
            start = (i // words_per_segment) * duration_per_segment
            segments.append({
                "start": start,
                "end": min(start + duration_per_segment, duration),
                "text": chunk
            })
        return segments

    def generate_from_segments(self, segments: list[dict[str, Any]], base_name: str) -> SubtitleArtifact:
        json_path = self.config.subtitle_store_dir / f"{base_name}.json"
        srt_path = self.config.subtitle_store_dir / f"{base_name}.srt"
        payload = {"segments": segments}
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        srt_path.write_text(self._to_srt(segments), encoding="utf-8")
        return SubtitleArtifact(srt_path=srt_path, json_path=json_path, segments=segments)

    def _guess_language(self, script: VideoScript | None) -> str:
        if script is None:
            return "en"
        blob = " ".join(
            getattr(script, field, "")
            for field in ("title", "hook", "problem", "insight", "solution", "cta", "full_script")
        ).lower()
        if any(ord(char) > 127 for char in blob):
            return "hi"
        return "en"

    def _to_srt(self, segments: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, segment in enumerate(segments, start=1):
            lines.extend(
                [
                    str(index),
                    f"{self._format_time(segment['start'])} --> {self._format_time(segment['end'])}",
                    segment["text"].strip(),
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _format_time(seconds: float) -> str:
        milliseconds = int(seconds * 1000)
        hours = milliseconds // 3_600_000
        minutes = (milliseconds % 3_600_000) // 60_000
        secs = (milliseconds % 60_000) // 1000
        ms = milliseconds % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
