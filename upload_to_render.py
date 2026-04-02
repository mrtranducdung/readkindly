#!/usr/bin/env python3
"""
Upload a locally generated story to the deployed Render webapp.

Usage:
    python upload_to_render.py out/2026-04-03_07-14-01
    python upload_to_render.py out/2026-04-03_07-14-01 --url https://your-app.onrender.com
    python upload_to_render.py out/2026-04-03_07-14-01 --url https://your-app.onrender.com --password secret

The RENDER_URL and ADMIN_PASSWORD env vars are read from .env if present.
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()


def find_latest_workdir() -> Path:
    out = Path("out")
    runs = sorted(out.glob("????-??-??_??-??-??"), reverse=True)
    if not runs:
        raise FileNotFoundError("No runs found in out/")
    return runs[0]


def upload(workdir: Path, base_url: str, password: str) -> None:
    base_url = base_url.rstrip("/")

    # ── Login ────────────────────────────────────────────────────────────────
    s = requests.Session()
    r = s.post(f"{base_url}/api/admin/login", json={"password": password}, timeout=15)
    if r.status_code == 403:
        print("✗ Wrong admin password.")
        sys.exit(1)
    r.raise_for_status()
    print(f"✓ Logged in to {base_url}")

    # ── Collect files ────────────────────────────────────────────────────────
    config_path = workdir / "story_config.json"
    images_dir  = workdir / "images"
    audio_dir   = workdir / "audio" / "scenes"

    if not config_path.exists():
        print(f"✗ story_config.json not found in {workdir}")
        sys.exit(1)
    if not images_dir.exists():
        print(f"✗ images/ not found in {workdir}")
        sys.exit(1)
    if not audio_dir.exists():
        print(f"✗ audio/scenes/ not found in {workdir}")
        sys.exit(1)

    images = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
    audios = sorted(audio_dir.glob("*.mp3"))

    print(f"  Config : {config_path.name}")
    print(f"  Images : {len(images)} files")
    print(f"  Audio  : {len(audios)} files")

    # ── Upload ───────────────────────────────────────────────────────────────
    print("Uploading...")
    files = []
    files.append(("config", ("story_config.json", config_path.open("rb"), "application/json")))
    for img in images:
        files.append(("images", (img.name, img.open("rb"), "image/png")))
    for audio in audios:
        files.append(("audio", (audio.name, audio.open("rb"), "audio/mpeg")))

    r = s.post(f"{base_url}/api/admin/stories", files=files, timeout=120)
    r.raise_for_status()
    result = r.json()

    print(f"\n✅ Published: \"{result['title']}\"")
    print(f"   Story ID : {result['id']}")
    print(f"   Live at  : {base_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a story to the deployed Render webapp")
    parser.add_argument(
        "workdir", nargs="?",
        help="Path to the story run dir (e.g. out/2026-04-03_07-14-01). Defaults to latest.",
    )
    parser.add_argument(
        "--url", "-u",
        default=os.environ.get("RENDER_URL", ""),
        help="Render webapp URL (or set RENDER_URL in .env)",
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("ADMIN_PASSWORD", "lumi2024"),
        help="Admin password (or set ADMIN_PASSWORD in .env)",
    )
    args = parser.parse_args()

    if not args.url:
        print("✗ --url is required (or set RENDER_URL in .env)")
        sys.exit(1)

    workdir = Path(args.workdir) if args.workdir else find_latest_workdir()
    if not workdir.exists():
        print(f"✗ Workdir not found: {workdir}")
        sys.exit(1)

    print(f"Workdir: {workdir}")
    upload(workdir, args.url, args.password)


if __name__ == "__main__":
    main()
