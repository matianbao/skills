#!/usr/bin/env python3
"""Generate a static HTML site from daily paper recommendation Markdown files.

Usage:
    python3 generate_site.py [--output-dir /path/to/output]

If --output-dir is not specified, reads from user-config.json web.github_pages_repo.
"""

import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import daily_papers_dir, load_user_config

# ── Paper notes directory ──────────────────────────────────────────────────

def _notes_dir() -> Path:
    """Return the path to paper notes directory."""
    config = load_user_config()
    vault = Path(config["paths"]["obsidian_vault"])
    folder = config["paths"].get("paper_notes_folder", "论文笔记")
    return vault / folder

def _load_notes_map() -> dict:
    """Build a map of note_name → markdown_content for all paper notes."""
    notes = {}
    nd = _notes_dir()
    if nd.is_dir():
        for f in nd.glob("*.md"):
            name = f.stem  # filename without .md
            notes[name] = f.read_text(encoding="utf-8")
    return notes

# ── Markdown → HTML conversion (pure regex, no dependencies) ─────────────────

def _md_to_html(md: str, notes_map: dict = None) -> str:
    """Convert Markdown to HTML using regex. Handles the subset used by daily papers."""
    lines = md.split("\n")
    out = []
    in_table = False
    in_blockquote = False
    in_code = False
    table_rows = []

    def _split_table_row(row: str) -> list:
        """Split a Markdown table row by |, but preserve | inside [[ ]] wikilinks."""
        # Replace | inside [[ ]] with a placeholder
        protected = re.sub(r'\[\[([^\]]*?)\|([^\]]*?)\]\]', lambda m: f'[[{m.group(1)}\x00{m.group(2)}]]', row)
        cells = [c.strip().replace('\x00', '|') for c in protected.strip("|").split("|")]
        return cells

    def flush_table():
        nonlocal table_rows, in_table
        if not table_rows:
            return
        h = '<table class="paper-table">\n'
        for i, row in enumerate(table_rows):
            cells = _split_table_row(row)
            if i == 0:
                h += "<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells) + "</tr></thead>\n<tbody>\n"
            elif all(set(c.strip()) <= set("-: ") for c in cells):
                continue  # separator row
            else:
                h += "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>\n"
        h += "</tbody></table>\n"
        out.append(h)
        table_rows = []
        in_table = False

    for line in lines:
        stripped = line.strip()

        # YAML frontmatter
        if stripped == "---":
            continue

        # Code blocks
        if stripped.startswith("```"):
            in_code = not in_code
            if in_code:
                out.append('<pre><code>')
            else:
                out.append('</code></pre>')
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        # Tables
        if "|" in stripped and stripped.startswith("|"):
            if not in_table:
                flush_table()
                in_table = True
                table_rows = []
            table_rows.append(stripped)
            continue
        elif in_table:
            flush_table()

        # Blockquotes
        if stripped.startswith("> "):
            if not in_blockquote:
                out.append('<blockquote>')
                in_blockquote = True
            out.append(f"<p>{_inline(stripped[2:])}</p>")
            continue
        elif in_blockquote:
            out.append('</blockquote>')
            in_blockquote = False

        # Headers
        m = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if m:
            level = len(m.group(1))
            text = _inline(m.group(2))
            slug = re.sub(r'[^\w\-]', '', re.sub(r'\s+', '-', m.group(2).lower()))
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            continue

        # Horizontal rule
        if stripped == "---":
            out.append("<hr>")
            continue

        # Images
        m = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if m:
            alt, src = m.group(1), m.group(2)
            if src and not src.startswith("data:"):
                out.append(f'<div class="paper-figure"><img src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy"></div>')
            continue

        # List items
        if re.match(r'^[-*]\s', stripped):
            # Skip "想精读" lines — CLI-only, not useful on web
            if '想精读' in stripped:
                continue
            # Embed paper notes as collapsible <details> section
            note_match = re.search(r'📒.*笔记.*\[\[([^\]]+)\]\]', stripped)
            if note_match and notes_map:
                note_name = note_match.group(1)
                # Handle pipe aliases: [[display|name]] or [[name|display]]
                if '|' in note_name:
                    note_name = note_name.split('|')[0]
                note_md = notes_map.get(note_name)
                if note_md:
                    # Strip frontmatter from note
                    _, note_body = parse_frontmatter(note_md)
                    note_html = _md_to_html(note_body)
                    out.append(
                        f'<details class="paper-note">'
                        f'<summary>\U0001f4d2 精读笔记: {html.escape(note_name)}</summary>'
                        f'<div class="note-body">{note_html}</div>'
                        f'</details>'
                    )
                    continue
                else:
                    # Note file not found, render as normal list item
                    content = _inline(stripped[2:])
                    out.append(f"<li>{content}</li>")
                    continue
            content = _inline(stripped[2:])
            out.append(f"<li>{content}</li>")
            continue

        # Empty line
        if not stripped:
            out.append("")
            continue

        # Paragraph
        out.append(f"<p>{_inline(stripped)}</p>")

    if in_table:
        flush_table()
    if in_blockquote:
        out.append('</blockquote>')

    return "\n".join(out)


