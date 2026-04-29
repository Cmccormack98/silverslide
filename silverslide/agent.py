"""
SilverSlide Agent — main orchestrator.
Ties together content generation, video search, QA, and PPTX export.

Builder selection (auto-detected):
  1. python-pptx  — default; pure Python, no extra installs beyond pip
  2. pptxgenjs    — used if Node.js is available AND builder="node" is passed
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .content import generate_deck_content
from .models import DeckConfig, VideoData
from .qa import run_qa
from .video import get_thumbnail_base64, search_video

SCRIPTS_DIR = Path(__file__).parent / "scripts"


def _node_available() -> bool:
    return shutil.which("node") is not None


class SilverSlideAgent:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    # ── public API ─────────────────────────────────────────────────────

    def create_deck(
        self,
        topic: str,
        objective: str | None = None,
        audience: str = "general seniors",
        tone: str = "calm and reassuring",
        slide_count: int = 5,
        include_video: bool = True,
        output_path: str | None = None,
    ) -> dict:
        """
        Full pipeline: content → video → QA → PPTX.
        Returns a result dict with output_path, qa_report, and metadata.
        """
        print(f"\n  Topic : {topic}")
        print(f"  Slides: {slide_count}  |  Audience: {audience}")

        # ── 1. Generate content ────────────────────────────────────────
        print("\n[1/4] Generating senior-friendly content with Claude...")
        config = DeckConfig(
            topic=topic,
            objective=objective,
            audience=audience,
            tone=tone,
            slide_count=slide_count,
        )
        deck = generate_deck_content(config)
        self._log(f"Title: {deck.title!r}  |  {len(deck.slides)} slides  |  risk={deck.risk_level}")

        # ── 2. Video search ────────────────────────────────────────────
        video_included = False
        video_meta: dict | None = None

        if include_video:
            print("[2/4] Searching for a relevant short video...")
            video: VideoData | None = search_video(topic)

            if video:
                self._log(f"Found: {video.title!r} ({video.duration})")
                print(f"      Found: {video.title} ({video.duration})")
                thumb = get_thumbnail_base64(video.video_id)
                video.thumbnail_base64 = thumb
                deck.video = video
                video_included = True
                video_meta = {
                    "video_id": video.video_id,
                    "title": video.title,
                    "channel": video.channel,
                    "thumbnail_base64": thumb,
                    "duration": video.duration,
                    "url": video.url,
                }
            else:
                print("      No suitable video found — skipping video slide.")
        else:
            print("[2/4] Video skipped (--no-video).")

        # ── 3. QA checks ───────────────────────────────────────────────
        print("[3/4] Running QA and accessibility checks...")
        qa_report = run_qa(deck)
        status = "PASS" if qa_report.passed else f"FAIL ({len(qa_report.issues)} issue(s))"
        self._log(f"QA: {status}  |  {len(qa_report.warnings)} warning(s)")

        # ── 4. Build PPTX ──────────────────────────────────────────────
        print("[4/4] Building PowerPoint presentation...")
        if not output_path:
            output_path = self._auto_filename(topic)

        build_payload = {
            "title": deck.title,
            "topic": topic,
            "slides": [
                {
                    "slide_type": s.slide_type.value,
                    "title": s.title,
                    "bullets": [{"text": b.text} for b in s.bullets],
                    "speaker_notes": s.speaker_notes or "",
                    "image_hint": s.image_hint or "",
                }
                for s in deck.slides
            ],
            "video": video_meta,
        }

        self._run_pptx_builder(build_payload, output_path, builder="python")

        return {
            "output_path": output_path,
            "title": deck.title,
            "slide_count": len(deck.slides) + (1 if video_included else 0),
            "video_included": video_included,
            "video_title": video_meta["title"] if video_meta else None,
            "video_duration": video_meta["duration"] if video_meta else None,
            "video_url": video_meta["url"] if video_meta else None,
            "review_required": qa_report.review_required,
            "review_reason": deck.review_reason,
            "source_notes": deck.source_notes,
            "qa_report": {
                "passed": qa_report.passed,
                "issues": qa_report.issues,
                "warnings": qa_report.warnings,
                "risk_level": qa_report.risk_level,
            },
        }

    # ── private helpers ────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"      [debug] {msg}")

    @staticmethod
    def _auto_filename(topic: str) -> str:
        safe = re.sub(r"[^\w\s-]", "", topic).strip()
        safe = re.sub(r"\s+", "_", safe)[:40]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"SilverSlide_{safe}_{ts}.pptx"

    def _run_pptx_builder(self, payload: dict, output_path: str, builder: str = "python") -> None:
        if builder == "node" and _node_available():
            self._run_node_builder(payload, output_path)
        else:
            self._run_python_builder(payload, output_path)

    def _run_python_builder(self, payload: dict, output_path: str) -> None:
        from .builder_python import build_pptx
        self._log("Using python-pptx builder")
        build_pptx(payload, output_path)

    def _run_node_builder(self, payload: dict, output_path: str) -> None:
        self._log("Using pptxgenjs (Node.js) builder")
        script = str(SCRIPTS_DIR / "build_pptx.js")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(payload, f, ensure_ascii=False)
            tmp_json = f.name

        try:
            result = subprocess.run(
                ["node", script, tmp_json, output_path],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                self._log(result.stdout.strip())
            if result.returncode != 0:
                raise RuntimeError(
                    f"pptxgenjs failed (exit {result.returncode}):\n{result.stderr}"
                )
        finally:
            os.unlink(tmp_json)
