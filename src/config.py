from __future__ import annotations
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "mistral-large-latest")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Tiny Good Habits")
VOICE = os.getenv("VOICE", "en-US-AnaNeural")
THEME = os.getenv("THEME", "kindness")
AGE_RANGE = os.getenv("AGE_RANGE", "4-8")
VIDEO_SECONDS = int(os.getenv("VIDEO_SECONDS", "35"))
