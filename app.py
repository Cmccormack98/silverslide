"""
SilverSlide Agent — Flask web server
Visit http://localhost:5000 to use the web interface.
"""

import functools
import hashlib
import io
import json
import os
import re
import smtplib
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests as http_requests
from flask import (Flask, after_this_request, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "silverslide-dev-secret-change-me")

# ── In-memory caches ──────────────────────────────────────────────────────────
_deck_cache: dict = {}
_news_cache: dict = {"data": None, "ts": 0}
NEWS_TTL = 1800

# ── Supabase client ───────────────────────────────────────────────────────────
def _get_supabase():
    url = os.environ.get("SUPABASE_URL", "https://xaoimkczjmlpvajbbvmr.supabase.co")
    key = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhhb2lta2N6am1scHZhamJidm1yIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzQ3OTI3MiwiZXhwIjoyMDkzMDU1MjcyfQ.tQ5XOV2ECgeY6WuUE6rdZVTGeQg218YMliloNReFyDc")
    from supabase import create_client
    return create_client(url, key)

# ── Deck helpers (Supabase) ───────────────────────────────────────────────────
def _load_decks(username: str) -> list:
    try:
        sb  = _get_supabase()
        res = sb.table("decks").select("id,title,topic,slide_count,theme,saved_at").eq("username", username).order("saved_at", desc=True).limit(50).execute()
        return res.data or []
    except Exception:
        return []

def _save_deck_db(username: str, payload: dict) -> str:
    deck_id = str(uuid.uuid4())
    sb = _get_supabase()
    sb.table("decks").insert({
        "id":          deck_id,
        "username":    username,
        "title":       payload.get("title", "Untitled"),
        "topic":       payload.get("topic", ""),
        "slide_count": len(payload.get("slides", [])),
        "theme":       payload.get("theme", "classic"),
        "payload":     payload,
    }).execute()
    return deck_id

def _get_deck_db(deck_id: str, username: str) -> dict | None:
    try:
        sb  = _get_supabase()
        res = sb.table("decks").select("payload").eq("id", deck_id).eq("username", username).single().execute()
        return res.data["payload"] if res.data else None
    except Exception:
        return None

def _delete_deck_db(deck_id: str, username: str) -> None:
    try:
        _get_supabase().table("decks").delete().eq("id", deck_id).eq("username", username).execute()
    except Exception:
        pass

# ── Auth helpers ──────────────────────────────────────────────────────────────
def _get_users() -> dict:
    """
    Read users from USERS env var.  Format:  username:password,username2:password2
    Falls back to a default admin account for local dev.
    """
    raw = os.environ.get("USERS", "cameryn:silverslide2024")
    users = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            u, p = pair.split(":", 1)
            users[u.strip()] = hashlib.sha256(p.strip().encode()).hexdigest()
    return users

def _check_password(username: str, password: str) -> bool:
    users = _get_users()
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return users.get(username) == hashed

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

# ── RSS feed definitions (Google News RSS — most reliable, no auth needed) ────
POP_FEEDS = [
    ("Google News", "https://news.google.com/rss/search?q=celebrity+music+movies+entertainment+pop+culture&hl=en-US&gl=US&ceid=US:en"),
    ("Google News", "https://news.google.com/rss/search?q=tv+shows+celebrity+awards+hollywood&hl=en-US&gl=US&ceid=US:en"),
]

SERIOUS_FEEDS = [
    ("Google News", "https://news.google.com/rss/search?q=economy+markets+business+finance&hl=en-US&gl=US&ceid=US:en"),
    ("Google News", "https://news.google.com/rss/search?q=world+news+politics+international&hl=en-US&gl=US&ceid=US:en"),
]


