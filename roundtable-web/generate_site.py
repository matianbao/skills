#!/usr/bin/env python3
"""Generate a static HTML site from roundtable meeting Markdown files.

Usage:
    python3 generate_site.py [--output-dir /path/to/output] [--force]
"""

import argparse
import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import markdown
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from xml.etree.ElementTree import Element

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import load_user_config

SKILL_DIR = Path(__file__).resolve().parent

# Expert emoji mapping
EXPERT_EMOJIS = {
    "elon-musk": "🚀", "munger": "📚", "taleb": "🦢", "feynman": "🔬",
    "paul-graham": "✍️", "naval": "🧘", "steve-jobs": "🍎",
    "zhang-yiming": "📱", "zhangxuefeng": "🎓", "andrej-karpathy": "🧠",
    "ilya-sutskever": "🤖", "mrbeast": "🎬", "trump": "🏛️",
    "sun-yuchen": "💰",
}

EXPERT_COLORS = [
    "#58a6ff", "#f85149", "#3fb950", "#d29922",
    "#bc8cff", "#f778ba", "#79c0ff", "#ffa657",
]


def _roundtable_dir() -> Path:
    config = load_user_config()
    vault = Path(config["paths"]["obsidian_vault"])
    rt_config = config.get("roundtable", {})
    folder = rt_config.get("save_dir", "Roundtable")
    return vault / folder


# ── Markdown processing ──────────────────────────────────────────────────────

class WikilinkPreprocessor(Preprocessor):
    WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')

    def run(self, lines):
        return [self.WIKILINK_RE.sub(
            lambda m: f'<span class="wikilink">{html.escape(m.group(1).split("|")[-1])}</span>',
            line,
        ) for line in lines]


class SpeakerBlockPreprocessor(Preprocessor):
    """Convert #### {emoji} {name} headings into styled speaker blocks."""
    SPEAKER_RE = re.compile(r'^####\s+(.+?)\s*$')
    FRAMEWORK_RE = re.compile(r'^>\s*📌\s*运用框架:\s*(.+)$')

    def run(self, lines):
        out = []
        in_speaker = False
        for line in lines:
            fm = self.FRAMEWORK_RE.match(line.strip())
            if fm:
                out.append(f'<div class="framework-tag">📌 {html.escape(fm.group(1))}</div>')
                continue
            m = self.SPEAKER_RE.match(line.strip())
            if m:
                if in_speaker:
                    out.append('</div></div>')
                in_speaker = True
                speaker = m.group(1)
                out.append(f'<div class="speaker-block" data-speaker="{html.escape(speaker)}">')
                out.append(f'<div class="speaker-name">{html.escape(speaker)}</div>')
                out.append('<div class="speaker-content">')
                continue
            out.append(line)
        if in_speaker:
            out.append('</div></div>')
        return out


class RoundtableExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(WikilinkPreprocessor(md), 'wikilinks', 30)
        md.preprocessors.register(SpeakerBlockPreprocessor(md), 'speakers', 29)


def md_to_html(text: str) -> str:
    md = markdown.Markdown(
        extensions=['tables', 'fenced_code', RoundtableExtension()]
    )
    return md.convert(text)


# ── Content parsing ──────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            body = text[end + 3:].strip()
            meta = {}
            # Simple YAML-like parsing
            current_key = None
            current_list = None
            for line in fm_text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- ") and current_list is not None:
                    # List item - parse as dict if has key:value pairs
                    item_text = stripped[2:].strip()
                    if ":" in item_text and current_key == "participants":
                        item = {}
                        for pair in re.findall(r'(\w+):\s*([^,]+)', item_text):
                            item[pair[0]] = pair[1].strip()
                        current_list.append(item)
                    else:
                        current_list.append(item_text)
                elif ":" in stripped and not stripped.startswith("-"):
                    key, val = stripped.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    current_key = key
                    if val:
                        meta[key] = val
                        current_list = None
                    else:
                        current_list = []
                        meta[key] = current_list
            return meta, body
    return {}, text


