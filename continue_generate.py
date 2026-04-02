from __future__ import annotations

import json
import os
from pathlib import Path

from genstory import _load_env
from import_story import import_story
from review_workflow import (
    build_pipeline,
    find_latest_reviewable_run,
    load_review_state,
    load_story_for_workdir,
    run_config_path,
    save_review_state,
)


def main() -> int:
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    _load_env()

    workdir = find_latest_reviewable_run({"images_ready"})
    state = load_review_state(workdir)
    config = json.loads(run_config_path(workdir).read_text(encoding="utf-8"))
    story = load_story_for_workdir(workdir)
    pipeline = build_pipeline(workdir)

    print(f"Resuming reviewed run: {workdir}")
    narration = pipeline.narration_agent.run(story)
    video = pipeline.video_agent.run(story, narration)
    qa = pipeline.qa_agent.run(story, narration, video)

    imported = import_story(workdir)
    if not imported:
        raise RuntimeError(f"Generation finished but import failed for {workdir}")

    save_review_state(
        workdir,
        "completed",
        title=config.get("title"),
        scene_count=len(config.get("scenes", [])),
        story_id=imported["id"],
        qa=qa,
    )

    print("\nGeneration summary:")
    print(
        json.dumps(
            {
                "workdir": str(workdir),
                "story_id": imported["id"],
                "title": imported["title"],
                "scene_count": imported["scene_count"],
                "video_path": video.video_path,
                "previous_status": state.get("status"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
