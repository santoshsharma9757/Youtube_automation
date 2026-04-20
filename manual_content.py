from __future__ import annotations

from dataclasses import dataclass

from script_generator import VideoScript
from seo_generator import SeoPackage


@dataclass(slots=True)
class TimedSegment:
    start: float
    end: float
    text: str


@dataclass(slots=True)
class ManualContentPackage:
    script: VideoScript
    seo: SeoPackage
    segments: list[TimedSegment]


def build_manual_content(topic: str) -> ManualContentPackage | None:
    """Disabled on purpose so no hidden domain-specific shortcuts remain."""

    _ = topic
    return None
