from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from genstory import MoralStoryPipeline, PromptConsistencyAgent, StoryAgent, StoryIdea, StoryPackage

REVIEW_STATE_NAME = "review_state.json"
RUN_CONFIG_NAME = "story_config.json"


def review_state_path(workdir: Path) -> Path:
    return Path(workdir) / REVIEW_STATE_NAME


def run_config_path(workdir: Path) -> Path:
    return Path(workdir) / RUN_CONFIG_NAME


def write_run_config(workdir: Path, config: dict[str, Any]) -> Path:
    path = run_config_path(workdir)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def save_review_state(workdir: Path, status: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "workdir": str(Path(workdir).resolve()),
        "updated_at": datetime.now().isoformat(),
    }
    payload.update(extra)
    review_state_path(workdir).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_review_state(workdir: Path) -> dict[str, Any]:
    return json.loads(review_state_path(workdir).read_text(encoding="utf-8"))


def find_latest_reviewable_run(statuses: set[str] | None = None) -> Path:
    out_root = Path("out")
    if not out_root.exists():
        raise FileNotFoundError("No out/ directory found.")

    dated_dirs = sorted(
        [d for d in out_root.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)],
        reverse=True,
    )
    for workdir in dated_dirs:
        state_file = review_state_path(workdir)
        if not state_file.exists():
            continue
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if statuses is None or state.get("status") in statuses:
            return workdir
    wanted = ", ".join(sorted(statuses)) if statuses else "any status"
    raise FileNotFoundError(f"No reviewable run found with status: {wanted}")


def load_story_for_workdir(workdir: Path) -> StoryPackage:
    story = StoryAgent()._load_from_json(run_config_path(workdir))
    story = PromptConsistencyAgent().run(story)
    attach_generated_images(story, workdir)
    return story


def attach_generated_images(story: StoryPackage, workdir: Path) -> StoryPackage:
    images_dir = Path(workdir) / "images"
    for ext in ("png", "jpg", "jpeg"):
        hook_path = images_dir / f"hook.{ext}"
        if hook_path.exists():
            story.hook_image_path = str(hook_path)
            break

    for scene in story.scenes:
        for ext in ("png", "jpg", "jpeg"):
            scene_path = images_dir / f"scene_{scene.index:02d}.{ext}"
            if scene_path.exists():
                scene.image_path = str(scene_path)
                break
    return story


def build_pipeline(workdir: Path) -> MoralStoryPipeline:
    return MoralStoryPipeline(workdir=str(Path(workdir)), tiktok_access_token="", reference_image_path="")


def default_story_idea(config: dict[str, Any]) -> StoryIdea:
    return StoryIdea(
        topic=config.get("title", "story"),
        moral=config.get("moral", ""),
        scene_count=len(config.get("scenes", [])),
    )
