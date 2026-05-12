"""
Phase 3: Export journal to a self-contained interactive HTML archive.

Usage (from project root):
    python -m src.export
"""

from __future__ import annotations

import calendar
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"
OUT_PATH = ROOT / "data" / "journal.html"

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
DAY_LETTERS  = ["M","T","W","T","F","S","S"]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_entries(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT d.draft_id, d.gmail_date, d.subject, d.body_text, d.word_count,
               t.entry_type, t.themes_json, t.mood, t.summary,
               t.is_pivotal, t.pivotal_reason
        FROM drafts d
        JOIN tags t ON d.draft_id = t.draft_id
        ORDER BY d.gmail_date
    """).fetchall()
    entries = []
    for r in rows:
        try:
            dt = datetime.fromisoformat(r[1])
        except Exception:
            continue
        themes = [t.lower().strip() for t in (json.loads(r[6]) if r[6] else []) if len(t.strip()) >= 3]
        entries.append({
            "id":             r[0],
            "date":           dt.strftime("%Y-%m-%d"),
            "display_date":   dt.strftime("%B %d, %Y"),
            "year":           dt.year,
            "month":          dt.month,
            "day":            dt.day,
            "subject":        r[2] or "",
            "body":           r[3] or "",
            "word_count":     r[4] or 0,
            "entry_type":     (r[5] or "").replace("_", " "),
            "themes":         themes,
            "mood":           r[7] or "",
            "summary":        r[8] or "",
            "is_pivotal":     bool(r[9]),
            "pivotal_reason": r[10] or "",
        })
    return entries


# ── HTML builders ─────────────────────────────────────────────────────────────

def build_calendar_sections(entries: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e["date"]] += 1

    years = sorted({e["year"] for e in entries})
    cal   = calendar.Calendar(firstweekday=0)
    parts = []

    for i, year in enumerate(years):
        open_attr = ' open' if i == 0 else ''
        parts.append(f'<div class="yr" id="y{year}">')
        parts.append(
            f'<div class="yr-hd" onclick="toggleYear({year})" id="yt-{year}">'
            f'<span class="yr-arrow" id="ya-{year}">{"▼" if i == 0 else "▶"}</span>'
            f'<span class="yr-num">{year}</span>'
            f'</div>'
        )
        display = 'block' if i == 0 else 'none'
        parts.append(f'<div class="yr-body" id="yb-{year}" style="display:{display}">')
        parts.append('<div class="months">')

        for m in range(1, 13):
            parts.append('<div class="month">')
            parts.append(f'<div class="mname">{MONTH_NAMES[m-1]}</div>')
            parts.append('<div class="cgrid">')
            for ltr in DAY_LETTERS:
                parts.append(f'<div class="ch">{ltr}</div>')
            for week in cal.monthdayscalendar(year, m):
                for d in week:
                    if d == 0:
                        parts.append('<div class="cd empty"></div>')
                    else:
                        date = f"{year}-{m:02d}-{d:02d}"
                        n    = counts.get(date, 0)
                        lvl  = "z" if n == 0 else ("a" if n == 1 else ("b" if n <= 3 else "c"))
                        if n > 0:
                            tip = f'{n} entr{"y" if n==1 else "ies"}'
                            parts.append(
                                f'<div class="cd {lvl}" data-date="{date}"'
                                f' title="{tip}" onclick="pickDay(\'{date}\')">{d}</div>'
                            )
                        else:
                            parts.append(f'<div class="cd z">{d}</div>')
            parts.append('</div></div>')  # cgrid, month

        parts.append('</div></div></div>')  # months, yr-body, yr
    return "\n".join(parts)


def build_pills(items: list[tuple[str,int]], cls: str) -> str:
    rows = []
    for v, n in items:
        safe = v.replace("'", "\\'")
        rows.append(
            f'<span class="pill {cls}" data-v="{v}" onclick="tog(\'{cls}\',\'{safe}\')">'
            f'{v}<em>{n}</em></span>'
        )
    return "\n".join(rows)


def build_html(entries: list[dict]) -> str:
    mood_counts:  dict[str,int] = defaultdict(int)
    theme_counts: dict[str,int] = defaultdict(int)
    type_counts:  dict[str,int] = defaultdict(int)
    year_counts:  dict[int,int]  = defaultdict(int)

    for e in entries:
        if e["mood"]:        mood_counts[e["mood"]]        += 1
        if e["entry_type"]:  type_counts[e["entry_type"]]  += 1
        year_counts[e["year"]] += 1
        for t in e["themes"]:
            theme_counts[t] += 1

    sorted_moods  = sorted(mood_counts.items(),  key=lambda x: -x[1])
    sorted_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:80]
    sorted_types  = sorted(type_counts.items(),  key=lambda x: -x[1])
    sorted_years  = sorted(year_counts.items())

    year_nav = " &middot; ".join(
        f'<a href="#y{y}" onclick="goYear({y});return false;">{y}</a>'
        for y, _ in sorted_years
    )
    calendar_html = build_calendar_sections(entries)
    mood_pills    = build_pills(sorted_moods,  "mp")
    theme_pills   = build_pills(sorted_themes, "tp")
    type_pills    = build_pills(sorted_types,  "ep")
    year_pills    = build_pills([(str(y), n) for y,n in sorted_years], "yp")

    entries_json  = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    total         = len(entries)
    years         = [y for y,_ in sorted_years]
    generated     = datetime.now().strftime("%B %d, %Y")

    return TEMPLATE.format(
        total=total,
        year_min=years[0], year_max=years[-1],
        generated=generated,
        year_nav=year_nav,
        year_pills=year_pills,
        mood_pills=mood_pills,
        theme_pills=theme_pills,
        type_pills=type_pills,
        calendar_html=calendar_html,
        entries_json=entries_json,
    )


# ── Template ──────────────────────────────────────────────────────────────────

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Journal Archive</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#f2f2f0;color:#1a1a1a;display:flex;min-height:100vh;font-size:14px}}

/* ── Sidebar ── */
#sb{{width:260px;min-width:260px;background:#fff;border-right:1px solid #e0e0dc;
  padding:20px 14px 40px;position:sticky;top:0;height:100vh;overflow-y:auto;
  display:flex;flex-direction:column;gap:0}}
#sb h1{{font-size:1.2em;font-weight:700;margin-bottom:2px}}
.sub{{font-size:0.72em;color:#888;margin-bottom:14px}}
#search{{width:100%;padding:7px 10px;border:1px solid #ddd;border-radius:6px;
  font-size:0.85em;outline:none;margin-bottom:4px}}
#search:focus{{border-color:#6aaed6}}
#clear-btn{{width:100%;padding:5px;border:1px solid #ddd;border-radius:6px;
  background:#fafaf8;font-size:0.75em;cursor:pointer;color:#888;margin-bottom:16px}}
#clear-btn:hover{{background:#eee}}
.sec{{margin-bottom:14px}}
.sec-hd{{font-size:0.68em;text-transform:uppercase;letter-spacing:.08em;
  color:#aaa;margin-bottom:7px;font-weight:700;display:flex;justify-content:space-between;align-items:center}}
.sec-hd .sel-ct{{color:#5a8ab5;font-weight:600;font-size:1em;text-transform:none;letter-spacing:0}}
.pills{{display:flex;flex-wrap:wrap;gap:4px}}
.pill{{font-size:0.72em;padding:3px 7px;border-radius:10px;cursor:pointer;
  background:#f0f0ee;color:#555;border:1px solid transparent;user-select:none;
  display:inline-flex;gap:4px;align-items:center}}
.pill em{{font-style:normal;color:#bbb;font-size:.9em}}
.pill:hover{{background:#e4e4e2}}
.pill.on{{background:#d0e8f5;color:#1a5a8a;border-color:#90c8e8}}
.pill.on em{{color:#5a9ec5}}
.yp{{font-variant-numeric:tabular-nums}}

/* ── Main ── */
#main{{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}}

/* Active filter bar */
#abar{{display:none;position:sticky;top:0;z-index:50;background:#fff;
  border-bottom:1px solid #e0e0dc;padding:8px 28px;gap:6px;flex-wrap:wrap;
  align-items:center}}
#abar-label{{font-size:0.72em;color:#aaa;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;margin-right:4px;white-space:nowrap}}
.atag{{font-size:0.75em;background:#d0e8f5;color:#1a5a8a;border:1px solid #90c8e8;
  border-radius:10px;padding:2px 8px;display:inline-flex;align-items:center;gap:5px}}
.atag-x{{cursor:pointer;font-size:1.1em;line-height:1;color:#5a8ab5;font-weight:700}}
.atag-x:hover{{color:#c0392b}}

/* Scrollable content */
#content{{padding:28px 36px 80px;overflow-y:auto;flex:1}}
nav.ynav{{margin-bottom:22px;line-height:2;font-size:0.88em}}
nav.ynav a{{color:#666;text-decoration:none;margin-right:8px}}
nav.ynav a:hover{{color:#000;text-decoration:underline}}

/* ── Calendar ── */
.yr{{margin-bottom:10px;background:#fff;border-radius:8px;
  box-shadow:0 1px 3px rgba(0,0,0,.05);overflow:hidden}}
.yr-hd{{display:flex;align-items:center;gap:10px;padding:12px 16px;cursor:pointer;
  user-select:none;border-bottom:1px solid transparent}}
.yr-hd:hover{{background:#f8f8f6}}
.yr-arrow{{font-size:0.7em;color:#aaa;width:12px}}
.yr-num{{font-size:1.05em;font-weight:700;color:#2a2a2a;letter-spacing:-.01em}}
.yr-body{{padding:14px 14px 16px}}
.months{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}}
.month{{background:#f8f8f6;border-radius:6px;padding:9px 7px 7px}}
.mname{{font-size:0.7em;font-weight:700;color:#888;margin-bottom:5px;text-align:center}}
.cgrid{{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}}
.ch{{font-size:7px;color:#ccc;text-align:center;padding:1px 0}}
.cd{{aspect-ratio:1;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:8.5px;font-weight:500;transition:opacity .15s}}
.cd.empty{{visibility:hidden}}
.cd.z{{color:#e0e0e0;background:transparent}}
.cd.a{{background:#c6ddf0;color:#2a5a80;cursor:pointer}}
.cd.b{{background:#4da3d4;color:#fff;cursor:pointer}}
.cd.c{{background:#1a6fad;color:#fff;cursor:pointer;font-weight:700}}
.cd.a:hover,.cd.b:hover,.cd.c:hover{{filter:brightness(1.1)}}
.cd.sel{{outline:2px solid #e05c1a;outline-offset:1px}}
.cd.dim{{opacity:.15}}

/* Legend */
.legend{{display:flex;align-items:center;gap:12px;margin-bottom:16px;
  font-size:0.72em;color:#aaa;flex-wrap:wrap}}
.leg-item{{display:flex;align-items:center;gap:4px}}
.leg-dot{{width:12px;height:12px;border-radius:50%;display:inline-block}}
.leg-dot.a{{background:#c6ddf0}}.leg-dot.b{{background:#4da3d4}}
.leg-dot.c{{background:#1a6fad}}.leg-dot.dim{{background:#ddd}}

/* ── Mobile header ── */
#mob-hd{{display:none;position:sticky;top:0;z-index:100;background:#fff;
  border-bottom:1px solid #e0e0dc;padding:10px 16px;align-items:center;gap:10px}}
#menu-btn{{background:none;border:none;cursor:pointer;font-size:1.4em;line-height:1;
  color:#444;padding:2px 6px}}
#mob-title{{font-weight:700;font-size:1em;flex:1}}
#overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:150}}

@media(max-width:700px){{
  body{{flex-direction:column}}
  #sb{{position:fixed;left:-290px;top:0;height:100vh;z-index:200;
    width:280px;min-width:280px;transition:left .25s ease}}
  #sb.open{{left:0}}
  #overlay.show{{display:block}}
  #mob-hd{{display:flex}}
  #content{{padding:16px 14px 60px}}
  .months{{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}}
  #abar{{padding:8px 14px}}
  nav.ynav{{font-size:0.82em}}
}}

/* ── Entry panel ── */
#panel{{margin-top:32px;display:none}}
#panel-hd{{display:flex;align-items:baseline;gap:10px;margin-bottom:16px;
  border-top:1px solid #e0e0dc;padding-top:20px}}
#panel-hd h3{{font-size:1em;font-weight:700}}
#panel-hd .phint{{font-size:0.78em;color:#aaa}}
.ecard{{background:#fff;border-radius:8px;padding:16px 20px;margin-bottom:12px;
  border-left:3px solid #e8e8e0;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.ecard.piv{{border-left-color:#e6c84a}}
.edate{{font-size:0.75em;color:#aaa;margin-bottom:5px}}
.emeta{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}}
.badge{{font-size:0.68em;padding:2px 7px;border-radius:9px;background:#f0f0ee;color:#666}}
.bm{{background:#e8f0fb;color:#3a5a99}}.bt{{background:#f0ebe8;color:#7a4a3a}}
.bp{{background:#fff8e1;color:#8a6800;font-weight:700}}
.ethemes{{font-size:0.72em;color:#bbb;margin-bottom:6px}}
.esum{{font-style:italic;color:#555;font-size:0.88em;margin-bottom:6px}}
.epiv{{font-size:0.78em;color:#7a5a00;background:#fffbec;
  border-left:2px solid #e6c84a;padding:5px 9px;margin-bottom:6px;border-radius:3px}}
.etog{{font-size:0.74em;color:#5a8ab5;cursor:pointer;margin-top:5px;
  user-select:none;display:inline-block}}
.etog:hover{{text-decoration:underline}}
.ebody{{display:none;margin-top:10px;white-space:pre-wrap;font-family:Georgia,serif;
  font-size:0.88em;line-height:1.8;color:#333;border-top:1px solid #f0f0f0;padding-top:10px}}
#no-res{{color:#aaa;font-style:italic;margin-top:12px;font-size:0.88em}}
</style>
</head>
<body>

<!-- Sidebar -->
<div id="sb">
  <h1>&#128211; Journal Archive</h1>
  <p class="sub">{total:,} entries &middot; {year_min}&ndash;{year_max} &middot; {generated}</p>

  <input id="search" type="search" placeholder="Search entries..." oninput="onSearch(this.value)">
  <button id="clear-btn" onclick="clearAll()">Clear all filters</button>

  <div class="sec">
    <div class="sec-hd">Year <span class="sel-ct" id="yct"></span></div>
    <div class="pills">{year_pills}</div>
  </div>
  <div class="sec">
    <div class="sec-hd">Entry Type <span class="sel-ct" id="ect"></span></div>
    <div class="pills">{type_pills}</div>
  </div>
  <div class="sec">
    <div class="sec-hd">Mood <span class="sel-ct" id="mct"></span></div>
    <div class="pills">{mood_pills}</div>
  </div>
  <div class="sec">
    <div class="sec-hd">Themes <span class="sel-ct" id="tct"></span></div>
    <div class="pills">{theme_pills}</div>
  </div>
</div>

<!-- Mobile header -->
<div id="mob-hd">
  <button id="menu-btn" onclick="openSb()">&#9776;</button>
  <span id="mob-title">Journal Archive</span>
</div>
<div id="overlay" onclick="closeSb()"></div>

<!-- Main -->
<div id="main">

  <!-- Sticky active filter bar -->
  <div id="abar">
    <span id="abar-label">Active:</span>
    <span id="atags"></span>
  </div>

  <!-- Scrollable content -->
  <div id="content">
    <nav class="ynav">{year_nav}</nav>

    <div class="legend">
      <span class="leg-item"><span class="leg-dot a"></span>1 entry</span>
      <span class="leg-item"><span class="leg-dot b"></span>2&ndash;3 entries</span>
      <span class="leg-item"><span class="leg-dot c"></span>4+ entries</span>
      <span class="leg-item"><span class="leg-dot dim"></span>no match (when filter active)</span>
    </div>

    {calendar_html}

    <div id="panel">
      <div id="panel-hd">
        <h3 id="ptitle"></h3>
        <span class="phint" id="phint"></span>
      </div>
      <div id="elist"></div>
      <div id="no-res" style="display:none">No entries match the current filters.</div>
    </div>
  </div>
</div>

<script>
const E = {entries_json};

const S = {{q:"", years:new Set(), moods:new Set(), themes:new Set(), types:new Set(), date:null}};

// ── Accordion ──────────────────────────────────────────────────────────────
function toggleYear(y){{
  const body  = document.getElementById("yb-"+y);
  const arrow = document.getElementById("ya-"+y);
  const open  = body.style.display === "block";
  document.querySelectorAll(".yr-body").forEach(b=>b.style.display="none");
  document.querySelectorAll(".yr-arrow").forEach(a=>a.textContent="▶");
  if(!open){{ body.style.display="block"; arrow.textContent="▼"; }}
}}
function goYear(y){{
  document.querySelectorAll(".yr-body").forEach(b=>b.style.display="none");
  document.querySelectorAll(".yr-arrow").forEach(a=>a.textContent="▶");
  const body  = document.getElementById("yb-"+y);
  const arrow = document.getElementById("ya-"+y);
  if(body){{ body.style.display="block"; arrow.textContent="▼"; }}
  document.getElementById("y"+y).scrollIntoView({{behavior:"smooth",block:"start"}});
}}

// ── Filter toggles ─────────────────────────────────────────────────────────
function tog(cls, v){{
  const map = {{mp:S.moods, tp:S.themes, ep:S.types, yp:S.years}};
  const set = map[cls]; if(!set) return;
  if(set.has(v)) set.delete(v); else set.add(v);
  if(window.innerWidth<=700) closeSb();
  render();
}}
function onSearch(v){{ S.q=v.toLowerCase().trim(); render(); }}
function pickDay(d){{ S.date = S.date===d ? null : d; render(); }}
function clearAll(){{
  S.q=""; S.years.clear(); S.moods.clear(); S.themes.clear(); S.types.clear(); S.date=null;
  document.getElementById("search").value="";
  document.querySelectorAll(".cd.sel").forEach(el=>el.classList.remove("sel"));
  render();
}}
function removeTag(type, v){{
  if(type==="year")  {{ S.years.delete(v); }}
  else if(type==="mood")  {{ S.moods.delete(v); }}
  else if(type==="theme") {{ S.themes.delete(v); }}
  else if(type==="type")  {{ S.types.delete(v); }}
  else if(type==="date")  {{ S.date=null; }}
  else if(type==="q")     {{ S.q=""; document.getElementById("search").value=""; }}
  render();
}}

// ── Core render ────────────────────────────────────────────────────────────
function hasFilter(){{
  return S.q || S.years.size || S.moods.size || S.themes.size || S.types.size || S.date;
}}
function getFiltered(){{
  return E.filter(e=>{{
    if(S.date && e.date!==S.date) return false;
    if(S.years.size && !S.years.has(String(e.year))) return false;
    if(S.moods.size && !S.moods.has(e.mood)) return false;
    if(S.themes.size && !e.themes.some(t=>S.themes.has(t))) return false;
    if(S.types.size && !S.types.has(e.entry_type)) return false;
    if(S.q){{
      const txt=(e.body+" "+e.summary+" "+e.subject).toLowerCase();
      if(!txt.includes(S.q)) return false;
    }}
    return true;
  }});
}}

function render(){{
  // ── Pill highlight ──
  document.querySelectorAll(".mp").forEach(p=>p.classList.toggle("on",S.moods.has(p.dataset.v)));
  document.querySelectorAll(".tp").forEach(p=>p.classList.toggle("on",S.themes.has(p.dataset.v)));
  document.querySelectorAll(".ep").forEach(p=>p.classList.toggle("on",S.types.has(p.dataset.v)));
  document.querySelectorAll(".yp").forEach(p=>p.classList.toggle("on",S.years.has(p.dataset.v)));

  // ── Section counts ──
  const ct = (set, id) => {{
    const el=document.getElementById(id);
    el.textContent = set.size ? set.size+" selected" : "";
  }};
  ct(S.years,"yct"); ct(S.types,"ect"); ct(S.moods,"mct"); ct(S.themes,"tct");

  // ── Active bar ──
  const abar = document.getElementById("abar");
  const atags = document.getElementById("atags");
  const tags = [];
  if(S.date) tags.push({{type:"date",v:S.date,label:S.date}});
  S.years.forEach(v=>tags.push({{type:"year",v,label:v}}));
  S.types.forEach(v=>tags.push({{type:"type",v,label:v}}));
  S.moods.forEach(v=>tags.push({{type:"mood",v,label:v}}));
  S.themes.forEach(v=>tags.push({{type:"theme",v,label:v}}));
  if(S.q) tags.push({{type:"q",v:S.q,label:'"'+S.q+'"'}});

  if(tags.length){{
    abar.style.display="flex";
    atags.innerHTML=tags.map(t=>
      `<span class="atag">${{t.label}}<span class="atag-x" onclick="removeTag('${{t.type}}','${{t.v.replace(/'/g,"\\'")}}')">x</span></span>`
    ).join("");
  }} else {{
    abar.style.display="none";
    atags.innerHTML="";
  }}

  // ── Calendar highlighting ──
  if(!hasFilter()){{
    document.querySelectorAll(".cd[data-date]").forEach(el=>{{
      el.classList.remove("sel","dim");
    }});
    document.getElementById("panel").style.display="none";
    return;
  }}

  const res     = getFiltered();
  const matches = new Set(res.map(e=>e.date));

  document.querySelectorAll(".cd[data-date]").forEach(el=>{{
    const d=el.dataset.date;
    el.classList.toggle("sel", d===S.date);
    el.classList.toggle("dim", !matches.has(d));
  }});

  // ── Entry panel ──
  const panel = document.getElementById("panel");
  panel.style.display = "block";

  const ptitle = document.getElementById("ptitle");
  const phint  = document.getElementById("phint");

  if(S.date){{
    const [y,m,d]=S.date.split("-").map(Number);
    ptitle.textContent=new Date(y,m-1,d).toLocaleDateString("en-US",{{month:"long",day:"numeric",year:"numeric"}});
  }} else {{
    ptitle.textContent=res.length+" entr"+(res.length===1?"y":"ies");
  }}

  const hints=[];
  if(S.years.size)  hints.push([...S.years].join(", "));
  if(S.types.size)  hints.push([...S.types].join(", "));
  if(S.moods.size)  hints.push([...S.moods].join(", "));
  if(S.themes.size) hints.push([...S.themes].join(", "));
  if(S.q)           hints.push('"'+S.q+'"');
  phint.textContent = hints.length ? "-- "+hints.join(" / ") : "";

  const none  = document.getElementById("no-res");
  const elist = document.getElementById("elist");

  if(res.length===0){{ elist.innerHTML=""; none.style.display="block"; return; }}
  none.style.display="none";

  elist.innerHTML=res.map(e=>{{
    const piv   = e.is_pivotal?'<span class="badge bp">* pivotal</span>':'';
    const themes= e.themes.slice(0,6).join(", ");
    const pr    = e.is_pivotal&&e.pivotal_reason?`<div class="epiv">${{e.pivotal_reason}}</div>`:"";
    const body  = e.body.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    return `<div class="ecard${{e.is_pivotal?' piv':''}}">
<div class="edate">${{e.display_date}}</div>
<div class="emeta">${{piv}}<span class="badge bm">${{e.mood}}</span><span class="badge bt">${{e.entry_type}}</span></div>
${{themes?`<div class="ethemes">${{themes}}</div>`:""}}
<div class="esum">${{e.summary}}</div>
${{pr}}
<span class="etog" onclick="togBody(this)">+ Read full entry</span>
<div class="ebody">${{body}}</div>
</div>`;
  }}).join("");

  panel.scrollIntoView({{behavior:"smooth",block:"start"}});
}}

function openSb(){{
  document.getElementById("sb").classList.add("open");
  document.getElementById("overlay").classList.add("show");
}}
function closeSb(){{
  document.getElementById("sb").classList.remove("open");
  document.getElementById("overlay").classList.remove("show");
}}

function togBody(el){{
  const b=el.nextElementSibling;
  const open=b.style.display==="block";
  b.style.display=open?"none":"block";
  el.textContent=open?"+ Read full entry":"- Collapse";
}}
</script>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    print("Loading entries...")
    entries = load_entries(conn)
    conn.close()

    print(f"Building HTML for {len(entries):,} entries...")
    html = build_html(entries)
    OUT_PATH.write_text(html, encoding="utf-8")

    size_mb = OUT_PATH.stat().st_size / 1_000_000
    print(f"Written to {OUT_PATH} ({size_mb:.1f} MB)")

    try:
        from src.gdrive import upload
        print("Uploading to Google Drive...")
        url = upload(OUT_PATH)
        print(f"Google Drive: {url}")
    except Exception as e:
        print(f"Drive upload skipped: {e}")


if __name__ == "__main__":
    main()
