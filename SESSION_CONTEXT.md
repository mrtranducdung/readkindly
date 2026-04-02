# Session Context

This repo has two separate content-generation tracks:

1. `genstory.py` + `webapp.py` flow
This is the active flow for the local story web app.

2. `src/` + `output/` flow
This still exists, but it is only used indirectly now because `generate_new.py`
calls the LLM story generator in `src/llm_agents.py` to create a fresh story
config for the active `genstory.py` pipeline.

## Active App Structure

- `webapp.py`
Flask backend for the story player and admin UI.
Uses:
  - `stories.db` for story metadata
  - `story_storage/<story_id>/` for imported assets
  - `templates/index.html` as the SPA frontend

- `templates/index.html`
Single-page frontend with:
  - home library
  - fullscreen player
  - admin login/dashboard

- `genstory.py`
Core local pipeline for:
  - loading a story config
  - generating a hook image first
  - generating 10 scene images using the hook image as reference
  - generating per-slide audio
  - rendering the final video

- `generate_new.py`
Entry point for the main workflow.
Behavior now:
  1. asks the LLM for a brand-new story
  2. writes project-root `story_config.json`
  3. writes a run-local copy to `out/<timestamp>/story_config.json`
  4. generates images only
  5. stops and waits for review

- `continue_generate.py`
Resumes the latest reviewed run with status `images_ready`.
Behavior:
  1. loads the run-local config from `out/<timestamp>/story_config.json`
  2. generates audio and video
  3. imports the run into `story_storage/` and `stories.db`

- `regenerate_scene.py`
Regenerates one scene image for the latest paused reviewable run.
Uses the already-generated `hook.png` as the reference image and optionally
appends extra user guidance to that scene prompt.

- `review_workflow.py`
Shared helpers for paused/resumable runs.
Stores:
  - `out/<timestamp>/story_config.json`
  - `out/<timestamp>/review_state.json`

## Current Image/Audio/Video Output Model

During a run, the dated output directory contains:

```text
out/<timestamp>/
  story_config.json
  review_state.json
  images/
    hook.png
    scene_01.png
    scene_02.png
    ...
    scene_10.png
  audio/
    captions.srt
    narration.mp3
    clips/
      hook.mp3
      outro.mp3
      scene_01.mp3
      ...
      scene_10.mp3
    scenes/
      hook.mp3
      outro.mp3
      scene_01.mp3
      ...
      scene_10.mp3
  video/
    story_video.mp4
    thumb.jpg
```

Important:
- there are now 11 images total per story
- `hook.png` is generated first
- `hook.png` is used as the reference image for all scene generations

## Story Config Model

`generate_new.py` writes a fresh `story_config.json` each run.
Important fields:
- `title`
- `hook`
- `moral`
- `outro`
- `hashtags`
- `hook_image_prompt`
- `characters`
- `character_consistency_prompt`
- `scenes` with exactly 10 items

Prompt behavior:
- `src/llm_agents.py` is instructed to return exactly 10 scenes
- prompts are compacted in `generate_new.py` before being written to config
- the old hardcoded Lumi-only prompt anchor was removed from the main path
- consistency is now driven mainly by the reference hook image, with a short
  character reminder appended by `PromptConsistencyAgent`

## Review / Resume Workflow

This is the main working model now.

### `generate_new`

Plain text `generate_new` should be interpreted as:

```bash
python generate_new.py
```

Expected result:
- a brand-new story config
- `hook.png` plus `scene_01.png` through `scene_10.png`
- `review_state.json` written with status `images_ready`
- no audio/video/import yet

After this, the assistant should stop and wait for review.

### `go ahead`

When the user says `go ahead`, the intended action is:

```bash
python continue_generate.py
```

Expected result:
- audio generation
- video render
- import into `story_storage/`
- insert into `stories.db`

### `regenerate scene N ...`

When the user says something like:

```text
regenerate scene 7 to make the character more consistent
```

the intended action is to run:

```bash
python regenerate_scene.py 7 to make the character more consistent
```

Behavior:
- edits the run-local `out/<timestamp>/story_config.json` scene prompt
- regenerates only that scene image
- keeps the same `hook.png` reference image
- keeps the run in `images_ready` review state

## Web App Data Model

`webapp.py` stores each published story under:

```text
story_storage/<story_id>/
  meta.json
  images/
    hook.png
    1.png
    2.png
    ...
    10.png
  audio/
    hook.mp3
    outro.mp3
    scene_01.mp3
    ...
    scene_10.mp3
```

`stories.db` table: `stories`
Columns:
- `id`
- `title`
- `moral`
- `hook`
- `outro`
- `hashtags`
- `scene_count`
- `created_at`
- `display_order`

## Player Model

The frontend player in `templates/index.html` uses:
- intro slide with `hook.png`
- one slide per scene image
- outro slide using the last scene image

Audio mapping:
- intro uses `/audio/hook`
- each scene uses `/audio/<scene_index>`
- outro uses `/audio/outro`

Important details:
- the library thumbnail now prefers `/image/hook`
- the player does not use the combined narration track for playback
- it expects per-slide audio files in storage

## Import Behavior

`import_story.py` now prefers the run-local config:

1. `out/<timestamp>/story_config.json`
2. fallback to project-root `story_config.json`

This matters because paused review runs and later runs must not get mixed up.

## Skill Behavior

A Codex skill exists at:

`~/.codex/skills/generate-new-story/`

But the practical trigger for this repo is plain text:
- `generate_new`
- `run generate_new`

The important behavior is no longer “run everything to import immediately.”
Future sessions should follow the new review checkpoint:
- `generate_new` -> stop after images
- `go ahead` -> continue from the latest `images_ready` run
- `regenerate scene N ...` -> redo just that scene

## Important Working Assumptions

- The user wants this flow fully automatic up to the image-review checkpoint.
- The user wants exactly 10 scenes plus 1 hook image.
- The hook image should include the recurring characters and set the story theme.
- The hook image is the consistency reference for all scene images.
- Future sessions should prefer the `generate_new.py` + `continue_generate.py` + `regenerate_scene.py` + `webapp.py` flow unless the user explicitly asks to work on the separate `src/` pipeline directly.
