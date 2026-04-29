#!/usr/bin/env python3
"""
SilverSlide Agent — CLI entry point

Creates senior-friendly PowerPoint presentations from a simple topic prompt.

Examples
--------
  python main.py "How to avoid phone scams"
  python main.py "What is blood pressure?" --slides 5 --tone "warm and simple"
  python main.py "Safe Internet Use" --audience "first-time smartphone users"
  python main.py "Understanding Medicare" --no-video --output medicare_deck.pptx
"""

import argparse
import sys

from silverslide.agent import SilverSlideAgent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SilverSlide Agent — Senior-friendly presentation generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("topic", help="Presentation topic (use quotes for multi-word topics)")
    parser.add_argument("--objective", help="Learning goal for the audience")
    parser.add_argument(
        "--audience",
        default="general seniors",
        help="Audience description, e.g. 'first-time smartphone users' (default: general seniors)",
    )
    parser.add_argument(
        "--tone",
        default="calm and reassuring",
        help="Presentation tone (default: 'calm and reassuring')",
    )
    parser.add_argument(
        "--slides",
        type=int,
        default=5,
        choices=range(3, 8),
        metavar="{3-7}",
        help="Number of slides to generate, 3–7 (default: 5)",
    )
    parser.add_argument("--output", "-o", help="Output .pptx filename (default: auto-generated)")
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip video search and video slide",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print debug details during generation",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  SilverSlide Agent  —  Senior-Friendly Presentations")
    print("=" * 60)

    agent = SilverSlideAgent(verbose=args.verbose)

    try:
        result = agent.create_deck(
            topic=args.topic,
            objective=args.objective,
            audience=args.audience,
            tone=args.tone,
            slide_count=args.slides,
            include_video=not args.no_video,
            output_path=args.output,
        )
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # ── Results summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)
    print(f"  File   : {result['output_path']}")
    print(f"  Title  : {result['title']}")
    print(f"  Slides : {result['slide_count']}")

    if result["video_included"]:
        print(f"  Video  : {result['video_title']}  ({result['video_duration']})")
        print(f"           {result['video_url']}")
    else:
        print("  Video  : not included")

    qa = result["qa_report"]
    if qa["passed"] and not qa["warnings"]:
        print("  QA     : PASS — ready to present")
    elif qa["passed"]:
        print(f"  QA     : PASS with {len(qa['warnings'])} note(s)")
    else:
        print(f"  QA     : {len(qa['issues'])} issue(s), {len(qa['warnings'])} note(s)")

    if result["review_required"]:
        print(f"\n  *** REVIEW RECOMMENDED ***")
        if result["review_reason"]:
            print(f"  Reason : {result['review_reason']}")
        print("  This deck covers a sensitive topic — have a qualified")
        print("  professional check accuracy before presenting.")

    if qa["issues"]:
        print("\n  Issues to fix:")
        for issue in qa["issues"]:
            print(f"    - {issue}")

    if qa["warnings"]:
        print("\n  Notes:")
        for w in qa["warnings"][:5]:
            print(f"    • {w}")
        if len(qa["warnings"]) > 5:
            print(f"    ... and {len(qa['warnings']) - 5} more")

    if result.get("source_notes"):
        print(f"\n  Source: {result['source_notes']}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
