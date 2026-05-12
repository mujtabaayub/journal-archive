"""
Phase 1: Extract all Gmail drafts into a local SQLite database.

Place `credentials.json` (OAuth desktop client) in the project root.
First run will open a browser for consent and create `token.json`.

Usage (run from project root):
    python -m src.extract              # incremental
    python -m src.extract --reset      # wipe DB and restart
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email import message_from_bytes
from email.message import Message
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Config ---------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DB_PATH = ROOT / "data" / "journal.db"
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.json"
SLEEP_BETWEEN_CALLS = 0.05

# --- Auth -----------------------------------------------------------------

def get_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                sys.exit(
                    f"Missing {CREDENTIALS_PATH}. See README for setup instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# --- Schema ---------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    draft_id      TEXT PRIMARY KEY,
    message_id    TEXT,
    thread_id     TEXT,
    gmail_date    TEXT,
    subject       TEXT,
    snippet       TEXT,
    body_text     TEXT,
    body_html     TEXT,
    headers_json  TEXT,
    word_count    INTEGER,
    fetched_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drafts_gmail_date ON drafts(gmail_date);
"""

def init_db(reset: bool = False) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# --- Parsing helpers ------------------------------------------------------

def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def extract_bodies(raw_b64: str) -> tuple[str, str]:
    raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("ASCII"))
    msg = message_from_bytes(raw_bytes)

    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get("Content-Disposition", "").startswith("attachment"):
                continue
            if ctype == "text/plain":
                plain_parts.append(_decode_part(part))
            elif ctype == "text/html":
                html_parts.append(_decode_part(part))
    else:
        ctype = msg.get_content_type()
        decoded = _decode_part(msg)
        if ctype == "text/html":
            html_parts.append(decoded)
        else:
            plain_parts.append(decoded)

    plain = "\n\n".join(p.strip() for p in plain_parts if p.strip())
    html = "\n\n".join(h for h in html_parts if h.strip())

    if not plain and html:
        import re
        plain = re.sub(r"<[^>]+>", "", html)
        plain = re.sub(r"\s+\n", "\n", plain).strip()

    return plain, html


def headers_to_dict(msg: Message) -> dict:
    keep = {"From", "To", "Cc", "Bcc", "Subject", "Date", "Message-ID"}
    return {k: v for k, v in msg.items() if k in keep}


# --- Main extraction loop -------------------------------------------------

def list_all_draft_ids(service) -> list[str]:
    ids: list[str] = []
    page_token = None
    while True:
        resp = service.users().drafts().list(
            userId="me", maxResults=500, pageToken=page_token
        ).execute()
        ids.extend(d["id"] for d in resp.get("drafts", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_and_store(service, conn: sqlite3.Connection, draft_id: str) -> bool:
    try:
        draft = service.users().drafts().get(
            userId="me", id=draft_id, format="raw"
        ).execute()
    except HttpError as e:
        print(f"  ! HTTP error on {draft_id}: {e}")
        return False

    message = draft.get("message", {})
    raw = message.get("raw")
    if not raw:
        return False

    raw_bytes = base64.urlsafe_b64decode(raw.encode("ASCII"))
    msg = message_from_bytes(raw_bytes)

    plain, html = extract_bodies(raw)
    headers = headers_to_dict(msg)

    internal_ms = int(message.get("internalDate", "0"))
    gmail_date = (
        datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc).isoformat()
        if internal_ms else None
    )

    conn.execute(
        """INSERT OR REPLACE INTO drafts
           (draft_id, message_id, thread_id, gmail_date, subject, snippet,
            body_text, body_html, headers_json, word_count, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            draft_id,
            message.get("id"),
            message.get("threadId"),
            gmail_date,
            headers.get("Subject", ""),
            message.get("snippet", ""),
            plain,
            html,
            json.dumps(headers, ensure_ascii=False),
            len(plain.split()) if plain else 0,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return True


def existing_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT draft_id FROM drafts")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe DB and start fresh")
    args = parser.parse_args()

    conn = init_db(reset=args.reset)
    service = get_service()

    print("Listing draft IDs (this can take ~30s for thousands)...")
    all_ids = list_all_draft_ids(service)
    print(f"Found {len(all_ids)} drafts in Gmail.")

    already = existing_ids(conn)
    todo = [d for d in all_ids if d not in already]
    print(f"{len(already)} already in DB. {len(todo)} to fetch.")

    failures = 0
    for i, draft_id in enumerate(todo, 1):
        if not fetch_and_store(service, conn, draft_id):
            failures += 1
        if i % 50 == 0:
            conn.commit()
            print(f"  {i}/{len(todo)} fetched ({failures} failures so far)")
        time.sleep(SLEEP_BETWEEN_CALLS)

    conn.commit()
    conn.close()
    print(f"\nDone. {len(todo) - failures} new drafts stored. {failures} failures.")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
