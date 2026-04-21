#!/usr/bin/env python3
"""
Upload stories to the deployed Render webapp.

Usage:
    python upload_to_render.py                          # upload latest out/ run
    python upload_to_render.py --all                    # upload all from story_storage/
    python upload_to_render.py out/2026-04-03_07-14-01  # upload specific run
    python upload_to_render.py story_storage/277c6631   # upload from story_storage

RENDER_URL and ADMIN_PASSWORD are read from .env if present.
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()


def find_latest_out() -> Path:
    runs = sorted(Path("out").glob("????-??-??_??-??-??"), reverse=True)
    if not runs:
        raise FileNotFoundError("No runs found in out/")
    return runs[0]


def collect_files_from_out(workdir: Path):
    """Collect files from an out/<timestamp>/ run directory."""
    config_path = workdir / "story_config.json"
    images_dir  = workdir / "images"
    audio_dir   = workdir / "audio" / "scenes"

    if not config_path.exists():
        raise FileNotFoundError(f"story_config.json not found in {workdir}")
    if not images_dir.exists():
        raise FileNotFoundError(f"images/ not found in {workdir}")
    if not audio_dir.exists():
        raise FileNotFoundError(f"audio/scenes/ not found in {workdir}")

    images = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
    audios = sorted(audio_dir.glob("*.mp3"))
    return config_path, images, audios


def collect_files_from_storage(story_dir: Path):
    """Collect files from a story_storage/<id>/ directory.
    Images are named 1.png…10.png — rename to scene_01.png… for the upload endpoint.
    """
    meta_path  = story_dir / "meta.json"
    images_dir = story_dir / "images"
    audio_dir  = story_dir / "audio"

    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json not found in {story_dir}")

    # Rename numeric images to scene_NN.png so the upload endpoint recognises them
    images = []
    for p in sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg")):
        stem = p.stem
        if stem == "hook":
            images.append((f"hook{p.suffix}", p))
        elif stem.isdigit():
            images.append((f"scene_{int(stem):02d}{p.suffix}", p))

    audios = [(p.name, p) for p in sorted(audio_dir.glob("*.mp3"))]
    return meta_path, images, audios


def login(base_url: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{base_url}/api/admin/login", json={"password": password}, timeout=15)
    if r.status_code == 403:
        print("✗ Wrong admin password.")
        sys.exit(1)
    r.raise_for_status()
    return s


def upload_out(session, workdir: Path, base_url: str):
    config_path, images, audios = collect_files_from_out(workdir)
    print(f"  Config : {config_path.name}")
    print(f"  Images : {len(images)}  Audio: {len(audios)}")

    files = [("config", ("story_config.json", config_path.open("rb"), "application/json"))]
    for img in images:
        files.append(("images", (img.name, img.open("rb"), "image/png")))
    for audio in audios:
        files.append(("audio", (audio.name, audio.open("rb"), "audio/mpeg")))

    r = session.post(f"{base_url}/api/admin/stories", files=files, timeout=120)
    r.raise_for_status()
    return r.json()


def upload_storage(session, story_dir: Path, base_url: str):
    meta_path, images, audios = collect_files_from_storage(story_dir)
    print(f"  Config : {meta_path.name}")
    print(f"  Images : {len(images)}  Audio: {len(audios)}")

    files = [("config", ("story_config.json", meta_path.open("rb"), "application/json"))]
    for upload_name, path in images:
        files.append(("images", (upload_name, path.open("rb"), "image/png")))
    for upload_name, path in audios:
        files.append(("audio", (upload_name, path.open("rb"), "audio/mpeg")))

    r = session.post(f"{base_url}/api/admin/stories", files=files, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload stories to the Render webapp")
    parser.add_argument("workdir", nargs="?",
                        help="Path to a run dir or story_storage/<id>. Defaults to latest out/ run.")
    parser.add_argument("--all", action="store_true",
                        help="Upload all stories from story_storage/")
    parser.add_argument("--url", "-u", default=os.environ.get("RENDER_URL", ""),
                        help="Render webapp URL (or set RENDER_URL in .env)")
    parser.add_argument("--password", "-p", default=os.environ.get("ADMIN_PASSWORD", "lumi2024"),
                        help="Admin password (or set ADMIN_PASSWORD in .env)")
    args = parser.parse_args()

    if not args.url:
        print("✗ --url is required (or set RENDER_URL in .env)")
        sys.exit(1)

    base_url = args.url.rstrip("/")
    s = login(base_url, args.password)
    print(f"✓ Logged in to {base_url}\n")

    if args.all:
        stories = sorted(Path("story_storage").iterdir())
        if not stories:
            print("✗ No stories found in story_storage/")
            sys.exit(1)
        for story_dir in stories:
            if not story_dir.is_dir():
                continue
            print(f"Uploading {story_dir.name}...")
            try:
                result = upload_storage(s, story_dir, base_url)
                print(f"  ✅ \"{result['title']}\" → ID: {result['id']}\n")
            except Exception as e:
                print(f"  ✗ Failed: {e}\n")
        return

    if args.workdir:
        workdir = Path(args.workdir)
        if not workdir.exists():
            print(f"✗ Not found: {workdir}")
            sys.exit(1)
        print(f"Uploading {workdir}...")
        # Detect format by presence of meta.json
        if (workdir / "meta.json").exists():
            result = upload_storage(s, workdir, base_url)
        else:
            result = upload_out(s, workdir, base_url)
    else:
        workdir = find_latest_out()
        print(f"Uploading latest: {workdir}...")
        result = upload_out(s, workdir, base_url)

    print(f"\n✅ Published: \"{result['title']}\"")
    print(f"   Story ID : {result['id']}")
    print(f"   Live at  : {base_url}")


if __name__ == "__main__":
    main()
