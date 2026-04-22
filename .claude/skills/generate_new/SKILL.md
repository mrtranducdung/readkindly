---
name: generate_new
description: Generate a new kids moral story end-to-end. Claude writes the story config, generates images, then automatically generates audio+video and uploads the complete story to the Render review queue. No chat approval needed — go straight to the webapp to review and publish.
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

## Step 2 — Run generate_new.py --from-config (images)

```bash
cd /home/dung/Desktop/kids-tiktok-agent && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True /home/dung/anaconda3/envs/demo/bin/python generate_new.py --from-config
```

This generates hook.png + scene_01.png … scene_10.png. When it finishes, immediately proceed to Step 3 — do NOT stop and ask the user.

## Step 3 — Run continue_generate.py (audio + video + upload for review)

```bash
cd /home/dung/Desktop/kids-tiktok-agent && /home/dung/anaconda3/envs/demo/bin/python continue_generate.py
```

This will:
1. Generate per-slide audio (hook.mp3, outro.mp3, scene_01.mp3 … scene_10.mp3)
2. Assemble the final video with subtitles
3. Automatically upload the complete story to the Render review queue

When done, tell the user:

> "**[Story Title]** is ready for review. Go to **https://readkindly.onrender.com** → Admin → Review Queue to watch the video and click **Approve & Publish** when you're happy with it."

Do NOT wait for "go ahead" — the full pipeline runs automatically in one shot.

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
