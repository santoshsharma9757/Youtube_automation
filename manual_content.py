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
    normalized = topic.strip().lower()
    if "ldc" in normalized or "export" in normalized or "rojgari" in normalized or "jobs" in normalized:
        return _build_ldc_exit_package()
    if "nepal" in normalized or "province" in normalized or "state" in normalized or "map" in normalized:
        return _build_nepal_province_package()
    return None


def _build_ldc_exit_package() -> ManualContentPackage:
    title = "Nepal LDC exit and job pressure"
    hook = "2026 mein Nepal ka LDC exit jobs par pressure kyun bana sakta hai?"
    problem = "Cheap export benefits kam hue to carpet, garment aur small industry par stress badh sakta hai."
    insight = (
        "Growth tab slow hoti hai jab productivity, infrastructure aur competition strong na ho."
    )
    solution = (
        "Export quality, tourism, hydropower aur local jobs par focus ho to challenge bhi chance ban sakta hai."
    )
    cta = "Aise simple explainers ke liye follow karo."
    full_script = " ".join([hook, problem, insight, solution, cta])

    script = VideoScript(
        title=title,
        hook=hook,
        problem=problem,
        insight=insight,
        solution=solution,
        cta=cta,
        full_script=full_script,
        estimated_duration_seconds=37,
        primary_keyword="Nepal LDC exit",
        retention_note="Roman script only. Keep it simple and job-focused.",
    )
    seo = SeoPackage(
        title="Nepal LDC exit ka jobs par asar",
        description=(
            "Nepal LDC exit ka jobs, export aur development par kya impact ho sakta hai? "
            "Is short mein simple Hindi-English explain kiya gaya hai.\n\n#Nepal #shorts #economy"
        ),
        tags=[
            "Nepal LDC exit",
            "Nepal economy",
            "Nepal jobs",
            "Nepal export",
            "Hindi English shorts",
        ],
        hashtags=["#Nepal", "#shorts", "#economy"],
        primary_keyword="Nepal LDC exit",
    )
    segments = [
        TimedSegment(0.0, 5.0, hook),
        TimedSegment(5.0, 12.0, problem),
        TimedSegment(12.0, 24.0, insight),
        TimedSegment(24.0, 34.0, solution),
        TimedSegment(34.0, 37.0, cta),
    ]
    return ManualContentPackage(script=script, seo=seo, segments=segments)


def _build_nepal_province_package() -> ManualContentPackage:
    title = "Nepal ke 7 provinces ko kaise yaad rakhein?"
    hook = "Nepal ke 7 provinces, 7 alag pehchaan. Kya tum sab yaad rakh paate ho?"
    problem = "Log Nepal ko ek hi nazar se dekhte hain, isliye har province ki real strength miss ho jaati hai."
    insight = (
        "Koshi tea aur hills, Madhesh farming aur trade, Bagmati capital aur administration, Gandaki mountains aur tourism."
    )
    solution = (
        "Lumbini heritage aur farming, Karnali nature aur water, Sudurpashchim culture aur potential. "
        "Province-wise socho to development ko better samajh paoge."
    )
    cta = "Aise useful explainers ke liye follow karo."
    full_script = " ".join([hook, problem, insight, solution, cta])

    script = VideoScript(
        title=title,
        hook=hook,
        problem=problem,
        insight=insight,
        solution=solution,
        cta=cta,
        full_script=full_script,
        estimated_duration_seconds=34,
        primary_keyword="Nepal provinces",
        retention_note="Roman script only. Short curiosity hook with concrete identifiers.",
    )
    seo = SeoPackage(
        title=title,
        description=(
            "Nepal ke 7 provinces ko simple Hindi-English mein samjho. "
            "Identity, strength aur development ek short mein.\n\n#Nepal #shorts #geography"
        ),
        tags=[
            "Nepal",
            "Nepal provinces",
            "Nepal map",
            "Hindi English shorts",
            "geography short",
        ],
        hashtags=["#Nepal", "#shorts", "#geography"],
        primary_keyword="Nepal provinces",
    )
    segments = [
        TimedSegment(0.0, 4.0, hook),
        TimedSegment(4.0, 9.0, problem),
        TimedSegment(9.0, 20.0, insight),
        TimedSegment(20.0, 31.0, solution),
        TimedSegment(31.0, 34.0, cta),
    ]
    return ManualContentPackage(script=script, seo=seo, segments=segments)
