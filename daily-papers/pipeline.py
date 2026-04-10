#!/usr/bin/env python3
"""pipeline.py — One-shot: fetch → enrich → filter.

Combines the three steps into a single invocation, outputting compact
filtered JSON ready for LLM review.

Usage:
    python3 pipeline.py                    # today
    python3 pipeline.py --days 3           # past 3 days
    python3 pipeline.py --date 2026-04-07  # specific date

Output: /tmp/daily_papers_filtered.json (compact, <10k tokens)
Also saves enriched data to /tmp/daily_papers_enriched.json for history/notes.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure parent packages are importable
_SKILL_DIR = Path(__file__).resolve().parent
_SHARED_DIR = _SKILL_DIR.parent / "_shared"
for p in (_SKILL_DIR, str(_SHARED_DIR)):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from user_config import temp_file_path


def main():
    parser = argparse.ArgumentParser(description="Daily papers pipeline: fetch → enrich → filter")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=1, help="Number of days to fetch (default: 1)")
    args = parser.parse_args()

    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else None
    )

    # Date string for file naming (avoids parallel runs overwriting each other)
    date_str = str(target_date) if target_date else str(datetime.now().date())

    # ── Step 1: Fetch & score ──
    print("=" * 50, file=sys.stderr)
    print("[pipeline] Step 1/3: Fetching and scoring...", file=sys.stderr)
    from fetch_and_score import run as fetch_run
    top_papers = fetch_run(target_date=target_date, days=args.days)
    print(f"[pipeline] Fetched {len(top_papers)} papers", file=sys.stderr)

    if not top_papers:
        print("[pipeline] No papers found. Exiting.", file=sys.stderr)
        # Write empty output
        output_path = str(temp_file_path(f"daily_papers_{date_str}_filtered.json"))
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    # Save raw scored data
    raw_path = str(temp_file_path(f"daily_papers_{date_str}_top30.json"))
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(top_papers, f, ensure_ascii=False, indent=2)

    # ── Step 2: Enrich ──
    print("=" * 50, file=sys.stderr)
    print("[pipeline] Step 2/3: Enriching with metadata...", file=sys.stderr)
    from enrich_papers import run as enrich_run
    enriched = enrich_run(top_papers)

    # Save enriched data (needed for history update and notes)
    enriched_path = str(temp_file_path(f"daily_papers_{date_str}_enriched.json"))
    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"[pipeline] Enriched data saved to {enriched_path}", file=sys.stderr)

    # ── Step 3: Filter & trim ──
    print("=" * 50, file=sys.stderr)
    print("[pipeline] Step 3/3: Filtering and trimming...", file=sys.stderr)
    from filter_papers import run as filter_run
    kept, excluded = filter_run(enriched)

    # Save filtered output
    output_path = str(temp_file_path(f"daily_papers_{date_str}_filtered.json"))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    print(f"[pipeline] {len(enriched)} → {len(kept)} relevant papers", file=sys.stderr)
    print(f"[pipeline] Output: {output_path}", file=sys.stderr)
    for ex in excluded[:5]:
        print(f"  ✗ {ex['title'][:60]}... — {ex['reason']}", file=sys.stderr)
    if len(excluded) > 5:
        print(f"  ... and {len(excluded) - 5} more excluded", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print(f"[pipeline] Done! Read {output_path} for LLM review.", file=sys.stderr)


if __name__ == "__main__":
    main()
