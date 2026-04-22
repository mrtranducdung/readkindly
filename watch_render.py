#!/usr/bin/env python3
"""
Local watcher — polls Render for two types of requests:
  1. Scene regen requests  → regenerate image + audio/video + re-upload
  2. Social upload queue   → upload approved stories to TikTok + YouTube

Usage:
    python watch_render.py          # polls every 60s
    python watch_render.py --once   # check once and exit

RENDER_URL and ADMIN_PASSWORD are read from .env.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RENDER_URL     = os.getenv("RENDER_URL", "").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
POLL_INTERVAL  = 60  # seconds
PROJECT_ROOT   = Path(__file__).resolve().parent
PYTHON         = "/home/dung/anaconda3/envs/demo/bin/python"
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def _run(cmd: list[str]) -> bool:
    env = os.environ.copy()
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return result.returncode == 0


def _get_json(session, url: str) -> list | None:
    """GET url, return parsed JSON list or None on error."""
    try:
        r = session.get(url, timeout=15)
        if not r.ok:
            print(f"  ✗ HTTP {r.status_code} from {url}")
            return None
        if "json" not in r.headers.get("Content-Type", ""):
            print(f"  ✗ Non-JSON response from {url} — code not deployed yet?")
            return None
        return r.json()
    except Exception as e:
        print(f"  ✗ Request error: {e}")
        return None


# ── Scene regeneration ────────────────────────────────────────────────────────

def handle_regen_requests(session) -> None:
    import upload_to_render

    items = _get_json(session, f"{RENDER_URL}/api/admin/review/regen-requests")
    if not items:
        return

    for req in items:
        run_id   = req["run_id"]
        scene    = req["scene"]
        guidance = req.get("guidance", "")
        title    = req.get("title", run_id)
        workdir  = PROJECT_ROOT / "out" / run_id

        if not workdir.exists():
            print(f"  ✗ Local workdir not found for {run_id} — skipping regen")
            continue

        print(f"\n🔄 Regenerating scene {scene} of '{title}'")
        if guidance:
            print(f"   Guidance: {guidance}")

        regen_cmd = [PYTHON, str(PROJECT_ROOT / "regenerate_scene.py"),
                     "--workdir", str(workdir), str(scene)]
        if guidance:
            regen_cmd.extend(guidance.split())

        if not _run(regen_cmd):
            print(f"  ✗ regenerate_scene.py failed"); continue

        if not _run([PYTHON, str(PROJECT_ROOT / "continue_generate.py"), "--workdir", str(workdir)]):
            print(f"  ✗ continue_generate.py failed"); continue

        try:
            result = upload_to_render.upload_pending_review(session, workdir, RENDER_URL)
            print(f"  ✅ Re-uploaded to review queue: {result.get('title')}")
        except Exception as e:
            print(f"  ✗ Re-upload failed: {e}"); continue

        session.delete(f"{RENDER_URL}/api/admin/review/{run_id}/regen-request", timeout=15)


# ── Social media upload ───────────────────────────────────────────────────────

def handle_social_queue(session) -> None:
    items = _get_json(session, f"{RENDER_URL}/api/admin/social-queue")
    if not items:
        return

    for item in items:
        run_id  = item["run_id"]
        title   = item.get("title", "")
        hashtags = item.get("hashtags", [])
        workdir = PROJECT_ROOT / "out" / run_id

        print(f"\n📤 Social upload for '{title}' ({run_id})")

        if not workdir.exists():
            print(f"  ✗ Local workdir not found — skipping social upload")
            session.delete(f"{RENDER_URL}/api/admin/social-queue/{run_id}", timeout=15)
            continue

        video_path = workdir / "video" / "story_video.mp4"
        if not video_path.exists():
            print(f"  ✗ Video not found at {video_path}")
            session.delete(f"{RENDER_URL}/api/admin/social-queue/{run_id}", timeout=15)
            continue

        caption = f"{title} {' '.join(hashtags)}"

        # TikTok
        tiktok_token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        if tiktok_token:
            try:
                from genstory import TikTokAgent
                tiktok = TikTokAgent(tiktok_token)
                init = tiktok.init_direct_post(caption[:2200], str(video_path))
                upload_url = init.get("data", {}).get("upload_url")
                if upload_url:
                    tiktok.upload_binary(upload_url, str(video_path))
                    print(f"  ✅ TikTok uploaded")
                else:
                    print(f"  ✗ TikTok: no upload_url in response")
            except Exception as e:
                print(f"  ✗ TikTok failed: {e}")
        else:
            print(f"  — TikTok skipped (TIKTOK_ACCESS_TOKEN not set)")

        # YouTube
        youtube_token = Path("youtube_token.json")
        if youtube_token.exists():
            try:
                from upload_to_youtube import upload_video
                result = upload_video(workdir)
                print(f"  ✅ YouTube: {result['url']}")
            except Exception as e:
                print(f"  ✗ YouTube failed: {e}")
        else:
            print(f"  — YouTube skipped (run python youtube_auth.py first)")

        # Clear from queue
        try:
            session.delete(f"{RENDER_URL}/api/admin/social-queue/{run_id}", timeout=15)
        except Exception:
            pass


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    args = parser.parse_args()

    if not RENDER_URL:
        print("✗ RENDER_URL not set in .env"); sys.exit(1)

    import upload_to_render
    session = upload_to_render.login(RENDER_URL, ADMIN_PASSWORD)
    print(f"✓ Watching {RENDER_URL} (regen + social upload)…")

    if args.once:
        handle_regen_requests(session)
        handle_social_queue(session)
        return

    while True:
        try:
            handle_regen_requests(session)
            handle_social_queue(session)
        except Exception as e:
            print(f"Poll error: {e}")
            try:
                session = upload_to_render.login(RENDER_URL, ADMIN_PASSWORD)
            except Exception:
                pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
