"""
Phase 2: Tag all drafts using Claude API.

Adds per-entry: entry_type, themes, entities, mood, summary, is_pivotal.
Also builds FTS5 full-text search index over subject + body.

Usage (from project root):
    python -m src.tag              # process untagged drafts
    python -m src.tag --reset      # wipe tags and restart
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"
SLEEP = 0.1

TAGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    draft_id       TEXT PRIMARY KEY REFERENCES drafts(draft_id),
    entry_type     TEXT,
    themes_json    TEXT,
    entities_json  TEXT,
    mood           TEXT,
    summary        TEXT,
    is_pivotal     INTEGER DEFAULT 0,
    pivotal_reason TEXT,
    tagged_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tags_entry_type ON tags(entry_type);
CREATE INDEX IF NOT EXISTS idx_tags_mood       ON tags(mood);
CREATE INDEX IF NOT EXISTS idx_tags_is_pivotal ON tags(is_pivotal);

CREATE VIRTUAL TABLE IF NOT EXISTS drafts_fts USING fts5(
    subject,
    body_text,
    content='drafts',
    content_rowid='rowid'
);
"""

SYSTEM_PROMPT = """You analyze personal journal entries written over many years by the same person.

Entry type definitions:
- experience_recap: recounting an event, trip, conversation, or experience that happened
- emotional_processing: working through feelings, problems, conflicts, or difficult inner states
- appreciation: expressing love or admiration for a person, book, film, piece of music, or place
- notes: practical notes for work, study, fitness, or health — more functional than personal
- reflection: philosophical or introspective thinking not tied to a specific event or emotion
- other: genuinely doesn't fit above

A pivotal entry marks a real turning point — a major realization, a significant decision, a shift in values or worldview, or the clear beginning or end of a chapter in the writer's life. Most entries are NOT pivotal. Only flag one if you're confident it would read as a hinge moment to someone reviewing this archive years later."""

TAG_TOOL = {
    "name": "tag_entry",
    "description": "Tag a journal entry with structured metadata",
    "input_schema": {
        "type": "object",
        "properties": {
            "entry_type": {
                "type": "string",
                "enum": [
                    "experience_recap",
                    "emotional_processing",
                    "appreciation",
                    "notes",
                    "reflection",
                    "other",
                ],
                "description": "The primary type of this entry",
            },
            "themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-5 specific themes or topics (e.g. grief, identity, running, friendship)",
            },
            "entities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Named people, books, films, places, or organizations mentioned",
            },
            "mood": {
                "type": "string",
                "description": "Single word capturing the emotional tone (e.g. reflective, anxious, joyful, melancholic, energized, neutral)",
            },
            "summary": {
                "type": "string",
                "description": "1-2 sentence summary of what this entry is about",
            },
            "is_pivotal": {
                "type": "boolean",
                "description": "True only if this reads as a genuine turning point or major realization — rare",
            },
            "pivotal_reason": {
                "type": "string",
                "description": "One sentence explaining why this is pivotal. Required when is_pivotal is true, omit otherwise.",
            },
        },
        "required": ["entry_type", "themes", "entities", "mood", "summary", "is_pivotal"],
    },
    "cache_control": {"type": "ephemeral"},
}


def init_db(conn: sqlite3.Connection, reset: bool = False) -> None:
    if reset:
        conn.execute("DROP TABLE IF EXISTS tags")
        conn.execute("DROP TABLE IF EXISTS drafts_fts")
    conn.executescript(TAGS_SCHEMA)
    conn.commit()


def build_fts(conn: sqlite3.Connection) -> None:
    print("Building FTS5 index...")
    conn.execute("INSERT INTO drafts_fts(drafts_fts) VALUES('rebuild')")
    conn.commit()
    print("FTS5 index built.")


def get_untagged(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        """
        SELECT d.draft_id, d.subject, d.body_text, d.gmail_date
        FROM drafts d
        LEFT JOIN tags t ON d.draft_id = t.draft_id
        WHERE t.draft_id IS NULL
          AND d.body_text IS NOT NULL AND d.body_text != ''
        ORDER BY d.gmail_date
        """
    ).fetchall()


def tag_entry(client: anthropic.Anthropic, date: str, subject: str, body: str) -> dict:
    header = f"Date: {date}\nSubject: {subject}\n\n" if subject else f"Date: {date}\n\n"
    content = header + body[:4000]

    for attempt in range(4):
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[TAG_TOOL],
                tool_choice={"type": "tool", "name": "tag_entry"},
                messages=[{"role": "user", "content": content}],
            )
            for block in resp.content:
                if block.type == "tool_use":
                    return block.input
            raise ValueError("No tool_use block returned")
        except anthropic.RateLimitError:
            wait = 2 ** attempt * 5
            print(f"    Rate limited, waiting {wait}s...")
            time.sleep(wait)
        except anthropic.APIError as e:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Failed after 4 attempts")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe tags and restart")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    init_db(conn, reset=args.reset)

    client = anthropic.Anthropic()

    untagged = get_untagged(conn)
    print(f"{len(untagged)} drafts to tag.")

    failures = 0
    for i, (draft_id, subject, body, date) in enumerate(untagged, 1):
        try:
            result = tag_entry(client, date or "", subject or "", body)
            conn.execute(
                """INSERT OR REPLACE INTO tags
                   (draft_id, entry_type, themes_json, entities_json,
                    mood, summary, is_pivotal, pivotal_reason, tagged_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    draft_id,
                    result.get("entry_type"),
                    json.dumps(result.get("themes", []), ensure_ascii=False),
                    json.dumps(result.get("entities", []), ensure_ascii=False),
                    result.get("mood"),
                    result.get("summary"),
                    1 if result.get("is_pivotal") else 0,
                    result.get("pivotal_reason"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception as e:
            print(f"  ! {draft_id}: {e}")
            failures += 1

        if i % 50 == 0:
            conn.commit()
            print(f"  {i}/{len(untagged)} tagged ({failures} failures so far)")

        time.sleep(SLEEP)

    conn.commit()
    build_fts(conn)
    conn.close()
    print(f"\nDone. {len(untagged) - failures} tagged, {failures} failures.")
    print("Pivotal entries: SELECT d.gmail_date, t.pivotal_reason FROM drafts d JOIN tags t ON d.draft_id=t.draft_id WHERE t.is_pivotal=1 ORDER BY d.gmail_date;")


if __name__ == "__main__":
    main()
