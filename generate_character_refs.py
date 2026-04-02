"""Generate individual character reference images from story_config.json.

Produces one image per character in out/<workdir>/images/ref_<name>.png
using text-only prompts (no IP-Adapter), so each image cleanly shows
only that one character.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from genstory import ImageAgent, _load_env
from review_workflow import find_latest_reviewable_run, run_config_path


def main() -> int:
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    _load_env()

    workdir = find_latest_reviewable_run({"images_ready"})
    config = json.loads(run_config_path(workdir).read_text(encoding="utf-8"))
    characters = config.get("characters", [])
    if not characters:
        print("No characters found in story config.")
        return 1

    image_agent = ImageAgent(Path(workdir) / "images")

    for char in characters:
        name = char["name"].strip()
        description = char["description"].strip()
        prompt = (
            f"{name} the character, {description}, "
            "solo portrait, full body, bright cheerful picture-book illustration style, "
            "white background, child-friendly, soft pastel colors"
        )
        safe_name = name.lower().replace(" ", "_")
        out_path = Path(workdir) / "images" / f"ref_{safe_name}.png"
        print(f"Generating reference for {name}...")
        image_agent._load_pipeline(use_ip_adapter=False)
        image_agent._render_image(prompt, out_path)
        image_agent._clear_pipeline()
        print(f"  Saved: {out_path}")

    print("\nCharacter references ready:")
    for char in characters:
        safe_name = char["name"].strip().lower().replace(" ", "_")
        print(f"  {char['name']}: {workdir}/images/ref_{safe_name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
