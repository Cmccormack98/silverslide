"""
Claude API content generation for SilverSlide Agent.
Transforms any topic into senior-friendly slide content.
"""

import re
import json
import anthropic
from .models import DeckConfig, DeckOutput, SlideData, SlideType, Bullet


def refine_slides(slides: list[dict], instruction: str) -> list[dict]:
    """Use Claude to apply a natural-language edit instruction to the slide list."""
    client = anthropic.Anthropic()

    slides_json = json.dumps(slides, indent=2)

    prompt = f"""You are editing a senior-friendly PowerPoint presentation.

Current slides (JSON array):
{slides_json}

Edit instruction from the user: "{instruction}"

Instructions:
- Apply the user's request to the slides (add/remove/rewrite slides or bullets, update image hints, etc.)
- Keep all language plain English, max 10 words per bullet, max 5 bullets per slide
- If asked to add a slide, insert it in a logical place between title and summary
- If asked to add pictures or images, improve the "image_hint" field on each slide with vivid, specific photo keywords (e.g. "elderly woman smiling at smartphone" not just "phone")
- slide_type must be one of: "title", "content", "summary" — never change the first (title) or last (summary) slide type
- Keep the warm, respectful, senior-friendly tone throughout
- Return ONLY a valid JSON array with the exact same field structure. No markdown. No explanation."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    return json.loads(text)


SYSTEM_PROMPT = """You are SilverSlide Agent, an expert at creating presentations for older adults (65+).

Your mission: Transform any topic into a clear, accessible, senior-friendly slide deck.

## Senior-Friendly Writing Rules
- Plain English only. No jargon or technical terms without explaining them simply.
- Short sentences. Active voice. Conversational.
- One idea per slide — never cram two concepts together.
- Max 5 bullets per slide, max 8–10 words per bullet.
- Use practical, relatable examples (grandchildren, doctor visits, phone calls, TV).
- Warm, respectful tone. Never condescending or overly simple.
- Repeat the key takeaway — seniors benefit from reinforcement.
- Concrete steps over abstract concepts.

## Risk Assessment
- Medical diagnosis or treatment recommendations → risk_level="high", review_flag=true
- Legal or investment/financial advice → risk_level="high", review_flag=true
- General health awareness or wellness education → risk_level="medium"
- Fraud/scam awareness → risk_level="low"
- Technology how-to guides → risk_level="low"
- General wellness tips → risk_level="low"

For high-risk topics: add "Talk to your doctor" or "Consult a professional" bullets.

## Output
Return ONLY valid JSON. No markdown. No extra text. No code blocks."""


def generate_deck_content(config: DeckConfig) -> DeckOutput:
    """Call Claude to generate a senior-friendly slide deck for the given topic."""
    client = anthropic.Anthropic()

    # Content slides = total - title - summary
    content_slides = max(1, config.slide_count - 2)

    user_prompt = f"""Create a {config.slide_count}-slide PowerPoint deck on this topic:

Topic: {config.topic}
{f"Learning goal: {config.objective}" if config.objective else ""}
Audience: {config.audience}
Tone: {config.tone}
Total slides: {config.slide_count} (1 title + {content_slides} content + 1 summary)

Return a single JSON object with EXACTLY this structure:
{{
  "title": "Clear, welcoming presentation title",
  "risk_level": "low",
  "review_flag": false,
  "review_reason": null,
  "source_notes": "One sentence about content accuracy",
  "slides": [
    {{
      "slide_type": "title",
      "title": "Welcoming subtitle or tagline for the title slide",
      "bullets": [],
      "speaker_notes": "2-3 sentences: welcome the audience, set the tone",
      "image_hint": "Brief description of an ideal welcoming image"
    }},
    {{
      "slide_type": "content",
      "title": "Clear, action-oriented slide title",
      "bullets": [
        {{"text": "Plain English point (max 10 words)"}},
        {{"text": "Another practical point"}},
        {{"text": "One more easy-to-remember idea"}}
      ],
      "speaker_notes": "2-4 sentences with expanded explanation and examples",
      "image_hint": "Brief description of a supportive, relatable image"
    }},
    {{
      "slide_type": "summary",
      "title": "What to Remember",
      "bullets": [
        {{"text": "Key takeaway 1 (concrete and actionable)"}},
        {{"text": "Key takeaway 2"}},
        {{"text": "Your next step today"}}
      ],
      "speaker_notes": "2-3 sentences of encouragement and closing",
      "image_hint": "Uplifting or positive image"
    }}
  ]
}}

Critical rules:
- Exactly {config.slide_count} slides: first is title, last is summary, middle {content_slides} are content
- Every content slide has 3-5 bullets, each max 10 words
- Speaker notes use natural, spoken language
- If topic involves medical/legal/financial specifics: review_flag=true, risk_level="high"
- Return ONLY the JSON object, nothing else"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract text block
    text_content = next(b.text for b in response.content if b.type == "text")

    # Strip any accidental markdown code fences
    text_content = re.sub(r"^```(?:json)?\s*", "", text_content.strip())
    text_content = re.sub(r"\s*```$", "", text_content.strip())

    data = json.loads(text_content)

    slides = []
    for s in data["slides"]:
        bullets = [Bullet(text=b["text"]) for b in s.get("bullets", [])]
        slides.append(
            SlideData(
                slide_type=SlideType(s["slide_type"]),
                title=s["title"],
                bullets=bullets,
                speaker_notes=s.get("speaker_notes"),
                image_hint=s.get("image_hint"),
            )
        )

    return DeckOutput(
        title=data["title"],
        slides=slides,
        risk_level=data.get("risk_level", "low"),
        review_flag=data.get("review_flag", False),
        review_reason=data.get("review_reason"),
        source_notes=data.get("source_notes"),
    )
