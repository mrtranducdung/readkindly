from __future__ import annotations
from pathlib import Path
import asyncio
import edge_tts
from .config import VOICE

def build_narration_text(story_pack) -> str:
    parts = [story_pack.hook.strip()]
    parts.extend(scene.narration.strip() for scene in story_pack.scenes)
    parts.append(f"The lesson is: {story_pack.moral.strip()}")
    return " ".join(parts)

async def _save_tts(text: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=VOICE)
    await communicate.save(str(out_path))

def generate_tts(text: str, out_path: Path) -> None:
    asyncio.run(_save_tts(text, out_path))