def _inline(text: str) -> str:
    """Process inline Markdown: bold, italic, code, links, wikilinks, images."""
    # Inline images
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', lambda m: f'<img src="{html.escape(m.group(2))}" alt="{html.escape(m.group(1))}" class="inline-img" loading="lazy">' if not m.group(2).startswith("data:") else "", text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    # Wikilinks → styled span
    text = re.sub(r'\[\[([^\]]+)\]\]', r'<span class="wikilink">\1</span>', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff;
  --fire: #f85149; --green: #3fb950; --yellow: #d29922;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.7;
  max-width: 1600px; margin: 0 auto; padding: 20px 40px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-size: 1.8em; margin: 1em 0 0.5em; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }
h2 { font-size: 1.4em; margin: 1.2em 0 0.4em; color: var(--accent); }
h3 { font-size: 1.15em; margin: 1em 0 0.3em; }
p, li { margin: 0.3em 0; }
li { margin-left: 1.5em; list-style: disc; }
hr { border: none; border-top: 1px solid var(--border); margin: 1.5em 0; }
code { background: var(--surface); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
pre { background: var(--surface); padding: 16px; border-radius: 8px; overflow-x: auto; margin: 1em 0; }
pre code { padding: 0; background: none; }
blockquote { border-left: 3px solid var(--accent); padding: 0.5em 1em;
  margin: 0.8em 0; background: var(--surface); border-radius: 0 8px 8px 0; }
img { max-width: 100%; border-radius: 8px; margin: 0.5em 0; }
.paper-figure { text-align: center; margin: 1em 0; }
.paper-table { width: 100%; border-collapse: collapse; margin: 1em 0; }
.paper-table th, .paper-table td { padding: 8px 12px; border: 1px solid var(--border); text-align: left; }
.paper-table th { background: var(--surface); }
.wikilink { background: var(--surface); padding: 2px 8px; border-radius: 4px;
  border: 1px solid var(--border); font-size: 0.9em; }
.nav { display: flex; gap: 12px; align-items: center; margin-bottom: 1.5em;
  padding: 12px 0; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.nav a { padding: 6px 14px; background: var(--surface); border-radius: 6px;
  border: 1px solid var(--border); font-size: 0.9em; }
.nav a:hover, .nav a.active { background: var(--accent); color: var(--bg); text-decoration: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; margin-right: 4px; }
.badge-fire { background: rgba(248,81,73,0.2); color: var(--fire); }
.badge-look { background: rgba(88,166,255,0.2); color: var(--accent); }
.badge-skip { background: rgba(139,148,158,0.2); color: var(--text2); }
/* ── Tab system ─────────────────────────────────────────── */
.tab-bar { display: flex; gap: 0; margin: 1.5em 0 0; border-bottom: 2px solid var(--border);
  overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
.tab-bar::-webkit-scrollbar { display: none; }
.tab-btn { padding: 10px 20px; background: none; border: none; color: var(--text2);
  font-size: 0.95em; cursor: pointer; white-space: nowrap; position: relative;
  transition: color 0.2s; font-family: inherit; }
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); font-weight: 600; }
.tab-btn.active::after { content: ''; position: absolute; bottom: -2px; left: 0; right: 0;
  height: 2px; background: var(--accent); border-radius: 2px 2px 0 0; }
.tab-btn .tab-count { display: inline-block; background: var(--surface); border: 1px solid var(--border);
  padding: 0 6px; border-radius: 10px; font-size: 0.8em; margin-left: 6px; min-width: 20px; text-align: center; }
.tab-btn.active .tab-count { background: rgba(88,166,255,0.15); border-color: var(--accent); color: var(--accent); }
.tab-panel { display: none; animation: fadeIn 0.25s ease; }
.tab-panel.active { display: block; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
/* ── Paper card ─────────────────────────────────────────── */
.paper-card { background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px; margin: 16px 0; transition: border-color 0.2s; }
.paper-card:hover { border-color: var(--accent); }
.paper-card h3 { margin-top: 0; font-size: 1.1em; }
.paper-card .paper-figure { margin: 12px 0; }
.paper-card .paper-figure img { max-height: 280px; object-fit: contain; }
/* ── Dashboard (index) ──────────────────────────────────── */
.dashboard { display: grid; grid-template-columns: 300px 1fr; gap: 24px; margin-top: 1em; }
.sidebar { display: flex; flex-direction: column; gap: 20px;
  position: sticky; top: 80px; align-self: start; max-height: calc(100vh - 100px); overflow-y: auto; }
.main-content { min-height: 400px; }
.panel { background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px 20px; }
.panel h3 { font-size: 1em; margin: 0 0 12px; color: var(--accent); border: none; }
/* Calendar */
.cal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.cal-header span { font-size: 1em; font-weight: 600; }
.cal-header button { background: none; border: 1px solid var(--border); color: var(--text2);
  border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 0.9em; }
.cal-header button:hover { background: var(--border); color: var(--text); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; text-align: center; }
.cal-dow { font-size: 0.75em; color: var(--text2); padding: 4px 0; font-weight: 600; }
.cal-day { position: relative; padding: 6px 0; font-size: 0.85em; border-radius: 6px;
  cursor: default; color: var(--text2); }
.cal-day.has-data { color: var(--text); cursor: pointer; font-weight: 500; }
.cal-day.has-data:hover { background: var(--border); }
.cal-day.selected { background: var(--accent); color: var(--bg); font-weight: 700; }
.cal-day .cal-dot { position: absolute; bottom: 2px; left: 50%; transform: translateX(-50%);
  width: 5px; height: 5px; border-radius: 50%; }
.cal-dot.fire { background: var(--fire); }
.cal-dot.look { background: var(--accent); }
/* Trends */
.trend-row { display: flex; align-items: center; gap: 8px; margin: 6px 0; font-size: 0.85em; }
.trend-label { width: 90px; text-align: right; color: var(--text2); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; cursor: pointer; position: relative; }
.trend-label:hover { overflow: visible; z-index: 10; }
.trend-label:hover::after { content: attr(data-full); position: absolute; right: 0; top: -28px;
  background: var(--surface); border: 1px solid var(--border); padding: 4px 10px;
  border-radius: 6px; white-space: nowrap; font-size: 0.85em; color: var(--text);
  box-shadow: 0 4px 12px rgba(0,0,0,0.4); z-index: 20; }
.trend-bar-bg { flex: 1; height: 16px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.trend-bar { height: 100%; border-radius: 4px; transition: width 0.4s ease; min-width: 2px; }
.trend-bar.fire { background: var(--fire); }
.trend-bar.accent { background: var(--accent); }
.trend-bar.green { background: var(--green); }
.trend-count { width: 24px; font-size: 0.8em; color: var(--text2); }
/* Quality timeline */
.qt-row { display: flex; align-items: center; gap: 6px; margin: 4px 0; font-size: 0.8em; cursor: pointer; }
.qt-row:hover { opacity: 0.8; }
.qt-row.selected { font-weight: 700; }
.qt-date { width: 50px; color: var(--text2); text-align: right; flex-shrink: 0; }
.qt-dots { display: flex; gap: 3px; }
.qt-dot { width: 10px; height: 10px; border-radius: 50%; }
.qt-dot.fire { background: var(--fire); }
.qt-dot.look { background: var(--accent); }
.qt-dot.skip { background: var(--border); }
/* Day detail in main area */
.day-hero { margin-bottom: 20px; }
.day-hero h2 { font-size: 1.5em; margin: 0 0 8px; color: var(--text); border: none; }
.day-hero .badges { margin: 8px 0; }
.day-hero .summary { color: var(--text2); font-size: 0.95em; line-height: 1.6; margin: 12px 0; }
.day-topics { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.topic-chip { background: var(--surface); border: 1px solid var(--border);
  padding: 4px 12px; border-radius: 20px; font-size: 0.8em; color: var(--text2); }
.view-detail { display: inline-block; margin-top: 16px; padding: 10px 24px;
  background: var(--accent); color: var(--bg); border-radius: 8px;
  font-weight: 600; font-size: 0.95em; }
.view-detail:hover { text-decoration: none; opacity: 0.9; }
.no-data { color: var(--text2); text-align: center; padding: 60px 20px; font-size: 1.1em; }
/* ── Collapsible notes ──────────────────────────────────── */
details.paper-note { margin: 12px 0; border: 1px solid var(--border); border-radius: 8px;
  background: var(--surface); }
details.paper-note summary { padding: 10px 16px; cursor: pointer; font-weight: 600;
  font-size: 0.95em; color: var(--accent); list-style: none; display: flex; align-items: center; gap: 8px; }
details.paper-note summary::-webkit-details-marker { display: none; }
details.paper-note summary::before { content: '▶'; font-size: 0.7em; transition: transform 0.2s; }
details.paper-note[open] summary::before { transform: rotate(90deg); }
details.paper-note .note-body { padding: 0 20px 16px; border-top: 1px solid var(--border);
  max-height: 600px; overflow-y: auto; }
details.paper-note .note-body h1 { display: none; }
details.paper-note .note-body h2 { font-size: 1.1em; margin: 1em 0 0.3em; }
details.paper-note .note-body h3 { font-size: 1em; }
.day-card { background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 20px; margin: 12px 0; transition: border-color 0.2s; }
.day-card:hover { border-color: var(--accent); }
.day-card h3 { margin-top: 0; }
.day-card .meta { color: var(--text2); font-size: 0.9em; margin-bottom: 0.5em; }
.day-card .summary { color: var(--text); }
.header { text-align: center; margin: 0; padding: 12px 0;
  position: sticky; top: 0; z-index: 100; background: var(--bg);
  border-bottom: 1px solid var(--border); }
.header h1 { border: none; font-size: 2em; margin: 0; }
.header p { color: var(--text2); }
@media (max-width: 768px) {
  .dashboard { grid-template-columns: 1fr; }
  .sidebar { order: 2; }
  .main-content { order: 1; }
  body { max-width: 100%; padding: 12px; }
  h1 { font-size: 1.4em; }
  .tab-btn { padding: 8px 14px; font-size: 0.85em; }
  .paper-card { padding: 14px 16px; }
}
"""

DASHBOARD_JS = """
<script>
var curYear, curMonth;
function pad(n){ return n<10?'0'+n:''+n; }
function renderCalendar(y,m){
  curYear=y; curMonth=m;
  var el=document.getElementById('cal-grid');
  document.getElementById('cal-month').textContent=y+'-'+pad(m);
  var first=new Date(y,m-1,1), last=new Date(y,m,0);
  var startDow=(first.getDay()+6)%7;
  var html='';
  for(var i=0;i<startDow;i++) html+='<div class="cal-day"></div>';
  var dateSet={};
  DAYS_DATA.forEach(function(d){ dateSet[d.date]=d; });
  for(var d=1;d<=last.getDate();d++){
    var ds=y+'-'+pad(m)+'-'+pad(d);
    var day=dateSet[ds];
    var cls='cal-day';
    if(day) cls+=' has-data';
    var sel=document.getElementById('main-content');
    if(sel && sel.dataset.date===ds) cls+=' selected';
    var dot='';
    if(day && day.counts.must>0) dot='<span class="cal-dot fire"></span>';
    else if(day && day.counts.look>0) dot='<span class="cal-dot look"></span>';
    var click=day?'onclick="selectDate(\\''+ds+'\\')"':'';
    html+='<div class="'+cls+'" '+click+'>'+d+dot+'</div>';
  }
  el.innerHTML=html;
}
function prevMonth(){ curMonth--; if(curMonth<1){curMonth=12;curYear--;} renderCalendar(curYear,curMonth); }
function nextMonth(){ curMonth++; if(curMonth>12){curMonth=1;curYear++;} renderCalendar(curYear,curMonth); }
function selectDate(ds){
  var day=null;
  DAYS_DATA.forEach(function(d){ if(d.date===ds) day=d; });
  var el=document.getElementById('main-content');
  if(!day){ el.innerHTML='<div class="no-data">该日期无推荐数据</div>'; return; }
  el.dataset.date=ds;
  // Show full content from hidden div
  var content=document.getElementById('content-'+ds);
  if(content){
    el.innerHTML='<div class="day-hero"><h2>'+ds+' '+day.weekday+'</h2></div>'+content.innerHTML;
    // Fix duplicate IDs: prefix all panel/tab IDs inside main-content
    el.querySelectorAll('[id^="panel-"]').forEach(function(p){
      p.id='mc-'+p.id;
    });
    el.querySelectorAll('.tab-btn[data-tab]').forEach(function(b){
      var tab=b.getAttribute('data-tab');
      b.setAttribute('onclick',"switchTabIn('mc-panel-"+tab+"','main-content')");
    });
    // Show the "all" panel by default
    var allPanel=el.querySelector('[id="mc-panel-all"]');
    if(allPanel) allPanel.classList.add('active');
    var allBtn=el.querySelector('.tab-btn[data-tab="all"]');
    if(allBtn) allBtn.classList.add('active');
  } else {
    el.innerHTML='<div class="no-data">该日期无推荐数据</div>';
  }
  // update calendar selection
  var parts=ds.split('-');
  var sy=parseInt(parts[0]),sm=parseInt(parts[1]);
  if(sy!==curYear||sm!==curMonth) renderCalendar(sy,sm);
  else{
    document.querySelectorAll('.cal-day').forEach(function(d){d.classList.remove('selected');});
    document.querySelectorAll('.cal-day.has-data').forEach(function(d){
      if(d.textContent.trim()===''+parseInt(parts[2])) d.classList.add('selected');
    });
  }
  // update quality timeline selection
  document.querySelectorAll('.qt-row').forEach(function(r){
    r.classList.toggle('selected',r.dataset.date===ds);
  });
  history.replaceState(null,'','#'+ds);
}
function switchTabIn(panelId, containerId){
  var container=document.getElementById(containerId);
  container.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
  container.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
  var panel=document.getElementById(panelId);
  if(panel) panel.classList.add('active');
  // activate the corresponding button
  var tabName=panelId.replace('mc-panel-','');
  container.querySelectorAll('.tab-btn').forEach(function(b){
    if(b.getAttribute('data-tab')===tabName) b.classList.add('active');
  });
}
function renderTrends(){
  var agg={};
  DAYS_DATA.forEach(function(d){
    if(!d.topicCounts) return;
    Object.keys(d.topicCounts).forEach(function(k){
      agg[k]=(agg[k]||0)+d.topicCounts[k];
    });
  });
  var sorted=Object.entries(agg).sort(function(a,b){return b[1]-a[1];}).slice(0,8);
  var max=sorted.length?sorted[0][1]:1;
  var el=document.getElementById('topic-trends');
  var html='';
  sorted.forEach(function(e){
    var pct=Math.round(e[1]/max*100);
    html+='<div class="trend-row">'+
      '<span class="trend-label" data-full="'+e[0]+'" title="'+e[0]+'">'+e[0]+'</span>'+
      '<div class="trend-bar-bg"><div class="trend-bar accent" style="width:'+pct+'%"></div></div>'+
      '<span class="trend-count">'+e[1]+'</span></div>';
  });
  el.innerHTML=html;
}
function renderQuality(){
  var el=document.getElementById('quality-timeline');
  var html='';
  DAYS_DATA.forEach(function(d){
    var short=d.date.slice(5);
    var dots='';
    for(var i=0;i<d.counts.must;i++) dots+='<span class="qt-dot fire"></span>';
    for(var i=0;i<d.counts.look;i++) dots+='<span class="qt-dot look"></span>';
    for(var i=0;i<d.counts.skip;i++) dots+='<span class="qt-dot skip"></span>';
    html+='<div class="qt-row" data-date="'+d.date+'" onclick="selectDate(\\''+d.date+'\\')">'
      +'<span class="qt-date">'+short+'</span>'
      +'<div class="qt-dots">'+dots+'</div></div>';
  });
  el.innerHTML=html;
}
document.addEventListener('DOMContentLoaded',function(){
  renderTrends();
  renderQuality();
  var hash=location.hash.slice(1);
  var initDate=hash||DAYS_DATA[0].date;
  var parts=initDate.split('-');
  renderCalendar(parseInt(parts[0]),parseInt(parts[1]));
  selectDate(initDate);
});
</script>
"""

TAB_JS = """
<script>
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelector('[data-tab="'+tabId+'"]').classList.add('active');
  document.getElementById('panel-'+tabId).classList.add('active');
  history.replaceState(null,'','#'+tabId);
}
document.addEventListener('DOMContentLoaded', function() {
  var hash = location.hash.slice(1);
  var target = hash && document.querySelector('[data-tab="'+hash+'"]');
  if (target) switchTab(hash);
});
</script>
"""

# ── Page templates ───────────────────────────────────────────────────────────

def _page_html(title: str, body: str, nav_html: str = "", include_tabs_js: bool = False,
               include_dashboard_js: bool = False, extra_head: str = "") -> str:
    js = ""
    if include_tabs_js:
        js += TAB_JS
    if include_dashboard_js:
        js += DASHBOARD_JS
    # Detail pages use narrower max-width
    style_override = ""
    if not include_dashboard_js:
        style_override = "<style>body{max-width:960px;}</style>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
{style_override}
{extra_head}
</head>
<body>
{nav_html}
{body}
<footer style="text-align:center;color:var(--text2);margin:3em 0 1em;font-size:0.85em;">
  Generated by daily-papers-web · Powered by Claude Code
</footer>
{js}
</body>
</html>"""


# ── Site generator ───────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple:
    """Extract YAML frontmatter and body."""
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
    """Extract first paragraph after the main heading as summary."""
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
    """Extract topic sections and count papers in each."""
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
    """Count papers in each tier from the triage table."""
    counts = {"必读": 0, "值得看": 0, "可跳过": 0}
    for line in body.split("\n"):
        if "必读" in line:
            counts["必读"] = len(re.findall(r'\[\[', line))
        elif "值得看" in line:
            counts["值得看"] = len(re.findall(r'\[\[', line))
        elif "可跳过" in line:
            counts["可跳过"] = len(re.findall(r'\[\[', line))
    return counts


def split_sections(body: str) -> tuple:
    """Split body into preamble (before first ## section with papers) and sections.

    Returns (preamble_md, sections) where sections is a list of
    {"title": str, "slug": str, "paper_count": int, "md": str}.
    Sections named '分流表' or '被排除的论文' are kept in preamble/epilogue.
    """
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
                # Part of preamble
                if current:
                    sections.append(current)
                    current = None
                preamble_lines.append(line)
                continue
            if heading in epilogue_titles:
                # Epilogue section — store as a special section
                if current:
                    sections.append(current)
                slug = re.sub(r'[^\w]', '', re.sub(r'\s+', '-', heading.lower()))
                current = {"title": heading, "slug": slug, "md_lines": [line], "is_epilogue": True}
                continue
            # Regular paper section
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

    # Finalize sections
    result_sections = []
    epilogue_md = ""
    for sec in sections:
        md = "\n".join(sec["md_lines"])
        paper_count = len(re.findall(r'^###\s+', md, re.MULTILINE))
        if sec.get("is_epilogue"):
            epilogue_md = md
        else:
            result_sections.append({
                "title": sec["title"],
                "slug": sec["slug"],
                "paper_count": paper_count,
                "md": md,
            })

    preamble_md = "\n".join(preamble_lines)
    return preamble_md, result_sections, epilogue_md


def _build_tabbed_detail(body: str, notes_map: dict = None) -> str:
    """Build HTML with tab navigation for a detail page body."""
    preamble_md, sections, epilogue_md = split_sections(body)

    if not sections:
        # No sections found, fall back to plain rendering
        return _md_to_html(body, notes_map)

    # Preamble (锐评 + 分流表) — always visible
    parts = [_md_to_html(preamble_md, notes_map)]

    # Build tab bar
    tab_bar = '<div class="tab-bar">'
    tab_bar += f'<button class="tab-btn active" data-tab="all" onclick="switchTab(\'all\')">📋 全部<span class="tab-count">{sum(s["paper_count"] for s in sections)}</span></button>'
    for sec in sections:
        emoji = _section_emoji(sec["title"])
        tab_bar += f'<button class="tab-btn" data-tab="{sec["slug"]}" onclick="switchTab(\'{sec["slug"]}\')">{emoji} {html.escape(sec["title"])}<span class="tab-count">{sec["paper_count"]}</span></button>'
    tab_bar += '</div>'
    parts.append(tab_bar)

    # "All" panel — all sections combined
    all_html = '<div id="panel-all" class="tab-panel active">'
    for sec in sections:
        all_html += _section_to_cards(sec, notes_map)
    all_html += '</div>'
    parts.append(all_html)

    # Individual section panels
    for sec in sections:
        panel_html = f'<div id="panel-{sec["slug"]}" class="tab-panel">'
        panel_html += _section_to_cards(sec, notes_map)
        panel_html += '</div>'
        parts.append(panel_html)

    # Epilogue (被排除的论文)
    if epilogue_md:
        parts.append('<hr>')
        parts.append(_md_to_html(epilogue_md, notes_map))

    return "\n".join(parts)


def _section_emoji(title: str) -> str:
    """Pick an emoji for a section based on its title."""
    mapping = {
        "框架": "\U0001f3d7", "基础设施": "\U0001f3d7",
        "多模态": "\U0001f3a8", "生成": "\U0001f3a8",
        "评估": "\U0001f4ca", "安全": "\U0001f6e1",
        "记忆": "\U0001f9e0",
        "视觉": "\U0001f441", "3D": "\U0001f441", "VLM": "\U0001f441",
        "LLM": "\U0001f916", "基础": "\U0001f916",
        "推荐": "\U0001f4c8", "对话": "\U0001f4ac", "工具": "\U0001f527",
        "Agent": "\U0001f916", "协作": "\U0001f91d",
    }
    for keyword, emoji in mapping.items():
        if keyword in title:
            return emoji
    return "\U0001f4c4"


def _section_to_cards(sec: dict, notes_map: dict = None) -> str:
    """Convert a section's markdown to paper cards HTML."""
    md = sec["md"]
    # Split by ### headers (papers)
    papers = re.split(r'(?=^###\s+)', md, flags=re.MULTILINE)
    result = ""
    for part in papers:
        part = part.strip()
        if not part:
            continue
        if part.startswith("###"):
            result += f'<div class="paper-card">{_md_to_html(part, notes_map)}</div>'
        elif part.startswith("##"):
            # Section header — render but skip wrapping in card
            result += _md_to_html(part, notes_map)
    return result


def generate_site(output_dir: Path):
    """Generate the full static site."""
    dp_dir = daily_papers_dir()
    md_files = sorted(dp_dir.glob("*-论文推荐.md"), reverse=True)

    if not md_files:
        print("No recommendation files found.", file=sys.stderr)
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load paper notes for embedding
    notes_map = _load_notes_map()

    # Collect all days
    days = []
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
        })

    # Generate detail pages
    for i, day in enumerate(days):
        nav_parts = ['<a href="index.html">🏠 首页</a>']
        if i < len(days) - 1:
            nav_parts.append(f'<a href="{days[i + 1]["date"]}.html">← 前一天</a>')
        if i > 0:
            nav_parts.append(f'<a href="{days[i - 1]["date"]}.html">后一天 →</a>')
        nav_html = f'<nav class="nav">{"".join(nav_parts)}</nav>'

        body_html = _build_tabbed_detail(day["body"], notes_map)
        page = _page_html(
            f'{day["date"]} 论文推荐',
            f'<div class="detail-page">{body_html}</div>',
            nav_html,
            include_tabs_js=True
        )
        (output_dir / f'{day["date"]}.html').write_text(page, encoding="utf-8")

    # Generate index page — dashboard with calendar + trends
    import json as _json

    # Build DAYS_DATA JSON for embedding (metadata only, no HTML)
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

    days_data_script = f"<script>const DAYS_DATA = {_json.dumps(days_json, ensure_ascii=False)};</script>"

    # Build hidden content divs with full rendered HTML for each day
    hidden_panels = []
    for day in days:
        body_html = _build_tabbed_detail(day["body"], notes_map)
        hidden_panels.append(
            f'<div class="day-full-content" id="content-{day["date"]}" style="display:none;">'
            f'{body_html}</div>'
        )
    hidden_html = "\n".join(hidden_panels)

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
<div id="hidden-contents" style="display:none;">
{hidden_html}
</div>
"""
    index_page = _page_html(
        "每日论文推荐", index_body,
        include_dashboard_js=True,
        include_tabs_js=True,
        extra_head=days_data_script
    )
    (output_dir / "index.html").write_text(index_page, encoding="utf-8")

    print(f"Generated {len(days)} detail pages + index.html → {output_dir}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate static site for daily papers")
    parser.add_argument("--output-dir", type=str, help="Output directory for HTML files")
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
            # Default: output next to DailyPapers
            output = daily_papers_dir().parent / "_site"

    generate_site(output)


if __name__ == "__main__":
    main()
