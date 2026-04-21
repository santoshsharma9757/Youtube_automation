# DailyFitX Shorts Automation

Production-oriented Python automation project for generating YouTube Shorts around fitness, yoga, meditation, motivation, fat loss, and healthy lifestyle content.

## Features

- AI idea generation for fitness and wellness topics
- Live trend discovery from YouTube when `YOUTUBE_API_KEY` is configured
- Script generation with a Shorts-friendly hook -> value -> CTA flow
- Text-to-speech with ElevenLabs primary and gTTS fallback
- Vertical video rendering with MoviePy
- Subtitle generation and SEO packaging
- Optional YouTube upload through Data API v3
- Scheduling via APScheduler
- Duplicate protection, history tracking, and reusable modules

## Setup

1. Create and activate a Python 3.10+ virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Install FFmpeg and ensure it is available in your `PATH`.
4. Add relevant portrait assets to `assets/backgrounds/` or local video clips to `assets/localvideos/`.
5. Fill in `.env` with the keys you want to use:

- `OPENAI_API_KEY`: recommended for scripts, SEO, and live-trend idea synthesis
- `YOUTUBE_API_KEY`: recommended for live YouTube trend discovery
- `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`: optional for voice quality
- `YOUTUBE_CLIENT_SECRETS_FILE`: required only for uploads
- `UPLOAD_ENABLED=true`: only when you are ready to publish

## Usage

Generate one Short locally:

```powershell
python main.py --count 1
```

Generate one topic-driven Short:

```powershell
python main.py --topic "walking yoga for stress relief"
```

Generate and upload one topic-driven Short:

```powershell
python main.py --topic "fasted morning workout sahi ya galat" --upload
```

Start the scheduler:

```powershell
python main.py --schedule
```

## Notes

- When `YOUTUBE_API_KEY` is available, the app first tries to collect recent YouTube Shorts trend signals and turns those into DailyFitX-style ideas.
- If live YouTube trend discovery is unavailable, the app falls back to the local ranked topic bank.
- Ranking depends more on hook strength, retention, replayability, and topic freshness than on tags alone.
