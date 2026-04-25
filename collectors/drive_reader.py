"""Google Drive read helper.

Reuses the BigQuery service account — requires the service-account email to
be shared as a Viewer on the target folder, and the Google Drive API to be
enabled on the same GCP project as BigQuery.

See memory/10_google_drive.md for one-time setup.
"""
from __future__ import annotations

import io
import json
import os
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_FOLDER_ID = os.getenv(
    "GDRIVE_FOLDER_ID", "1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74"
)


def _credentials():
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw:
        return service_account.Credentials.from_service_account_info(
            json.loads(raw), scopes=SCOPES
        )
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.exists(path):
        return service_account.Credentials.from_service_account_file(
            path, scopes=SCOPES
        )
    raise RuntimeError(
        "No Google credentials found. Set GOOGLE_APPLICATION_CREDENTIALS_JSON "
        "(Replit) or GOOGLE_APPLICATION_CREDENTIALS (local path)."
    )


def _client():
    return build("drive", "v3", credentials=_credentials(), cache_discovery=False)


def list_folder(folder_id: str = DEFAULT_FOLDER_ID, page_size: int = 1000):
    """List direct children of a Drive folder."""
    svc = _client()
    q = f"'{folder_id}' in parents and trashed = false"
    fields = "files(id,name,mimeType,modifiedTime,size,parents)"
    res = svc.files().list(q=q, fields=fields, pageSize=page_size).execute()
    return res.get("files", [])


def walk(folder_id: str = DEFAULT_FOLDER_ID, prefix: str = ""):
    """Recursive walk. Yields (path, file_dict)."""
    for f in list_folder(folder_id):
        path = f"{prefix}/{f['name']}" if prefix else f["name"]
        if f["mimeType"] == "application/vnd.google-apps.folder":
            yield from walk(f["id"], path)
        else:
            yield path, f


def download(file_id: str, out_path: str) -> str:
    """Download a binary file. Returns out_path."""
    svc = _client()
    req = svc.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        dl = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
    return out_path


# MIME types for google-native files → export format
EXPORT_MIMES = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


def export(file_id: str, mime_type: str, out_path: str) -> str:
    """Export a Google-native file (Doc/Sheet/Slides) to a downloadable format."""
    svc = _client()
    data = svc.files().export(fileId=file_id, mimeType=mime_type).execute()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def read_text(file_id: str, mime_type: Optional[str] = None) -> str:
    """Convenience: return a file's text content. Auto-exports Google Docs."""
    svc = _client()
    meta = svc.files().get(fileId=file_id, fields="mimeType,name").execute()
    native_mime = meta["mimeType"]
    if native_mime in EXPORT_MIMES:
        target = mime_type or EXPORT_MIMES[native_mime][0]
        data = svc.files().export(fileId=file_id, mimeType=target).execute()
        return data.decode("utf-8", errors="replace")
    req = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue().decode("utf-8", errors="replace")


if __name__ == "__main__":
    # Smoke test: list the shared folder
    try:
        files = list_folder()
        print(f"Found {len(files)} items in folder {DEFAULT_FOLDER_ID}:")
        for f in files:
            print(f"  {f['mimeType']:45s}  {f['name']}  ({f['id']})")
    except Exception as e:
        print(f"ERROR: {e}")
        print("Did you share the folder with the service account email?")
        print("See memory/10_google_drive.md for setup.")
