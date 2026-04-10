#!/usr/bin/env python3
"""build_recommendation.py — Merge filtered papers + LLM reviews → final markdown.

Eliminates LLM markdown generation overhead: the LLM outputs only a compact
reviews JSON, and this script assembles the complete recommendation file
with all metadata (authors, affiliations, links, figures, sources).

Usage:
    python3 build_recommendation.py --date 2026-04-10
    python3 build_recommendation.py  # auto-detect today's date

Reads:
    /tmp/daily_papers_{date}_filtered.json  (paper metadata from pipeline)
    /tmp/daily_papers_{date}_reviews.json   (LLM reviews)

Writes:
    {DAILY_PAPERS_PATH}/{date}-论文推荐.md
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent
_SHARED_DIR = _SKILL_DIR.parent / "_shared"
for p in (str(_SKILL_DIR), str(_SHARED_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from user_config import daily_papers_config, daily_papers_dir, temp_file_path


def format_source(paper: dict) -> str:
    source = paper.get("source", "")
    hf_upvotes = paper.get("hf_upvotes", 0) or 0
    if source == "hf-daily":
        return f"📰 HF Daily，⬆️ {hf_upvotes}"
    elif source == "hf-trending":
        return f"🔥 HF Trending，⬆️ {hf_upvotes}"
    elif source == "arxiv":
        return "📄 arXiv 关键词检索"
    return source


def build_paper_section(paper: dict, review: dict, number: int) -> list[str]:
    """Build markdown lines for a single paper section."""
    lines = []
    title = paper.get("title", "Untitled")
    lines.append(f"### {number}. {title}")

    note_name = review.get("note_name", "")

    # Authors
    authors = paper.get("authors", "")
    if authors:
        lines.append(f"- **作者**: {authors}")

    # Affiliations
    affiliations = paper.get("affiliations", "")
    if affiliations:
        lines.append(f"- **机构**: {affiliations}")

    # Links
    url = paper.get("url", "")
    pdf = paper.get("pdf", "")
    link_parts = []
    if url:
        link_parts.append(f"[arXiv]({url})")
    if pdf:
        link_parts.append(f"[PDF]({pdf})")
    if link_parts:
        lines.append(f"- **链接**: {' | '.join(link_parts)}")

    # Source
    lines.append(f"- **来源**: {format_source(paper)}")

    # Existing note reference
    if note_name:
        lines.append(f"- 📒 **笔记**: [[{note_name}]]")

    # Figures (prefer figure_urls list, fallback to single figure_url)
    figure_urls = paper.get("figure_urls", [])
    if not figure_urls:
        figure_url = paper.get("figure_url", "")
        if figure_url:
            figure_urls = [figure_url]
    if figure_urls:
        lines.append("")
        for fig_url in figure_urls:
            lines.append(f"![]({fig_url})")
            lines.append("")

    lines.append("")

    # Review fields
    core_method = review.get("core_method", "")
    if core_method:
        lines.append(f"- **核心方法**: {core_method}")

    baselines = review.get("baselines", "")
    if baselines:
        lines.append(f"- **对比方法/Baselines**: {baselines}")

    significance = review.get("significance", "")
    if significance:
        lines.append(f"- **借鉴意义**: {significance}")

    review_text = review.get("review", "")
    if review_text:
        lines.append(f"- **锐评**: {review_text}")

    # Read hint (only for papers without existing notes)
    if review.get("show_read_hint") and not note_name:
        lines.append(f"- 💡 **想精读？** 运行：`读一下 {title}`")

    return lines


def build_markdown(papers: list[dict], reviews_data: dict, date_str: str) -> str:
    """Build the complete recommendation markdown."""
    config = daily_papers_config()
    keywords = config.get("keywords", [])[:8]

    lines = []

    # ── Frontmatter ──
    lines.append("---")
    lines.append(f"date: {date_str}")
    kw_str = ", ".join(keywords)
    lines.append(f"keywords: [{kw_str}]")
    lines.append("tags: [daily-papers, auto-generated]")
    lines.append("---")
    lines.append("")

    # ── Header + summary ──
    lines.append("# 🔪 今日锐评")
    lines.append("")
    summary = reviews_data.get("summary", "")
    if summary:
        lines.append(summary)
        lines.append("")

    # ── Triage table ──
    triage = reviews_data.get("triage", {})
    lines.append("## 分流表")
    lines.append("| 等级 | 论文 |")
    lines.append("|------|------|")

    level_map = [
        ("must_read", "🔥 必读"),
        ("worth_reading", "👀 值得看"),
        ("skip", "💤 可跳过"),
    ]
    for key, label in level_map:
        entries = triage.get(key, [])
        if entries:
            content = " · ".join(entries)
            lines.append(f"| {label} | {content} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Group papers by topic ──
    reviews_by_index = {}
    for r in reviews_data.get("reviews", []):
        idx = r.get("paper_index", -1)
        if 0 <= idx < len(papers):
            reviews_by_index[idx] = r

    # Collect topic groups in order of first appearance
    topic_order = []
    topic_papers = {}
    for r in reviews_data.get("reviews", []):
        topic = r.get("topic_group", "其他")
        idx = r.get("paper_index", -1)
        if topic not in topic_papers:
            topic_order.append(topic)
            topic_papers[topic] = []
        if 0 <= idx < len(papers):
            topic_papers[topic].append(idx)

    paper_num = 1
    for topic in topic_order:
        indices = topic_papers.get(topic, [])
        if not indices:
            continue

        lines.append(f"## {topic}")
        lines.append("")

        for idx in indices:
            paper = papers[idx]
            review = reviews_by_index.get(idx, {})
            section = build_paper_section(paper, review, paper_num)
            lines.extend(section)
            lines.append("")
            paper_num += 1

        lines.append("---")
        lines.append("")

    # ── Excluded papers ──
    excluded = reviews_data.get("excluded", [])
    if excluded:
        lines.append("## 被排除的论文")
        lines.append("")
        for ex in excluded:
            if isinstance(ex, dict):
                lines.append(f"- {ex.get('title', '')} — {ex.get('reason', '')}")
            else:
                lines.append(f"- {ex}")
        lines.append("")

    # ── Trend ──
    trend = reviews_data.get("trend", "")
    if trend:
        lines.append(trend)
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build recommendation markdown from reviews")
    parser.add_argument("--date", help="Date string YYYY-MM-DD (default: today)")
    parser.add_argument("--output", "-o", help="Output path (default: vault DailyPapers dir)")
    parser.add_argument("--filtered", help="Path to filtered JSON")
    parser.add_argument("--reviews", help="Path to reviews JSON")
    args = parser.parse_args()

    date_str = args.date or str(datetime.now().date())

    # Auto-detect file paths
    filtered_path = args.filtered or str(temp_file_path(f"daily_papers_{date_str}_filtered.json"))
    reviews_path = args.reviews or str(temp_file_path(f"daily_papers_{date_str}_reviews.json"))

    # Read inputs
    try:
        with open(filtered_path, "r", encoding="utf-8") as f:
            papers = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[build] Error reading filtered papers {filtered_path}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(reviews_path, "r", encoding="utf-8") as f:
            reviews_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[build] Error reading reviews {reviews_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Build markdown
    markdown = build_markdown(papers, reviews_data, date_str)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(daily_papers_dir() / f"{date_str}-论文推荐.md")

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"[build] Generated: {output_path}", file=sys.stderr)
    print(f"[build] {len(papers)} papers, {len(reviews_data.get('reviews', []))} reviews", file=sys.stderr)


if __name__ == "__main__":
    main()
