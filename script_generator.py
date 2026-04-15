from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass

from config import AppConfig
from idea_generator import VideoIdea
from llm_fallback import LlmFallbackClient, build_json_with_fallback


LOGGER = logging.getLogger(__name__)
MIN_SCRIPT_WORDS = 85
MIN_DURATION_SECONDS = 31


@dataclass(slots=True)
class VideoScript:
    title: str
    hook: str
    problem: str
    insight: str
    solution: str
    cta: str
    full_script: str
    estimated_duration_seconds: int
    primary_keyword: str
    retention_note: str


class ScriptGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_script(self, idea: VideoIdea) -> VideoScript:
        LOGGER.info("Generating script for idea '%s'", idea.title)
        style = self._determine_style(idea)
        language_direction = self._language_direction(style, getattr(idea, "language_preference", "hinglish"))
        tone_direction = self._tone_direction(style)
        payoff_direction = self._payoff_direction(style)
        theme_hint = getattr(idea, "theme_hint", "")
        prompt = textwrap.dedent(
            f"""
            Write a highly engaging, viral 30-45 second YouTube Shorts script for the channel 'DailyFitX'.
            {language_direction}
            {tone_direction}
            {payoff_direction}

            Idea title: {idea.title}
            Angle: {idea.angle}
            Topic: {idea.topic}
            Hook suggestion: {idea.hook}
            Viewer value: {idea.audience_value}
            Theme hint: {theme_hint}

            Constraints:
            - Return strict JSON with keys:
              title, hook, problem, insight, solution, cta, estimated_duration_seconds,
              primary_keyword, retention_note
            - Make the spoken script long enough for at least 30 seconds of voiceover
            - Combined hook + problem + insight + solution + cta should be about 95-125 words
            - Hook must create curiosity in the first 2 seconds and avoid generic greetings
            - First line should feel like a pattern interrupt that makes people stop scrolling
            - Emphasize practical, biological, or physiological changes and tips (e.g. exactly how muscles respond over 30 days, actual diet effects).
            - Give specific, outcome-driven value, avoid vague 'you can do it' motivational fluff.
            - Make the script feel like one flowing story: pain/curiosity, mechanism, exact fix, result.
            - Provide real action steps, not just mindset tips.
            - Avoid fake timelines, miracle claims, and medical promises
            - Use short spoken lines with emotional rhythm for TTS and subtitles
            - Avoid filler like 'in this video' or 'let me tell you'
            - Use only Roman script written with normal English letters
            - Do not use Devanagari, Nepali, Hindi script, emojis, or special symbols
            - Hindi lines must be Roman Hindi only, mixed naturally with English
            - CTA must be action-driven and feel native to Shorts
            - Use one high-intent search keyword for fitness, yoga, or motivation
            - Retention note should briefly explain why the opening should hold attention
            - Output should sound credible, sharp, and helpful enough that viewers save it
            """
        ).strip()

        payload, provider_used = build_json_with_fallback(
            self.llm,
            prompt,
            lambda: self._fallback_script_payload(idea),
            "template-script",
        )
        LOGGER.info("Script generation provider used: %s", provider_used)

        hook = payload["hook"].strip()
        problem = payload["problem"].strip()
        insight = payload["insight"].strip()
        solution = payload["solution"].strip()
        cta = payload["cta"].strip()
        if any(self._contains_non_ascii_text(value) for value in (payload["title"], hook, problem, insight, solution, cta)):
            LOGGER.warning("LLM returned non-Roman text; switching to Roman-script fallback for '%s'", idea.title)
            payload = self._fallback_script_payload(idea)
            hook = payload["hook"].strip()
            problem = payload["problem"].strip()
            insight = payload["insight"].strip()
            solution = payload["solution"].strip()
            cta = payload["cta"].strip()
        full_script = " ".join([hook, problem, insight, solution, cta])
        full_script = self._extend_script_if_needed(full_script, idea)

        return VideoScript(
            title=payload["title"].strip(),
            hook=hook,
            problem=problem,
            insight=insight,
            solution=solution,
            cta=cta,
            full_script=full_script,
            estimated_duration_seconds=max(MIN_DURATION_SECONDS, int(payload.get("estimated_duration_seconds", 35))),
            primary_keyword=payload["primary_keyword"].strip(),
            retention_note=payload["retention_note"].strip(),
        )

    @staticmethod
    def _fallback_script_payload(idea: VideoIdea) -> dict:
        title_key = idea.title.lower()
        style = ScriptGenerator._determine_style(idea)
        if style == "yoga":
            problem = (
                "Bahut log yoga ko sirf stretching samajhte hain, phir unka body calm bhi nahi hota aur posture bhi change nahi hota."
            )
            insight = (
                "Real yoga tab kaam karta hai jab breath, balance, and awareness ek saath move karein. Wahin se strength bhi aati hai, shanti bhi."
            )
            solution = (
                f"Roz bas 10 mindful minutes do. Slow inhale, strong hold, clean posture. Fir {idea.audience_value.lower()} naturally dikhne lagta hai."
            )
            primary_keyword = "yoga motivation hindi"
        elif "fat loss" in title_key or "cardio" in title_key:
            problem = "Most people attack fat loss with more suffering, then wonder why they rebound fast."
            insight = "The real issue is not effort. It is poor recovery, weak food structure, and random cardio."
            solution = f"Use a repeatable calorie plan, lift hard, walk daily, and let {idea.audience_value.lower()} come from consistency."
            primary_keyword = "fat loss motivation hindi"
        elif "muscle" in title_key or "strength" in title_key or "back" in title_key:
            problem = "Most people chase heavy weight before they earn control, tension, and recovery."
            insight = "Strength and size grow faster when technique, overload, and sleep work together."
            solution = f"Master a few big lifts, track reps honestly, and use {idea.audience_value.lower()} as the result of better execution."
            primary_keyword = "strength training motivation hindi"
        else:
            problem = f"Most people fail at {idea.topic.lower()} because they rely on emotion instead of a repeatable system."
            insight = f"Real {idea.angle.lower()} starts on the days when your body says quit but your identity says keep going."
            solution = f"Pick one small non-negotiable action, repeat it daily, track it weekly, and let {idea.audience_value.lower()} become your edge."
            primary_keyword = f"{idea.topic} motivation hindi"

        return {
            "title": idea.title,
            "hook": ScriptGenerator._fallback_hook(idea, style),
            "problem": problem,
            "insight": insight,
            "solution": solution,
            "cta": ScriptGenerator._fallback_cta(style),
            "estimated_duration_seconds": 35,
            "primary_keyword": primary_keyword,
            "retention_note": ScriptGenerator._fallback_retention_note(style),
        }

    @staticmethod
    def _extend_script_if_needed(full_script: str, idea: VideoIdea) -> str:
        words = full_script.split()
        if len(words) >= MIN_SCRIPT_WORDS:
            return full_script

        style = ScriptGenerator._determine_style(idea)
        if style == "yoga":
            extension = (
                " Yoga sirf body shape nahi badalta, yeh andar ka noise bhi dheere dheere shaant karta hai. "
                f"Jab tum {idea.topic.lower()} ko breath ke saath practice karte ho, confidence aur grace dono saath grow karte hain."
            )
        else:
            extension = (
                f" Most people chase results, but champions chase systems. "
                f"If you master {idea.topic.lower()} with patience, intensity, and repetition, your confidence changes first and your physique follows next."
            )
        expanded = f"{full_script}{extension}"
        if len(expanded.split()) < MIN_SCRIPT_WORDS:
            extra = (
                "Kal ka wait mat karo. Aaj body ko presence do, breath ko control do, aur routine ko respect do."
                if style == "yoga"
                else "Stop negotiating with yourself. Show up, finish the rep, respect the process, and let consistency do what motivation never could."
            )
            expanded = f"{expanded} {extra}"
        return expanded

    @staticmethod
    def _determine_style(idea: VideoIdea) -> str:
        haystack = f"{idea.title} {idea.angle} {idea.topic} {idea.hook} {idea.audience_value}".lower()
        yoga_terms = {"yoga", "asana", "breath", "breathing", "mobility", "stretch", "meditation", "pranayam", "pranayama"}
        return "yoga" if any(term in haystack for term in yoga_terms) else "fitness"

    @staticmethod
    def _language_direction(style: str, language_preference: str) -> str:
        if language_preference == "english":
            return (
                "The language should be English-first with only very light Hindi seasoning if needed. Keep it fully readable in Roman letters."
            )
        if language_preference == "hindi":
            return (
                "The language should be Roman Hindi first, using only normal English letters, with a few English fitness words when useful."
            )
        if style == "yoga":
            return (
                "The language should be Hindi-first Hinglish. Prefer simple spoken Hindi with a few natural English words like breath, balance, posture, focus, and flow."
            )
        return (
            "The language should be Hinglish with short Hindi lines and some English punch words. Use phrases like 'ruk mat', 'discipline', 'focus', 'strength', and 'consistency' naturally."
        )

    @staticmethod
    def _tone_direction(style: str) -> str:
        if style == "yoga":
            return (
                "The tone must feel beautiful, soulful, and motivating. Calm power, inner healing, body awareness, and graceful discipline should come through."
            )
        return (
            "The tone must be intense, memorable, and highly shareable with a direct, no-excuses edge."
        )

    @staticmethod
    def _payoff_direction(style: str) -> str:
        if style == "yoga":
            return (
                "Focus on one clear payoff like stress relief, posture improvement, body flexibility, emotional calm, or core strength."
            )
        return (
            "Focus on one clear payoff like fat loss, strength, confidence, better form, or discipline."
        )

    @staticmethod
    def _fallback_hook(idea: VideoIdea, style: str) -> str:
        if style == "yoga":
            return idea.hook or "Agar tumhara mind heavy hai, shayad tumhe rest nahi, yoga ki need hai."
        return idea.hook or "Ruko. Tum motivation nahi, ek better system miss kar rahe ho."

    @staticmethod
    def _fallback_cta(style: str) -> str:
        if style == "yoga":
            return "DailyFitX ko follow karo, kal nahi, aaj se apne body aur breath ko respect dena shuru karo."
        return "Follow DailyFitX and build discipline that shows in your body and mind."

    @staticmethod
    def _fallback_retention_note(style: str) -> str:
        if style == "yoga":
            return "Hindi-first emotional hook opens with pain relief and promises calm plus visible body change."
        return "Pattern-interrupt hook, short punchy lines, and a concrete payoff support higher retention."

    @staticmethod
    def _contains_non_ascii_text(value: str) -> bool:
        return any(ord(char) > 127 for char in value)
