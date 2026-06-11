"""
Upload or update journal.html in Google Drive.

Uses a separate token (drive_token.json) so Gmail auth is unaffected.
On first run, opens a browser for Drive consent.
The Drive file ID is stored in data/drive_file_id.txt so subsequent
runs update the same file rather than creating a new one.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"
DRIVE_TOKEN_PATH = ROOT / "drive_token.json"
DRIVE_FILE_ID_PATH = ROOT / "data" / "drive_file_id.txt"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
MIME = "text/html"
FILENAME = "journal.html"


def _get_service():
    creds = None
    if DRIVE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(DRIVE_TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Drive token refresh failed ({e}); starting fresh consent flow...")
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(host="127.0.0.1", port=8085)
        DRIVE_TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload(local_path: Path) -> str:
    """Upload or update journal.html in Drive. Returns the shareable file URL."""
    service = _get_service()
    media = MediaFileUpload(str(local_path), mimetype=MIME, resumable=False)

    if DRIVE_FILE_ID_PATH.exists():
        file_id = DRIVE_FILE_ID_PATH.read_text().strip()
        try:
            service.files().update(fileId=file_id, media_body=media).execute()
            return f"https://drive.google.com/file/d/{file_id}/view"
        except Exception:
            pass  # file was deleted or moved — fall through to create a new one

    result = service.files().create(
        body={"name": FILENAME},
        media_body=media,
        fields="id",
    ).execute()
    file_id = result["id"]
    DRIVE_FILE_ID_PATH.write_text(file_id)
    return f"https://drive.google.com/file/d/{file_id}/view"
