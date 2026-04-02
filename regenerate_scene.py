from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from genstory import ImageAgent, _load_env
from review_workflow import (
    find_latest_reviewable_run,
    load_story_for_workdir,
    run_config_path,
    save_review_state,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate one scene for the latest reviewable run.")
    parser.add_argument("scene_number", type=int, help="Scene number to regenerate")
    parser.add_argument("extra_prompt", nargs="*", help="Extra prompt guidance to append")
    parser.add_argument("--ip-scale", type=float, default=0.6, help="IP-Adapter influence scale (0.0=text only, 0.6=default)")
    parser.add_argument("--reference", type=str, default=None, help="Path to a custom reference image (overrides hook.png)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    _load_env()

    workdir = find_latest_reviewable_run({"images_ready"})
    config_path = run_config_path(workdir)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    extra_prompt = " ".join(args.extra_prompt).strip()

    scene_data = next((scene for scene in config.get("scenes", []) if int(scene.get("index", 0)) == args.scene_number), None)
    if not scene_data:
        raise RuntimeError(f"Scene {args.scene_number} not found in {config_path}")

    if extra_prompt:
        base_prompt = scene_data["image_prompt"]
        if extra_prompt not in base_prompt:
            scene_data["image_prompt"] = f"{base_prompt}, {extra_prompt}"
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    story = load_story_for_workdir(workdir)
    target_scene = next((scene for scene in story.scenes if scene.index == args.scene_number), None)
    if target_scene is None:
        raise RuntimeError(f"Scene {args.scene_number} not available for regeneration")

    ref_path = Path(args.reference) if args.reference else Path(workdir) / "images" / "hook.png"
    if not ref_path.exists():
        raise RuntimeError(f"Reference image not found: {ref_path}")
    image_agent = ImageAgent(Path(workdir) / "images", reference_image_path=str(ref_path))
    new_path = image_agent.regenerate_scene(target_scene, ref_path, extra_prompt=extra_prompt, ip_scale=args.ip_scale)

    save_review_state(
        workdir,
        "images_ready",
        title=config.get("title"),
        scene_count=len(config.get("scenes", [])),
        last_regenerated_scene=args.scene_number,
        last_extra_prompt=extra_prompt,
    )

    print(json.dumps({"workdir": str(workdir), "scene_number": args.scene_number, "image_path": new_path}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
