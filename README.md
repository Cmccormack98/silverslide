# SilverSlide Agent

An AI agent that turns any topic into a short, editable, senior-friendly PowerPoint presentation — complete with relevant video content.

## Features

- Generates 3–7 senior-friendly slides from a plain-language topic prompt
- Large readable text (30–40 pt titles, 24 pt body)
- High-contrast design (navy + white + amber)
- Searches YouTube for a short relevant video and embeds it as a clickable link
- Runs accessibility and readability QA checks before export
- Flags medical / legal / financial topics for human review
- Outputs an editable `.pptx` with speaker notes

---

## Setup

### 1. Install Python ≥ 3.10

Download from [python.org](https://python.org) and check **"Add to PATH"** during install.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your Anthropic API key

```bash
# Windows (Command Prompt)
set ANTHROPIC_API_KEY=sk-ant-...

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

### 4. (Optional) Install Node.js for the enhanced pptxgenjs builder

If you have [Node.js ≥ 14](https://nodejs.org) installed, run:
```bash
npm install
```
The agent auto-detects Node.js and uses pptxgenjs when available.

---

## Usage

```bash
# Basic — 5 slides, includes video
python main.py "How to avoid phone scams"

# Custom options
python main.py "What is blood pressure?" --slides 5 --tone "warm and simple"

# Specific audience
python main.py "Safe Internet Use" --audience "first-time smartphone users"

# No video, custom output file
python main.py "Understanding Medicare" --no-video --output medicare_deck.pptx

# Show debug details
python main.py "Preventing Falls at Home" --verbose
```

### All options

| Flag | Default | Description |
|------|---------|-------------|
| `topic` | *(required)* | Presentation topic |
| `--objective` | — | Specific learning goal |
| `--audience` | `general seniors` | Audience description |
| `--tone` | `calm and reassuring` | Presentation tone |
| `--slides` | `5` | Number of slides (3–7) |
| `--output` / `-o` | auto-generated | Output `.pptx` filename |
| `--no-video` | — | Skip video search |
| `--verbose` / `-v` | — | Show debug output |

---

## Output

Each run produces:
- An editable `.pptx` file with speaker notes on every slide
- A console QA report (issues + warnings)
- A review flag for sensitive topics (medical, legal, financial)

### Slide structure

| Slide | Type | Content |
|-------|------|---------|
| 1 | Title | Deck title + welcoming tagline |
| 2–N | Content | 3–5 plain-language bullets per slide |
| N+1 | Video *(if found)* | Clickable thumbnail + video info |
| Last | Summary | Key takeaways with ✓ checkmarks |

---

## Design principles

- **Font**: Calibri 30 pt (titles) / 24 pt (body) — clear and universally available
- **Contrast**: Dark navy on white for content; white on dark navy for title/summary
- **Bullets**: Max 5 per slide, max ~10 words each
- **Video**: Prefer 15–90 second clips; linked with a clickable button
- **Tone**: Warm, respectful — never condescending

---

## Example output

```
============================================================
  SilverSlide Agent  —  Senior-Friendly Presentations
============================================================

  Topic : How to avoid phone scams
  Slides: 5  |  Audience: general seniors

[1/4] Generating senior-friendly content with Claude...
[2/4] Searching for a relevant short video...
      Found: Phone Scam Warning Signs (1:15)
[3/4] Running QA and accessibility checks...
[4/4] Building PowerPoint presentation...

============================================================
  DONE
============================================================
  File   : SilverSlide_How_to_avoid_phone_scams_20250408.pptx
  Title  : Stay Safe: Spotting and Avoiding Phone Scams
  Slides : 6
  Video  : Phone Scam Warning Signs  (1:15)
  QA     : PASS — ready to present
```
