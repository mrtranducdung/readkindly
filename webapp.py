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
import subprocess
import threading
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


# ── Review-queue helpers ──────────────────────────────────────────────────────

_OUT_DIR = Path(__file__).parent.resolve() / "out"
_PYTHON_BIN = "/home/dung/anaconda3/envs/demo/bin/python"
_BASE_DIR = Path(__file__).parent.resolve()
_RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")
_jobs: dict = {}
_jobs_lock = threading.Lock()


def _scan_pending_runs() -> list:
    runs = []
    if not _OUT_DIR.exists():
        return runs
    for d in sorted(_OUT_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not _RUN_ID_RE.match(d.name):
            continue
        sf = d / "review_state.json"
        if not sf.exists():
            continue
        try:
            state = json.loads(sf.read_text())
            if state.get("status") != "images_ready":
                continue
            cfg_file = d / "story_config.json"
            cfg = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
            scenes_info = [
                {"index": s["index"], "title": s.get("title", ""), "on_screen_text": s.get("on_screen_text", "")}
                for s in cfg.get("scenes", [])
            ]
            runs.append({
                "run_id": d.name,
                "title": state.get("title") or cfg.get("title", "Untitled"),
                "moral": cfg.get("moral", ""),
                "created_at": state.get("updated_at", ""),
                "scene_count": state.get("scene_count", 10),
                "scenes_info": scenes_info,
            })
        except Exception:
            continue
    return runs


def _run_job(job_id: str, cmd: list) -> None:
    env = os.environ.copy()
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "output": "", "error": ""}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done" if proc.returncode == 0 else "error",
                "output": (proc.stdout or "")[-4000:],
                "error": (proc.stderr or "")[-2000:],
            }
    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "output": "", "error": str(exc)}


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


# ── Admin review queue ────────────────────────────────────────────────────────

@app.route("/api/admin/review/runs")
@admin_required
def list_review_runs():
    return jsonify(_scan_pending_runs())


@app.route("/api/admin/review/<run_id>/image/<filename>")
@admin_required
def serve_review_image(run_id, filename):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    if not re.match(r"^(hook|scene_\d{2})\.png$", filename):
        return jsonify({"error": "Invalid filename"}), 400
    img_path = _OUT_DIR / run_id / "images" / filename
    if not img_path.exists():
        return jsonify({"error": "Not found"}), 404
    return send_file(img_path, mimetype="image/png")


@app.route("/api/admin/review/<run_id>/approve", methods=["POST"])
@admin_required
def approve_run(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    workdir = _OUT_DIR / run_id
    if not (workdir / "review_state.json").exists():
        return jsonify({"error": "Run not found"}), 404
    job_id = str(uuid.uuid4())[:8]
    cmd = [_PYTHON_BIN, str(_BASE_DIR / "continue_generate.py"), "--workdir", str(workdir)]
    threading.Thread(target=_run_job, args=(job_id, cmd), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/admin/review/<run_id>/regenerate", methods=["POST"])
@admin_required
def regenerate_scene_route(run_id):
    if not _RUN_ID_RE.match(run_id):
        return jsonify({"error": "Invalid run_id"}), 400
    workdir = _OUT_DIR / run_id
    if not (workdir / "review_state.json").exists():
        return jsonify({"error": "Run not found"}), 404
    data = request.get_json() or {}
    scene_n = str(data.get("scene", "")).strip()
    if not scene_n.isdigit():
        return jsonify({"error": "scene number required"}), 400
    guidance = str(data.get("guidance", "")).strip()
    job_id = str(uuid.uuid4())[:8]
    cmd = [_PYTHON_BIN, str(_BASE_DIR / "regenerate_scene.py"),
           "--workdir", str(workdir), scene_n]
    if guidance:
        cmd.extend(guidance.split())
    threading.Thread(target=_run_job, args=(job_id, cmd), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/admin/review/jobs/<job_id>")
@admin_required
def get_job_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


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
<h1>Terms of Service</h1>
<p><strong>App name:</strong> ReadKindly &nbsp;|&nbsp; <strong>Last updated:</strong> April 7, 2026</p>

<h2>1. Acceptance of Terms</h2>
<p>By accessing or using ReadKindly ("the App", "we", "our"), you agree to be bound by these Terms of Service. If you do not agree, please do not use the App.</p>

<h2>2. Description of Service</h2>
<p>ReadKindly is a children's story platform that generates and publishes short animated moral stories for kids. Content is created automatically and made available for viewing through our website and partner platforms.</p>

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
<h1>Privacy Policy</h1>
<p><strong>App name:</strong> ReadKindly &nbsp;|&nbsp; <strong>Last updated:</strong> April 7, 2026</p>

<h2>1. Introduction</h2>
<p>ReadKindly ("the App", "we", "us", "our") is committed to protecting your privacy. This Privacy Policy explains how we handle information when you use the ReadKindly website and services.</p>

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
