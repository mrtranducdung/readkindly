from __future__ import annotations

import argparse
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
import upload_to_render


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default="", help="Specific run workdir (default: latest images_ready)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    _load_env()

    if args.workdir:
        workdir = Path(args.workdir).resolve()
    else:
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

    # Upload to Render review queue
    render_url = os.getenv("RENDER_URL", "").rstrip("/")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if render_url:
        print(f"\nUploading to Render review queue: {render_url} ...")
        try:
            session = upload_to_render.login(render_url, admin_password)
            result_render = upload_to_render.upload_pending_review(session, workdir, render_url)
            print(f"✅ Story in review queue: \"{result_render['title']}\"")
            print(f"   Review at: {render_url} → Admin → Review Queue")
        except Exception as e:
            print(f"✗ Render upload failed: {e}")
    else:
        print("\nSkipping Render upload (RENDER_URL not set)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
