from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json

def make_run_dir(base: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def save_json(path: Path, data) -> None:
    if hasattr(data, "model_dump"):
        payload = data.model_dump()
    else:
        payload = data
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
