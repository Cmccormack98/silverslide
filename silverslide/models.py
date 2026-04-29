"""Data models for SilverSlide Agent."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class SlideType(str, Enum):
    TITLE = "title"
    CONTENT = "content"
    VIDEO = "video"
    SUMMARY = "summary"


class Bullet(BaseModel):
    text: str


class SlideData(BaseModel):
    slide_type: SlideType
    title: str
    bullets: list[Bullet] = Field(default_factory=list)
    speaker_notes: Optional[str] = None
    image_hint: Optional[str] = None


class VideoData(BaseModel):
    video_id: str
    title: str
    channel: str
    thumbnail_base64: Optional[str] = None
    duration: Optional[str] = None
    url: str


class DeckConfig(BaseModel):
    topic: str
    objective: Optional[str] = None
    audience: str = "general seniors"
    tone: str = "calm and reassuring"
    slide_count: int = 5
    language: str = "English"


class DeckOutput(BaseModel):
    title: str
    slides: list[SlideData]
    video: Optional[VideoData] = None
    risk_level: str = "low"
    review_flag: bool = False
    review_reason: Optional[str] = None
    source_notes: Optional[str] = None


class QAReport(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    review_required: bool = False
