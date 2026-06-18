# Wonder Stories TV – Automation Pipeline

Python automation pipeline for **Wonder Stories TV** — AI-generated Hindi kids stories featuring **Chintu** and magical elements with moral lessons.

## Features

- AI story idea generation (Chintu series, mythology, dadi kahani, animal tales, etc.)
- LLM-generated 4-scene (Short) or 8-scene (Long/Mini) story plans
- Scene prompts saved for manual AI video/image generation (Veo / Imagen)
- Edge TTS narration with Hindi voiceover
- Vertical video assembly with subtitles and transitions (MoviePy + FFmpeg)
- Kids SEO packaging — title, description, tags, hashtags
- YouTube Data API v3 upload with scheduled publish times
- Facebook/Instagram Reels cross-posting
- APScheduler for daily automated runs

## Setup

1. Create and activate a Python 3.10+ virtual environment.
2. `pip install -r requirements.txt`
3. Install FFmpeg and add it to `PATH`.
4. Add `.env` with your keys:

```
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
YOUTUBE_API_KEY=...
YOUTUBE_CLIENT_SECRETS_FILE=client_secret.json
UPLOAD_ENABLED=false
CHANNEL=stories
CHANNEL_NAME=Wonder Stories TV
CHANNEL_BRAND=Chintu
CHANNEL_HANDLE=@WonderStoriesTV
```

## Usage

### Generate story prompts (1 Short)
```powershell
python main.py --count 1
```

### Generate a Long / Mini story
```powershell
python main.py --long
```

### Force a specific story topic
```powershell
python main.py --topic "Chintu Aur Magical Watch"
```

### Force a story category
```powershell
python main.py --count 2 --category mythology
```

### Stitch manually placed clips into final video
```powershell
python main.py --stitch
```

### Deploy / schedule stitched videos to YouTube + Facebook
```powershell
python main.py --deploy
```

### Mark as Made for Kids
```powershell
python main.py --stitch --children
```

### Start the scheduler (runs daily at 2:30 PM IST)
```powershell
python main.py --schedule
```

## Pipeline Flow

```
Idea Generation → Story Plan (JSON) → Scene Prompts saved
    → Manual AI video/image creation → Stitch (--stitch)
    → SEO packaging → Upload / Schedule (--deploy)
```

## Story Categories

| Category | Description |
|---|---|
| `magical_adventure` | Chintu + magical object + moral (core series) |
| `mythology` | Indian epics simplified for kids |
| `dadi_kahani` | Grandma tales — nostalgia + magic |
| `real_life` | Everyday situations with a magical twist |
| `family_funny` | Relatable family comedy |
| `animal_tales` | Talking animal stories |
| `mystery` | Short whodunit / puzzle stories |
| `seasonal` | Festival content (Diwali, Holi, Raksha Bandhan, etc.) |
| `horror` | Cozy spooky stories with moral |
