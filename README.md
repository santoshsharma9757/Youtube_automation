# Wonder Stories TV – Automation Pipeline

Python automation pipeline for **Wonder Stories TV** — AI-generated viral Hindi stories covering Mystery, Suspense, Horror, Thriller, Crime, Karma, Dark Facts, Psychological, Shocking Facts, Real-Life Facts, and Moral Stories.

## Pipeline Priority

```
1. SCRIPT  → LLM generates complete Hindi story + voiceover script
2. VOICE   → ElevenLabs (Raunak) synthesizes viral Hindi narration
3. IMAGES  → Cinematic scene image prompts saved for manual generation
4. STITCH  → Assemble clips + audio into final video
5. DEPLOY  → Upload to YouTube with viral SEO metadata
```

## Story Categories

| Category | Description |
|---|---|
| `mystery_stories` | Mystery stories with shocking twist endings |
| `shocking_facts` | Jaw-dropping real/fictional facts |
| `suspense_stories` | Psychological tension with unresolved builds |
| `dark_facts` | Dark side of history, world, and society |
| `psychological` | Mind-bending stories, inner conflict |
| `thriller_stories` | High stakes, fast-paced thrills |
| `horror_stories` | Atmospheric horror with cinematic imagery |
| `crime_stories` | Real/fictional crime with justice served |
| `karma_stories` | Poetic justice and karma stories |
| `real_life_facts` | Inspiring/shocking real events |
| `moral_stories` | Powerful life lesson stories |

## Video Formats

| Format | Mode | Duration |
|---|---|---|
| Short | Image-to-video | Max **45 seconds** (5–7 scenes × 7–8s) |
| Short | Video-to-video | Max **45 seconds** (4–5 scenes × 9–10s) |
| Long | Image-to-video | Max **3 minutes** (10–14 scenes × 12–15s) |
| Long | Video-to-video | Max **3 minutes** (8–10 scenes × 15–20s) |

## Setup

1. Create and activate a Python 3.10+ virtual environment.
2. `pip install -r requirements.txt`
3. Install FFmpeg and add it to `PATH`.
4. Add `.env` with your keys:

```env
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=<raunak_voice_id>   # Set Raunak's voice ID here
YOUTUBE_API_KEY=...
YOUTUBE_CLIENT_SECRETS_FILE=client_secret.json
UPLOAD_ENABLED=false
CHANNEL=stories
CHANNEL_NAME=Wonder Stories TV
CHANNEL_HANDLE=@WonderStoriesTV
```

## Usage

### Generate 1 short story (default: mystery)
```powershell
python main.py --count 1
```

### Generate a long story
```powershell
python main.py --long
```

### Generate with specific category
```powershell
python main.py --count 2 --category horror_stories
```

### Force a specific topic from the topic bank
```powershell
python main.py --topic "Woh Letter Jo 20 Saal Baad Aaya"
```

### Use video-to-video mode (instead of image)
```powershell
python main.py --count 1 --mode video
```

### Skip voiceover during generation (save API costs)
```powershell
python main.py --count 1 --no-voice
```

### Use free local Edge TTS (no ElevenLabs cost)
```powershell
python main.py --count 1 --local-tts
```

### Stitch manually placed images/clips into final video
```powershell
python main.py --stitch
```

### Deploy / schedule stitched videos to YouTube
```powershell
python main.py --deploy
```

### Start the scheduler (runs daily at 2:30 PM IST)
```powershell
python main.py --schedule
```

## Module Structure

| File | Purpose |
|---|---|
| `main.py` | CLI entry point, orchestrates the pipeline |
| `config.py` | All config via `.env` — API keys, paths, channel settings |
| `story_idea_generator.py` | Generates viral story ideas across 11 categories |
| `story_generator.py` | LLM generates complete Hindi script + scene image prompts |
| `tts_engine.py` | ElevenLabs (Raunak) primary + Edge TTS fallback |
| `video_assembler.py` | MoviePy + FFmpeg video assembly with subtitles |
| `seo_generator.py` | YouTube SEO: viral titles, tags, descriptions |
| `story_topics.py` | 200+ curated viral story seeds across all categories |
| `upload_all.py` | Schedules & uploads videos to YouTube |
| `uploader.py` | YouTube Data API v3 uploader |
| `llm_fallback.py` | OpenAI → Gemini → DeepSeek fallback chain |
| `scheduler.py` | APScheduler — runs pipeline daily at 2:30 PM IST |

## Folder Structure

```
input/clips/{story_folder}/       ← Place your scene images/videos here
  plan.json                       ← Story plan with scene details
  metadata.json                   ← SEO + upload metadata
  scene_1.mp3, scene_2.mp3...     ← Pre-synthesized voiceovers

output/veo_prompts/{story}.txt    ← Complete prompts file (copy-paste ready)
output/final_videos/              ← Assembled videos ready for upload
output/data/                      ← JSON data stores
```
