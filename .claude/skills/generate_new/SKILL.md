---
name: generate_new
description: Generate a new kids moral story for the webapp. Claude invents the story config, generates hook + scene images, then stops for review. Say 'go ahead' to continue with audio/video/import.
disable-model-invocation: true
---

Generate a brand-new kids moral story by following these exact steps:

## Step 1 — Claude writes story_config.json

You (Claude) invent the story. Do NOT call Mistral or any LLM. Write the story config directly.

If the user suggested a theme (e.g. "generate_new about a brave little elephant" or "generate_new with friendship theme"), build the story around that theme. Otherwise invent a fresh theme.

Create a story with:
- Cute animal characters (bunny, bear, fox, owl, or similar)
- A clear positive moral
- Bright, child-friendly visuals
- Exactly 10 scenes, each ~5-7 seconds
- Total video around 70-90 seconds

Write the JSON to `/home/dung/Desktop/kids-tiktok-agent/story_config.json` with this exact schema:

```json
{
  "title": "string — catchy story title",
  "hook": "string — opening question or hook line read aloud on intro slide",
  "moral": "string — the lesson (e.g. 'Sharing makes everyone happier')",
  "outro": "string — closing sentence read aloud on outro slide, e.g. '[Title] shows that [moral]'",
  "hashtags": ["#kids", "#goodhabits", "#storytime"],
  "hook_image_prompt": "string — rich visual description of the opening image showing all main characters together (max 60 words)",
  "characters": [
    {
      "name": "string",
      "description": "string — visual description for consistency (fur color, clothing, accessories)"
    }
  ],
  "character_consistency_prompt": "string — 'Same recurring characters as the hook image: Name1, Name2'",
  "scenes": [
    {
      "index": 1,
      "title": "string",
      "narration": "string — short sentence read aloud (1-2 sentences)",
      "on_screen_text": "string — very short text overlay (3-6 words)",
      "image_prompt": "string — detailed visual description for this scene (max 55 words)",
      "duration_seconds": 6.0
    }
  ]
}
```

Rules:
- Exactly 10 scenes (index 1 through 10)
- Keep narration short and simple (child-safe)
- Keep on_screen_text very short (3-6 words)
- image_prompt must describe animal characters and setting richly
- hook_image_prompt must show ALL main characters together
- character_consistency_prompt: "Same recurring characters as the hook image: Name1, Name2, ..."

## Step 2 — Run generate_new.py --from-config

After writing story_config.json, run:

```bash
cd /home/dung/Desktop/kids-tiktok-agent && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True /home/dung/anaconda3/envs/demo/bin/python generate_new.py --from-config
```

This will:
1. Read the `story_config.json` you just wrote
2. Generate `hook.png` (the anchor/reference image for character consistency)
3. Generate `scene_01.png` through `scene_10.png` using `hook.png` as the reference
4. Write `review_state.json` with status `images_ready`
5. **Stop and wait** — no audio, no video, no import yet

When the script finishes, report:
- The story title
- The workdir path (`out/YYYY-MM-DD_HH-MM-SS/`)
- The hook image path
- Ask the user to review the images, then say **"go ahead"** to continue or **"regenerate scene N"** to redo a scene

## Step 3 — Wait for user review

Do NOT proceed automatically. The user needs to view the generated images and decide:

- **"go ahead"** → run `continue_generate.py` (generates audio, video, imports into webapp)
- **"regenerate scene N ..."** → run `regenerate_scene.py N <extra guidance>` (redoes just that scene image using `hook.png` as reference, keeps status `images_ready`)

## When user says "go ahead"

```bash
cd /home/dung/Desktop/kids-tiktok-agent && /home/dung/anaconda3/envs/demo/bin/python continue_generate.py
```

This will:
- Generate per-slide audio with ElevenLabs (hook.mp3, outro.mp3, scene_01.mp3 … scene_10.mp3)
- Assemble the final video with subtitles
- Import the story into `story_storage/` and `stories.db`
- Mark the run as `completed`

Report the story ID, video path, and that it is now live at http://localhost:5000

## When user says "regenerate scene N ..."

```bash
cd /home/dung/Desktop/kids-tiktok-agent && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True /home/dung/anaconda3/envs/demo/bin/python regenerate_scene.py N <extra guidance words>
```

Example: "regenerate scene 7 make the fox look friendlier" →
```bash
python regenerate_scene.py 7 make the fox look friendlier
```

This regenerates only that one scene image using `hook.png` as the consistency reference, optionally appending extra guidance to the image prompt. The run stays in `images_ready` state. After regeneration, ask the user to review again.

## Output model reminder

After a successful run the dated output directory contains:
```
out/<timestamp>/
  story_config.json      ← run-local config (source of truth for this run)
  review_state.json
  images/
    hook.png             ← anchor image (generated first, used as IP-Adapter reference)
    scene_01.png … scene_10.png
  audio/
    clips/               ← raw TTS clips
      hook.mp3, outro.mp3, scene_01.mp3 … scene_10.mp3
    scenes/              ← per-slide audio (copied to story_storage on import)
      hook.mp3, outro.mp3, scene_01.mp3 … scene_10.mp3
  video/
    story_video.mp4
    thumb.jpg
```

The webapp player shows **12 slides**: intro (hook image + hook audio) → 10 story scenes → outro (last scene image + outro audio).
