/**
 * SilverSlide Agent — PPTX Builder
 * Creates a senior-friendly PowerPoint from a JSON deck definition.
 *
 * Usage: node build_pptx.js input.json output.pptx
 *
 * Design principles (per PRD):
 *   - Title fonts: 36–40 pt  |  Body fonts: 24–26 pt
 *   - High contrast: dark text on light slides, white text on dark slides
 *   - Max 5 bullets per slide, one key message per slide
 *   - Warm, calm palette: deep navy + amber accent
 *   - Clear slide structure: title bar → spacious content area
 */

"use strict";

const pptxgen = require("pptxgenjs");
const fs = require("fs");

// ── CLI args ────────────────────────────────────────────────────────────────
const [, , inputPath, outputPath] = process.argv;
if (!inputPath || !outputPath) {
  console.error("Usage: node build_pptx.js input.json output.pptx");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(inputPath, "utf8"));

// ── Palette ─────────────────────────────────────────────────────────────────
// "Senior Calm" — deep navy + warm amber, maximum readability
const C = {
  navy:        "1B3A5C",  // primary dark: title bars, dark slide bg
  navyDeep:    "122743",  // footer / bottom bar
  amber:       "E07B39",  // accent: bullets, highlight, left stripe
  white:       "FFFFFF",
  offWhite:    "F8F6F2",  // slide background (warmer than pure white)
  textDark:    "1A202C",  // body text on light slides
  textLight:   "D8E8F3",  // subtitle / caption on dark slides
  steelBlue:   "9EC8E0",  // secondary on dark: subtitle text
  slideNum:    "A0AEC0",  // de-emphasised slide numbers
  videoBg:     "EEF6FB",  // video slide background
  videoPanel:  "1B3A5C",  // video info panel
  playRed:     "CC0000",  // YouTube-style play button
  linkBlue:    "2563EB",  // hyperlink text
};

const FONT = "Calibri";  // universally available, excellent readability

const PT = {
  mainTitle:   40,   // title slide headline
  slideTitle:  30,   // content / summary slide title bar
  body:        24,   // bullet text
  caption:     15,   // captions, footers, video info
  tiny:        12,   // slide numbers, fine print
};

// Slide canvas: 10" × 5.625" (LAYOUT_16x9)
const W = 10;
const H = 5.625;

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Add a slide number in the bottom-right corner. */
function addSlideNum(slide, current, total) {
  slide.addText(`${current} / ${total}`, {
    x: W - 1.1, y: H - 0.38, w: 0.95, h: 0.28,
    fontSize: PT.tiny, color: C.slideNum,
    align: "right", fontFace: FONT, margin: 0,
  });
}

/** Add the navy title bar + white title text used on every content slide. */
function addTitleBar(slide, title) {
  // Navy bar spanning full width
  slide.addShape("rect", {
    x: 0, y: 0, w: W, h: 1.15,
    fill: { color: C.navy },
    line: { color: C.navy, width: 0 },
  });
  // Title text inside bar
  slide.addText(title, {
    x: 0.45, y: 0.12, w: W - 0.9, h: 0.95,
    fontSize: PT.slideTitle, fontFace: FONT, bold: true,
    color: C.white, valign: "middle", align: "left", margin: 0,
  });
}

/** Amber vertical accent stripe on the left edge. */
function addLeftStripe(slide, yStart, height) {
  slide.addShape("rect", {
    x: 0, y: yStart, w: 0.28, h: height,
    fill: { color: C.amber },
    line: { color: C.amber, width: 0 },
  });
}

// ── Build deck ───────────────────────────────────────────────────────────────
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author  = "SilverSlide Agent";
pres.title   = data.title;

const contentSlides = data.slides.filter(s => s.slide_type === "content");
const summarySlide  = data.slides.find(s => s.slide_type === "summary");
const titleSlide    = data.slides.find(s => s.slide_type === "title");

// Count visible slides for numbering (video slide counts too)
const hasVideo  = !!(data.video && data.video.url);
const totalVisible = 1 + contentSlides.length + (hasVideo ? 1 : 0) + 1;
let   slideNum  = 0;

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 1 — TITLE
// ════════════════════════════════════════════════════════════════════════════
slideNum++;
const s1 = pres.addSlide();
s1.background = { color: C.navy };

// Left amber stripe (full height)
addLeftStripe(s1, 0, H);

// Bottom footer bar (slightly darker navy)
s1.addShape("rect", {
  x: 0, y: H - 0.5, w: W, h: 0.5,
  fill: { color: C.navyDeep },
  line: { color: C.navyDeep, width: 0 },
});

// Horizontal amber divider line
s1.addShape("rect", {
  x: 0.55, y: 2.9, w: W - 1.1, h: 0.04,
  fill: { color: C.amber },
  line: { color: C.amber, width: 0 },
});

