"""
Phase 3: Export journal to a self-contained interactive HTML archive.

Generates a single-file web app with:
  - Calendar heatmap (per-year accordion)
  - Browse view with filters, sort, and load-more pagination
  - Full-text search with match highlighting
  - Insights: built-in analytics charts (no Streamlit needed)
  - Pivotal entries timeline
  - Dark / light mode, mobile-friendly layout
  - "On this day" and random-entry features

Usage (from project root):
    python -m src.export
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"
OUT_PATH = ROOT / "data" / "journal.html"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_entries(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT d.draft_id, d.gmail_date, d.subject, d.body_text, d.word_count,
               t.entry_type, t.themes_json, t.entities_json, t.mood, t.summary,
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
        entities = [e.strip() for e in (json.loads(r[7]) if r[7] else []) if e.strip()]
        entries.append({
            "id":             r[0],
            "date":           dt.strftime("%Y-%m-%d"),
            "year":           dt.year,
            "month":          dt.month,
            "day":            dt.day,
            "subject":        r[2] or "",
            "body":           r[3] or "",
            "wc":             r[4] or 0,
            "type":           (r[5] or "").replace("_", " "),
            "themes":         themes,
            "entities":       entities[:10],
            "mood":           r[8] or "",
            "summary":        r[9] or "",
            "piv":            bool(r[10]),
            "pivr":           r[11] or "",
        })
    return entries


# ── Template ──────────────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Journal Archive</title>
<style>
:root{
  --bg:#f7f4ee; --bg2:#fffdf9; --card:#fffdf9; --ink:#211d18; --muted:#8d8578;
  --line:#e7e1d6; --accent:#b4541f; --accent-soft:#f4e3d8; --accent-ink:#8a3c12;
  --gold:#b08c2e; --gold-soft:#faf3df;
  --heat0:#eee8dc; --heat1:#ecc4a8; --heat2:#d98a52; --heat3:#b4541f;
  --shadow:0 1px 3px rgba(60,45,30,.08),0 4px 14px rgba(60,45,30,.05);
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
}
[data-theme="dark"]{
  --bg:#171411; --bg2:#1f1b17; --card:#241f1a; --ink:#ece5da; --muted:#9a9081;
  --line:#352e26; --accent:#e0855a; --accent-soft:#3a2a20; --accent-ink:#eda579;
  --gold:#d4b052; --gold-soft:#332b18;
  --heat0:#2a251f; --heat1:#5a3a26; --heat2:#a05a32; --heat3:#e0855a;
  --shadow:0 1px 3px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.2);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--sans);background:var(--bg);color:var(--ink);font-size:15px;
  -webkit-font-smoothing:antialiased;transition:background .25s,color .25s}
button{font-family:inherit;color:inherit}
mark{background:var(--gold-soft);color:var(--gold);border-radius:3px;padding:0 2px;font-weight:600}

/* ── Header ── */
header{position:sticky;top:0;z-index:100;background:color-mix(in srgb,var(--bg2) 88%,transparent);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.hd-row{max-width:1100px;margin:0 auto;padding:14px 20px 10px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;gap:1px;margin-right:auto}
.brand h1{font-family:var(--serif);font-size:1.35em;font-weight:700;letter-spacing:-.01em}
.brand .sub{font-size:.72em;color:var(--muted)}
.searchwrap{position:relative;flex:1;min-width:200px;max-width:420px}
.searchwrap svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:14px;height:14px;
  stroke:var(--muted);fill:none;stroke-width:2;pointer-events:none}
#search{width:100%;padding:9px 32px 9px 32px;border:1px solid var(--line);border-radius:99px;
  background:var(--card);color:var(--ink);font-size:.88em;outline:none;transition:border-color .15s,box-shadow .15s}
#search:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
#search-x{position:absolute;right:6px;top:50%;transform:translateY(-50%);border:none;background:none;
  color:var(--muted);cursor:pointer;font-size:1.05em;padding:4px 7px;display:none;line-height:1}
.hbtn{border:1px solid var(--line);background:var(--card);border-radius:99px;padding:8px 14px;
  font-size:.8em;cursor:pointer;color:var(--ink);white-space:nowrap;transition:border-color .15s,background .15s}
.hbtn:hover{border-color:var(--accent);color:var(--accent)}
.iconbtn{width:36px;height:36px;display:flex;align-items:center;justify-content:center;padding:0;font-size:1em}

/* tabs */
.tabs{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{border:none;background:none;padding:9px 14px 11px;font-size:.85em;color:var(--muted);cursor:pointer;
  border-bottom:2px solid transparent;white-space:nowrap;transition:color .15s}
.tab:hover{color:var(--ink)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
.tab .n{font-size:.82em;color:var(--muted);margin-left:4px}

/* ── Layout ── */
#wrap{max-width:1100px;margin:0 auto;padding:22px 20px 90px}
.view{display:none}.view.on{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

/* chips */
#chips{display:none;max-width:1100px;margin:0 auto;padding:10px 20px 0;gap:6px;flex-wrap:wrap;align-items:center}
#chips.show{display:flex}
.chip{font-size:.76em;background:var(--accent-soft);color:var(--accent-ink);border:1px solid transparent;
  border-radius:99px;padding:4px 6px 4px 11px;display:inline-flex;align-items:center;gap:6px}
.chip b{font-weight:600}
.chip button{border:none;background:none;cursor:pointer;color:inherit;opacity:.65;font-size:1.05em;
  line-height:1;padding:1px 5px;border-radius:99px}
.chip button:hover{opacity:1;background:rgba(0,0,0,.08)}
#clear-all{font-size:.76em;border:none;background:none;color:var(--muted);cursor:pointer;
  text-decoration:underline;padding:4px}
#clear-all:hover{color:var(--accent)}

/* ── Filter drawer ── */
#scrim{position:fixed;inset:0;background:rgba(20,14,8,.45);z-index:200;opacity:0;pointer-events:none;transition:opacity .25s}
#scrim.show{opacity:1;pointer-events:auto}
#drawer{position:fixed;top:0;right:-360px;width:340px;max-width:92vw;height:100dvh;background:var(--bg2);
  z-index:201;transition:right .28s ease;box-shadow:-8px 0 30px rgba(0,0,0,.15);display:flex;flex-direction:column}
#drawer.show{right:0}
.dr-hd{display:flex;align-items:center;justify-content:space-between;padding:16px 18px;border-bottom:1px solid var(--line)}
.dr-hd h2{font-size:1em;font-family:var(--serif)}
.dr-body{overflow-y:auto;padding:14px 18px 40px;flex:1}
.fsec{margin-bottom:18px}
.fsec h3{font-size:.68em;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:8px;
  display:flex;justify-content:space-between}
.fsec h3 span{text-transform:none;letter-spacing:0;color:var(--accent)}
.pills{display:flex;flex-wrap:wrap;gap:5px}
.pill{font-size:.76em;padding:4px 10px;border-radius:99px;cursor:pointer;background:var(--bg);
  color:var(--ink);border:1px solid var(--line);user-select:none;display:inline-flex;gap:5px;align-items:center;
  transition:background .12s,border-color .12s}
.pill em{font-style:normal;color:var(--muted);font-size:.88em}
.pill:hover{border-color:var(--accent)}
.pill.on{background:var(--accent-soft);color:var(--accent-ink);border-color:var(--accent)}
.pill.on em{color:var(--accent-ink);opacity:.7}

/* ── Calendar ── */
.legend{display:flex;align-items:center;gap:14px;margin:2px 0 16px;font-size:.74em;color:var(--muted);flex-wrap:wrap}
.leg{display:flex;align-items:center;gap:5px}
.dot{width:11px;height:11px;border-radius:4px;display:inline-block}
.yr{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:12px;
  box-shadow:var(--shadow);overflow:hidden}
.yr-hd{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer;user-select:none}
.yr-hd:hover{background:color-mix(in srgb,var(--accent-soft) 35%,transparent)}
.yr-arrow{font-size:.65em;color:var(--muted);width:12px;transition:transform .2s}
.yr.open .yr-arrow{transform:rotate(90deg)}
.yr-num{font-family:var(--serif);font-size:1.15em;font-weight:700}
.yr-ct{font-size:.74em;color:var(--muted);margin-left:auto}
.yr-body{display:none;padding:4px 16px 18px}
.yr.open .yr-body{display:block}
.months{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.month{background:var(--bg);border-radius:10px;padding:10px 8px 8px}
.mname{font-size:.7em;font-weight:700;color:var(--muted);margin-bottom:6px;text-align:center;
  text-transform:uppercase;letter-spacing:.08em}
.cgrid{display:grid;grid-template-columns:repeat(7,1fr);grid-auto-rows:17px;gap:2px}
.ch{font-size:7.5px;color:var(--muted);opacity:.6;text-align:center;padding:1px 0;
  display:flex;align-items:center;justify-content:center}
.cd{border-radius:5px;display:flex;align-items:center;justify-content:center;
  font-size:8.5px;font-weight:500;transition:opacity .15s,transform .1s}
.cd.empty{visibility:hidden}
.cd.z{color:var(--muted);opacity:.45}
.cd.h1{background:var(--heat1);color:var(--ink);cursor:pointer}
.cd.h2{background:var(--heat2);color:#fff;cursor:pointer}
.cd.h3{background:var(--heat3);color:#fff;cursor:pointer;font-weight:700}
.cd.h1:hover,.cd.h2:hover,.cd.h3:hover{transform:scale(1.25)}
.cd.dim{opacity:.13}

/* ── Cards ── */
.toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.toolbar .count{font-size:.82em;color:var(--muted)}
.sortbtn{margin-left:auto}
.card{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line);
  border-radius:12px;padding:16px 20px;margin-bottom:12px;box-shadow:var(--shadow);
  transition:border-color .15s}
.card:hover{border-left-color:var(--accent)}
.card.piv{border-left-color:var(--gold)}
.card-top{display:flex;align-items:baseline;gap:10px;margin-bottom:7px;flex-wrap:wrap}
.cdate{font-family:var(--serif);font-weight:700;font-size:1.02em}
.cwords{font-size:.72em;color:var(--muted);margin-left:auto;white-space:nowrap}
.badges{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.badge{font-size:.68em;padding:2.5px 9px;border-radius:99px;background:var(--bg);
  border:1px solid var(--line);color:var(--muted)}
.badge.bm{color:var(--accent-ink);background:var(--accent-soft);border-color:transparent}
.badge.bp{color:var(--gold);background:var(--gold-soft);border-color:transparent;font-weight:700}
.csum{font-style:italic;color:var(--muted);font-size:.9em;line-height:1.55;margin-bottom:6px}
.cpiv{font-size:.78em;color:var(--gold);background:var(--gold-soft);border-radius:7px;
  padding:7px 11px;margin:7px 0;line-height:1.5}
.cthemes{font-size:.72em;color:var(--muted);margin-bottom:4px;line-height:1.7}
.cthemes span{background:var(--bg);border-radius:99px;padding:1.5px 8px;margin-right:4px;
  display:inline-block;border:1px solid var(--line)}
.csnip{font-family:var(--serif);font-size:.86em;line-height:1.7;color:var(--ink);
  background:var(--bg);border-radius:8px;padding:9px 13px;margin:8px 0}
.ctog{font-size:.78em;color:var(--accent);cursor:pointer;border:none;background:none;
  padding:5px 0 0;font-weight:600}
.ctog:hover{text-decoration:underline}
.cbody{display:none;margin-top:12px;white-space:pre-wrap;font-family:var(--serif);
  font-size:.95em;line-height:1.85;border-top:1px solid var(--line);padding-top:13px}
.cbody.show{display:block}
#more{display:block;margin:18px auto;padding:10px 28px;border-radius:99px;border:1px solid var(--line);
  background:var(--card);cursor:pointer;font-size:.85em;box-shadow:var(--shadow)}
#more:hover{border-color:var(--accent);color:var(--accent)}
.empty{color:var(--muted);font-style:italic;padding:50px 0;text-align:center;font-size:.92em}

/* ── Insights ── */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:22px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow)}
.stat .v{font-family:var(--serif);font-size:1.55em;font-weight:700;color:var(--accent)}
.stat .l{font-size:.7em;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-top:3px}
.chartcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
  margin-bottom:16px;box-shadow:var(--shadow)}
.chartcard h3{font-family:var(--serif);font-size:1em;margin-bottom:4px}
.chartcard .note{font-size:.72em;color:var(--muted);margin-bottom:12px}
.chartcard svg{width:100%;height:auto;display:block}
.chlegend{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;font-size:.72em;color:var(--muted)}
.chlegend .leg .dot{border-radius:99px;width:9px;height:9px}
.hrow{display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:.8em}
.hrow .hl{width:130px;min-width:130px;text-align:right;color:var(--muted);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.hrow .hb-track{flex:1;background:var(--bg);border-radius:99px;height:16px;overflow:hidden}
.hrow .hb{height:100%;border-radius:99px;background:var(--accent);min-width:2px;
  transition:width .5s ease}
.hrow .hv{width:46px;color:var(--muted);font-size:.9em}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}

/* ── Modal ── */
#modal{position:fixed;inset:0;background:rgba(20,14,8,.5);z-index:300;display:none;
  align-items:flex-start;justify-content:center;padding:5vh 16px;overflow-y:auto}
#modal.show{display:flex}
#modal-card{background:var(--bg2);border-radius:16px;max-width:720px;width:100%;
  padding:26px 30px 30px;box-shadow:0 20px 60px rgba(0,0,0,.3);position:relative;margin-bottom:5vh}
#modal-x{position:absolute;top:14px;right:14px;border:1px solid var(--line);background:var(--card);
  border-radius:99px;width:32px;height:32px;cursor:pointer;font-size:1em;color:var(--muted)}
#modal-x:hover{color:var(--accent);border-color:var(--accent)}
#modal-card .cbody{display:block;border:none;margin-top:14px;padding-top:0}

/* scroll-top */
#top-btn{position:fixed;bottom:22px;right:22px;width:42px;height:42px;border-radius:99px;
  border:1px solid var(--line);background:var(--card);box-shadow:var(--shadow);cursor:pointer;
  font-size:1.05em;color:var(--muted);display:none;z-index:90}
#top-btn:hover{color:var(--accent);border-color:var(--accent)}

@media(max-width:700px){
  .hd-row{padding:12px 14px 8px;gap:8px}
  .brand .sub{display:none}
  #wrap{padding:16px 14px 80px}
  .months{grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:8px}
  .card{padding:14px 15px}
  .hrow .hl{width:90px;min-width:90px}
}
</style>
</head>
<body>

<header>
  <div class="hd-row">
    <div class="brand">
      <h1>&#128211; Journal Archive</h1>
      <span class="sub">__TOTAL__ entries &middot; __YMIN__&ndash;__YMAX__ &middot; built __GENERATED__</span>
    </div>
    <div class="searchwrap">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
      <input id="search" type="search" placeholder="Search entries...  ( / )" autocomplete="off">
      <button id="search-x" onclick="clearSearch()">&times;</button>
    </div>
    <button class="hbtn" onclick="onThisDay()" title="Entries from this date across the years">On this day</button>
    <button class="hbtn iconbtn" onclick="randomEntry()" title="Random entry">&#127922;</button>
    <button class="hbtn" onclick="openDrawer()">Filters<span id="fct"></span></button>
    <button class="hbtn iconbtn" id="theme-btn" onclick="toggleTheme()" title="Toggle dark mode">&#9789;</button>
  </div>
  <nav class="tabs">
    <button class="tab on" data-view="calendar" onclick="setView('calendar')">Calendar</button>
    <button class="tab" data-view="browse" onclick="setView('browse')">Browse</button>
    <button class="tab" data-view="insights" onclick="setView('insights')">Insights</button>
    <button class="tab" data-view="pivotal" onclick="setView('pivotal')">Pivotal<span class="n" id="pivn"></span></button>
  </nav>
</header>

<div id="chips"></div>

<div id="wrap">
  <div class="view on" id="v-calendar">
    <div class="legend">
      <span class="leg"><span class="dot" style="background:var(--heat1)"></span>1 entry</span>
      <span class="leg"><span class="dot" style="background:var(--heat2)"></span>2&ndash;3</span>
      <span class="leg"><span class="dot" style="background:var(--heat3)"></span>4+</span>
      <span class="leg" id="leg-dim" style="display:none"><span class="dot" style="background:var(--heat0)"></span>no match</span>
    </div>
    <div id="cal"></div>
  </div>

  <div class="view" id="v-browse">
    <div class="toolbar">
      <span class="count" id="b-count"></span>
      <button class="hbtn sortbtn" id="sort-btn" onclick="toggleSort()">Newest first</button>
    </div>
    <div id="blist"></div>
    <button id="more" onclick="loadMore()">Show more</button>
    <div class="empty" id="b-empty" style="display:none">No entries match. Try clearing some filters.</div>
  </div>

  <div class="view" id="v-insights"><div id="ins"></div></div>

  <div class="view" id="v-pivotal">
    <div class="toolbar"><span class="count" id="p-count"></span></div>
    <div id="plist"></div>
  </div>
</div>

<!-- Filter drawer -->
<div id="scrim" onclick="closeDrawer()"></div>
<div id="drawer">
  <div class="dr-hd"><h2>Filters</h2>
    <button class="hbtn" onclick="closeDrawer()">Done</button></div>
  <div class="dr-body" id="dr-body"></div>
</div>

<!-- Modal -->
<div id="modal" onclick="if(event.target===this)closeModal()">
  <div id="modal-card">
    <button id="modal-x" onclick="closeModal()">&times;</button>
    <div id="modal-body"></div>
  </div>
</div>

<button id="top-btn" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="Back to top">&#8593;</button>

<script>
const E = __ENTRIES__;
const MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const MONTHS_F=["January","February","March","April","May","June","July","August","September","October","November","December"];
const PALETTE=["#c2562e","#3a7ca5","#7a9a4e","#b08c2e","#8a5a9e","#5a8a8a","#a54e62","#6a6aa5","#8a6a4e","#4ea58a","#a5984e","#c2762e"];
const PAGE=25;

const S={view:'calendar',q:'',years:new Set(),types:new Set(),moods:new Set(),themes:new Set(),
         date:null,md:null,sort:'desc',shown:PAGE};

const fmt=n=>n.toLocaleString("en-US");
const esc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
function dispDate(e){return MONTHS_F[e.month-1]+" "+e.day+", "+e.year}

// ── Filtering ────────────────────────────────────────────────────────────────
function hasFilter(){return S.q||S.years.size||S.types.size||S.moods.size||S.themes.size||S.date||S.md}
function getFiltered(){
  const q=S.q;
  return E.filter(e=>{
    if(S.date&&e.date!==S.date)return false;
    if(S.md&&!(e.month===S.md[0]&&e.day===S.md[1]))return false;
    if(S.years.size&&!S.years.has(String(e.year)))return false;
    if(S.types.size&&!S.types.has(e.type))return false;
    if(S.moods.size&&!S.moods.has(e.mood))return false;
    if(S.themes.size&&!e.themes.some(t=>S.themes.has(t)))return false;
    if(q){const txt=(e.body+" "+e.summary+" "+e.subject).toLowerCase();if(!txt.includes(q))return false}
    return true;
  });
}

// ── Highlight & snippet ──────────────────────────────────────────────────────
function hl(text){
  if(!S.q)return esc(text);
  const safe=esc(text), qe=S.q.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
  return safe.replace(new RegExp("("+qe+")","gi"),"<mark>$1</mark>");
}
function snippet(e){
  if(!S.q)return "";
  const i=e.body.toLowerCase().indexOf(S.q);
  if(i<0)return "";
  const a=Math.max(0,i-110), b=Math.min(e.body.length,i+S.q.length+170);
  return '<div class="csnip">'+(a>0?"&hellip;":"")+hl(e.body.slice(a,b))+(b<e.body.length?"&hellip;":"")+'</div>';
}

// ── Card rendering ───────────────────────────────────────────────────────────
function card(e){
  const badges=[
    e.piv?'<span class="badge bp">&#9733; pivotal</span>':'',
    e.mood?'<span class="badge bm">'+esc(e.mood)+'</span>':'',
    e.type?'<span class="badge">'+esc(e.type)+'</span>':''
  ].join('');
  const themes=e.themes.length?'<div class="cthemes">'+e.themes.slice(0,6).map(t=>'<span>'+esc(t)+'</span>').join('')+'</div>':'';
  const pivr=e.piv&&e.pivr?'<div class="cpiv">&#9733; '+esc(e.pivr)+'</div>':'';
  return '<div class="card'+(e.piv?' piv':'')+'">'
    +'<div class="card-top"><span class="cdate">'+dispDate(e)+'</span>'
    +'<span class="cwords">'+fmt(e.wc)+' words</span></div>'
    +'<div class="badges">'+badges+'</div>'
    +(e.summary?'<div class="csum">'+hl(e.summary)+'</div>':'')
    +pivr+themes+snippet(e)
    +'<button class="ctog" onclick="togBody(this)">Read entry &darr;</button>'
    +'<div class="cbody">'+hl(e.body)+'</div></div>';
}
function togBody(btn){
  const b=btn.nextElementSibling, open=b.classList.toggle('show');
  btn.innerHTML=open?'Collapse &uarr;':'Read entry &darr;';
}

// ── Views ────────────────────────────────────────────────────────────────────
function setView(v){
  S.view=v;
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.view===v));
  document.querySelectorAll('.view').forEach(el=>el.classList.toggle('on',el.id==='v-'+v));
  if(v==='insights'&&!insBuilt)buildInsights();
  if(v==='browse')renderBrowse();
  if(v==='pivotal')renderPivotal();
  if(v==='calendar')updateCalendar();
  window.scrollTo({top:0});
}

// Calendar ---------------------------------------------------------------
const counts={};
E.forEach(e=>{counts[e.date]=(counts[e.date]||0)+1});
const YEARS=[...new Set(E.map(e=>e.year))].sort((a,b)=>b-a);

function buildCalendar(){
  const yearCt={};E.forEach(e=>{yearCt[e.year]=(yearCt[e.year]||0)+1});
  let html='';
  YEARS.forEach((y,yi)=>{
    html+='<div class="yr'+(yi===0?' open':'')+'" id="yr-'+y+'">'
      +'<div class="yr-hd" onclick="this.parentNode.classList.toggle(\'open\')">'
      +'<span class="yr-arrow">&#9654;</span><span class="yr-num">'+y+'</span>'
      +'<span class="yr-ct">'+fmt(yearCt[y]||0)+' entries</span></div>'
      +'<div class="yr-body"><div class="months">';
    for(let m=0;m<12;m++){
      html+='<div class="month"><div class="mname">'+MONTHS[m]+'</div><div class="cgrid">';
      "MTWTFSS".split("").forEach(l=>html+='<div class="ch">'+l+'</div>');
      const first=(new Date(y,m,1).getDay()+6)%7, dim=new Date(y,m+1,0).getDate();
      for(let i=0;i<first;i++)html+='<div class="cd empty"></div>';
      for(let d=1;d<=dim;d++){
        const date=y+"-"+String(m+1).padStart(2,"0")+"-"+String(d).padStart(2,"0");
        const n=counts[date]||0;
        if(n===0){html+='<div class="cd z">'+d+'</div>'}
        else{
          const lvl=n===1?"h1":(n<=3?"h2":"h3");
          html+='<div class="cd '+lvl+'" data-date="'+date+'" title="'+n+(n===1?' entry':' entries')
            +'" onclick="pickDay(\''+date+'\')">'+d+'</div>';
        }
      }
      html+='</div></div>';
    }
    html+='</div></div></div>';
  });
  document.getElementById('cal').innerHTML=html;
}
function updateCalendar(){
  const active=hasFilter();
  document.getElementById('leg-dim').style.display=active?'flex':'none';
  if(!active){
    document.querySelectorAll('.cd[data-date]').forEach(el=>el.classList.remove('dim'));
    return;
  }
  const matches=new Set(getFiltered().map(e=>e.date));
  document.querySelectorAll('.cd[data-date]').forEach(el=>{
    el.classList.toggle('dim',!matches.has(el.dataset.date));
  });
}
function pickDay(d){S.date=d;S.shown=PAGE;setView('browse');refresh()}

// Browse -------------------------------------------------------------------
function sortEntries(arr){
  return S.sort==='desc'?[...arr].sort((a,b)=>b.date<a.date?-1:1):[...arr].sort((a,b)=>a.date<b.date?-1:1);
}
function renderBrowse(){
  const res=sortEntries(getFiltered());
  document.getElementById('b-count').textContent=fmt(res.length)+' of '+fmt(E.length)+' entries';
  const empty=document.getElementById('b-empty');
  empty.style.display=res.length?'none':'block';
  document.getElementById('blist').innerHTML=res.slice(0,S.shown).map(card).join('');
  document.getElementById('more').style.display=res.length>S.shown?'block':'none';
}
function loadMore(){S.shown+=PAGE;renderBrowse()}
function toggleSort(){
  S.sort=S.sort==='desc'?'asc':'desc';
  document.getElementById('sort-btn').textContent=S.sort==='desc'?'Newest first':'Oldest first';
  renderBrowse();
}

// Pivotal ------------------------------------------------------------------
function renderPivotal(){
  const piv=E.filter(e=>e.piv);
  document.getElementById('p-count').textContent=fmt(piv.length)+' pivotal entries';
  document.getElementById('plist').innerHTML=piv.map(card).join('');
}

// ── Search & filters UI ──────────────────────────────────────────────────────
let qTimer=null;
document.getElementById('search').addEventListener('input',function(){
  clearTimeout(qTimer);
  const v=this.value;
  qTimer=setTimeout(()=>{
    S.q=v.toLowerCase().trim();S.shown=PAGE;
    document.getElementById('search-x').style.display=S.q?'block':'none';
    if(S.q&&S.view!=='browse')setView('browse');
    refresh();
  },200);
});
function clearSearch(){
  document.getElementById('search').value='';S.q='';
  document.getElementById('search-x').style.display='none';refresh();
}
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement.tagName!=='INPUT'&&document.activeElement.tagName!=='TEXTAREA'){
    e.preventDefault();document.getElementById('search').focus();
  }
  if(e.key==='Escape'){closeModal();closeDrawer()}
});

function buildDrawer(){
  const ct={mood:{},theme:{},type:{},year:{}};
  E.forEach(e=>{
    if(e.mood)ct.mood[e.mood]=(ct.mood[e.mood]||0)+1;
    if(e.type)ct.type[e.type]=(ct.type[e.type]||0)+1;
    ct.year[e.year]=(ct.year[e.year]||0)+1;
    e.themes.forEach(t=>ct.theme[t]=(ct.theme[t]||0)+1);
  });
  const pills=(obj,key,limit)=>Object.entries(obj).sort((a,b)=>b[1]-a[1]).slice(0,limit||999)
    .map(([v,n])=>'<span class="pill" data-set="'+key+'" data-v="'+esc(v)+'" onclick="togPill(this)">'
      +esc(v)+'<em>'+fmt(n)+'</em></span>').join('');
  document.getElementById('dr-body').innerHTML=
    '<div class="fsec"><h3>Year <span id="ct-years"></span></h3><div class="pills">'
      +Object.entries(ct.year).sort((a,b)=>b[0]-a[0]).map(([v,n])=>'<span class="pill" data-set="years" data-v="'+v+'" onclick="togPill(this)">'+v+'<em>'+fmt(n)+'</em></span>').join('')+'</div></div>'
    +'<div class="fsec"><h3>Entry type <span id="ct-types"></span></h3><div class="pills">'+pills(ct.type,'types')+'</div></div>'
    +'<div class="fsec"><h3>Mood <span id="ct-moods"></span></h3><div class="pills">'+pills(ct.mood,'moods')+'</div></div>'
    +'<div class="fsec"><h3>Themes <span id="ct-themes"></span></h3><div class="pills">'+pills(ct.theme,'themes',60)+'</div></div>';
}
function togPill(el){
  const set=S[el.dataset.set],v=el.dataset.v;
  set.has(v)?set.delete(v):set.add(v);
  S.shown=PAGE;refresh();
}
function openDrawer(){document.getElementById('drawer').classList.add('show');document.getElementById('scrim').classList.add('show')}
function closeDrawer(){document.getElementById('drawer').classList.remove('show');document.getElementById('scrim').classList.remove('show')}

function refresh(){
  // pill states
  document.querySelectorAll('.pill').forEach(p=>{
    p.classList.toggle('on',S[p.dataset.set]&&S[p.dataset.set].has(p.dataset.v));
  });
  ['years','types','moods','themes'].forEach(k=>{
    const el=document.getElementById('ct-'+k);
    if(el)el.textContent=S[k].size?S[k].size+' selected':'';
  });
  const nf=S.years.size+S.types.size+S.moods.size+S.themes.size;
  document.getElementById('fct').textContent=nf?' ('+nf+')':'';
  // chips
  const chips=[];
  if(S.date)chips.push(['date',S.date,S.date]);
  if(S.md)chips.push(['md','md',MONTHS_F[S.md[0]-1]+' '+S.md[1]+' across years']);
  S.years.forEach(v=>chips.push(['years',v,v]));
  S.types.forEach(v=>chips.push(['types',v,v]));
  S.moods.forEach(v=>chips.push(['moods',v,v]));
  S.themes.forEach(v=>chips.push(['themes',v,v]));
  if(S.q)chips.push(['q','q','&ldquo;'+esc(S.q)+'&rdquo;']);
  const bar=document.getElementById('chips');
  bar.classList.toggle('show',chips.length>0);
  bar.innerHTML=chips.map(([t,v,l])=>'<span class="chip"><b>'+l+'</b><button onclick="dropChip(\''+t+'\',\''+esc(String(v)).replace(/'/g,"\\'")+'\')">&times;</button></span>').join('')
    +(chips.length>1?'<button id="clear-all" onclick="clearAll()">clear all</button>':'');
  // views
  if(S.view==='browse')renderBrowse();
  if(S.view==='calendar')updateCalendar();
}
function dropChip(t,v){
  if(t==='date')S.date=null;else if(t==='md')S.md=null;
  else if(t==='q'){S.q='';document.getElementById('search').value='';document.getElementById('search-x').style.display='none'}
  else S[t].delete(v);
  S.shown=PAGE;refresh();
}
function clearAll(){
  S.q='';S.date=null;S.md=null;S.years.clear();S.types.clear();S.moods.clear();S.themes.clear();S.shown=PAGE;
  document.getElementById('search').value='';document.getElementById('search-x').style.display='none';
  refresh();
}

// ── On this day & random ─────────────────────────────────────────────────────
function onThisDay(){
  const now=new Date();
  S.md=[now.getMonth()+1,now.getDate()];S.date=null;S.shown=PAGE;
  setView('browse');refresh();
}
function randomEntry(){
  const pool=hasFilter()?getFiltered():E;
  if(!pool.length)return;
  const e=pool[Math.floor(Math.random()*pool.length)];
  document.getElementById('modal-body').innerHTML=
    '<div class="card-top"><span class="cdate" style="font-size:1.3em">'+dispDate(e)+'</span>'
    +'<span class="cwords">'+fmt(e.wc)+' words</span></div>'
    +'<div class="badges">'+(e.piv?'<span class="badge bp">&#9733; pivotal</span>':'')
    +(e.mood?'<span class="badge bm">'+esc(e.mood)+'</span>':'')
    +(e.type?'<span class="badge">'+esc(e.type)+'</span>':'')+'</div>'
    +(e.summary?'<div class="csum">'+esc(e.summary)+'</div>':'')
    +(e.piv&&e.pivr?'<div class="cpiv">&#9733; '+esc(e.pivr)+'</div>':'')
    +'<div class="cbody">'+esc(e.body)+'</div>';
  document.getElementById('modal').classList.add('show');
}
function closeModal(){document.getElementById('modal').classList.remove('show')}

// ── Theme ────────────────────────────────────────────────────────────────────
function applyTheme(t){
  document.documentElement.dataset.theme=t;
  document.getElementById('theme-btn').innerHTML=t==='dark'?'&#9788;':'&#9789;';
}
function toggleTheme(){
  const t=document.documentElement.dataset.theme==='dark'?'light':'dark';
  localStorage.setItem('jtheme',t);applyTheme(t);
}
applyTheme(localStorage.getItem('jtheme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));

// ── Insights ─────────────────────────────────────────────────────────────────
let insBuilt=false;
function vbarSVG(data,color){
  // data: [{l, v}]
  const W=820,H=210,P={t:12,r:6,b:26,l:46};
  const max=Math.max(...data.map(d=>d.v),1);
  const bw=(W-P.l-P.r)/data.length;
  let s='<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="xMidYMid meet">';
  for(let i=0;i<=3;i++){
    const yy=P.t+(H-P.t-P.b)*i/3, val=Math.round(max*(1-i/3));
    s+='<line x1="'+P.l+'" y1="'+yy+'" x2="'+(W-P.r)+'" y2="'+yy+'" stroke="var(--line)" stroke-width="1"/>'
      +'<text x="'+(P.l-6)+'" y="'+(yy+3)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+fmt(val)+'</text>';
  }
  data.forEach((d,i)=>{
    const h=(H-P.t-P.b)*d.v/max, x=P.l+i*bw;
    s+='<rect x="'+(x+bw*0.12)+'" y="'+(H-P.b-h)+'" width="'+(bw*0.76)+'" height="'+h
      +'" rx="3" fill="'+color+'"><title>'+d.l+': '+fmt(d.v)+'</title></rect>';
    const every=Math.ceil(data.length/16);
    if(i%every===0)s+='<text x="'+(x+bw/2)+'" y="'+(H-8)+'" text-anchor="middle" font-size="9.5" fill="var(--muted)">'+d.l+'</text>';
  });
  return s+'</svg>';
}
function stackSVG(labels,series){
  // series: [{name,color,values[]}]
  const W=820,H=230,P={t:12,r:6,b:26,l:46};
  const totals=labels.map((_,i)=>series.reduce((a,sr)=>a+sr.values[i],0));
  const max=Math.max(...totals,1), bw=(W-P.l-P.r)/labels.length;
  let s='<svg viewBox="0 0 '+W+' '+H+'">';
  for(let i=0;i<=3;i++){
    const yy=P.t+(H-P.t-P.b)*i/3, val=Math.round(max*(1-i/3));
    s+='<line x1="'+P.l+'" y1="'+yy+'" x2="'+(W-P.r)+'" y2="'+yy+'" stroke="var(--line)"/>'
      +'<text x="'+(P.l-6)+'" y="'+(yy+3)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+fmt(val)+'</text>';
  }
  labels.forEach((lab,i)=>{
    let y=H-P.b;const x=P.l+i*bw;
    series.forEach(sr=>{
      const h=(H-P.t-P.b)*sr.values[i]/max;
      if(h>0){y-=h;
        s+='<rect x="'+(x+bw*0.12)+'" y="'+y+'" width="'+(bw*0.76)+'" height="'+h+'" fill="'+sr.color
          +'"><title>'+lab+' &#183; '+sr.name+': '+fmt(sr.values[i])+'</title></rect>';}
    });
    const every=Math.ceil(labels.length/16);
    if(i%every===0)s+='<text x="'+(x+bw/2)+'" y="'+(H-8)+'" text-anchor="middle" font-size="9.5" fill="var(--muted)">'+lab+'</text>';
  });
  return s+'</svg>';
}
function lineSVG(labels,series){
  const W=820,H=230,P={t:12,r:10,b:26,l:46};
  const max=Math.max(...series.flatMap(s=>s.values),1);
  const xw=(W-P.l-P.r)/Math.max(labels.length-1,1);
  let s='<svg viewBox="0 0 '+W+' '+H+'">';
  for(let i=0;i<=3;i++){
    const yy=P.t+(H-P.t-P.b)*i/3, val=Math.round(max*(1-i/3));
    s+='<line x1="'+P.l+'" y1="'+yy+'" x2="'+(W-P.r)+'" y2="'+yy+'" stroke="var(--line)"/>'
      +'<text x="'+(P.l-6)+'" y="'+(yy+3)+'" text-anchor="end" font-size="9" fill="var(--muted)">'+fmt(val)+'</text>';
  }
  labels.forEach((lab,i)=>{
    const every=Math.ceil(labels.length/16);
    if(i%every===0)s+='<text x="'+(P.l+i*xw)+'" y="'+(H-8)+'" text-anchor="middle" font-size="9.5" fill="var(--muted)">'+lab+'</text>';
  });
  series.forEach(sr=>{
    const pts=sr.values.map((v,i)=>(P.l+i*xw)+','+(H-P.b-(H-P.t-P.b)*v/max)).join(' ');
    s+='<polyline points="'+pts+'" fill="none" stroke="'+sr.color+'" stroke-width="2" stroke-linejoin="round"/>';
    sr.values.forEach((v,i)=>{
      s+='<circle cx="'+(P.l+i*xw)+'" cy="'+(H-P.b-(H-P.t-P.b)*v/max)+'" r="2.6" fill="'+sr.color
        +'"><title>'+labels[i]+' &#183; '+sr.name+': '+fmt(v)+'</title></circle>';
    });
  });
  return s+'</svg>';
}
function hbars(data,maxOverride){
  const max=maxOverride||Math.max(...data.map(d=>d.v),1);
  return data.map(d=>'<div class="hrow"><span class="hl" title="'+esc(d.l)+'">'+esc(d.l)+'</span>'
    +'<div class="hb-track"><div class="hb" style="width:'+(100*d.v/max)+'%;background:'+(d.c||'var(--accent)')+'"></div></div>'
    +'<span class="hv">'+fmt(d.v)+'</span></div>').join('');
}
function legend(series){
  return '<div class="chlegend">'+series.map(s=>'<span class="leg"><span class="dot" style="background:'+s.color+'"></span>'+esc(s.name)+'</span>').join('')+'</div>';
}

function buildInsights(){
  insBuilt=true;
  const years=[...YEARS].sort((a,b)=>a-b).map(String);
  const byYear={},wordsYear={},moodCt={},typeCt={},themeCt={},monthCt=new Array(12).fill(0),dowCt=new Array(7).fill(0);
  E.forEach(e=>{
    byYear[e.year]=(byYear[e.year]||0)+1;
    wordsYear[e.year]=(wordsYear[e.year]||0)+e.wc;
    if(e.mood)moodCt[e.mood]=(moodCt[e.mood]||0)+1;
    if(e.type)typeCt[e.type]=(typeCt[e.type]||0)+1;
    e.themes.forEach(t=>themeCt[t]=(themeCt[t]||0)+1);
    monthCt[e.month-1]++;
    dowCt[(new Date(e.year,e.month-1,e.day).getDay()+6)%7]++;
  });
  const totalWords=E.reduce((a,e)=>a+e.wc,0);
  const activeDays=Object.keys(counts).length;
  // longest streak of consecutive days with entries
  const dates=Object.keys(counts).sort();
  let streak=1,best=dates.length?1:0;
  for(let i=1;i<dates.length;i++){
    if(new Date(dates[i])-new Date(dates[i-1])===86400000){streak++;best=Math.max(best,streak)}
    else streak=1;
  }
  const topMoods=Object.entries(moodCt).sort((a,b)=>b[1]-a[1]);
  const topThemes=Object.entries(themeCt).sort((a,b)=>b[1]-a[1]);
  const topTypes=Object.entries(typeCt).sort((a,b)=>b[1]-a[1]);
  const moodColor={};topMoods.forEach(([m],i)=>moodColor[m]=PALETTE[i%PALETTE.length]);

  const perYearSeries=(keys,getKey)=>keys.map(([k],i)=>({
    name:k,color:PALETTE[i%PALETTE.length],
    values:years.map(y=>E.filter(e=>String(e.year)===y&&getKey(e)===k).length)
  }));
  const moodSeries=perYearSeries(topMoods.slice(0,6),e=>e.mood);
  const typeSeries=perYearSeries(topTypes.slice(0,6),e=>e.type);
  const themeSeries=topThemes.slice(0,7).map(([t],i)=>({
    name:t,color:PALETTE[i%PALETTE.length],
    values:years.map(y=>E.filter(e=>String(e.year)===y&&e.themes.includes(t)).length)
  }));

  document.getElementById('ins').innerHTML=
    '<div class="stats">'
    +'<div class="stat"><div class="v">'+fmt(E.length)+'</div><div class="l">Entries</div></div>'
    +'<div class="stat"><div class="v">'+fmt(totalWords)+'</div><div class="l">Words written</div></div>'
    +'<div class="stat"><div class="v">'+fmt(activeDays)+'</div><div class="l">Days written</div></div>'
    +'<div class="stat"><div class="v">'+fmt(Math.round(totalWords/Math.max(E.length,1)))+'</div><div class="l">Avg words / entry</div></div>'
    +'<div class="stat"><div class="v">'+fmt(best)+'</div><div class="l">Longest day streak</div></div>'
    +'<div class="stat"><div class="v">'+fmt(E.filter(e=>e.piv).length)+'</div><div class="l">Pivotal entries</div></div>'
    +'</div>'
    +'<div class="chartcard"><h3>Entries per year</h3><div class="note">How much you wrote, year by year</div>'
      +vbarSVG(years.map(y=>({l:y,v:byYear[y]||0})),'var(--accent)')+'</div>'
    +'<div class="chartcard"><h3>Words per year</h3><div class="note">Total volume of writing</div>'
      +vbarSVG(years.map(y=>({l:y,v:wordsYear[y]||0})),'#3a7ca5')+'</div>'
    +'<div class="chartcard"><h3>Mood over time</h3><div class="note">Top 6 moods, stacked by year</div>'
      +stackSVG(years,moodSeries)+legend(moodSeries)+'</div>'
    +'<div class="chartcard"><h3>Entry types over time</h3><div class="note">Top 6 types, stacked by year</div>'
      +stackSVG(years,typeSeries)+legend(typeSeries)+'</div>'
    +'<div class="chartcard"><h3>Themes over time</h3><div class="note">Top 7 themes across the years</div>'
      +lineSVG(years,themeSeries)+legend(themeSeries)+'</div>'
    +'<div class="grid2">'
    +'<div class="chartcard"><h3>Top moods</h3><div class="note">All-time distribution</div>'
      +hbars(topMoods.slice(0,10).map(([l,v])=>({l,v,c:moodColor[l]})))+'</div>'
    +'<div class="chartcard"><h3>Top themes</h3><div class="note">Most recurring themes</div>'
      +hbars(topThemes.slice(0,10).map(([l,v])=>({l,v})))+'</div>'
    +'<div class="chartcard"><h3>Writing by month</h3><div class="note">Seasonal rhythm</div>'
      +hbars(monthCt.map((v,i)=>({l:MONTHS_F[i],v})))+'</div>'
    +'<div class="chartcard"><h3>Writing by weekday</h3><div class="note">Which days you write most</div>'
      +hbars(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].map((l,i)=>({l,v:dowCt[i]})))+'</div>'
    +'</div>';
}

// ── Scroll-top ───────────────────────────────────────────────────────────────
window.addEventListener('scroll',()=>{
  document.getElementById('top-btn').style.display=window.scrollY>600?'block':'none';
},{passive:true});

// ── Init ─────────────────────────────────────────────────────────────────────
document.getElementById('pivn').textContent=fmt(E.filter(e=>e.piv).length);
buildCalendar();
buildDrawer();
refresh();
</script>
</body>
</html>
"""


def build_html(entries: list[dict]) -> str:
    entries_json = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    # Prevent the embedded JSON from terminating the <script> block early
    entries_json = entries_json.replace("</", "<\\/")
    years = sorted({e["year"] for e in entries})
    return (
        TEMPLATE
        .replace("__ENTRIES__", entries_json)
        .replace("__TOTAL__", f"{len(entries):,}")
        .replace("__YMIN__", str(years[0]))
        .replace("__YMAX__", str(years[-1]))
        .replace("__GENERATED__", datetime.now().strftime("%B %d, %Y"))
    )


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
