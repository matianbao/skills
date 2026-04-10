#!/usr/bin/env python3
"""Generate a static HTML site from daily paper recommendation Markdown files.

Usage:
    python3 generate_site.py [--output-dir /path/to/output] [--force]

Changes from v1:
  - Markdown parsing via `markdown` library (replaces hand-written regex parser)
  - CSS/JS loaded from external files (style.css, dashboard.js, tabs.js)
  - Index page uses lazy-loading via fragment files (replaces hidden-div prerender)
  - Incremental build: only regenerates pages whose source changed (use --force to rebuild all)
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
from markdown.treeprocessors import Treeprocessor
from xml.etree.ElementTree import Element

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import daily_papers_dir, load_user_config

SKILL_DIR = Path(__file__).resolve().parent


# ── Paper notes ───────────────────────────────────────────────────────────────

def _notes_dir() -> Path:
    config = load_user_config()
    vault = Path(config["paths"]["obsidian_vault"])
    folder = config["paths"].get("paper_notes_folder", "论文笔记")
    return vault / folder


def _load_notes_map() -> dict:
    notes = {}
    nd = _notes_dir()
    if nd.is_dir():
        for f in nd.glob("**/*.md"):
            notes[f.stem] = f.read_text(encoding="utf-8")
    return notes


# ── Custom markdown extensions ────────────────────────────────────────────────

class WikilinkPreprocessor(Preprocessor):
    """Convert [[link]] and [[display|link]] to HTML spans before markdown parsing."""
    WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')

    def run(self, lines):
        new_lines = []
        for line in lines:
            line = self.WIKILINK_RE.sub(self._replace, line)
            new_lines.append(line)
        return new_lines

    def _replace(self, m):
        content = m.group(1)
        display = content.split('|')[-1] if '|' in content else content
        return f'<span class="wikilink">{html.escape(display)}</span>'


class SkipLinePreprocessor(Preprocessor):
    """Remove lines containing '想精读' (CLI-only, not useful on web)."""
    def run(self, lines):
        return [l for l in lines if '想精读' not in l]


class MathProtectPreprocessor(Preprocessor):
    """Protect LaTeX math from markdown processing by wrapping in special tags."""
    def run(self, lines):
        out = []
        in_math = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("$$") and not in_math:
                if stripped.endswith("$$") and len(stripped) > 4:
                    out.append(f'<div class="math-block">{html.escape(stripped)}</div>')
                    continue
                in_math = True
                out.append(f'<div class="math-block">{html.escape(stripped)}')
                continue
            if in_math:
                if stripped.endswith("$$"):
                    out.append(f'{html.escape(stripped)}</div>')
                    in_math = False
                else:
                    out.append(html.escape(stripped))
                continue
            # Protect inline math $...$ — replace with placeholder
            line = re.sub(r'\$(?!\$)([^\$\n]+?)\$', lambda m: f'<span class="math-inline">{html.escape(m.group(0))}</span>', line)
            out.append(line)
        return out


class PaperNotePreprocessor(Preprocessor):
    """Convert paper note wikilinks to collapsible details sections."""
    NOTE_RE = re.compile(r'^[-*]\s+📒.*笔记.*\[\[([^\]]+)\]\]')

    def __init__(self, md, notes_map):
        super().__init__(md)
        self.notes_map = notes_map or {}

    def run(self, lines):
        out = []
        for line in lines:
            m = self.NOTE_RE.match(line.strip())
            if m and self.notes_map:
                note_name = m.group(1).split('|')[0] if '|' in m.group(1) else m.group(1)
                note_md = self.notes_map.get(note_name)
                if note_md:
                    _, note_body = parse_frontmatter(note_md)
                    note_html = md_to_html(note_body)
                    out.append(
                        f'<details class="paper-note">'
                        f'<summary>\U0001f4d2 精读笔记: {html.escape(note_name)}</summary>'
                        f'<div class="note-body">{note_html}</div>'
                        f'</details>'
                    )
                    continue
            out.append(line)
        return out


class ImageWrapTreeprocessor(Treeprocessor):
    """Wrap standalone images in paper-figure div for centering."""
    def run(self, root):
        for parent in root.iter():
            for i, child in enumerate(list(parent)):
                if child.tag == 'p' and len(child) == 1 and child[0].tag == 'img':
                    img = child[0]
                    src = img.get('src', '')
                    if src and not src.startswith('data:'):
                        div = Element('div')
                        div.set('class', 'paper-figure')
                        img.set('loading', 'lazy')
                        div.append(img)
                        parent[i] = div


class CustomExtension(Extension):
    def __init__(self, notes_map=None, **kwargs):
        self.notes_map = notes_map
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        md.preprocessors.register(MathProtectPreprocessor(md), 'math_protect', 30)
        md.preprocessors.register(SkipLinePreprocessor(md), 'skip_lines', 29)
        md.preprocessors.register(PaperNotePreprocessor(md, self.notes_map), 'paper_notes', 28)
        md.preprocessors.register(WikilinkPreprocessor(md), 'wikilinks', 27)
        md.treeprocessors.register(ImageWrapTreeprocessor(md), 'img_wrap', 15)


def md_to_html(text: str, notes_map: dict = None) -> str:
    """Convert Markdown to HTML using the markdown library with custom extensions."""
    md = markdown.Markdown(
        extensions=['tables', 'fenced_code', CustomExtension(notes_map=notes_map)]
    )
    return md.convert(text)


# ── Content parsing ───────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm = text[3:end].strip()
            body = text[end + 3:].strip()
            date_m = re.search(r'date:\s*(\S+)', fm)
            keywords_m = re.search(r'keywords:\s*(.+)', fm)
            return {
                "date": date_m.group(1) if date_m else "",
                "keywords": keywords_m.group(1) if keywords_m else "",
            }, body
    return {}, text


def extract_summary(body: str) -> str:
    lines = body.split("\n")
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            capture = True
            continue
        if capture and stripped and not stripped.startswith("#") and not stripped.startswith("|") and not stripped.startswith("## "):
            return stripped[:300]
    return ""


def extract_topics(body: str) -> dict:
    skip = {"分流表", "被排除的论文"}
    topics = {}
    current_topic = None
    for line in body.split("\n"):
        m = re.match(r'^##\s+(.+)$', line.strip())
        if m:
            heading = m.group(1).strip()
            if heading not in skip:
                current_topic = heading
                topics[current_topic] = 0
        elif current_topic and re.match(r'^###\s+', line.strip()):
            topics[current_topic] += 1
    return topics


def count_papers_by_tier(body: str) -> dict:
    """Count papers in each tier from the triage table.

    Looks for table rows containing tier names and counts paper references
    (### headings) within the body that match each tier's papers.
    """
    counts = {"必读": 0, "值得看": 0, "可跳过": 0}
    in_table = False
    for line in body.split("\n"):
        stripped = line.strip()
        # Detect table rows
        if stripped.startswith("|") and "|" in stripped[1:]:
            in_table = True
            # Count wikilinks OR plain text entries in tier rows
            for tier in counts:
                if tier in stripped:
                    # Count [[...]] wikilinks
                    wl_count = len(re.findall(r'\[\[', stripped))
                    if wl_count > 0:
                        counts[tier] = wl_count
                    else:
                        # Count comma-separated entries in last cell
                        cells = stripped.split("|")
                        if len(cells) >= 3:
                            content = cells[-2].strip()
                            if content and content != "-":
                                counts[tier] = len([x for x in content.split(",") if x.strip()])
        elif in_table and not stripped.startswith("|"):
            in_table = False
    return counts


def split_sections(body: str) -> tuple:
    lines = body.split("\n")
    preamble_lines = []
    sections = []
    current = None
    skip_titles = {"分流表"}
    epilogue_titles = {"被排除的论文"}

    for line in lines:
        m = re.match(r'^##\s+(.+)$', line.strip())
        if m:
            heading = m.group(1).strip()
            if heading in skip_titles:
                if current:
                    sections.append(current)
                    current = None
                preamble_lines.append(line)
                continue
            if heading in epilogue_titles:
                if current:
                    sections.append(current)
                slug = re.sub(r'[^\w]', '', re.sub(r'\s+', '-', heading.lower()))
                current = {"title": heading, "slug": slug, "md_lines": [line], "is_epilogue": True}
                continue
            if current:
                sections.append(current)
            slug = re.sub(r'[^\w]', '', re.sub(r'\s+', '-', heading.lower()))
            current = {"title": heading, "slug": slug, "md_lines": [line], "is_epilogue": False}
        elif current:
            current["md_lines"].append(line)
        else:
            preamble_lines.append(line)

    if current:
        sections.append(current)

    result_sections = []
    epilogue_md = ""
    for sec in sections:
        md_text = "\n".join(sec["md_lines"])
        paper_count = len(re.findall(r'^###\s+', md_text, re.MULTILINE))
        if sec.get("is_epilogue"):
            epilogue_md = md_text
        else:
            result_sections.append({
                "title": sec["title"],
                "slug": sec["slug"],
                "paper_count": paper_count,
                "md": md_text,
            })

    return "\n".join(preamble_lines), result_sections, epilogue_md


# ── HTML building ─────────────────────────────────────────────────────────────

SECTION_EMOJIS = {
    "框架": "\U0001f3d7", "基础设施": "\U0001f3d7",
    "多模态": "\U0001f3a8", "生成": "\U0001f3a8",
    "评估": "\U0001f4ca", "安全": "\U0001f6e1",
    "记忆": "\U0001f9e0",
    "视觉": "\U0001f441", "3D": "\U0001f441", "VLM": "\U0001f441",
    "LLM": "\U0001f916", "基础": "\U0001f916",
    "推荐": "\U0001f4c8", "对话": "\U0001f4ac", "工具": "\U0001f527",
    "Agent": "\U0001f916", "协作": "\U0001f91d",
}


def _section_emoji(title: str) -> str:
    for keyword, emoji in SECTION_EMOJIS.items():
        if keyword in title:
            return emoji
    return "\U0001f4c4"


def _section_to_cards(sec: dict, notes_map: dict = None) -> str:
    md_text = sec["md"]
    topic = html.escape(sec["title"])
    papers = re.split(r'(?=^###\s+)', md_text, flags=re.MULTILINE)
    result = ""
    for part in papers:
        part = part.strip()
        if not part:
            continue
        if part.startswith("###"):
            result += f'<div class="paper-card" data-topic="{topic}">{md_to_html(part, notes_map)}</div>'
        elif part.startswith("##"):
            result += md_to_html(part, notes_map)
    return result


def _build_tabbed_detail(body: str, notes_map: dict = None) -> str:
    preamble_md, sections, epilogue_md = split_sections(body)

    if not sections:
        return md_to_html(body, notes_map)

    parts = [md_to_html(preamble_md, notes_map)]

    # Tab bar
    total = sum(s["paper_count"] for s in sections)
    tab_bar = '<div class="tab-bar">'
    tab_bar += f'<button class="tab-btn active" data-tab="all" onclick="switchTab(\'all\')">📋 全部<span class="tab-count">{total}</span></button>'
    for sec in sections:
        emoji = _section_emoji(sec["title"])
        tab_bar += f'<button class="tab-btn" data-tab="{sec["slug"]}" onclick="switchTab(\'{sec["slug"]}\')">{emoji} {html.escape(sec["title"])}<span class="tab-count">{sec["paper_count"]}</span></button>'
    tab_bar += '</div>'
    parts.append(tab_bar)

    # "All" panel
    all_html = '<div id="panel-all" class="tab-panel active">'
    for sec in sections:
        all_html += _section_to_cards(sec, notes_map)
    all_html += '</div>'
    parts.append(all_html)

    # Per-section panels
    for sec in sections:
        panel = f'<div id="panel-{sec["slug"]}" class="tab-panel">'
        panel += _section_to_cards(sec, notes_map)
        panel += '</div>'
        parts.append(panel)

    if epilogue_md:
        parts.append('<hr>')
        parts.append(md_to_html(epilogue_md, notes_map))

    return "\n".join(parts)


def _page_html(title: str, body: str, nav_html: str = "",
               js_files: list = None, is_detail: bool = False,
               extra_head: str = "") -> str:
    js_tags = ""
    for f in (js_files or []):
        js_tags += f'<script src="{f}"></script>\n'

    width_override = "<style>body{max-width:960px;}</style>" if is_detail else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}});"></script>
<link rel="stylesheet" href="style.css">
{width_override}
{extra_head}
</head>
<body>
{nav_html}
{body}
<footer style="text-align:center;color:var(--text2);margin:3em 0 1em;font-size:0.85em;">
  Generated by daily-papers-web &middot; Powered by Claude Code
</footer>
{js_tags}
</body>
</html>"""


# ── Site generator ────────────────────────────────────────────────────────────

def _needs_rebuild(src: Path, dst: Path) -> bool:
    """Check if dst needs to be rebuilt based on src modification time."""
    if not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def generate_site(output_dir: Path, force: bool = False):
    dp_dir = daily_papers_dir()
    md_files = sorted(dp_dir.glob("*-论文推荐.md"), reverse=True)

    if not md_files:
        print("No recommendation files found.", file=sys.stderr)
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    frag_dir = output_dir / "fragments"
    frag_dir.mkdir(exist_ok=True)

    # Copy static assets
    for asset in ["style.css", "dashboard.js", "tabs.js"]:
        src = SKILL_DIR / asset
        dst = output_dir / asset
        if src.exists() and (force or _needs_rebuild(src, dst)):
            shutil.copy2(src, dst)

    notes_map = _load_notes_map()

    # Collect metadata for all days
    days = []
    rebuilt = 0
    skipped = 0

    for f in md_files:
        text = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        date_str = meta.get("date", "")
        if not date_str:
            m = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
            date_str = m.group(1) if m else f.stem
        summary = extract_summary(body)
        counts = count_papers_by_tier(body)
        topic_counts = extract_topics(body)

        days.append({
            "date": date_str,
            "filename": f.name,
            "summary": summary,
            "counts": counts,
            "topic_counts": topic_counts,
            "body": body,
            "meta": meta,
            "src_path": f,
        })

    # Generate detail pages + fragment files (incremental)
    for i, day in enumerate(days):
        detail_path = output_dir / f'{day["date"]}.html'
        frag_path = frag_dir / f'{day["date"]}.html'

        if not force and not _needs_rebuild(day["src_path"], detail_path):
            skipped += 1
            continue

        rebuilt += 1

        # Fragment (body content only, for lazy loading on index)
        body_html = _build_tabbed_detail(day["body"], notes_map)
        frag_path.write_text(body_html, encoding="utf-8")

        # Full detail page
        nav_parts = ['<a href="index.html">\U0001f3e0 首页</a>']
        if i < len(days) - 1:
            nav_parts.append(f'<a href="{days[i + 1]["date"]}.html">← 前一天</a>')
        if i > 0:
            nav_parts.append(f'<a href="{days[i - 1]["date"]}.html">后一天 →</a>')
        nav_html = f'<nav class="nav">{"".join(nav_parts)}</nav>'

        page = _page_html(
            f'{day["date"]} 论文推荐',
            f'<div class="detail-page">{body_html}</div>',
            nav_html,
            js_files=["tabs.js"],
            is_detail=True,
        )
        detail_path.write_text(page, encoding="utf-8")

    # Always regenerate index (metadata may have changed)
    days_json = []
    for day in days:
        c = day["counts"]
        try:
            dt = datetime.strptime(day["date"], "%Y-%m-%d")
            weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
        except ValueError:
            weekday = ""
        days_json.append({
            "date": day["date"],
            "weekday": weekday,
            "counts": {"must": c["必读"], "look": c["值得看"], "skip": c["可跳过"]},
            "topicCounts": day["topic_counts"],
        })

    days_data_script = f"<script>const DAYS_DATA = {json.dumps(days_json, ensure_ascii=False)};</script>"

    index_body = f"""
<div class="header">
  <h1>📚 每日论文推荐</h1>
  <p>共 {len(days)} 天记录</p>
</div>
<div class="dashboard">
  <div class="sidebar">
    <div class="panel">
      <div class="cal-header">
        <button onclick="prevMonth()">◀</button>
        <span id="cal-month"></span>
        <button onclick="nextMonth()">▶</button>
      </div>
      <div class="cal-grid" id="cal-grid">
        <div class="cal-dow">一</div><div class="cal-dow">二</div><div class="cal-dow">三</div>
        <div class="cal-dow">四</div><div class="cal-dow">五</div><div class="cal-dow">六</div>
        <div class="cal-dow">日</div>
      </div>
    </div>
    <div class="panel">
      <h3>📊 主题趋势</h3>
      <div id="topic-trends"></div>
    </div>
    <div class="panel">
      <h3>🔥 质量分布</h3>
      <div id="quality-timeline"></div>
    </div>
  </div>
  <div class="main-content" id="main-content">
    <div class="no-data">选择日期查看论文推荐</div>
  </div>
</div>
"""
    index_page = _page_html(
        "每日论文推荐", index_body,
        js_files=["tabs.js", "dashboard.js"],
        extra_head=days_data_script,
    )
    (output_dir / "index.html").write_text(index_page, encoding="utf-8")

    print(f"Generated: {rebuilt} rebuilt, {skipped} cached, {len(days)} total → {output_dir}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate static site for daily papers")
    parser.add_argument("--output-dir", type=str, help="Output directory for HTML files")
    parser.add_argument("--force", action="store_true", help="Force rebuild all pages")
    args = parser.parse_args()

    if args.output_dir:
        output = Path(args.output_dir)
    else:
        config = load_user_config()
        web_config = config.get("web", {})
        repo = web_config.get("github_pages_repo", "")
        sub = web_config.get("output_dir", "")
        if repo:
            output = Path(repo).expanduser()
            if sub:
                output = output / sub
        else:
            output = daily_papers_dir().parent / "_site"

    generate_site(output, force=args.force)


if __name__ == "__main__":
    main()
