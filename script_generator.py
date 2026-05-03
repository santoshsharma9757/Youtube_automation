from __future__ import annotations

import logging
import re
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
    overlay_text: str
    hook: str
    problem: str
    insight: str
    solution: str
    cta: str
    full_script: str
    estimated_duration_seconds: int
    primary_keyword: str
    retention_note: str
    video_type: str = "short"


class ScriptGenerator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.llm = LlmFallbackClient(config)

    def generate_script(self, idea: VideoIdea) -> VideoScript:
        is_long = getattr(idea, "video_type", "short") == "long"
        duration_desc = "80-90 second YouTube video" if is_long else "30-45 second YouTube Shorts"
        min_duration = 80 if is_long else 31
        word_count_desc = "200-240 words" if is_long else "95-125 words"

        LOGGER.info("Generating script for idea '%s' (type: %s)", idea.title, getattr(idea, "video_type", "short"))
        style = self._determine_style(idea)
        language_direction = self._language_direction(style, getattr(idea, "language_preference", "hinglish"))
        tone_direction = self._tone_direction(style)
        payoff_direction = self._payoff_direction(style)
        theme_hint = getattr(idea, "theme_hint", "")
        prompt = textwrap.dedent(
            f"""
            Write a highly engaging, viral {duration_desc} script for the channel 'DailyFitX'.
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
              title, overlay_text, hook, problem, insight, solution, cta, estimated_duration_seconds,
              primary_keyword, retention_note
            - Make the spoken script long enough for at least {min_duration} seconds of voiceover
            - Combined hook + problem + insight + solution + cta should be about {word_count_desc}
            - Hook must create INSTANT curiosity in the first 2 seconds and completely avoid generic greetings
            - overlay_text must be 3 to 7 words, ultra-clear, and look natural as small top-screen text on a Short
            - Make sure the script is A-grade content: highly attractive, deeply engaging, and incredibly helpful to the viewer
            - Every script must feel fresh. Avoid repeating channel cliches, avoid repeating the same CTA pattern, and avoid recycled lines like "ruk mat", "consistency hi sab kuch hai", or "show up every day" unless the topic truly needs it
            - Use "Curiosity Loops": open a question in the hook and promise the answer in the solution
            - Use "Pattern Interrupts": change the tone or angle every 10-15 words to keep the brain engaged
            - The solution MUST provide highly specific, actionable, and life-improving value. Provide real fixes to their struggles.
            - Provide a practical action plan or a hidden insight that gives the viewer an immediate "aha!" moment
            - Emphasize scientifically-backed or logical real-world facts (e.g., exact physiological changes, proven methods)
            - Make the script feel like a high-value masterclass compressed into a flowing story: pain, mechanism, exact fix, result.
            - NO vague "you can do it" motivational fluff. Give them real utility they can apply right now.
            - Avoid fake timelines, miracle claims, and medical promises
            - Use short, punchy spoken lines with high-energy emotional rhythm for TTS and subtitles
            - Use "Hook -> Context -> Problem -> Secret Insight -> Actionable Solution -> High-Energy CTA" flow
            - Avoid filler like 'in this video' or 'let me tell you'
            - Use only Roman script written with normal English letters
            - Do not use Devanagari, Hindi script, emojis, or special symbols
            - Hindi lines must be Roman Hindi only, mixed naturally with English
            - CTA must be action-driven, urgent, and feel native to Shorts, but it must vary from video to video
            - The solution section must teach at least 2 concrete steps, checks, or corrections the viewer can apply immediately
            - Prefer scripts that make the viewer feel smarter in 20 seconds, not just more motivated
            - Use one high-intent search keyword for fitness, yoga, diet, or health
            - Retention note should briefly explain why the opening should hold attention
            - Output should sound credible, sharp, and genuinely helpful enough that viewers save it
            """
        ).strip()

        payload, provider_used = build_json_with_fallback(
            self.llm,
            prompt,
            lambda: self._fallback_script_payload(idea),
            "template-script",
        )
        LOGGER.info("Script generation provider used: %s", provider_used)

        payload = self._normalize_payload(payload)
        if not self._payload_is_usable(payload):
            LOGGER.warning("LLM payload was incomplete or too weak; switching to structured fallback for '%s'", idea.title)
            payload = self._fallback_script_payload(idea)
        hook = payload["hook"].strip()
        problem = payload["problem"].strip()
        insight = payload["insight"].strip()
        solution = payload["solution"].strip()
        cta = payload["cta"].strip()
        overlay_text = payload.get("overlay_text", "").strip()
        full_script = " ".join([hook, problem, insight, solution, cta])
        full_script = self._extend_script_if_needed(full_script, idea)
        clean_title = self._clean_display_text(payload["title"].strip()) or self._clean_display_text(idea.title)
        clean_overlay = self._clean_overlay_text(overlay_text or clean_title)

        return VideoScript(
            title=clean_title,
            overlay_text=clean_overlay,
            hook=hook,
            problem=problem,
            insight=insight,
            solution=solution,
            cta=cta,
            full_script=full_script,
            estimated_duration_seconds=max(min_duration, min(90, int(payload.get("estimated_duration_seconds", min_duration + 5)))),
            primary_keyword=payload["primary_keyword"].strip(),
            retention_note=payload["retention_note"].strip(),
            video_type=getattr(idea, "video_type", "short"),
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
        elif "diet" in title_key or "food" in title_key or "khane" in title_key or "protein" in title_key:
            problem = "Bahut log diet ko sirf kam khana samajhte hain, phir unki energy crash hoti hai aur cravings badhti hain."
            insight = "Real weight loss tab hota hai jab aap calories kam karein par volume aur nutrients badha dein. Gut health is the secret."
            solution = f"Apne khane mein protein aur fibers add karo. {idea.audience_value.lower()} se aapka metabolism aur digestion dono boost honge."
            primary_keyword = "indian diet tips weight loss"
        elif "health" in title_key or "bloating" in title_key or "sleep" in title_key:
            problem = "Modern lifestyle mein hum bhool jate hain ki body ko basic care chahiye. Stress aur fatigue normal nahi hain."
            insight = "Choti aadatein jaise sahi time pe sona aur gut health ka dhyan rakhna aapki life quality badal sakti hain."
            solution = f"Roz bas yeh ek health shift follow karo. {idea.audience_value.lower()} se aap fit aur active feel karenge."
            primary_keyword = "health tips hindi"
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
            insight = f"The real problem is usually poor structure, not low motivation. Without one clear trigger and one measurable action, progress stays random."
            solution = f"Pick one trigger, one action, and one score. Example: same workout time, same first exercise, and track reps or minutes for 7 days. That is how {idea.audience_value.lower()} becomes real."
            primary_keyword = f"{idea.topic} motivation hindi"

        return {
            "title": ScriptGenerator._clean_display_text(idea.title),
            "overlay_text": ScriptGenerator._fallback_overlay_text(idea, style),
            "hook": ScriptGenerator._fallback_hook(idea, style),
            "problem": problem,
            "insight": insight,
            "solution": solution,
            "cta": ScriptGenerator._fallback_cta(style),
            "estimated_duration_seconds": 85 if getattr(idea, "video_type", "short") == "long" else 35,
            "primary_keyword": primary_keyword,
            "retention_note": ScriptGenerator._fallback_retention_note(style),
        }

    @staticmethod
    def _extend_script_if_needed(full_script: str, idea: VideoIdea) -> str:
        words = full_script.split()
        is_long = getattr(idea, "video_type", "short") == "long"
        min_words = 175 if is_long else MIN_SCRIPT_WORDS
        if len(words) >= min_words:
            return full_script

        style = ScriptGenerator._determine_style(idea)
        if style == "yoga":
            extension = (
                " Yoga sirf body shape nahi badalta, yeh andar ka noise bhi dheere dheere shaant karta hai. "
                f"Jab tum {idea.topic.lower()} ko breath ke saath practice karte ho, confidence aur grace dono saath grow karte hain."
            )
        elif style in ("diet", "health"):
            extension = (
                f" Ek simple rule yaad rakho: pehle trigger identify karo, fir fix lagao. "
                f"Agar issue {idea.topic.lower()} se juda hai, toh random hacks nahi, daily repeat hone wala system kaam karega."
            )
        else:
            extension = (
                f" Most people stay stuck because unka plan measurable hi nahi hota. "
                f"If you turn {idea.topic.lower()} into one repeatable system, results stop feeling random and start compounding."
            )
        expanded = f"{full_script}{extension}"
        if len(expanded.split()) < min_words:
            if style == "yoga":
                extra = "Kal ka wait mat karo. Aaj body ko presence do, breath ko control do, aur routine ko respect do."
            elif style in ("diet", "health"):
                extra = "Aaj se ek small food ya recovery change test karo, 7 din observe karo, aur jo kaam kare sirf usi ko repeat karo."
            else:
                extra = "Aaj hi ek baseline set karo, next 7 din compare karo, aur sirf woh habits rakho jo actual result deti hain."
            expanded = f"{expanded} {extra}"
        return expanded

    @staticmethod
    def _determine_style(idea: VideoIdea) -> str:
        haystack = f"{idea.title} {idea.angle} {idea.topic} {idea.hook} {idea.audience_value}".lower()
        yoga_terms = {"yoga", "asana", "breath", "breathing", "mobility", "stretch", "meditation", "pranayam", "pranayama"}
        diet_terms = {"diet", "food", "khana", "protein", "calories", "fat loss", "weight loss", "sugar", "eating", "meal"}
        health_terms = {"health", "gut", "digestion", "pachan", "bloating", "sleep", "fatigue", "energy", "skin"}
        
        if any(term in haystack for term in yoga_terms): return "yoga"
        if any(term in haystack for term in diet_terms): return "diet"
        if any(term in haystack for term in health_terms): return "health"
        return "fitness"

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
        if style in ("diet", "health"):
            return (
                "The language should be helpful, expert-style Hinglish. Use natural Indian terms for food like 'dal', 'paneer', 'pachan' mixed with English terms like 'metabolism', 'nutrients', and 'cravings'."
            )
        return (
            "The language should be Hinglish with short Hindi lines and sharp English punch words. Keep it natural, modern, and varied. Avoid relying on the same signature phrases in every script."
        )

    @staticmethod
    def _tone_direction(style: str) -> str:
        if style == "yoga":
            return (
                "The tone must feel beautiful, soulful, and motivating. Calm power, inner healing, body awareness, and graceful discipline should come through."
            )
        if style == "diet":
            return (
                "The tone must be informative, eye-opening, and practical. Use a 'did you know?' or 'secret revealed' style that makes the viewer feel smarter."
            )
        if style == "health":
            return (
                "The tone must be caring, scientific yet simple, and deeply helpful. Focus on long-term wellness and energy."
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
        if style == "diet":
            return (
                "Focus on one clear payoff like faster metabolism, easier weight loss, better digestion, or budget-friendly healthy eating."
            )
        if style == "health":
            return (
                "Focus on one clear payoff like deep sleep, clear skin, high energy, or better digestion."
            )
        return (
            "Focus on one clear payoff like fat loss, strength, confidence, better form, or discipline."
        )

    @staticmethod
    def _fallback_hook(idea: VideoIdea, style: str) -> str:
        if idea.hook and len(idea.hook.split()) > 4:
            return idea.hook
        topic = idea.topic.lower().replace(" ", " ")
        angle = idea.angle.lower()
        # Dynamic hooks based on angle type for higher stop-the-scroll rate
        if "comparison" in angle or "vs" in topic:
            return f"Bahut log choose karte hain {topic} — lekin dono mein se ek tumhara time waste kar raha hai."
        if "myth" in angle or "truth" in angle:
            return f"{idea.title.split(':')[0].strip()} ke baare mein jo tum sochte ho, woh bilkul galat hai."
        if "beginner" in angle or "start" in topic:
            return f"Shuru karna mushkil nahi hai. Sirf ek wrong step hai jo sabko rok deta hai."
        if "form" in angle or "mistake" in topic:
            return f"Yeh {topic.split()[0]} mistake 90 percent log karte hain. Aur yahi reason hai progress nahi hota."
        if style == "yoga":
            return idea.hook or "Agar tumhara mind heavy hai, shayad tumhe rest nahi — sirf 5 minute ka yeh yoga chahiye."
        return idea.hook or f"{idea.title.split(':')[0].strip()} — yeh un logon ke liye hai jo actually result chahte hain, excuses nahi."

    @staticmethod
    def _fallback_cta(style: str) -> str:
        if style == "yoga":
            return "Agar yeh useful laga, DailyFitX follow karo aur kal se nahi, aaj se 5 mindful minutes lock karo."
        if style == "diet":
            return "Isko save karo, next meal se ek change lagao, aur DailyFitX follow karo for practical fat loss."
        if style == "health":
            return "Is tip ko save karo, 7 din test karo, aur DailyFitX follow karo for simple health fixes."
        return "Isko save karo, next workout mein apply karo, aur DailyFitX follow karo for sharper fitness scripts."

    @staticmethod
    def _fallback_overlay_text(idea: VideoIdea, style: str) -> str:
        title = ScriptGenerator._clean_display_text(idea.title)
        topic = idea.topic.lower()
        if "why" in title.lower() or "kyun" in title.lower():
            return title[:34]
        if "mistake" in topic or "galti" in title.lower():
            return "Yeh galti mat karo"
        if "discipline" in topic or "motivation" in topic:
            return "Aaj yeh sun lo"
        if style == "yoga":
            return "Mind ko calm karo"
        return "Result chahiye toh dekho"

    @staticmethod
    def _fallback_retention_note(style: str) -> str:
        if style == "yoga":
            return "Hindi-first emotional hook opens with pain relief and promises calm plus visible body change."
        if style in ("diet", "health"):
            return "The opening creates a problem-solution gap fast and promises a usable fix, which improves saves and retention."
        return "The opening challenges a common mistake fast, then pays it off with concrete steps instead of generic hype."

    @classmethod
    def _normalize_payload(cls, payload: dict) -> dict:
        normalized = dict(payload)
        for key in ("title", "overlay_text", "hook", "problem", "insight", "solution", "cta", "primary_keyword", "retention_note"):
            normalized[key] = cls._clean_display_text(str(normalized.get(key, "")))
        return normalized

    @staticmethod
    def _payload_is_usable(payload: dict) -> bool:
        required_keys = ("title", "hook", "problem", "insight", "solution", "cta", "primary_keyword", "retention_note")
        if any(not str(payload.get(key, "")).strip() for key in required_keys):
            return False
        combined = " ".join(str(payload.get(key, "")) for key in ("hook", "problem", "insight", "solution", "cta")).lower()
        banned_repetition = (
            "ruk mat",
            "show up every day",
            "consistency is everything",
        )
        if sum(1 for phrase in banned_repetition if phrase in combined) >= 2:
            return False
        return len(combined.split()) >= 45

    @staticmethod
    def _contains_non_ascii_text(value: str) -> bool:
        return any(ord(char) > 127 for char in value)

    @staticmethod
    def _clean_display_text(value: str) -> str:
        text = re.sub(r"\b\d{6,}\b", "", value)
        text = re.sub(r"[_-]\d{4,}\b", "", text)
        text = "".join(char for char in text if ord(char) < 128)
        text = re.sub(r"\s*[|:]\s*\d+\s*$", "", text)
        text = re.sub(r"\s+", " ", text).strip(" -_")
        return text.strip()

    @classmethod
    def _clean_overlay_text(cls, value: str) -> str:
        text = cls._clean_display_text(value)
        text = re.sub(r"[^\w\s?!]", "", text)
        words = text.split()
        if not words:
            return "Watch this"
        return " ".join(words[:5])[:28].strip()
