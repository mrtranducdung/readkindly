#!/usr/bin/env python3
"""
Local watcher — polls Render for scene regeneration requests and handles them.

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

RENDER_URL = os.getenv("RENDER_URL", "").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
POLL_INTERVAL = 60  # seconds
PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON = str(PROJECT_ROOT / ".." / ".." / "anaconda3" / "envs" / "demo" / "bin" / "python")
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def _run(cmd: list[str]) -> bool:
    env = os.environ.copy()
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return result.returncode == 0


def handle_regen_requests(session) -> None:
    import upload_to_render

    r = session.get(f"{RENDER_URL}/api/admin/review/regen-requests", timeout=15)
    if not r.ok:
        print(f"  ✗ HTTP {r.status_code} from regen-requests endpoint")
        if r.status_code in (401, 403):
            print("     Session expired — will re-login next poll")
        return
    ct = r.headers.get("Content-Type", "")
    if "json" not in ct:
        print(f"  ✗ Unexpected response (Content-Type: {ct}) — is the new code deployed on Render?")
        print(f"     First 200 chars: {r.text[:200]}")
        return
    requests_list = r.json()

    if not requests_list:
        return

    for req in requests_list:
        run_id = req["run_id"]
        scene = req["scene"]
        guidance = req.get("guidance", "")
        title = req.get("title", run_id)

        workdir = PROJECT_ROOT / "out" / run_id
        if not workdir.exists():
            print(f"  ✗ Local workdir not found for {run_id} — skipping")
            continue

        print(f"\n🔄 Regenerating scene {scene} of '{title}' ({run_id})")
        print(f"   Guidance: {guidance or '(none)'}")

        # Step 1: regenerate the scene image
        regen_cmd = [PYTHON, str(PROJECT_ROOT / "regenerate_scene.py"),
                     "--workdir", str(workdir), str(scene)]
        if guidance:
            regen_cmd.extend(guidance.split())

        if not _run(regen_cmd):
            print(f"  ✗ regenerate_scene.py failed for scene {scene}")
            continue

        # Step 2: re-generate audio + video
        if not _run([PYTHON, str(PROJECT_ROOT / "continue_generate.py"), "--workdir", str(workdir)]):
            print(f"  ✗ continue_generate.py failed")
            continue

        # Step 3: re-upload to Render (overwrites existing pending run)
        try:
            result = upload_to_render.upload_pending_review(session, workdir, RENDER_URL)
            print(f"  ✅ Re-uploaded to review queue: {result.get('title')}")
        except Exception as e:
            print(f"  ✗ Re-upload failed: {e}")
            continue

        # Step 4: clear the regen request on Render
        try:
            session.delete(f"{RENDER_URL}/api/admin/review/{run_id}/regen-request", timeout=15)
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    args = parser.parse_args()

    if not RENDER_URL:
        print("✗ RENDER_URL not set in .env")
        sys.exit(1)

    import upload_to_render
    session = upload_to_render.login(RENDER_URL, ADMIN_PASSWORD)
    print(f"✓ Watching {RENDER_URL} for regen requests…")

    if args.once:
        handle_regen_requests(session)
        return

    while True:
        try:
            handle_regen_requests(session)
        except Exception as e:
            print(f"Poll error: {e}")
            # Re-login on auth errors
            try:
                session = upload_to_render.login(RENDER_URL, ADMIN_PASSWORD)
            except Exception:
                pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
