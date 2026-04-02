from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import argparse

from genstory import MoralStoryPipeline, StoryIdea, _load_env
from review_workflow import save_review_state, write_run_config
from src.llm_agents import generate_story_pack


def _normalize_hashtags(values: list[str]) -> list[str]:
    hashtags: list[str] = []
    for value in values:
        tag = value.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        hashtags.append(tag)
    return hashtags


def _build_outro(title: str, moral: str) -> str:
    return f"{title} shows that {moral[0].lower() + moral[1:]}" if moral else f"Remember what {title} teaches us."


def _build_character_consistency_prompt(characters: list[Any]) -> str:
    names = []
    for character in characters:
        name = character.name.strip()
        if name:
            names.append(name)
    if not names:
        return ""
    return "Same recurring characters as the hook image: " + ", ".join(names)


def _compact_prompt(text: str, limit_words: int = 55) -> str:
    cleaned = re.sub(r"\s+", " ", text.replace("\n", " ")).strip(" ,.")
    if not cleaned:
        return cleaned

    parts = [part.strip(" ,.") for part in cleaned.split(",") if part.strip(" ,.")]
    compact_parts: list[str] = []
    total_words = 0
    for part in parts:
        words = part.split()
        if compact_parts and total_words + len(words) > limit_words:
            break
        if not compact_parts and len(words) > limit_words:
            compact_parts.append(" ".join(words[:limit_words]))
            total_words = limit_words
            break
        compact_parts.append(part)
        total_words += len(words)

    compact = ", ".join(compact_parts) if compact_parts else " ".join(cleaned.split()[:limit_words])
    return compact.strip(" ,.")


def build_story_config(theme: str = "") -> dict[str, Any]:
    story_pack = generate_story_pack(theme=theme)
    if len(story_pack.scenes) != 10:
        raise RuntimeError(f"Expected exactly 10 scenes, got {len(story_pack.scenes)}")

    scenes = []
    for scene in story_pack.scenes:
        scenes.append(
            {
                "index": scene.scene_number,
                "title": scene.title,
                "narration": scene.narration,
                "on_screen_text": scene.onscreen_text,
                "image_prompt": _compact_prompt(scene.visual_description),
                "duration_seconds": float(scene.duration_seconds),
            }
        )

    return {
        "title": story_pack.title,
        "hook": story_pack.hook,
        "moral": story_pack.moral,
        "outro": _build_outro(story_pack.title, story_pack.moral),
        "hashtags": _normalize_hashtags(story_pack.hashtags),
        "hook_image_prompt": _compact_prompt(story_pack.hook_visual_description, limit_words=60),
        "characters": [
            {"name": character.name, "description": character.description}
            for character in story_pack.characters
        ],
        "character_consistency_prompt": _build_character_consistency_prompt(story_pack.characters),
        "scenes": scenes,
    }


def write_story_config(project_root: Path, theme: str = "") -> dict[str, Any]:
    config = build_story_config(theme=theme)
    config_path = project_root / "story_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Generated new story config: {config['title']}")
    print(f"Wrote: {config_path}")
    return config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="", help="Optional story theme (used with Mistral LLM)")
    parser.add_argument("--from-config", action="store_true",
                        help="Skip LLM — use existing story_config.json written by Claude")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    workdir = project_root / "out" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    workdir.mkdir(parents=True, exist_ok=True)

    _load_env()
    if args.from_config:
        config_path = project_root / "story_config.json"
        if not config_path.exists():
            print("✗ story_config.json not found. Write it first before using --from-config.")
            return 1
        config = json.loads(config_path.read_text(encoding="utf-8"))
        write_run_config(workdir, config)
        print(f"Using existing story config: {config.get('title', '?')}")
    else:
        if args.theme:
            print(f"Theme: {args.theme}")
        config = write_story_config(project_root, theme=args.theme)
    write_run_config(workdir, config)

    pipeline = MoralStoryPipeline(
        workdir=str(workdir),
        tiktok_access_token="",
        reference_image_path="",
    )
    story = pipeline.story_agent.run(
        StoryIdea(
            topic=config["title"],
            moral=config["moral"],
            scene_count=len(config["scenes"]),
        )
    )
    story = pipeline.prompt_agent.run(story)
    story = pipeline.image_agent.run(story)

    save_review_state(
        workdir,
        "images_ready",
        title=config["title"],
        scene_count=len(config["scenes"]),
    )

    print("\nImages ready for review:")
    print(
        json.dumps(
            {
                "workdir": str(workdir),
                "title": config["title"],
                "scene_count": len(config["scenes"]),
                "hook_image_path": story.hook_image_path,
                "first_scene_image_path": story.scenes[0].image_path if story.scenes else None,
            },
            indent=2,
        )
    )
    print("Review the images, then say 'go ahead' to continue or 'regenerate scene N ...' to redo one scene.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
