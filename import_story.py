"""
Import an existing genstory.py output directory into the webapp.
Usage: python import_story.py out/2026-04-01_07-40-23
       python import_story.py   (imports the most recent out/ directory)

New audio layout (12-slide model):
  story_storage/<id>/audio/hook.mp3     ← intro slide
  story_storage/<id>/audio/outro.mp3    ← outro slide
  story_storage/<id>/audio/scene_01.mp3 … scene_10.mp3  ← scene narrations

Audio is sourced from (in priority order):
  1. out/.../scenes/  (new format: hook.mp3 + outro.mp3 + scene_NN.mp3)
  2. out/.../audio/clips/  (raw TTS clips: hook.mp3 + outro.mp3 + scene_NN.mp3)
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

STORAGE  = Path("story_storage")
STORAGE.mkdir(exist_ok=True)
DB_PATH  = "stories.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, moral TEXT,
            hook TEXT, outro TEXT, hashtags TEXT, scene_count INTEGER DEFAULT 10,
            created_at TEXT, display_order INTEGER DEFAULT 0
        )
    """)
    conn.commit(); conn.close()


def import_story(out_dir: Path):
    out_dir     = Path(out_dir)
    config_path = out_dir / "story_config.json"
    if not config_path.exists():
        config_path = Path("story_config.json")
    img_dir     = out_dir / "images"
    scenes_dir  = out_dir / "scenes"          # new format: hook.mp3 + outro.mp3 + scene_NN.mp3
    clips_dir   = out_dir / "audio" / "clips" # raw TTS clips (fallback)

    if not config_path.exists():
        print(f"✗ story_config.json not found in {Path('.').resolve()}")
        return None
    if not img_dir.exists():
        print(f"✗ images/ not found at {img_dir}")
        return None

    config   = json.loads(config_path.read_text())
    n_scenes = len(config.get("scenes", []))

    # ── Find audio source ──────────────────────────────────────────────────────
    # Prefer scenes/ if it has hook.mp3 (new format)
    if scenes_dir.exists() and (scenes_dir / "hook.mp3").exists():
        audio_source = scenes_dir
        print(f"✓ New-format scenes/ found (hook + outro + narrations)")
    elif clips_dir.exists() and (clips_dir / "hook.mp3").exists():
        audio_source = clips_dir
        print(f"✓ Using clips/ as audio source")
    else:
        print("✗ No audio source found. Run genstory.py to regenerate.")
        return None

    # ── Create story directory ─────────────────────────────────────────────────
    story_id  = str(uuid.uuid4())[:8]
    story_dir = STORAGE / story_id
    s_img_dir = story_dir / "images"
    s_aud_dir = story_dir / "audio"
    s_img_dir.mkdir(parents=True)
    s_aud_dir.mkdir(parents=True)

    # Copy images
    img_count = 0
    for ext in ("png", "jpg", "jpeg"):
        hook_img = img_dir / f"hook.{ext}"
        if hook_img.exists():
            shutil.copy(hook_img, s_img_dir / f"hook.{ext}")
            img_count += 1
            break
    for ext in ("png", "jpg", "jpeg"):
        for img in sorted(img_dir.glob(f"scene_*.{ext}")):
            m = re.search(r"scene_(\d+)", img.name)
            if m:
                shutil.copy(img, s_img_dir / f"{int(m.group(1))}.{ext}")
                img_count += 1
    print(f"✓ {img_count} images copied")

    # Copy hook and outro audio
    for fname in ("hook.mp3", "outro.mp3"):
        src = audio_source / fname
        if src.exists():
            shutil.copy(src, s_aud_dir / fname)
        else:
            print(f"  ✗ {fname} not found in {audio_source}")

    # Copy scene narration clips
    aud_count = 0
    for af in sorted(audio_source.glob("scene_*.mp3")):
        m = re.search(r"scene_(\d+)", af.name)
        if m:
            shutil.copy(af, s_aud_dir / f"scene_{int(m.group(1)):02d}.mp3")
            aud_count += 1
    print(f"✓ hook.mp3 + outro.mp3 + {aud_count} scene clips copied")

    # ── Metadata ───────────────────────────────────────────────────────────────
    meta = {**config, "id": story_id, "created_at": datetime.now().isoformat()}
    (story_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # ── Database ───────────────────────────────────────────────────────────────
    init_db()
    conn = sqlite3.connect(DB_PATH)
    max_order = conn.execute("SELECT COALESCE(MAX(display_order),-1) FROM stories").fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO stories "
        "(id,title,moral,hook,outro,hashtags,scene_count,created_at,display_order) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (story_id, config.get("title","Untitled"), config.get("moral",""),
         config.get("hook",""), config.get("outro",""),
         json.dumps(config.get("hashtags",[])), n_scenes,
         meta["created_at"], max_order + 1)
    )
    conn.commit(); conn.close()

    print(f'\n✅ Imported: "{config["title"]}" → ID: {story_id}')
    print("   Open http://localhost:5000 to view it.")
    return {
        "id": story_id,
        "title": config.get("title", "Untitled"),
        "out_dir": str(out_dir),
        "story_dir": str(story_dir),
        "scene_count": n_scenes,
    }


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)   # run from project root
    if len(sys.argv) > 1:
        import_story(Path(sys.argv[1]))
    else:
        out_root = Path("out")
        dirs = sorted([d for d in out_root.iterdir() if d.is_dir()], reverse=True) if out_root.exists() else []
        if not dirs:
            print("✗ No out/ directory found. Pass a path: python import_story.py out/YYYY-MM-DD_HH-MM-SS")
            sys.exit(1)
        # Skip 'video' or other non-dated dirs
        dated = [d for d in dirs if re.match(r"\d{4}-\d{2}-\d{2}", d.name)]
        if not dated:
            print("✗ No dated output directories found in out/")
            sys.exit(1)
        print(f"→ Importing most recent: {dated[0]}")
        import_story(dated[0])
