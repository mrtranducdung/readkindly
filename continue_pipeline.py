#!/usr/bin/env python3
"""Continue the pipeline from images_ready state: run narration + video."""
import json
import os
import sys
from pathlib import Path

# Load .env
def _load_env(path: str = ".env") -> None:
    env_file = Path(path)
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

_load_env()

import random
from genstory import (
    StoryPackage, Scene, Character,
    NarrationAgent, VideoAgent, QAAgent,
)

workdir = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(Path("out").glob("????-??-??_??-??-??"), reverse=True)[0]
print(f"Working in: {workdir}")

# 1. Load story config
data = json.loads((workdir / "story_config.json").read_text(encoding="utf-8"))
scenes = [
    Scene(
        index=s["index"],
        title=s["title"],
        narration=s["narration"],
        on_screen_text=s["on_screen_text"],
        image_prompt=s["image_prompt"],
        duration_seconds=float(s["duration_seconds"]),
    )
    for s in data["scenes"]
]
characters = [
    Character(name=c["name"], description=c["description"])
    for c in data.get("characters", [])
]
story = StoryPackage(
    title=data.get("title", scenes[0].title),
    hook=data["hook"],
    moral=data["moral"],
    hook_image_prompt=data.get("hook_image_prompt", data["scenes"][0]["image_prompt"]),
    scenes=scenes,
    outro=data["outro"],
    character_consistency_prompt=data.get("character_consistency_prompt", ""),
    hashtags=data.get("hashtags", []),
    characters=characters,
)

# 2. Attach image paths
images_dir = workdir / "images"
story.hook_image_path = str(images_dir / "hook.png")
for scene in story.scenes:
    scene.image_path = str(images_dir / f"scene_{scene.index:02d}.png")

# 3. Narration
elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
_voices = [v.strip() for v in os.getenv("ELEVENLABS_VOICE_IDS", "").split(",") if v.strip()]
if not _voices:
    _voices = [v.strip() for v in os.getenv("ELEVENLABS_VOICE_ID", "").split(",") if v.strip()]
voice = random.choice(_voices) if _voices else ""
print(f"Voice: {voice}")

narration_agent = NarrationAgent(workdir / "audio", elevenlabs_key, voice)
narration = narration_agent.run(story)

# 4. Video
video_agent = VideoAgent(workdir / "video")
video = video_agent.run(story, narration)

# 5. QA
qa_agent = QAAgent()
qa = qa_agent.run(story, narration, video)
print("QA:", qa)

# 6. Update review_state
import datetime
review = {
    "status": "video_ready",
    "workdir": str(workdir.resolve()),
    "updated_at": datetime.datetime.now().isoformat(),
    "title": story.title,
    "scene_count": len(story.scenes),
    "qa": qa,
}
(workdir / "review_state.json").write_text(json.dumps(review, indent=2))
print(f"\nDone! Video: {video.video_path}")
print(f"review_state.json updated → status=video_ready")
