#!/usr/bin/env python3
"""
Automated story generator — picks a random theme from a pool and runs the
image-generation pipeline to images_ready state. Used by cron (2x daily).
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = "/home/dung/anaconda3/envs/demo/bin/python"
USED_FILE = BASE / "used_themes.json"

THEMES = [
    "sharing toys with friends",
    "being kind to animals",
    "telling the truth even when it's scary",
    "helping someone who is lost",
    "trying your best even when it's hard",
    "taking care of nature and plants",
    "saying sorry and making things right",
    "being patient while waiting for something",
    "making a new friend at school",
    "being brave when you are scared",
    "cleaning up and keeping things tidy",
    "listening carefully to your parents",
    "not giving up after you fail",
    "being grateful for what you have",
    "including everyone in your games",
    "being gentle with small animals",
    "asking for help when you need it",
    "learning something new from a mistake",
    "keeping your promises to friends",
    "taking turns and being fair",
    "being a good sport when you lose",
    "helping someone who feels left out",
    "being curious and exploring new things",
    "standing up for a friend who is upset",
    "taking care of your own health",
    "respecting that everyone is different",
    "saying thank you and please",
    "working together as a team",
    "being responsible with your belongings",
    "showing kindness to someone who is sad",
    "eating healthy food to grow strong",
    "being honest about a mistake you made",
    "caring for a sick friend or pet",
    "sharing a meal and being generous",
    "following the rules to keep everyone safe",
]


def _load_used() -> set:
    if USED_FILE.exists():
        return set(json.loads(USED_FILE.read_text()))
    return set()


def _save_used(used: set) -> None:
    USED_FILE.write_text(json.dumps(sorted(used), indent=2))


def pick_theme() -> str:
    used = _load_used()
    available = [t for t in THEMES if t not in used]
    if not available:
        used = set()
        available = list(THEMES)
    theme = random.choice(available)
    used.add(theme)
    _save_used(used)
    return theme


def main() -> int:
    theme = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else pick_theme()
    print(f"[auto_generate] Theme: {theme}", flush=True)

    env = os.environ.copy()
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    result = subprocess.run(
        [PYTHON, str(BASE / "generate_new.py"), "--theme", theme],
        env=env,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
