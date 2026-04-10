#!/usr/bin/env python3
"""filter_papers.py — Filter enriched papers by relevance and trim fields.

Reads enriched JSON, filters by keywords/negative_keywords from config,
and outputs a compact JSON with only fields needed for LLM review.

Usage:
    python3 filter_papers.py
    # reads /tmp/daily_papers_enriched.json → writes /tmp/daily_papers_filtered.json

    python3 filter_papers.py --input /path/to/enriched.json --output /path/to/filtered.json
"""

import argparse
import json
import sys
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import daily_papers_config, temp_file_path

# Fields to keep in the output (everything else is stripped)
KEEP_FIELDS = {
    "title", "authors", "affiliations", "abstract",
    "url", "pdf", "date", "score", "source", "hf_upvotes",
    "figure_url", "figure_urls", "method_names", "method_summary",
}

ABSTRACT_MAX_CHARS = 400
METHOD_NAMES_MAX = 8


def filter_and_trim(papers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Filter papers by relevance and trim fields.

    Returns (kept, excluded) where excluded contains (title, reason) pairs.
    """
    config = daily_papers_config()
    keywords = [kw.lower() for kw in config["keywords"]]
    negative_keywords = [kw.lower() for kw in config["negative_keywords"]]

    kept = []
    excluded = []

    for paper in papers:
        text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()

        # Check negative keywords
        neg_hit = next((kw for kw in negative_keywords if kw in text), None)
        if neg_hit:
            excluded.append({"title": paper.get("title", ""), "reason": f"negative keyword: {neg_hit}"})
            continue

        # Check positive keyword relevance
        has_keyword = any(kw in text for kw in keywords)
        if not has_keyword:
            excluded.append({"title": paper.get("title", ""), "reason": "no keyword match"})
            continue

        # Trim fields
        trimmed = {}
        for field in KEEP_FIELDS:
            if field in paper:
                trimmed[field] = paper[field]

        # Truncate abstract
        abstract = trimmed.get("abstract", "")
        if len(abstract) > ABSTRACT_MAX_CHARS:
            cut = abstract.rfind(". ", ABSTRACT_MAX_CHARS - 100, ABSTRACT_MAX_CHARS + 50)
            if cut > 0:
                trimmed["abstract"] = abstract[:cut + 1]
            else:
                trimmed["abstract"] = abstract[:ABSTRACT_MAX_CHARS] + "..."

        # Limit method_names
        if "method_names" in trimmed and len(trimmed["method_names"]) > METHOD_NAMES_MAX:
            trimmed["method_names"] = trimmed["method_names"][:METHOD_NAMES_MAX]

        kept.append(trimmed)

    # Sort by score descending
    kept.sort(key=lambda x: x.get("score", 0), reverse=True)

    return kept, excluded


def run(papers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Core logic for use by pipeline.py. Returns (kept, excluded)."""
    return filter_and_trim(papers)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", help="Input enriched JSON path")
    parser.add_argument("--output", "-o", help="Output filtered JSON path")
    args = parser.parse_args()

    input_path = args.input or str(temp_file_path("daily_papers_enriched.json"))
    output_path = args.output or str(temp_file_path("daily_papers_filtered.json"))

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            papers = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    kept, excluded = filter_and_trim(papers)

    print(f"[filter] {len(papers)} → {len(kept)} papers (excluded {len(excluded)})", file=sys.stderr)
    for ex in excluded:
        print(f"  ✗ {ex['title'][:60]}... — {ex['reason']}", file=sys.stderr)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    print(f"[filter] Output: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
