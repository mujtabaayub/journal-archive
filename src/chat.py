"""
Phase 4: Chat interface — ask questions about your journal.

Usage (from project root):
    python -m src.chat
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"

SYSTEM = """You are a thoughtful assistant with access to excerpts from the user's personal journal.
The entries span many years and cover a wide range of experiences, emotions, and reflections.
Answer questions grounded in the entries provided. If the entries don't contain enough to answer well, say so.
Be direct and personal — you're helping someone understand their own life and writing."""


STOP_WORDS = {
    "a","an","the","is","are","was","were","be","been","being","have","has","had",
    "do","does","did","will","would","could","should","may","might","shall","can",
    "i","you","he","she","it","we","they","me","him","her","us","them","my","your",
    "how","what","when","where","who","which","why","many","much","times","often",
    "about","across","after","along","and","any","because","but","by","for","from",
    "in","into","of","on","or","over","so","than","that","this","through","to",
    "up","with","number","instances","mention","mentions","mentioned","refer","refers",
    "entries","entry","journal","ever","all","most","more","some","there","their",
    "tell","show","describe","find","get","give","make","see","know","think","feel",
}

def extract_terms(query: str) -> str:
    words = [w.strip('.,?!') for w in query.lower().split()]
    terms = [w for w in words if w and w not in STOP_WORDS and len(w) > 2]
    return " OR ".join(terms) if terms else query


def search(conn: sqlite3.Connection, query: str, limit: int = 15) -> list[dict]:
    fts_query = extract_terms(query)
    rows = conn.execute(
        """
        SELECT d.gmail_date, d.subject, d.body_text,
               t.mood, t.entry_type, t.summary
        FROM drafts_fts
        JOIN drafts d ON drafts_fts.rowid = d.rowid
        JOIN tags   t ON d.draft_id = t.draft_id
        WHERE drafts_fts MATCH ?
        ORDER BY drafts_fts.rank
        LIMIT ?
        """,
        (fts_query, limit),
    ).fetchall()
    return [
        {
            "date":    r[0][:10] if r[0] else "",
            "subject": r[1] or "",
            "body":    (r[2] or "")[:1500],
            "mood":    r[3] or "",
            "type":    (r[4] or "").replace("_", " "),
            "summary": r[5] or "",
        }
        for r in rows
    ]


def format_entries(entries: list[dict]) -> str:
    parts = []
    for e in entries:
        parts.append(
            f"[{e['date']} · {e['mood']} · {e['type']}]\n"
            f"Summary: {e['summary']}\n"
            f"{e['body']}"
        )
    return "\n\n---\n\n".join(parts)


def ask(client: anthropic.Anthropic, history: list[dict], question: str, context: str) -> str:
    history.append({
        "role": "user",
        "content": f"Journal entries relevant to my question:\n\n{context}\n\n---\n\nMy question: {question}",
    })
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM,
        messages=history,
    )
    answer = resp.content[0].text
    history.append({"role": "assistant", "content": answer})
    return answer


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    client = anthropic.Anthropic()
    history: list[dict] = []

    print("Journal chat — type your question, or 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not question:
            continue
        if question.lower() in {"quit", "exit", "q"}:
            print("Bye.")
            break

        entries = search(conn, question)
        if not entries:
            print("Assistant: I couldn't find any relevant entries for that query.\n")
            continue

        context = format_entries(entries)
        answer = ask(client, history, question, context)
        print(f"\nAssistant: {answer}\n")

    conn.close()


if __name__ == "__main__":
    main()