// Main title
s1.addText(data.title, {
  x: 0.55, y: 0.9, w: W - 1.0, h: 1.8,
  fontSize: PT.mainTitle, fontFace: FONT, bold: true,
  color: C.white, align: "left", valign: "middle",
});

// Subtitle / tagline from title slide data
const tagline = titleSlide ? titleSlide.title : "";
if (tagline && tagline !== data.title) {
  s1.addText(tagline, {
    x: 0.55, y: 3.05, w: W - 1.1, h: 0.75,
    fontSize: 20, fontFace: FONT,
    color: C.steelBlue, align: "left", valign: "top",
  });
}

// Footer text
s1.addText("Created by SilverSlide Agent  •  Senior-Friendly Presentation", {
  x: 0.55, y: H - 0.42, w: W - 1.1, h: 0.32,
  fontSize: PT.tiny, fontFace: FONT,
  color: "6B8FAF", align: "left", margin: 0,
});

if (titleSlide && titleSlide.speaker_notes) {
  s1.addNotes(titleSlide.speaker_notes);
}

// ════════════════════════════════════════════════════════════════════════════
// CONTENT SLIDES
// ════════════════════════════════════════════════════════════════════════════
for (let i = 0; i < contentSlides.length; i++) {
  slideNum++;
  const sd = contentSlides[i];
  const sl = pres.addSlide();
  sl.background = { color: C.offWhite };

  addTitleBar(sl, sd.title);

  // Amber left accent (content area only, below title bar)
  sl.addShape("rect", {
    x: 0, y: 1.15, w: 0.28, h: H - 1.15,
    fill: { color: C.amber },
    line: { color: C.amber, width: 0 },
  });

  // Bullets
  if (sd.bullets && sd.bullets.length > 0) {
    const bulletRuns = sd.bullets.map((b, idx) => ({
      text: b.text,
      options: {
        bullet: true,
        fontSize: PT.body,
        fontFace: FONT,
        color: C.textDark,
        paraSpaceAfter: 10,
        breakLine: idx < sd.bullets.length - 1,
      },
    }));

    sl.addText(bulletRuns, {
      x: 0.5, y: 1.25, w: W - 0.65, h: H - 1.55,
      valign: "top",
      margin: [0.18, 0.1, 0.1, 0.18],
    });
  }

  addSlideNum(sl, slideNum, totalVisible);

  if (sd.speaker_notes) {
    sl.addNotes(sd.speaker_notes);
  }
}

