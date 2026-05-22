# Talk to Your Journal

A system to help you visualize and chat with your Journal — extracts, classifies, and makes a years-long writing archive searchable and explorable.

Wrote this routine to help me semantically map and archive around 3,500+ journal entries that I made from 2010-2026 into a searchable interface. It also uses the Claude Haiku model to help me chat with my Journal, and explore the evolution of my thoughts on different topics over the years.

> **Privacy note:** All journal data (`data/`) is excluded from this repository via `.gitignore`. Only the code and pipeline are public.

---

## Demo

**HTML Archive** — calendar heatmap with filtering by mood, theme, and entry type:

![Journal Archive](GIFs/Journal%20Archive.gif)

**Chat Interface** — ask natural-language questions, grounded in semantically retrieved entries:

![Journal Chat](GIFs/Journal%20Chat.gif)

---

## What it does

Gmail Drafts used as a private journal → pulled into a local SQLite database → tagged by an LLM → explored through three interfaces:

| Interface | Description |
|-----------|-------------|
| **HTML archive** | Self-contained, offline-ready browser app with calendar heatmap, filters, and full-text search |
| **Streamlit app** | Local analytics dashboard — mood trends, theme frequency, word volume by year |
| **Chat interface** | Ask natural-language questions about your journal; answers are grounded in semantically retrieved entries |

---

## Pipeline

```
Gmail Drafts
    │
    ▼
src/extract.py      Phase 1 — Pull all drafts into SQLite (incremental, skips existing)
    │
    ▼
src/tag.py          Phase 2 — Claude API classifies each entry:
    │                          entry_type, mood, themes, entities, summary, is_pivotal
    │                          Also builds FTS5 full-text search index
    ▼
src/embed.py        Phase 3 — Sentence-transformer embeddings for semantic search
    │
    ├──▶ src/export.py    → data/journal.html  (self-contained archive, ~6 MB)
    └──▶ src/server.py    → http://localhost:5000  (Flask chat app)
         src/app.py       → http://localhost:8501  (Streamlit analytics)
```

---

## Tech stack

- **Gmail API** (Google OAuth) — draft extraction
- **SQLite + FTS5** — storage and full-text search
- **Anthropic Claude** — entry classification and chat
- **Sentence Transformers** (`all-MiniLM-L6-v2`) — semantic embeddings
- **Flask** — chat API server
- **Streamlit + Plotly** — analytics UI
- **Google Drive API** — optional HTML archive upload

---

## Setup

### 1. Google Cloud (one-time)

1. [console.cloud.google.com](https://console.cloud.google.com) — create a project
2. Enable **Gmail API** and **Google Drive API**
3. OAuth consent screen → External → add yourself as a test user
4. Create Credentials → OAuth client ID → Desktop app → download as `credentials.json`

### 2. Local environment

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment variable

```bash
export ANTHROPIC_API_KEY=your-key-here   # Mac/Linux
$env:ANTHROPIC_API_KEY="your-key-here"   # Windows PowerShell
```

---

## Running the pipeline

```bash
# Pull new drafts (incremental — safe to re-run anytime)
python -m src.extract

# Tag untagged entries with Claude
python -m src.tag

# Build semantic embeddings
python -m src.embed

# Export HTML archive
python -m src.export
```

---

## Running the interfaces

```bash
# Chat app (Flask)
python -m src.server
# → http://localhost:5000

# Analytics dashboard (Streamlit)
streamlit run src/app.py
# → http://localhost:8501
```

---

## Project structure

```
journal-archive/
├── src/
│   ├── extract.py      Phase 1: Gmail → SQLite
│   ├── tag.py          Phase 2: Claude tagging + FTS5
│   ├── embed.py        Phase 3: Sentence-transformer embeddings
│   ├── export.py       Phase 4a: HTML archive generator
│   ├── server.py       Phase 4b: Flask chat server
│   ├── app.py          Phase 4c: Streamlit analytics
│   ├── gdrive.py       Google Drive upload helper
│   └── chat.py         Chat utilities
├── data/               ← gitignored (your private archive lives here)
│   ├── journal.db
│   └── journal.html
├── credentials.json    ← gitignored (your OAuth secret)
├── token.json          ← gitignored (auto-created on first auth)
└── requirements.txt
```
