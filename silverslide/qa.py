"""
QA and accessibility checker for SilverSlide Agent.
Validates readability, slide density, and flags sensitive content.
"""

from .models import DeckOutput, QAReport


# Topics that always need expert review before presenting
HIGH_RISK_TERMS = [
    "diagnosis", "diagnose", "treatment plan", "medication", "dosage",
    "prescription", "clinical trial", "drug interaction",
    "legal advice", "file a lawsuit", "tax advice", "invest in",
    "financial planning", "estate planning", "emergency procedure",
    "call 911 if",
]

# Gentle reminders to add when these topics appear
SENSITIVE_TERMS = [
    "blood pressure", "diabetes", "cholesterol", "heart", "stroke",
    "cancer", "arthritis", "dementia", "alzheimer",
    "medicare", "medicaid", "social security", "insurance",
    "password", "bank account", "credit card", "wire transfer",
]


def run_qa(deck: DeckOutput) -> QAReport:
    """Run all QA checks on the generated deck. Returns a QAReport."""
    issues: list[str] = []
    warnings: list[str] = []

    # ── Slide count ────────────────────────────────────────────────────
    if len(deck.slides) < 3:
        issues.append(
            f"Only {len(deck.slides)} slides generated — minimum is 3 for a complete deck."
        )
    if len(deck.slides) > 8:
        warnings.append(
            f"{len(deck.slides)} slides may be too many for a senior audience. "
            "Consider trimming to 5–6."
        )

    # ── Per-slide checks ───────────────────────────────────────────────
    for i, slide in enumerate(deck.slides, 1):
        label = f"Slide {i} ({slide.slide_type.value})"

        # Title length
        if len(slide.title) > 65:
            warnings.append(
                f"{label}: Title is long ({len(slide.title)} chars). "
                "Shorter titles are easier to scan."
            )

        # Bullet count
        if slide.slide_type.value == "content":
            if len(slide.bullets) > 5:
                issues.append(
                    f"{label}: Has {len(slide.bullets)} bullets — max 5 for senior audiences."
                )
            if len(slide.bullets) == 0:
                warnings.append(f"{label}: No bullets — ensure content is visible on slide.")

        # Bullet word count
        for j, bullet in enumerate(slide.bullets, 1):
            words = bullet.text.split()
            if len(words) > 12:
                warnings.append(
                    f"{label}, bullet {j}: '{bullet.text[:45]}...' "
                    f"is {len(words)} words — aim for 8–10 max."
                )

        # Missing speaker notes
        if not slide.speaker_notes and slide.slide_type.value in ("content", "summary"):
            warnings.append(f"{label}: No speaker notes — presenters benefit from talking points.")

    # ── Content risk scan ──────────────────────────────────────────────
    all_text = " ".join(
        slide.title + " " + " ".join(b.text for b in slide.bullets)
        for slide in deck.slides
    ).lower()

    for term in HIGH_RISK_TERMS:
        if term in all_text:
            issues.append(
                f"High-risk term detected: '{term}' — have a qualified professional "
                "review this deck before presenting."
            )
            break  # one issue is enough; don't flood

    for term in SENSITIVE_TERMS:
        if term in all_text:
            warnings.append(
                f"Sensitive topic '{term}' detected — "
                "confirm information accuracy and consider adding 'talk to your doctor / advisor'."
            )
            break  # one warning is enough

    # ── Honour risk flag from Claude ───────────────────────────────────
    if deck.review_flag and deck.risk_level == "high":
        issues.append(
            "Content flagged for expert review: this deck covers a high-risk topic. "
            f"Reason: {deck.review_reason or 'See source notes.'}"
        )

    passed = len(issues) == 0
    review_required = deck.review_flag or deck.risk_level in ("medium", "high")

    return QAReport(
        passed=passed,
        issues=issues,
        warnings=warnings,
        risk_level=deck.risk_level,
        review_required=review_required,
    )
