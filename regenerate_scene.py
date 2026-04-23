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
    parser.add_argument("scene", help="Scene to regenerate: 'hook', 'outro', or a scene number (1, 2, …)")
    parser.add_argument("extra_prompt", nargs="*", help="Extra prompt guidance to append")
    parser.add_argument("--ip-scale", type=float, default=0.6, help="IP-Adapter influence scale (0.0=text only, 0.6=default)")
    parser.add_argument("--reference", type=str, default=None, help="Path to a custom reference image (overrides hook.png)")
    parser.add_argument("--workdir", default="", help="Specific run workdir (default: latest images_ready)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    _load_env()

    if args.workdir:
        workdir = Path(args.workdir).resolve()
    else:
        workdir = find_latest_reviewable_run({"images_ready"})
    config_path = run_config_path(workdir)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    extra_prompt = " ".join(args.extra_prompt).strip()

    scene_key = args.scene.strip().lower()

    # ── Outro: text-only, no image — update config so continue_generate re-TTSs it
    if scene_key == "outro":
        if extra_prompt:
            config["outro"] = extra_prompt
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            print(f"  Updated outro text → '{extra_prompt}'")
        else:
            print("  No guidance provided — outro audio will be re-generated from existing text")
        save_review_state(workdir, "images_ready",
                          title=config.get("title"), scene_count=len(config.get("scenes", [])),
                          last_regenerated_scene="outro", last_extra_prompt=extra_prompt)
        print(json.dumps({"workdir": str(workdir), "scene": "outro", "image_path": None}, indent=2))
        return 0

    # ── Hook: regenerate hook.png using hook_image_prompt
    if scene_key == "hook":
        if extra_prompt:
            base = config.get("hook_image_prompt", "")
            if extra_prompt not in base:
                config["hook_image_prompt"] = f"{base}, {extra_prompt}" if base else extra_prompt
                config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        story = load_story_for_workdir(workdir)
        images_dir = Path(workdir) / "images"
        image_agent = ImageAgent(images_dir)
        char_refs = image_agent._load_char_refs_from_disk()
        hook_path = images_dir / "hook.png"
        prompt = story.hook_image_prompt
        if char_refs:
            hook_ref = image_agent._composite_refs(list(char_refs.values()))
            image_agent._render_image(prompt, hook_path, ref_image=hook_ref, ip_scale=args.ip_scale)
        else:
            image_agent._render_image(prompt, hook_path)
        print(f"  Saved: {hook_path}")
        save_review_state(workdir, "images_ready",
                          title=config.get("title"), scene_count=len(config.get("scenes", [])),
                          last_regenerated_scene="hook", last_extra_prompt=extra_prompt)
        print(json.dumps({"workdir": str(workdir), "scene": "hook", "image_path": str(hook_path)}, indent=2))
        return 0

    # ── Numbered scene
    if not scene_key.isdigit():
        raise RuntimeError(f"Invalid scene '{args.scene}' — use 'hook', 'outro', or a number")
    scene_number = int(scene_key)

    scene_data = next((s for s in config.get("scenes", []) if int(s.get("index", 0)) == scene_number), None)
    if not scene_data:
        raise RuntimeError(f"Scene {scene_number} not found in {config_path}")

    if extra_prompt:
        base_prompt = scene_data["image_prompt"]
        if extra_prompt not in base_prompt:
            scene_data["image_prompt"] = f"{base_prompt}, {extra_prompt}"
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    story = load_story_for_workdir(workdir)
    target_scene = next((s for s in story.scenes if s.index == scene_number), None)
    if target_scene is None:
        raise RuntimeError(f"Scene {scene_number} not available for regeneration")

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
        last_regenerated_scene=scene_number,
        last_extra_prompt=extra_prompt,
    )

    print(json.dumps({"workdir": str(workdir), "scene": scene_number, "image_path": new_path}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
