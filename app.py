"""
SilverSlide Agent — Flask web server
Visit http://localhost:5000 to use the web interface.
"""

import os
import re
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as http_requests
from flask import Flask, after_this_request, jsonify, render_template, request, send_file

app = Flask(__name__)

# ── In-memory caches ──────────────────────────────────────────────────────────
_deck_cache: dict = {}           # job_id -> build_payload
_news_cache: dict = {"data": None, "ts": 0}
NEWS_TTL = 1800                  # refresh news every 30 minutes

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

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/news")
def news():
    """Return 3 pop-culture + 3 serious/economic headlines from RSS feeds."""
    try:
        return jsonify(_get_news())
    except Exception as exc:
        return jsonify({"pop_culture": [], "serious": [], "error": str(exc)})


@app.route("/preview", methods=["POST"])
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


if __name__ == "__main__":
    print("\n  SilverSlide Agent — Web Interface")
    print("  Open your browser to: http://localhost:5000\n")
    app.run(debug=False, port=5000)
