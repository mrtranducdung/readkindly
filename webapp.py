"""
Lumi Story Player — Flask backend
Run:  /home/dung/anaconda3/envs/demo/bin/python webapp.py
Admin password: set ADMIN_PASSWORD env var (default: lumi2024)
"""
import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "lumi-secret-key-2024")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "lumi2024")

# DATA_DIR lets Render (or any host) point storage at a persistent disk.
# Locally defaults to the project root so nothing changes.
_data_dir = Path(os.environ.get("DATA_DIR", "."))
STORAGE = _data_dir / "story_storage"
STORAGE.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_data_dir / "stories.db")


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id            TEXT PRIMARY KEY,
                title         TEXT NOT NULL,
                moral         TEXT,
                hook          TEXT,
                outro         TEXT,
                hashtags      TEXT,
                scene_count   INTEGER DEFAULT 10,
                created_at    TEXT,
                display_order INTEGER DEFAULT 0
            )
        """)
        conn.commit()


init_db()


# ── Auth ──────────────────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Wrong password"}), 403


@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})


@app.route("/api/admin/check")
def admin_check():
    return jsonify({"is_admin": bool(session.get("is_admin"))})


# ── Public story API ──────────────────────────────────────────────────────────

@app.route("/api/stories")
def list_stories():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM stories ORDER BY display_order ASC, created_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/stories/<story_id>")
def get_story(story_id):
    meta_path = STORAGE / story_id / "meta.json"
    if not meta_path.exists():
        return jsonify({"error": "Not found"}), 404
    return jsonify(json.loads(meta_path.read_text()))


@app.route("/api/stories/<story_id>/image/<int:n>")
def story_image(story_id, n):
    img_dir = STORAGE / story_id / "images"
    for ext in ("png", "jpg", "jpeg"):
        p = img_dir / f"{n}.{ext}"
        if p.exists():
            return send_file(p, mimetype=f"image/{'jpeg' if ext == 'jpeg' else ext}")
    return jsonify({"error": "Not found"}), 404


@app.route("/api/stories/<story_id>/image/hook")
def story_hook_image(story_id):
    img_dir = STORAGE / story_id / "images"
    for ext in ("png", "jpg", "jpeg"):
        p = img_dir / f"hook.{ext}"
        if p.exists():
            return send_file(p, mimetype=f"image/{'jpeg' if ext == 'jpeg' else ext}")
    for ext in ("png", "jpg", "jpeg"):
        p = img_dir / f"1.{ext}"
        if p.exists():
            return send_file(p, mimetype=f"image/{'jpeg' if ext == 'jpeg' else ext}")
    return jsonify({"error": "Not found"}), 404


@app.route("/api/stories/<story_id>/audio/<int:n>")
def scene_audio(story_id, n):
    """Per-scene narration audio — scene_01.mp3 through scene_10.mp3."""
    audio_dir = STORAGE / story_id / "audio"
    p = audio_dir / f"scene_{n:02d}.mp3"
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return send_file(p, mimetype="audio/mpeg", conditional=True)


@app.route("/api/stories/<story_id>/audio/hook")
def story_hook_audio(story_id):
    """Intro slide audio."""
    p = STORAGE / story_id / "audio" / "hook.mp3"
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return send_file(p, mimetype="audio/mpeg", conditional=True)


@app.route("/api/stories/<story_id>/audio/outro")
def story_outro_audio(story_id):
    """Outro slide audio."""
    p = STORAGE / story_id / "audio" / "outro.mp3"
    if not p.exists():
        return jsonify({"error": "Not found"}), 404
    return send_file(p, mimetype="audio/mpeg", conditional=True)


# ── Admin story management ────────────────────────────────────────────────────

@app.route("/api/admin/stories", methods=["POST"])
@admin_required
def upload_story():
    config_file = request.files.get("config")
    image_files = request.files.getlist("images")
    audio_files = request.files.getlist("audio")   # scene_01.mp3 … scene_10.mp3

    if not config_file or not audio_files or not image_files:
        return jsonify({"error": "config, images and per-scene audio files are required"}), 400

    try:
        config = json.loads(config_file.read().decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"Invalid config JSON: {e}"}), 400

    story_id  = str(uuid.uuid4())[:8]
    story_dir = STORAGE / story_id
    img_dir   = story_dir / "images"
    aud_dir   = story_dir / "audio"
    img_dir.mkdir(parents=True)
    aud_dir.mkdir(parents=True)

    # Save images — detect index from filename scene_NN.*
    for img in image_files:
        fname = img.filename.lower()
        if fname.startswith("hook."):
            ext = fname.rsplit(".", 1)[-1]
            img.save(img_dir / f"hook.{ext}")
        else:
            m = re.search(r"scene_(\d+)", fname)
            if not m:
                continue
            idx = int(m.group(1))
            ext = fname.rsplit(".", 1)[-1]
            img.save(img_dir / f"{idx}.{ext}")

    # Save audio — hook.mp3, outro.mp3, and scene_NN.mp3
    saved_audio = 0
    for af in audio_files:
        fname = af.filename.lower()
        if fname == "hook.mp3":
            af.save(aud_dir / "hook.mp3")
        elif fname == "outro.mp3":
            af.save(aud_dir / "outro.mp3")
        else:
            m = re.search(r"scene_(\d+)", fname)
            if m:
                idx = int(m.group(1))
                af.save(aud_dir / f"scene_{idx:02d}.mp3")
                saved_audio += 1

    if saved_audio == 0:
        shutil.rmtree(story_dir)
        return jsonify({"error": "No audio files matched scene_NN.mp3 naming"}), 400

    # Save metadata
    meta = {
        **config,
        "id": story_id,
        "created_at": datetime.now().isoformat(),
    }
    (story_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Insert into DB
    with get_db() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(display_order), -1) FROM stories"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO stories "
            "(id, title, moral, hook, outro, hashtags, scene_count, created_at, display_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                story_id,
                config.get("title", "Untitled"),
                config.get("moral", ""),
                config.get("hook", ""),
                config.get("outro", ""),
                json.dumps(config.get("hashtags", [])),
                len(config.get("scenes", [])),
                meta["created_at"],
                max_order + 1,
            ),
        )
        conn.commit()

    return jsonify({"id": story_id, "title": config.get("title"), "audio_scenes": saved_audio})


@app.route("/api/admin/stories/<story_id>", methods=["DELETE"])
@admin_required
def delete_story(story_id):
    story_dir = STORAGE / story_id
    if story_dir.exists():
        shutil.rmtree(story_dir)
    with get_db() as conn:
        conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/stories/reorder", methods=["PATCH"])
@admin_required
def reorder_stories():
    order = request.get_json().get("order", [])
    with get_db() as conn:
        for i, sid in enumerate(order):
            conn.execute("UPDATE stories SET display_order = ? WHERE id = ?", (i, sid))
        conn.commit()
    return jsonify({"ok": True})


# ── Serve SPA ─────────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path=""):
    return render_template("index.html")


if __name__ == "__main__":
    print("Lumi Story Player starting on http://localhost:5000")
    print(f"Admin password: {ADMIN_PASSWORD}")
    app.run(debug=True, port=5000, host="0.0.0.0")
