# Kids TikTok Agent

A fully automated daily content pipeline for a kids education TikTok channel.

What it does:
1. Generates a short moral story with an AI model
2. Converts the story into short scenes
3. Creates simple visual slides automatically
4. Generates narration audio with TTS
5. Adds subtitles
6. Renders a vertical 1080x1920 MP4 video
7. Saves caption and hashtags for posting

This starter is designed to run locally every day.

## Quick start

### 1) Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2) Install ffmpeg
Movie rendering needs ffmpeg installed and available on PATH.

### 3) Set environment variables
Copy `.env.example` to `.env` and fill in your API key.

```bash
cp .env.example .env
```

### 4) Generate one video
```bash
python -m src.main
```

### 4b) Generate and publish to the web app
```bash
python generate_new.py
```

This runs the `genstory.py` pipeline, writes a fresh dated folder under `out/`,
then imports the generated images/audio/config into the Flask web app's
`story_storage/` and `stories.db`.

### 5) Generate daily
Mac/Linux cron example:
```bash
0 8 * * * cd /path/to/kids-tiktok-agent && /usr/bin/env bash -lc 'source .venv/bin/activate && python -m src.main'
```

## Supported model providers
This project uses an OpenAI-compatible chat API by default.
You can point it at:
- OpenAI
- OpenRouter
- compatible gateways
- local compatible endpoints

Set:
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` if needed
- `MODEL_NAME`

## Output
Each run creates a new folder in `output/` containing:
- `story.json`
- `script.json`
- `caption.txt`
- `scene_*.png`
- `narration.mp3`
- `subtitles.srt`
- `video.mp4`

## Notes
- This is fully automated generation, but you should still review before posting.
- The visual style is intentionally simple and dependable: bright slide visuals with text and icons.
- You can later replace the slide generator with image generation APIs.
