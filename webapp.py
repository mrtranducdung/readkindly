"""
Lumi Story Player — Flask backend

Storage backends (auto-detected):
  Supabase  — set SUPABASE_URL + SUPABASE_KEY  (production on Render free tier)
  Local     — default, uses story_storage/ + stories.db  (local dev)
"""
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, session

load_dotenv()

app = Flask(__name__)
app.secret_key   = os.environ.get("SECRET_KEY", "lumi-secret-key-2024")
ADMIN_PASSWORD   = os.environ.get("ADMIN_PASSWORD", "lumi2024")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

if USE_SUPABASE:
    from supabase import create_client
    _sb     = create_client(SUPABASE_URL, SUPABASE_KEY)
    _BUCKET = "stories"
    print("Storage: Supabase")
else:
    import sqlite3
    _data_dir = Path(os.environ.get("DATA_DIR", "."))
    STORAGE   = _data_dir / "story_storage"
    STORAGE.mkdir(parents=True, exist_ok=True)
    DB_PATH   = str(_data_dir / "stories.db")
    print(f"Storage: local")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _local_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    if USE_SUPABASE:
        return  # table is created once in the Supabase dashboard (see README)
    with _local_db() as conn:
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
                display_order INTEGER DEFAULT 0,
                config        TEXT
            )
        """)
        conn.commit()


def db_list():
    if USE_SUPABASE:
        res = _sb.table("stories").select("*").order("display_order").execute()
        return res.data or []
    with _local_db() as conn:
        rows = conn.execute(
            "SELECT * FROM stories ORDER BY display_order ASC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def db_get_config(story_id):
    if USE_SUPABASE:
        res = _sb.table("stories").select("config").eq("id", story_id).maybe_single().execute()
        if not res.data:
            return None
        cfg = res.data["config"]
        return cfg if isinstance(cfg, dict) else json.loads(cfg)
    with _local_db() as conn:
        row = conn.execute("SELECT config FROM stories WHERE id = ?", (story_id,)).fetchone()
        if not row or not row[0]:
            return None
        return json.loads(row[0])


def db_insert(story_id, config, created_at):
    row = {
        "id":            story_id,
        "title":         config.get("title", "Untitled"),
        "moral":         config.get("moral", ""),
        "hook":          config.get("hook", ""),
        "outro":         config.get("outro", ""),
        "hashtags":      json.dumps(config.get("hashtags", [])),
        "scene_count":   len(config.get("scenes", [])),
        "created_at":    created_at,
        "display_order": db_max_order() + 1,
        "config":        config if USE_SUPABASE else json.dumps(config),
    }
    if USE_SUPABASE:
        _sb.table("stories").insert(row).execute()
    else:
        with _local_db() as conn:
            conn.execute(
                "INSERT INTO stories "
                "(id,title,moral,hook,outro,hashtags,scene_count,created_at,display_order,config) "
                "VALUES (:id,:title,:moral,:hook,:outro,:hashtags,:scene_count,:created_at,:display_order,:config)",
                row,
            )
            conn.commit()


def db_max_order():
    if USE_SUPABASE:
        res = _sb.table("stories").select("display_order").order("display_order", desc=True).limit(1).execute()
        return res.data[0]["display_order"] if res.data else -1
    with _local_db() as conn:
        return conn.execute("SELECT COALESCE(MAX(display_order),-1) FROM stories").fetchone()[0]


def db_delete(story_id):
    if USE_SUPABASE:
        _sb.table("stories").delete().eq("id", story_id).execute()
    else:
        with _local_db() as conn:
            conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
            conn.commit()


def db_reorder(order):
    if USE_SUPABASE:
        for i, sid in enumerate(order):
            _sb.table("stories").update({"display_order": i}).eq("id", sid).execute()
    else:
        with _local_db() as conn:
            for i, sid in enumerate(order):
                conn.execute("UPDATE stories SET display_order = ? WHERE id = ?", (i, sid))
            conn.commit()


init_db()


# ── Storage helpers ───────────────────────────────────────────────────────────

def store_file(story_id, folder, filename, data: bytes, content_type: str):
    if USE_SUPABASE:
        path = f"{story_id}/{folder}/{filename}"
        _sb.storage.from_(_BUCKET).upload(
            path, data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    else:
        dest = STORAGE / story_id / folder
        dest.mkdir(parents=True, exist_ok=True)
        (dest / filename).write_bytes(data)


def file_url(story_id, folder, filename):
    """Return public Supabase URL, or None if using local storage."""
    if USE_SUPABASE:
        return _sb.storage.from_(_BUCKET).get_public_url(f"{story_id}/{folder}/{filename}")
    return None


def delete_story_files(story_id):
    if USE_SUPABASE:
        for folder in ("images", "audio"):
            items = _sb.storage.from_(_BUCKET).list(f"{story_id}/{folder}") or []
            paths = [f"{story_id}/{folder}/{f['name']}" for f in items]
            if paths:
                _sb.storage.from_(_BUCKET).remove(paths)
    else:
        d = STORAGE / story_id
        if d.exists():
            shutil.rmtree(d)


def serve_asset(story_id, folder, candidates, mimetype):
    """Redirect to Supabase URL, or send local file, for the first matching candidate."""
    if USE_SUPABASE:
        for name in candidates:
            url = file_url(story_id, folder, name)
            if url:
                return redirect(url)
        return jsonify({"error": "Not found"}), 404
    for name in candidates:
        p = STORAGE / story_id / folder / name
        if p.exists():
            return send_file(p, mimetype=mimetype, conditional=(mimetype == "audio/mpeg"))
    return jsonify({"error": "Not found"}), 404


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

@app.route("/api/stories/<story_id>/asset-urls")
def story_asset_urls(story_id):
    """Return direct CDN URLs for all assets so the frontend skips redirect hops."""
    config = db_get_config(story_id)
    if not config:
        return jsonify({"error": "Not found"}), 404
    n = len(config.get("scenes", []))

    def img_url(name):
        if USE_SUPABASE:
            return file_url(story_id, "images", name)
        return f"/api/stories/{story_id}/image/{name.split('.')[0]}"

    def aud_url(name):
        if USE_SUPABASE:
            return file_url(story_id, "audio", name)
        key = name.replace(".mp3", "").replace("scene_", "")
        return f"/api/stories/{story_id}/audio/{key}"

    return jsonify({
        "hook_image": img_url("hook.png"),
        "hook_audio": aud_url("hook.mp3"),
        "outro_audio": aud_url("outro.mp3"),
        "images": {str(i): img_url(f"{i}.png") for i in range(1, n + 1)},
        "audio":  {str(i): aud_url(f"scene_{i:02d}.mp3") for i in range(1, n + 1)},
    })


@app.route("/api/stories")
def list_stories():
    return jsonify(db_list())


@app.route("/api/stories/<story_id>")
def get_story(story_id):
    config = db_get_config(story_id)
    if not config:
        return jsonify({"error": "Not found"}), 404
    return jsonify(config)


@app.route("/api/stories/<story_id>/image/<int:n>")
def story_image(story_id, n):
    return serve_asset(story_id, "images",
                       [f"{n}.png", f"{n}.jpg", f"{n}.jpeg"], "image/png")


@app.route("/api/stories/<story_id>/image/hook")
def story_hook_image(story_id):
    return serve_asset(story_id, "images",
                       ["hook.png", "hook.jpg", "1.png", "1.jpg"], "image/png")


@app.route("/api/stories/<story_id>/audio/<int:n>")
def scene_audio(story_id, n):
    return serve_asset(story_id, "audio", [f"scene_{n:02d}.mp3"], "audio/mpeg")


@app.route("/api/stories/<story_id>/audio/hook")
def story_hook_audio(story_id):
    return serve_asset(story_id, "audio", ["hook.mp3"], "audio/mpeg")


@app.route("/api/stories/<story_id>/audio/outro")
def story_outro_audio(story_id):
    return serve_asset(story_id, "audio", ["outro.mp3"], "audio/mpeg")


# ── Admin story management ────────────────────────────────────────────────────

@app.route("/api/admin/stories", methods=["POST"])
@admin_required
def upload_story():
    config_file = request.files.get("config")
    image_files = request.files.getlist("images")
    audio_files = request.files.getlist("audio")

    if not config_file or not audio_files or not image_files:
        return jsonify({"error": "config, images and audio files are required"}), 400

    try:
        config = json.loads(config_file.read().decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"Invalid config JSON: {e}"}), 400

    story_id   = str(uuid.uuid4())[:8]
    created_at = datetime.now().isoformat()

    # Save images
    for img in image_files:
        fname = img.filename.lower()
        data  = img.read()
        ext   = fname.rsplit(".", 1)[-1]
        if fname.startswith("hook."):
            store_file(story_id, "images", f"hook.{ext}", data, f"image/{ext}")
        else:
            m = re.search(r"scene_(\d+)", fname)
            if m:
                store_file(story_id, "images", f"{int(m.group(1))}.{ext}", data, f"image/{ext}")

    # Save audio
    saved_audio = 0
    for af in audio_files:
        fname = af.filename.lower()
        data  = af.read()
        if fname == "hook.mp3":
            store_file(story_id, "audio", "hook.mp3", data, "audio/mpeg")
        elif fname == "outro.mp3":
            store_file(story_id, "audio", "outro.mp3", data, "audio/mpeg")
        else:
            m = re.search(r"scene_(\d+)", fname)
            if m:
                store_file(story_id, "audio", f"scene_{int(m.group(1)):02d}.mp3", data, "audio/mpeg")
                saved_audio += 1

    if saved_audio == 0:
        delete_story_files(story_id)
        return jsonify({"error": "No audio files matched scene_NN.mp3 naming"}), 400

    meta = {**config, "id": story_id, "created_at": created_at}
    db_insert(story_id, meta, created_at)

    return jsonify({"id": story_id, "title": config.get("title"), "audio_scenes": saved_audio})


@app.route("/api/admin/stories/<story_id>", methods=["DELETE"])
@admin_required
def delete_story(story_id):
    delete_story_files(story_id)
    db_delete(story_id)
    return jsonify({"ok": True})


@app.route("/api/admin/stories/reorder", methods=["PATCH"])
@admin_required
def reorder_stories():
    db_reorder(request.get_json().get("order", []))
    return jsonify({"ok": True})


# ── Serve SPA ─────────────────────────────────────────────────────────────────

@app.route("/tos")
def tos():
    return """<!DOCTYPE html><html><head><title>Terms of Service</title>
<meta name="tiktok-developers-site-verification" content="WmoaEztuqNLmKpOmR8NyCvvPlsBdwA5d" />
</head><body>
<h1>Terms of Service</h1>
<p>This app generates and publishes kids moral stories. By using this service you agree to use it responsibly and in compliance with applicable laws.</p>
<p>We reserve the right to update these terms at any time. Last updated: 2026-04-07.</p>
</body></html>"""

@app.route("/privacy")
def privacy():
    return """<!DOCTYPE html><html><head><title>Privacy Policy</title></head><body>
<h1>Privacy Policy</h1>
<p>This app does not collect personal data from users. Story content is generated automatically and stored on our servers.</p>
<p>We do not share any data with third parties except as required to operate the service.</p>
<p>Last updated: 2026-04-07.</p>
</body></html>"""

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path=""):
    return render_template("index.html")


if __name__ == "__main__":
    print(f"Lumi Story Player — http://localhost:5000  (Supabase: {USE_SUPABASE})")
    print(f"Admin password: {ADMIN_PASSWORD}")
    app.run(debug=True, port=5000, host="0.0.0.0")
