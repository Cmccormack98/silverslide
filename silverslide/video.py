"""
YouTube video search and thumbnail retrieval for SilverSlide Agent.
Finds short, relevant videos suitable for senior audiences.
"""

import base64
from typing import Optional

import requests

from .models import VideoData


# Prefer videos in this duration range (seconds)
TARGET_MIN = 15
TARGET_MAX = 90
FALLBACK_MAX = 180  # accept up to 3 minutes as fallback


def search_video(topic: str) -> Optional[VideoData]:
    """Search YouTube for a short, senior-friendly video on the topic."""
    try:
        from youtubesearchpython import VideosSearch
    except ImportError:
        print("   [video] youtube-search-python not installed, skipping video search")
        return None

    queries = [
        f"{topic} explained simply",
        f"{topic} for beginners easy",
        f"{topic} seniors guide",
    ]

    for query in queries:
        try:
            search = VideosSearch(query, limit=8)
            results = search.result()
            video = _pick_best_result(results)
            if video:
                return video
        except Exception as e:
            print(f"   [video] Search error for '{query}': {e}")
            continue

    return None


def _pick_best_result(results: dict) -> Optional[VideoData]:
    """Pick the best video from search results, preferring short durations."""
    if not results or not results.get("result"):
        return None

    candidates = results["result"]

    # First pass: find a video in the ideal 15–90s range
    for item in candidates:
        secs = _parse_duration(item.get("duration", ""))
        if secs is not None and TARGET_MIN <= secs <= TARGET_MAX:
            return _build_video_data(item)

    # Second pass: accept up to FALLBACK_MAX
    for item in candidates:
        secs = _parse_duration(item.get("duration", ""))
        if secs is not None and secs <= FALLBACK_MAX:
            return _build_video_data(item)

    # Last resort: first result regardless of duration
    if candidates:
        return _build_video_data(candidates[0])

    return None


def _build_video_data(item: dict) -> VideoData:
    video_id = item.get("id", "")
    channel_info = item.get("channel") or {}
    return VideoData(
        video_id=video_id,
        title=item.get("title", ""),
        channel=channel_info.get("name", "") if isinstance(channel_info, dict) else "",
        duration=item.get("duration", ""),
        url=item.get("link", f"https://www.youtube.com/watch?v={video_id}"),
    )


def _parse_duration(duration_str: str) -> Optional[int]:
    """Convert 'M:SS' or 'H:MM:SS' to total seconds. Returns None on failure."""
    if not duration_str:
        return None
    parts = duration_str.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, IndexError):
        return None
    return None


def get_thumbnail_base64(video_id: str) -> Optional[str]:
    """Download a YouTube thumbnail and return it as a base64 data URI."""
    qualities = ["maxresdefault", "hqdefault", "mqdefault", "default"]
    for quality in qualities:
        url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
        try:
            resp = requests.get(url, timeout=10)
            # YouTube returns a 120x90 grey placeholder for missing thumbnails —
            # those are tiny files (~1-2 KB). Skip them.
            if resp.status_code == 200 and len(resp.content) > 5_000:
                encoded = base64.b64encode(resp.content).decode("utf-8")
                return f"image/jpeg;base64,{encoded}"
        except requests.RequestException:
            continue
    return None
