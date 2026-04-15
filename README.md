# Janapakchya Nepal Shorts Automation

Production-oriented Python automation project for generating high-quality YouTube Shorts about Nepal in simple Nepali.

## Features

- AI idea generation focused on Nepal's history, economy, corruption, development, awareness, and solutions
- Script generation with a fixed Shorts-friendly structure
- Text-to-speech with ElevenLabs primary and gTTS fallback
- Vertical video rendering with MoviePy
- OpenAI Whisper API transcription for subtitles
- SEO title, description, and tags generation
- Search-intent optimization for Nepal and Nepali queries
- Manual topic mode for directed Nepal explainers
- Optional YouTube upload through Data API v3
- Daily scheduling via APScheduler
- Logging, duplicate protection, and reusable modules

## Project Structure

```text
project/
|-- main.py
|-- config.py
|-- idea_generator.py
|-- script_generator.py
|-- tts.py
|-- video_generator.py
|-- subtitle_generator.py
|-- seo_generator.py
|-- uploader.py
|-- scheduler.py
|-- assets/
|   |-- backgrounds/
|   `-- fonts/
|-- output/
|-- requirements.txt
`-- .env
```

## Setup

1. Create and activate a Python 3.10+ virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Install FFmpeg and ensure it is available in your `PATH`.

3. Add a Nepali-friendly font file to:

```text
assets/fonts/NotoSansDevanagari-Bold.ttf
```

4. Add Nepal-related portrait images or videos to:

```text
assets/backgrounds/
```

5. Fill in `.env`:

- `OPENAI_API_KEY`: required for ideas, scripts, and SEO
- `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`: optional but recommended for better voice quality
- `YOUTUBE_CLIENT_SECRETS_FILE`: OAuth client JSON from Google Cloud
- `UPLOAD_ENABLED=true`: only when you are ready to publish

6. For YouTube upload:

- Enable YouTube Data API v3 in Google Cloud
- Download OAuth desktop client credentials
- Save the JSON file at the path set in `.env`
- The first upload run opens a local OAuth flow and stores `youtube_token.json`

## Usage

Generate one Short locally without uploading:

```powershell
python main.py --count 1
```

Generate and upload one Short:

```powershell
python main.py --count 1 --upload
```

Generate one topic-driven Nepali explainer:

```powershell
python main.py --topic "नेपालका ७ प्रदेश"
```

Generate and upload a topic-driven Nepali explainer:

```powershell
python main.py --topic "नेपालका ७ प्रदेश" --upload
```

Start the daily scheduler:

```powershell
python main.py --schedule
```

Generate up to three videos in one run:

```powershell
python main.py --count 3
```

## Output

Generated files are stored under `output/`:

- `output/audio/`: voice tracks
- `output/videos/`: rendered Shorts
- `output/subtitles/`: SRT and Whisper JSON
- `output/data/ideas.json`: generated ideas
- `output/data/content_history.json`: content history for duplicate protection
- `output/logs/automation.log`: run logs

## Notes

- Shorts recognition on YouTube is primarily based on vertical aspect ratio and total duration under 60 seconds.
- To keep quality high, background assets should be relevant to the script topic.
- gTTS fallback may sound less natural than ElevenLabs.
- Subtitle generation uses the OpenAI transcription API, so it does not require a local Whisper installation.
- The scheduler runs once daily at 9:00 AM in the timezone set by `SCHEDULER_TIMEZONE`, and each run generates `DAILY_VIDEO_COUNT` videos.
- Ranking is not controlled by metadata alone. Titles, first-two-second hook, retention, rewatches, comments, and topic freshness matter more than tags.

## Ranking Guidance

- Target one primary keyword per Short, such as a Nepal problem, policy, city, or issue people would genuinely search for.
- Keep the hook emotionally strong but credible; misleading intros can hurt retention.
- Use specific Nepal terms in title and script, not only generic words like "facts" or "viral".
- Publish consistently and review which topics get the best average view duration and swipe-through rate.