def _fetch_rss(source: str, url: str, max_items: int = 5) -> list[dict]:
    """Fetch and return headlines from a single RSS feed. Never raises."""
    try:
        resp = http_requests.get(
            url, timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SilverSlide/1.0)"},
        )
        resp.raise_for_status()

        # Strip XML namespaces so findall(".//item") always works
        text = re.sub(r'\sxmlns(?::\w+)?="[^"]*"', "", resp.text)
        root = ET.fromstring(text.encode("utf-8", errors="replace"))

        out = []
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            # Strip CDATA wrappers if present
            title = re.sub(r"^<!\[CDATA\[(.+?)]]>$", r"\1", title, flags=re.S).strip()
            # Google News appends " - Source Name" — extract it and use as source
            src = source
            gnews_match = re.match(r"^(.+?)\s+-\s+([^-]+)$", title)
            if gnews_match:
                title = gnews_match.group(1).strip()
                src   = gnews_match.group(2).strip()
            link  = (item.findtext("link") or "").strip()
            if title and len(title) > 15:
                out.append({"title": title, "url": link, "source": src})
        return out
    except Exception:
        return []


def _get_news() -> dict:
    """Return cached news or fetch fresh. Fetches all feeds in parallel."""
    global _news_cache
    now = time.time()
    if _news_cache["data"] and now - _news_cache["ts"] < NEWS_TTL:
        return _news_cache["data"]

    pop_pool:     list[dict] = []
    serious_pool: list[dict] = []

    futures = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for src, url in POP_FEEDS:
            futures[ex.submit(_fetch_rss, src, url)] = "pop"
        for src, url in SERIOUS_FEEDS:
            futures[ex.submit(_fetch_rss, src, url)] = "serious"

        for future in as_completed(futures, timeout=8):
            category = futures[future]
            try:
                items = future.result()
            except Exception:
                items = []
            if category == "pop":
                pop_pool.extend(items)
            else:
                serious_pool.extend(items)

    # De-duplicate by title prefix, keep first 3 per category
    def dedup(pool: list[dict], limit: int = 3) -> list[dict]:
        seen, out = set(), []
        for item in pool:
            key = item["title"][:40].lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
            if len(out) >= limit:
                break
        return out

    data = {
        "pop_culture": dedup(pop_pool),
        "serious":     dedup(serious_pool),
    }
    _news_cache = {"data": data, "ts": now}
    return data


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if session.get("username"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        if _check_password(u, p):
            session["username"] = u
            return redirect(url_for("index"))
        error = "Incorrect username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session["username"])


@app.route("/news")
@login_required
def news():
    """Return 3 pop-culture + 3 serious/economic headlines from RSS feeds."""
    try:
        return jsonify(_get_news())
    except Exception as exc:
        return jsonify({"pop_culture": [], "serious": [], "error": str(exc)})


@app.route("/preview", methods=["POST"])
@login_required
def preview():
    """Step 1 — Generate content with Claude, return slide data for browser preview."""
    from silverslide.content import generate_deck_content
    from silverslide.video import search_video, get_thumbnail_base64
    from silverslide.qa import run_qa
    from silverslide.models import DeckConfig

    data = request.get_json()
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Please enter a topic."}), 400

    try:
        slide_count = max(3, min(7, int(data.get("slides", 5))))
    except (ValueError, TypeError):
        slide_count = 5

    audience      = (data.get("audience")      or "general seniors").strip()
    tone          = (data.get("tone")           or "calm and reassuring").strip()
    include_video = bool(data.get("include_video", True))
    theme         = (data.get("theme")          or "classic").strip()

    try:
        config = DeckConfig(topic=topic, audience=audience, tone=tone, slide_count=slide_count)
        deck   = generate_deck_content(config)

        video_meta = None
        if include_video:
            video = search_video(topic)
            if video:
                thumb = get_thumbnail_base64(video.video_id)
                video.thumbnail_base64 = thumb
                deck.video = video
                video_meta = {
                    "video_id":         video.video_id,
                    "title":            video.title,
                    "channel":          video.channel,
                    "thumbnail_base64": thumb,
                    "duration":         video.duration,
                    "url":              video.url,
                }

        qa_report = run_qa(deck)

        build_payload = {
            "title":  deck.title,
            "topic":  topic,
            "theme":  theme,
            "slides": [
                {
                    "slide_type":    s.slide_type.value,
                    "title":         s.title,
                    "bullets":       [{"text": b.text} for b in s.bullets],
                    "speaker_notes": s.speaker_notes or "",
                    "image_hint":    s.image_hint    or "",
                }
                for s in deck.slides
            ],
            "video": video_meta,
        }

        job_id = str(uuid.uuid4())
        _deck_cache[job_id] = build_payload

        return jsonify({
            "job_id":        job_id,
            "title":         deck.title,
            "theme":         theme,
            "risk_level":    deck.risk_level,
            "review_flag":   deck.review_flag,
            "review_reason": deck.review_reason,
            "source_notes":  deck.source_notes,
            "slides":        build_payload["slides"],
            "video":         video_meta,
            "qa": {
                "passed":   qa_report.passed,
                "issues":   qa_report.issues,
                "warnings": qa_report.warnings,
            },
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/thumbnails", methods=["POST"])
@login_required
def thumbnails():
    """Return Pexels thumbnail URLs for a list of image hints (for preview cards)."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return jsonify({})

    hints = request.get_json().get("hints", [])

    def fetch_one(hint):
        try:
            resp = http_requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": hint, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": key},
                timeout=5,
            )
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                if photos:
                    return hint, photos[0]["src"]["small"]
        except Exception:
            pass
        return hint, None

    results = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for hint, url in ex.map(fetch_one, hints):
            if url:
                results[hint] = url

    return jsonify(results)


@app.route("/debug/pexels")
def debug_pexels():
    """Quick diagnostic — visit this URL to check if Pexels is working."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return jsonify({"status": "ERROR", "reason": "PEXELS_API_KEY env var is not set — restart the server after setting it"})
    try:
        resp = http_requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": "senior smiling outdoors", "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=6,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                return jsonify({"status": "OK", "photo_url": photos[0]["src"]["medium"], "message": "Pexels is working!"})
            return jsonify({"status": "OK but no photos returned", "raw": resp.json()})
        return jsonify({"status": f"HTTP {resp.status_code}", "body": resp.text[:300]})
    except Exception as exc:
        return jsonify({"status": "ERROR", "reason": str(exc)})


@app.route("/refine/<job_id>", methods=["POST"])
@login_required
def refine(job_id):
    """Apply a natural-language edit instruction to the slides using Claude."""
    from silverslide.content import refine_slides

    data        = request.get_json()
    instruction = (data.get("instruction") or "").strip()
    slides      = data.get("slides") or []

    if not instruction:
        return jsonify({"error": "Please enter an edit instruction."}), 400
    if not slides:
        return jsonify({"error": "No slides provided."}), 400

    try:
        updated = refine_slides(slides, instruction)

        # Update the server cache so the download uses the refined content
        if job_id in _deck_cache:
            _deck_cache[job_id]["slides"] = updated

        return jsonify({"slides": updated})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/download/<job_id>", methods=["POST"])
@login_required
def download(job_id):
    """Step 2 — Build PPTX from cached preview data and send for download."""
    if job_id not in _deck_cache:
        return jsonify({"error": "Preview expired — please generate a new preview first."}), 404

    build_payload = dict(_deck_cache.pop(job_id))
    topic         = build_payload.get("title", "presentation")

    # Accept edited slides from the client (Make Edits feature)
    body = request.get_json(silent=True) or {}
    if body.get("slides"):
        build_payload["slides"] = body["slides"]

    tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
    tmp.close()
    output_path = tmp.name

    try:
        from silverslide.builder_python import build_pptx
        build_pptx(build_payload, output_path)

        safe     = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)
        safe     = safe.strip().replace(" ", "_")[:40]
        filename = f"SilverSlide_{safe}.pptx"

        @after_this_request
        def cleanup(response):
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return response

        return send_file(
            output_path,
            as_attachment=True,
            download_name=filename,
            mimetype=(
                "application/vnd.openxmlformats-officedocument"
                ".presentationml.presentation"
            ),
        )

    except Exception as exc:
        try:
            os.unlink(output_path)
        except OSError:
            pass
        return jsonify({"error": str(exc)}), 500


# ── Saved Decks ───────────────────────────────────────────────────────────────

@app.route("/decks", methods=["GET"])
@login_required
def list_decks():
    return jsonify(_load_decks(session["username"]))


@app.route("/decks/save/<job_id>", methods=["POST"])
@login_required
def save_deck(job_id):
    if job_id not in _deck_cache:
        return jsonify({"error": "Preview expired."}), 404
    payload = dict(_deck_cache[job_id])
    body    = request.get_json(silent=True) or {}
    if body.get("slides"):
        payload["slides"] = body["slides"]
    try:
        deck_id = _save_deck_db(session["username"], payload)
        return jsonify({"deck_id": deck_id, "message": "Deck saved!"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/decks/<deck_id>", methods=["DELETE"])
@login_required
def delete_deck(deck_id):
    _delete_deck_db(deck_id, session["username"])
    return jsonify({"message": "Deleted"})


@app.route("/decks/<deck_id>/download", methods=["POST"])
@login_required
def download_saved(deck_id):
    payload = _get_deck_db(deck_id, session["username"])
    if not payload:
        return jsonify({"error": "Deck not found."}), 404
    tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
    tmp.close()
    output_path = tmp.name
    try:
        from silverslide.builder_python import build_pptx
        build_pptx(payload, output_path)
        safe     = "".join(c if c.isalnum() or c in " -_" else "" for c in payload.get("title","deck"))
        safe     = safe.strip().replace(" ", "_")[:40]
        filename = f"SilverSlide_{safe}.pptx"

        @after_this_request
        def cleanup(response):
            try: os.unlink(output_path)
            except OSError: pass
            return response

        return send_file(output_path, as_attachment=True, download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    except Exception as exc:
        try: os.unlink(output_path)
        except OSError: pass
        return jsonify({"error": str(exc)}), 500


# ── Email ─────────────────────────────────────────────────────────────────────

@app.route("/email/<job_id>", methods=["POST"])
@login_required
def email_deck(job_id):
    if job_id not in _deck_cache:
        return jsonify({"error": "Preview expired — please regenerate first."}), 404

    body      = request.get_json(silent=True) or {}
    to_email  = (body.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        return jsonify({"error": "Please enter a valid email address."}), 400

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        return jsonify({"error": "Email not configured on the server yet. Set SMTP_USER and SMTP_PASSWORD environment variables."}), 500

    payload = dict(_deck_cache[job_id])
    if body.get("slides"):
        payload["slides"] = body["slides"]

    tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
    tmp.close()
    output_path = tmp.name

    try:
        from silverslide.builder_python import build_pptx
        build_pptx(payload, output_path)

        title    = payload.get("title", "SilverSlide Presentation")
        safe     = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip().replace(" ", "_")[:40]
        filename = f"SilverSlide_{safe}.pptx"

        msg = MIMEMultipart()
        msg["From"]    = smtp_user
        msg["To"]      = to_email
        msg["Subject"] = f"Your SilverSlide Presentation: {title}"
        msg.attach(MIMEText(
            f"Hi,\n\nAttached is your SilverSlide presentation: \"{title}\"\n\n"
            "Generated by SilverSlide Agent — Senior-Friendly Presentations.\n", "plain"))

        with open(output_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return jsonify({"message": f"Sent to {to_email}!"})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        try: os.unlink(output_path)
        except OSError: pass


if __name__ == "__main__":
    print("\n  SilverSlide Agent — Web Interface")
    print("  Open your browser to: http://localhost:5000\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
