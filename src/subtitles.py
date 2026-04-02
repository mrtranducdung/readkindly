from __future__ import annotations
from pathlib import Path

def _format_timestamp(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    total = int(seconds)
    s = total % 60
    m = (total // 60) % 60
    h = total // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(story_pack, out_path: Path) -> None:
    current = 0.0
    chunks = [story_pack.hook] + [scene.narration for scene in story_pack.scenes] + [f"The lesson is: {story_pack.moral}"]
    durations = [3] + [scene.duration_seconds for scene in story_pack.scenes] + [4]
    lines = []
    for idx, (text, dur) in enumerate(zip(chunks, durations), start=1):
        start = _format_timestamp(current)
        end = _format_timestamp(current + dur)
        lines.extend([str(idx), f"{start} --> {end}", text.strip(), ""])
        current += dur
    out_path.write_text("\n".join(lines), encoding="utf-8")
