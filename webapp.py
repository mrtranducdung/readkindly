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
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import stripe
from werkzeug.security import check_password_hash, generate_password_hash

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, redirect, render_template, request, send_file, session

load_dotenv()

app = Flask(__name__)
app.secret_key   = os.environ.get("SECRET_KEY", "lumi-secret-key-2024")
app.permanent_session_lifetime = timedelta(days=30)
ADMIN_PASSWORD   = os.environ.get("ADMIN_PASSWORD", "lumi2024")

stripe.api_key          = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET   = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID         = os.environ.get("STRIPE_PRICE_ID", "")

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

_stories_cache: dict = {"data": None, "at": 0.0}

def _invalidate_stories_cache():
    _stories_cache["at"] = 0.0


# ── Review-queue helpers ──────────────────────────────────────────────────────

_PENDING_DIR = Path(__file__).parent.resolve() / "pending_review"
_PENDING_DIR.mkdir(exist_ok=True)
_SOCIAL_QUEUE_DIR = Path(__file__).parent.resolve() / "social_queue"
_SOCIAL_QUEUE_DIR.mkdir(exist_ok=True)
_RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")


def _scan_pending_runs() -> list:
    runs = []
    for d in sorted(_PENDING_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not _RUN_ID_RE.match(d.name):
            continue
        sf = d / "review_state.json"
        if not sf.exists():
            continue
        try:
            state = json.loads(sf.read_text())
            if state.get("status") != "pending_review":
                continue
            cfg_file = d / "story_config.json"
            cfg = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
            scenes_info = [
                {"index": s["index"], "title": s.get("title", ""), "on_screen_text": s.get("on_screen_text", "")}
                for s in cfg.get("scenes", [])
            ]
            regen_queue = []
            rq_path = d / "regen_queue.json"
            if rq_path.exists():
                try:
                    regen_queue = json.loads(rq_path.read_text())
                except Exception:
                    pass
            runs.append({
                "run_id": d.name,
                "title": state.get("title") or cfg.get("title", "Untitled"),
                "moral": cfg.get("moral", ""),
                "created_at": state.get("created_at", ""),
                "scene_count": state.get("scene_count", 10),
                "has_video": state.get("has_video", False),
                "scenes_info": scenes_info,
                "regen_queue": regen_queue,
            })
        except Exception:
            continue
    return runs


# ── Storage helpers ───────────────────────────────────────────────────────────

def store_file(story_id, folder, filename, data: bytes, content_type: str):
    if USE_SUPABASE:
        path = f"{story_id}/{folder}/{filename}"
        _sb.storage.from_(_BUCKET).upload(
            path, data,
            file_options={"content-type": content_type, "upsert": "true", "cache-control": "public, max-age=31536000"},
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
                resp = make_response(redirect(url))
                resp.headers["Cache-Control"] = "public, max-age=3600"
                return resp
        return jsonify({"error": "Not found"}), 404
    for name in candidates:
        p = STORAGE / story_id / folder / name
        if p.exists():
            resp = make_response(send_file(p, mimetype=mimetype, conditional=True))
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
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
    now = time.time()
    if now - _stories_cache["at"] > 10:
        _stories_cache["data"] = db_list()
        _stories_cache["at"] = now
    return jsonify(_stories_cache["data"])


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
    _invalidate_stories_cache()

    return jsonify({"id": story_id, "title": config.get("title"), "audio_scenes": saved_audio})


@app.route("/api/admin/stories/<story_id>", methods=["DELETE"])
@admin_required
def delete_story(story_id):
    delete_story_files(story_id)
    db_delete(story_id)
    _invalidate_stories_cache()
    return jsonify({"ok": True})


@app.route("/api/admin/stories/reorder", methods=["PATCH"])
@admin_required
def reorder_stories():
    db_reorder(request.get_json().get("order", []))
    _invalidate_stories_cache()
    return jsonify({"ok": True})


# ── Admin review queue ────────────────────────────────────────────────────────

@app.route("/api/admin/review/runs")
@admin_required
def list_review_runs():
    return jsonify(_scan_pending_runs())


@app.route("/api/admin/pending", methods=["POST"])
@admin_required
def submit_for_review():
    run_id = request.form.get("run_id", "").strip()
    if not run_id or not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid or missing run_id"}), 400
    config_file = request.files.get("config")
    if not config_file:
        return jsonify({"error": "config required"}), 400

    pending_dir = _PENDING_DIR / run_id
    images_dir = pending_dir / "images"
    audio_dir = pending_dir / "audio"
    video_dir = pending_dir / "video"
    for d in (images_dir, audio_dir, video_dir):
        d.mkdir(parents=True, exist_ok=True)

    try:
        config = json.loads(config_file.read().decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"Invalid config JSON: {e}"}), 400
    (pending_dir / "story_config.json").write_text(json.dumps(config, indent=2))

    for img in request.files.getlist("images"):
        fname = img.filename
        if re.match(r"^(hook|scene_\d{2})\.(png|jpg|jpeg)$", fname):
            (images_dir / fname).write_bytes(img.read())

    for af in request.files.getlist("audio"):
        fname = af.filename
        if re.match(r"^(hook|outro|scene_\d{2})\.mp3$", fname):
            (audio_dir / fname).write_bytes(af.read())

    video_file = request.files.get("video")
    has_video = False
    if video_file:
        (video_dir / "story_video.mp4").write_bytes(video_file.read())
        has_video = True

    state = {
        "status": "pending_review",
        "run_id": run_id,
        "title": config.get("title", "Untitled"),
        "scene_count": len(config.get("scenes", [])),
        "has_video": has_video,
        "created_at": datetime.now().isoformat(),
    }
    (pending_dir / "review_state.json").write_text(json.dumps(state, indent=2))
    return jsonify({"ok": True, "run_id": run_id, "title": state["title"]})


@app.route("/api/admin/review/<run_id>/image/<filename>")
@admin_required
def serve_review_image(run_id, filename):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    if not re.match(r"^(hook|scene_\d{2})\.(png|jpg|jpeg)$", filename):
        return jsonify({"error": "Invalid filename"}), 400
    img_path = _PENDING_DIR / run_id / "images" / filename
    if not img_path.exists():
        return jsonify({"error": "Not found"}), 404
    ext = filename.rsplit(".", 1)[-1]
    return send_file(img_path, mimetype=f"image/{ext}")


@app.route("/api/admin/review/<run_id>/video")
@admin_required
def serve_review_video(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    video_path = _PENDING_DIR / run_id / "video" / "story_video.mp4"
    if not video_path.exists():
        return jsonify({"error": "Not found"}), 404
    return send_file(video_path, mimetype="video/mp4", conditional=True)


@app.route("/api/admin/review/<run_id>/approve", methods=["POST"])
@admin_required
def approve_run(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    pending_dir = _PENDING_DIR / run_id
    if not (pending_dir / "review_state.json").exists():
        return jsonify({"error": "Run not found"}), 404

    config = json.loads((pending_dir / "story_config.json").read_text())
    story_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().isoformat()

    images_dir = pending_dir / "images"
    for img in sorted(images_dir.glob("*")):
        ext = img.suffix.lstrip(".")
        data = img.read_bytes()
        if img.stem == "hook":
            store_file(story_id, "images", f"hook.{ext}", data, f"image/{ext}")
        else:
            m = re.search(r"scene_(\d+)", img.name)
            if m:
                store_file(story_id, "images", f"{int(m.group(1))}.{ext}", data, f"image/{ext}")

    audio_dir = pending_dir / "audio"
    saved_audio = 0
    for af in sorted(audio_dir.glob("*.mp3")):
        data = af.read_bytes()
        if af.name in ("hook.mp3", "outro.mp3"):
            store_file(story_id, "audio", af.name, data, "audio/mpeg")
        else:
            m = re.search(r"scene_(\d+)", af.name)
            if m:
                store_file(story_id, "audio", f"scene_{int(m.group(1)):02d}.mp3", data, "audio/mpeg")
                saved_audio += 1

    if saved_audio == 0:
        shutil.rmtree(pending_dir, ignore_errors=True)
        return jsonify({"error": "No audio scene files found in pending run"}), 400

    meta = {**config, "id": story_id, "created_at": created_at}
    db_insert(story_id, meta, created_at)
    _invalidate_stories_cache()

    # Queue social media upload for the local watcher to handle
    social = {
        "run_id": run_id,
        "story_id": story_id,
        "title": config.get("title", ""),
        "hashtags": config.get("hashtags", []),
        "approved_at": created_at,
    }
    (_SOCIAL_QUEUE_DIR / f"{run_id}.json").write_text(json.dumps(social, indent=2))

    shutil.rmtree(pending_dir, ignore_errors=True)
    return jsonify({"ok": True, "story_id": story_id, "title": config.get("title")})


@app.route("/api/admin/social-queue")
@admin_required
def list_social_queue():
    results = []
    for f in sorted(_SOCIAL_QUEUE_DIR.glob("*.json"), reverse=True):
        try:
            results.append(json.loads(f.read_text()))
        except Exception:
            continue
    return jsonify(results)


@app.route("/api/admin/social-queue/<run_id>", methods=["DELETE"])
@admin_required
def clear_social_queue(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    path = _SOCIAL_QUEUE_DIR / f"{run_id}.json"
    if path.exists():
        path.unlink()
    return jsonify({"ok": True})


@app.route("/api/admin/review/<run_id>", methods=["DELETE"])
@admin_required
def reject_run(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    pending_dir = _PENDING_DIR / run_id
    if not pending_dir.exists():
        return jsonify({"error": "Run not found"}), 404
    shutil.rmtree(pending_dir, ignore_errors=True)
    return jsonify({"ok": True})


@app.route("/api/admin/review/<run_id>/regen-request", methods=["POST"])
@admin_required
def create_regen_request(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    pending_dir = _PENDING_DIR / run_id
    if not (pending_dir / "review_state.json").exists():
        return jsonify({"error": "Run not found"}), 404
    data = request.get_json() or {}
    scene = str(data.get("scene", "")).strip().lower()
    if not scene or (scene not in ("hook", "outro") and not scene.isdigit()):
        return jsonify({"error": "scene required: 'hook', 'outro', or a scene number"}), 400
    rq_path = pending_dir / "regen_queue.json"
    queue = []
    if rq_path.exists():
        try:
            queue = json.loads(rq_path.read_text())
        except Exception:
            pass
    regen = {
        "scene": scene,
        "guidance": str(data.get("guidance", "")).strip(),
        "created_at": datetime.now().isoformat(),
    }
    queue.append(regen)
    rq_path.write_text(json.dumps(queue, indent=2))
    return jsonify({"ok": True, "run_id": run_id, "scene": regen["scene"], "queue_length": len(queue)})


@app.route("/api/admin/review/<run_id>/regen-request", methods=["DELETE"])
@admin_required
def clear_regen_request(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    rq_path = _PENDING_DIR / run_id / "regen_queue.json"
    if rq_path.exists():
        try:
            queue = json.loads(rq_path.read_text())
            if queue:
                queue.pop(0)
            if queue:
                rq_path.write_text(json.dumps(queue, indent=2))
            else:
                rq_path.unlink()
        except Exception:
            rq_path.unlink(missing_ok=True)
    return jsonify({"ok": True})


@app.route("/api/admin/review/regen-requests")
@admin_required
def list_regen_requests():
    results = []
    for d in sorted(_PENDING_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not _RUN_ID_RE.match(d.name):
            continue
        rq_path = d / "regen_queue.json"
        if not rq_path.exists():
            continue
        try:
            queue = json.loads(rq_path.read_text())
            if not queue:
                continue
            req = queue[0]  # watcher always processes the head of the queue
            state = json.loads((d / "review_state.json").read_text())
            results.append({
                "run_id": d.name,
                "title": state.get("title", "Untitled"),
                "scene": req["scene"],
                "guidance": req.get("guidance", ""),
                "created_at": req["created_at"],
            })
        except Exception:
            continue
    return jsonify(results)


# ── Users DB ──────────────────────────────────────────────────────────────────

def _init_users_db():
    if USE_SUPABASE:
        return  # create table once in Supabase dashboard
    with _local_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                   TEXT PRIMARY KEY,
                email                TEXT UNIQUE NOT NULL,
                password_hash        TEXT NOT NULL,
                created_at           TEXT,
                stripe_customer_id   TEXT,
                stripe_subscription_id TEXT,
                is_premium           INTEGER DEFAULT 0
            )
        """)
        conn.commit()

_init_users_db()


def _user_by_email(email):
    if USE_SUPABASE:
        r = _sb.table("users").select("*").eq("email", email).maybe_single().execute()
        return r.data
    with _local_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None


def _user_by_id(uid):
    if USE_SUPABASE:
        r = _sb.table("users").select("*").eq("id", uid).maybe_single().execute()
        return r.data
    with _local_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None


def _user_by_customer(customer_id):
    if USE_SUPABASE:
        r = _sb.table("users").select("*").eq("stripe_customer_id", customer_id).maybe_single().execute()
        return r.data
    with _local_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE stripe_customer_id=?", (customer_id,)).fetchone()
        return dict(row) if row else None


def _user_create(email, password):
    uid = str(uuid.uuid4())[:12]
    row = {"id": uid, "email": email,
           "password_hash": generate_password_hash(password),
           "created_at": datetime.now().isoformat(),
           "stripe_customer_id": None, "stripe_subscription_id": None, "is_premium": 0}
    if USE_SUPABASE:
        _sb.table("users").insert(row).execute()
    else:
        with _local_db() as conn:
            conn.execute(
                "INSERT INTO users (id,email,password_hash,created_at,stripe_customer_id,stripe_subscription_id,is_premium) "
                "VALUES (:id,:email,:password_hash,:created_at,:stripe_customer_id,:stripe_subscription_id,:is_premium)", row)
            conn.commit()
    return row


def _user_patch(uid, **fields):
    if USE_SUPABASE:
        _sb.table("users").update(fields).eq("id", uid).execute()
    else:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        with _local_db() as conn:
            conn.execute(f"UPDATE users SET {set_clause} WHERE id=?", [*fields.values(), uid])
            conn.commit()


def _user_patch_by_customer(customer_id, **fields):
    if USE_SUPABASE:
        _sb.table("users").update(fields).eq("stripe_customer_id", customer_id).execute()
    else:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        with _local_db() as conn:
            conn.execute(f"UPDATE users SET {set_clause} WHERE stripe_customer_id=?", [*fields.values(), customer_id])
            conn.commit()


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    data     = request.get_json() or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if _user_by_email(email):
        return jsonify({"error": "Email already registered — please sign in"}), 409
    user = _user_create(email, password)
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "email": email, "is_premium": False})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data     = request.get_json() or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    user     = _user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Wrong email or password"}), 401
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "email": email, "is_premium": bool(user.get("is_premium"))})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def auth_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"logged_in": False})
    user = _user_by_id(uid)
    if not user:
        session.pop("user_id", None)
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "email": user["email"], "is_premium": bool(user.get("is_premium"))})


# ── Stripe routes ─────────────────────────────────────────────────────────────

@app.route("/api/stripe/create-checkout", methods=["POST"])
def stripe_create_checkout():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401
    user = _user_by_id(uid)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if not stripe.api_key:
        return jsonify({"error": "Payments not configured yet"}), 503
    try:
        customer_id = user.get("stripe_customer_id")
        if not customer_id:
            customer    = stripe.Customer.create(email=user["email"])
            customer_id = customer.id
            _user_patch(uid, stripe_customer_id=customer_id)
        base = request.host_url.rstrip("/")
        session_obj = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            mode="subscription",
            success_url=base + "/?premium=success",
            cancel_url=base + "/",
        )
        return jsonify({"url": session_obj.url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return jsonify({"error": "Invalid signature"}), 400

    etype = event["type"]
    obj   = event["data"]["object"]

    if etype == "checkout.session.completed":
        customer_id = obj.get("customer")
        sub_id      = obj.get("subscription")
        if customer_id:
            _user_patch_by_customer(customer_id, is_premium=1, stripe_subscription_id=sub_id)

    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        _user_patch_by_customer(obj.get("customer", ""), is_premium=0)

    elif etype == "invoice.payment_failed":
        _user_patch_by_customer(obj.get("customer", ""), is_premium=0)

    elif etype == "customer.subscription.updated":
        status = obj.get("status")
        _user_patch_by_customer(obj.get("customer", ""), is_premium=1 if status == "active" else 0)

    return jsonify({"ok": True})


@app.route("/api/premium/check")
def check_premium():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"logged_in": False, "is_premium": False})
    user = _user_by_id(uid)
    if not user:
        return jsonify({"logged_in": False, "is_premium": False})
    return jsonify({"logged_in": True, "is_premium": bool(user.get("is_premium")), "email": user["email"]})


# ── Serve SPA ─────────────────────────────────────────────────────────────────

_LEGAL_STYLE = """
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="tiktok-developers-site-verification" content="WmoaEztuqNLmKpOmR8NyCvvPlsBdwA5d" />
<style>
  body{font-family:sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#222;line-height:1.7}
  h1{color:#333}h2{color:#444;margin-top:2em}
  a{color:#555}footer{margin-top:3em;font-size:.85em;color:#888;border-top:1px solid #ddd;padding-top:1em}
</style>
"""

@app.route("/tos")
def tos():
    return f"""<!DOCTYPE html><html><head><title>Terms of Service – ReadKindly</title>{_LEGAL_STYLE}</head><body>
<h1>ReadKindly – Terms of Service</h1>
<p><strong>App name:</strong> ReadKindly (readkindlyapp) &nbsp;|&nbsp; <strong>Last updated:</strong> April 24, 2026</p>

<h2>1. Acceptance of Terms</h2>
<p>By accessing or using ReadKindly, also known as <strong>readkindlyapp</strong> ("the App", "we", "our"), you agree to be bound by these Terms of Service. If you do not agree, please do not use the App.</p>

<h2>2. Description of Service</h2>
<p>ReadKindly (readkindlyapp) is a children's story platform that generates and publishes short animated moral stories for kids. Content is created automatically and made available for viewing through our website and partner platforms.</p>

<h2>3. Permitted Use</h2>
<p>You may use ReadKindly for personal, non-commercial viewing of story content. You agree not to:</p>
<ul>
  <li>Reproduce or redistribute content without permission</li>
  <li>Attempt to reverse-engineer or interfere with the App</li>
  <li>Use the App for any unlawful purpose</li>
</ul>

<h2>4. Content</h2>
<p>All stories on ReadKindly are AI-generated and intended for children aged 3–10. We strive to ensure content is safe and appropriate. We reserve the right to remove or modify any content at any time.</p>

<h2>5. Intellectual Property</h2>
<p>All content, including story text, images, and audio, is owned by ReadKindly or its licensors. You may not copy or distribute it without written permission.</p>

<h2>6. Disclaimer of Warranties</h2>
<p>ReadKindly is provided "as is" without warranties of any kind. We do not guarantee uninterrupted or error-free access to the App.</p>

<h2>7. Limitation of Liability</h2>
<p>To the fullest extent permitted by law, ReadKindly shall not be liable for any indirect, incidental, or consequential damages arising from your use of the App.</p>

<h2>8. Changes to Terms</h2>
<p>We may update these Terms at any time. Continued use of ReadKindly after changes constitutes acceptance of the revised Terms.</p>

<h2>9. Contact</h2>
<p>For questions about these Terms, contact us at: <a href="mailto:support@readkindly.com">support@readkindly.com</a></p>

<footer><a href="/">← Back to ReadKindly</a> &nbsp;|&nbsp; <a href="/privacy">Privacy Policy</a></footer>
</body></html>"""


@app.route("/privacy")
def privacy():
    return f"""<!DOCTYPE html><html><head><title>Privacy Policy – ReadKindly</title>{_LEGAL_STYLE}</head><body>
<h1>ReadKindly – Privacy Policy</h1>
<p><strong>App name:</strong> ReadKindly (readkindlyapp) &nbsp;|&nbsp; <strong>Last updated:</strong> April 24, 2026</p>

<h2>1. Introduction</h2>
<p>ReadKindly, also known as <strong>readkindlyapp</strong> ("the App", "we", "us", "our") is committed to protecting your privacy. This Privacy Policy explains how we handle information when you use the ReadKindly website and services.</p>

<h2>2. Information We Collect</h2>
<p>ReadKindly does <strong>not</strong> require users to create an account or provide personal information to view stories. We do not collect names, email addresses, or any personally identifiable information from general visitors.</p>
<p>We may collect non-personal technical data such as:</p>
<ul>
  <li>Browser type and version</li>
  <li>Device type and operating system</li>
  <li>Pages viewed and time spent on the App (via anonymous analytics)</li>
</ul>

<h2>3. How We Use Information</h2>
<p>Any technical data collected is used solely to:</p>
<ul>
  <li>Improve App performance and user experience</li>
  <li>Diagnose technical issues</li>
</ul>
<p>We do not sell, rent, or share personal data with third parties for marketing purposes.</p>

<h2>4. Children's Privacy</h2>
<p>ReadKindly is designed for children and family audiences. We do not knowingly collect personal information from children under 13. If you believe a child has provided us personal information, please contact us and we will promptly delete it.</p>

<h2>5. Cookies</h2>
<p>ReadKindly uses only essential session cookies required for admin functionality. No tracking or advertising cookies are used.</p>

<h2>6. Third-Party Services</h2>
<p>ReadKindly may use the following third-party services to operate:</p>
<ul>
  <li><strong>Supabase</strong> – for data storage (subject to Supabase's privacy policy)</li>
  <li><strong>Render</strong> – for web hosting (subject to Render's privacy policy)</li>
</ul>
<p>We do not control and are not responsible for the privacy practices of these third parties.</p>

<h2>7. Data Retention</h2>
<p>Story content is retained on our servers indefinitely unless removed by an administrator. No personal user data is retained.</p>

<h2>8. Your Rights</h2>
<p>Since we do not collect personal data from general users, there is no personal information to access, correct, or delete. If you have an admin account and wish to have it removed, contact us.</p>

<h2>9. Changes to This Policy</h2>
<p>We may update this Privacy Policy from time to time. We will post the updated policy on this page with a revised date.</p>

<h2>10. Contact</h2>
<p>If you have questions about this Privacy Policy, contact us at: <a href="mailto:support@readkindly.com">support@readkindly.com</a></p>

<footer><a href="/">← Back to ReadKindly</a> &nbsp;|&nbsp; <a href="/tos">Terms of Service</a></footer>
</body></html>"""

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path=""):
    return render_template("index.html")


if __name__ == "__main__":
    print(f"Lumi Story Player — http://localhost:5000  (Supabase: {USE_SUPABASE})")
    print(f"Admin password: {ADMIN_PASSWORD}")
    app.run(debug=True, port=5000, host="0.0.0.0")
