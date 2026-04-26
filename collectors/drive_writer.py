"""
collectors/drive_writer.py
===========================
Google Drive write helper — saves and retrieves agent-generated files.

Uses the same BigQuery service account. The service account email must be
shared on the target Drive folder with *Editor* access.

One-time setup:
  1. Enable "Google Drive API" in Google Cloud Console (same project as BQ).
  2. Find the service-account email in GOOGLE_APPLICATION_CREDENTIALS_JSON
     (field: client_email).
  3. Share GDRIVE_REPORTS_FOLDER_ID folder with that email → Editor.

Env vars:
  GDRIVE_REPORTS_FOLDER_ID  — ID of the Drive folder where reports are saved.
                               Defaults to same as GDRIVE_FOLDER_ID.
  GDRIVE_FOLDER_ID           — root shared folder (set from memory/10_google_drive.md)
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# Write scope: allows creating / updating files owned by the service account.
# Combined with readonly for browsing.
_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # write files the app owns
    "https://www.googleapis.com/auth/drive.readonly",  # read any shared file
]

REPORTS_FOLDER_ID = (
    os.getenv("GDRIVE_REPORTS_FOLDER_ID")
    or os.getenv("GDRIVE_FOLDER_ID", "1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74")
)


def _credentials():
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw:
        return service_account.Credentials.from_service_account_info(
            json.loads(raw), scopes=_SCOPES
        )
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.exists(path):
        return service_account.Credentials.from_service_account_file(
            path, scopes=_SCOPES
        )
    raise RuntimeError(
        "No Google credentials. Set GOOGLE_APPLICATION_CREDENTIALS_JSON "
        "or GOOGLE_APPLICATION_CREDENTIALS."
    )


def _client():
    return build("drive", "v3", credentials=_credentials(), cache_discovery=False)


# ─── Upload ────────────────────────────────────────────────────────────────────

def upload_html(
    html_content: str | bytes,
    filename: str,
    folder_id: str = REPORTS_FOLDER_ID,
) -> str:
    """
    Upload or update an HTML file in the specified Drive folder.
    If a file with the same name already exists, it is updated in-place
    so the share URL stays stable.

    Args:
        html_content: HTML string or bytes to upload.
        filename:     e.g. "latest.html" or "2026-04-26.html"
        folder_id:    Drive folder to upload into.

    Returns the Drive file ID.
    """
    if isinstance(html_content, str):
        html_content = html_content.encode("utf-8")

    svc = _client()
    media = MediaIoBaseUpload(
        io.BytesIO(html_content), mimetype="text/html", resumable=False
    )

    # Check if file already exists in folder
    q = (
        f"name = '{filename}' and '{folder_id}' in parents "
        "and trashed = false"
    )
    existing = (
        svc.files()
        .list(q=q, fields="files(id,name)", spaces="drive")
        .execute()
        .get("files", [])
    )

    if existing:
        file_id = existing[0]["id"]
        svc.files().update(fileId=file_id, media_body=media).execute()
        print(f"[drive] Updated {filename} (id={file_id})")
    else:
        meta = {"name": filename, "parents": [folder_id], "mimeType": "text/html"}
        result = (
            svc.files()
            .create(body=meta, media_body=media, fields="id")
            .execute()
        )
        file_id = result["id"]
        print(f"[drive] Created {filename} (id={file_id})")

    return file_id


def download_html(filename: str, folder_id: str = REPORTS_FOLDER_ID) -> Optional[bytes]:
    """
    Download an HTML file from Drive by name. Returns raw bytes, or None
    if the file doesn't exist.
    """
    svc = _client()
    q = (
        f"name = '{filename}' and '{folder_id}' in parents "
        "and trashed = false"
    )
    files = (
        svc.files()
        .list(q=q, fields="files(id,name)", spaces="drive")
        .execute()
        .get("files", [])
    )
    if not files:
        return None
    file_id = files[0]["id"]
    req = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def save_report_to_drive(html_path: Path | str) -> Optional[str]:
    """
    Upload a report HTML file to Drive. Uploads both the dated file and
    updates latest.html. Returns the Drive file ID of latest.html, or None
    on failure.

    Called by reports/render.py after saving locally.
    """
    html_path = Path(html_path)
    if not html_path.exists():
        print(f"[drive] File not found: {html_path}")
        return None

    content = html_path.read_bytes()
    filename = html_path.name

    try:
        file_id = upload_html(content, filename)
        # Also keep latest.html in sync (overwrite)
        if filename != "latest.html":
            upload_html(content, "latest.html")
        return file_id
    except Exception as e:
        print(f"[drive] Upload failed for {filename}: {e}")
        return None


# ─── Fallback loader (used by Flask app) ──────────────────────────────────────

def load_report_from_drive(report_date: str | None = None) -> Optional[bytes]:
    """
    Download a report from Drive for serving.

    Args:
        report_date: "YYYY-MM-DD" or None for latest.

    Returns raw HTML bytes, or None if not found.
    """
    filename = "latest.html" if not report_date else f"{report_date}.html"
    try:
        return download_html(filename)
    except Exception as e:
        print(f"[drive] Download failed for {filename}: {e}")
        return None