def extract_participants(body: str) -> list:
    """Extract participant names from the meeting markdown."""
    participants = []
    in_table = False
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## 参会专家"):
            in_table = True
            continue
        if in_table and stripped.startswith("|") and "---" not in stripped:
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if cells and cells[0] and "专家" not in cells[0]:
                participants.append(cells[0])
        elif in_table and stripped.startswith("##"):
            break
        # Also try list format: - {emoji} {name} — ...
        m = re.match(r'^[-*]\s+(.+?)\s*[—–-]\s*(.+)$', stripped)
        if m and in_table:
            participants.append(m.group(1))
    return participants


def extract_rounds(body: str) -> int:
    """Count the number of discussion rounds."""
    return len(re.findall(r'^###\s+第.+轮', body, re.MULTILINE))


def extract_summary_section(body: str) -> str:
    """Extract the meeting summary section."""
    m = re.search(r'^##\s+会议纪要\s*\n(.*)', body, re.MULTILINE | re.DOTALL)
    if m:
        # Take everything until the next ## or end
        text = m.group(1)
        end = re.search(r'^##\s+', text, re.MULTILINE)
        if end:
            text = text[:end.start()]
        return text.strip()
    return ""


def extract_topic(meta: dict, body: str) -> str:
    """Get topic from frontmatter or first heading."""
    if meta.get("topic"):
        return meta["topic"]
    m = re.search(r'^#\s+圆桌会议:\s*(.+)$', body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return "未命名会议"


# ── HTML building ────────────────────────────────────────────────────────────

def _build_detail_html(body: str) -> str:
    """Convert meeting body to styled HTML with speaker blocks."""
    return md_to_html(body)


def _page_html(title: str, body: str, nav_html: str = "",
               js_files: list = None, is_detail: bool = False,
               extra_head: str = "") -> str:
    js_tags = "\n".join(f'<script src="{f}"></script>' for f in (js_files or []))
    width_override = "<style>body{max-width:960px;}</style>" if is_detail else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="style.css">
{width_override}
{extra_head}
</head>
<body>
{nav_html}
{body}
<footer style="text-align:center;color:var(--text2);margin:3em 0 1em;font-size:0.85em;">
  Generated by roundtable-web &middot; Powered by Claude Code
</footer>
{js_tags}
</body>
</html>"""


# ── Site generator ───────────────────────────────────────────────────────────

def _needs_rebuild(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def _slugify(text: str) -> str:
    """Create a URL-safe slug from text."""
    text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    return text[:60]


def generate_site(output_dir: Path, force: bool = False):
    rt_dir = _roundtable_dir()
    md_files = sorted(rt_dir.glob("*.md"), reverse=True)

    if not md_files:
        print("No roundtable meeting files found.", file=sys.stderr)
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy static assets
    for asset in ["style.css", "roundtable.js"]:
        src = SKILL_DIR / asset
        dst = output_dir / asset
        if src.exists() and (force or _needs_rebuild(src, dst)):
            shutil.copy2(src, dst)

    # Collect metadata for all meetings
    meetings = []
    rebuilt = 0
    skipped = 0

    for f in md_files:
        text = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        date_str = meta.get("date", "")
        if not date_str:
            m = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
            date_str = m.group(1) if m else ""

        topic = extract_topic(meta, body)
        participants = extract_participants(body)
        rounds = extract_rounds(body)
        summary = extract_summary_section(body)

        slug = f.stem  # Use filename as slug

        meetings.append({
            "date": date_str,
            "topic": topic,
            "participants": participants,
            "rounds": rounds,
            "summary": summary,
            "slug": slug,
            "body": body,
            "src_path": f,
        })

    # Generate detail pages
    for i, meeting in enumerate(meetings):
        detail_path = output_dir / f'{meeting["slug"]}.html'

        if not force and not _needs_rebuild(meeting["src_path"], detail_path):
            skipped += 1
            continue

        rebuilt += 1

        body_html = _build_detail_html(meeting["body"])

        nav_parts = ['<a href="index.html">🏛️ 首页</a>']
        if i < len(meetings) - 1:
            nav_parts.append(f'<a href="{meetings[i + 1]["slug"]}.html">← 上一场</a>')
        if i > 0:
            nav_parts.append(f'<a href="{meetings[i - 1]["slug"]}.html">下一场 →</a>')
        nav_html = f'<nav class="nav">{"".join(nav_parts)}</nav>'

        # Participant badges
        badges = " ".join(
            f'<span class="expert-badge">{html.escape(p)}</span>'
            for p in meeting["participants"]
        )
        header = f"""
<div class="meeting-hero">
  <div class="meeting-date">{html.escape(meeting["date"])}</div>
  <h1>{html.escape(meeting["topic"])}</h1>
  <div class="meeting-meta">{badges} · {meeting["rounds"]} 轮讨论</div>
</div>
"""
        page = _page_html(
            f'圆桌: {meeting["topic"]}',
            header + f'<div class="meeting-body">{body_html}</div>',
            nav_html,
            is_detail=True,
        )
        detail_path.write_text(page, encoding="utf-8")

    # Generate index page
    # Expert statistics
    expert_counts = {}
    for m in meetings:
        for p in m["participants"]:
            expert_counts[p] = expert_counts.get(p, 0) + 1
    sorted_experts = sorted(expert_counts.items(), key=lambda x: -x[1])

    meetings_json = []
    for m in meetings:
        try:
            dt = datetime.strptime(m["date"], "%Y-%m-%d")
            weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
        except ValueError:
            weekday = ""
        meetings_json.append({
            "date": m["date"],
            "weekday": weekday,
            "topic": m["topic"],
            "participants": m["participants"],
            "rounds": m["rounds"],
            "slug": m["slug"],
        })

    data_script = f"<script>const MEETINGS_DATA = {json.dumps(meetings_json, ensure_ascii=False)};</script>"

    # Expert stats HTML
    max_count = sorted_experts[0][1] if sorted_experts else 1
    expert_stats = ""
    for name, count in sorted_experts:
        pct = round(count / max_count * 100)
        expert_stats += f"""<div class="expert-row">
  <span class="expert-label">{html.escape(name)}</span>
  <div class="expert-bar-bg"><div class="expert-bar" style="width:{pct}%"></div></div>
  <span class="expert-count">{count}</span>
</div>"""

    # Meeting list HTML
    meeting_list = ""
    for m in meetings:
        badges = " ".join(
            f'<span class="expert-badge-sm">{html.escape(p)}</span>'
            for p in m["participants"][:4]
        )
        extra = f'+{len(m["participants"]) - 4}' if len(m["participants"]) > 4 else ''
        meeting_list += f"""<a class="meeting-card" href="{m["slug"]}.html">
  <div class="mc-date">{html.escape(m["date"])}</div>
  <div class="mc-topic">{html.escape(m["topic"])}</div>
  <div class="mc-meta">{badges}{extra} · {m["rounds"]}轮</div>
</a>"""

    index_body = f"""
<div class="header">
  <h1>🏛️ 圆桌会议记录</h1>
  <p>共 {len(meetings)} 场会议</p>
</div>
<div class="dashboard">
  <div class="sidebar">
    <div class="panel">
      <h3>👥 专家出席统计</h3>
      {expert_stats}
    </div>
  </div>
  <div class="main-content">
    <div class="meeting-list">
      {meeting_list}
    </div>
  </div>
</div>
"""

    index_page = _page_html(
        "圆桌会议记录",
        index_body,
        js_files=["roundtable.js"],
        extra_head=data_script,
    )
    (output_dir / "index.html").write_text(index_page, encoding="utf-8")

    print(f"Generated: {rebuilt} rebuilt, {skipped} cached, {len(meetings)} total → {output_dir}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate static site for roundtable meetings")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--force", action="store_true", help="Force rebuild all")
    args = parser.parse_args()

    if args.output_dir:
        output = Path(args.output_dir)
    else:
        config = load_user_config()
        web_config = config.get("web", {})
        rt_config = config.get("roundtable", {}).get("web", {})
        repo = web_config.get("github_pages_repo", "")
        sub = rt_config.get("output_dir", "roundtable")
        if repo:
            output = Path(repo).expanduser()
            if sub:
                output = output / sub
        else:
            output = _roundtable_dir().parent / "_site" / "roundtable"

    generate_site(output, force=args.force)


if __name__ == "__main__":
    main()
