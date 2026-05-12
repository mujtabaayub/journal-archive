"""
Phase 4c: Build semantic embeddings for all journal entries.

Run once (from project root):
    python -m src.embed

Re-run anytime new entries are added — skips already-embedded entries.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH = 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    draft_id TEXT PRIMARY KEY REFERENCES drafts(draft_id),
    vec      BLOB NOT NULL
);
"""


def entry_text(row: tuple) -> str:
    draft_id, subject, body, mood, entry_type, themes_json, summary = row
    import json
    themes = ", ".join(json.loads(themes_json) if themes_json else [])
    parts = []
    if summary:   parts.append(summary)
    if mood:      parts.append(f"Mood: {mood}")
    if themes:    parts.append(f"Themes: {themes}")
    if body:      parts.append(body[:600])
    return " | ".join(parts)


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(SCHEMA)
    conn.commit()

    rows = conn.execute("""
        SELECT d.draft_id, d.subject, d.body_text,
               t.mood, t.entry_type, t.themes_json, t.summary
        FROM drafts d
        JOIN tags t ON d.draft_id = t.draft_id
        LEFT JOIN embeddings e ON d.draft_id = e.draft_id
        WHERE e.draft_id IS NULL
    """).fetchall()

    if not rows:
        print("All entries already embedded.")
        conn.close()
        return

    print(f"Loading model '{MODEL_NAME}'...")
    model = SentenceTransformer(MODEL_NAME)

    print(f"Embedding {len(rows)} entries...")
    texts = [entry_text(r) for r in rows]
    ids   = [r[0] for r in rows]

    for i in range(0, len(texts), BATCH):
        batch_texts = texts[i:i+BATCH]
        batch_ids   = ids[i:i+BATCH]
        vecs = model.encode(batch_texts, normalize_embeddings=True, show_progress_bar=False)
        conn.executemany(
            "INSERT OR REPLACE INTO embeddings (draft_id, vec) VALUES (?, ?)",
            [(bid, vec.astype(np.float32).tobytes()) for bid, vec in zip(batch_ids, vecs)],
        )
        conn.commit()
        print(f"  {min(i+BATCH, len(texts))}/{len(texts)}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