// ════════════════════════════════════════════════════════════════════════════
// VIDEO SLIDE (optional)
// ════════════════════════════════════════════════════════════════════════════
if (hasVideo) {
  slideNum++;
  const v  = data.video;
  const vs = pres.addSlide();
  vs.background = { color: C.videoBg };

  addTitleBar(vs, "Watch This Short Video");

  // ── Thumbnail (left panel) ──────────────────────────────────────────
  const thumbX = 0.4;
  const thumbY = 1.3;
  const thumbW = 5.5;
  const thumbH = 3.1;

  if (v.thumbnail_base64) {
    vs.addImage({
      data: v.thumbnail_base64,
      x: thumbX, y: thumbY, w: thumbW, h: thumbH,
      hyperlink: { url: v.url },
      altText: `Thumbnail: ${v.title}`,
    });
  } else {
    // Grey placeholder if thumbnail unavailable
    vs.addShape("rect", {
      x: thumbX, y: thumbY, w: thumbW, h: thumbH,
      fill: { color: "CCCCCC" },
      line: { color: "AAAAAA", width: 1 },
    });
    vs.addText("[ Video Thumbnail ]", {
      x: thumbX, y: thumbY + thumbH / 2 - 0.25, w: thumbW, h: 0.5,
      fontSize: 16, fontFace: FONT, color: "777777", align: "center",
    });
  }

  // Play-button circle overlay
  const cx = thumbX + thumbW / 2 - 0.5;
  const cy = thumbY + thumbH / 2 - 0.45;
  vs.addShape("ellipse", {
    x: cx, y: cy, w: 1.0, h: 1.0,
    fill: { color: C.playRed, transparency: 15 },
    line: { color: C.white, width: 2 },
    hyperlink: { url: v.url },
  });
  vs.addText("▶", {
    x: cx + 0.08, y: cy, w: 1.0, h: 1.0,
    fontSize: 28, color: C.white,
    align: "center", valign: "middle",
    fontFace: FONT, margin: 0,
    hyperlink: { url: v.url },
  });

  // Click-to-open link below thumbnail
  vs.addText("Click the image above to open the video", {
    x: thumbX, y: thumbY + thumbH + 0.1, w: thumbW, h: 0.35,
    fontSize: PT.caption, fontFace: FONT, color: C.linkBlue,
    align: "center", underline: true,
    hyperlink: { url: v.url },
  });

  // ── Info panel (right) ──────────────────────────────────────────────
  const panelX = 6.1;
  const panelY = 1.3;
  const panelW = 3.65;
  const panelH = 3.1;

  vs.addShape("rect", {
    x: panelX, y: panelY, w: panelW, h: panelH,
    fill: { color: C.videoPanel },
    line: { color: C.navyDeep, width: 0 },
  });

  vs.addText("HOW TO PLAY", {
    x: panelX + 0.15, y: panelY + 0.15, w: panelW - 0.3, h: 0.35,
    fontSize: 11, fontFace: FONT, bold: true,
    color: C.amber, align: "center", margin: 0,
  });

  vs.addText("Click the thumbnail\nor the play button", {
    x: panelX + 0.15, y: panelY + 0.55, w: panelW - 0.3, h: 0.7,
    fontSize: 16, fontFace: FONT, bold: true,
    color: C.white, align: "center",
  });

  // Divider
  vs.addShape("rect", {
    x: panelX + 0.25, y: panelY + 1.35, w: panelW - 0.5, h: 0.03,
    fill: { color: "3A5A7A" },
    line: { color: "3A5A7A", width: 0 },
  });

  // Video title
  vs.addText(v.title || "Video", {
    x: panelX + 0.15, y: panelY + 1.45, w: panelW - 0.3, h: 0.85,
    fontSize: 13, fontFace: FONT,
    color: C.steelBlue, align: "center",
  });

  // Duration
  if (v.duration) {
    vs.addText(`Duration: ${v.duration}`, {
      x: panelX + 0.15, y: panelY + 2.35, w: panelW - 0.3, h: 0.3,
      fontSize: 12, fontFace: FONT,
      color: "7AACCB", align: "center",
    });
  }

  // Channel
  if (v.channel) {
    vs.addText(`From: ${v.channel}`, {
      x: panelX + 0.15, y: panelY + 2.65, w: panelW - 0.3, h: 0.3,
      fontSize: 11, fontFace: FONT,
      color: "5A8AAA", align: "center",
    });
  }

  addSlideNum(vs, slideNum, totalVisible);
  vs.addNotes(
    `Video: ${v.title}\nChannel: ${v.channel}\nDuration: ${v.duration}\nURL: ${v.url}`
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SUMMARY / CLOSING SLIDE
// ════════════════════════════════════════════════════════════════════════════
slideNum++;
const ss = pres.addSlide();
ss.background = { color: C.navy };

// Left amber stripe
addLeftStripe(ss, 0, H);

// Bottom bar
ss.addShape("rect", {
  x: 0, y: H - 0.5, w: W, h: 0.5,
  fill: { color: C.navyDeep },
  line: { color: C.navyDeep, width: 0 },
});

// Title
const summaryTitle = (summarySlide && summarySlide.title) ? summarySlide.title : "What to Remember";
ss.addText(summaryTitle, {
  x: 0.5, y: 0.2, w: W - 0.7, h: 0.9,
  fontSize: 34, fontFace: FONT, bold: true,
  color: C.white, align: "left", valign: "middle",
});

// Amber divider
ss.addShape("rect", {
  x: 0.5, y: 1.18, w: W - 0.7, h: 0.04,
  fill: { color: C.amber },
  line: { color: C.amber, width: 0 },
});

// Checkmark bullets — rendered as plain text runs with ✓ prefix
// (avoids double-bullet when mixing unicode + bullet:true)
if (summarySlide && summarySlide.bullets && summarySlide.bullets.length > 0) {
  const runs = summarySlide.bullets.map((b, idx) => ({
    text: `\u2713  ${b.text}`,
    options: {
      fontSize: PT.body,
      fontFace: FONT,
      color: C.white,
      paraSpaceAfter: 14,
      breakLine: idx < summarySlide.bullets.length - 1,
    },
  }));

  ss.addText(runs, {
    x: 0.5, y: 1.3, w: W - 0.7, h: H - 2.1,
    valign: "top",
    margin: [0.15, 0.1, 0.1, 0.1],
  });
}

// Encouraging footer line
ss.addText(
  "Questions? Talk with your doctor, family member, or community coordinator.",
  {
    x: 0.5, y: H - 0.46, w: W - 0.7, h: 0.35,
    fontSize: 12, fontFace: FONT, italic: true,
    color: "6B8FAF", align: "left", margin: 0,
  }
);

if (summarySlide && summarySlide.speaker_notes) {
  ss.addNotes(summarySlide.speaker_notes);
}

// ── Write file ────────────────────────────────────────────────────────────────
pres
  .writeFile({ fileName: outputPath })
  .then(() => {
    console.log(`Saved: ${outputPath}`);
  })
  .catch(err => {
    console.error("Error writing PPTX:", err);
    process.exit(1);
  });
