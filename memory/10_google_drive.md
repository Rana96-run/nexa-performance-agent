# Google Drive Connection

Shared folder for creative assets, reports, and reference docs that sit
alongside (not inside) the code repo.

- **Folder URL:** https://drive.google.com/drive/folders/1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74
- **Folder ID:** `1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74`

## Subfolder IDs (set in Railway 2026-06-12)

| Env var | Folder ID | Purpose |
|---|---|---|
| `GDRIVE_REPORTS_FOLDER_ID` | `1YPyFKhegbtf04yf_Z3UpiuCWmjXv9wcl` | Monthly performance decks (PPTX) |
| `GDRIVE_CREATIVE_REPORTS_FOLDER_ID` | `1h4JvcYdsKi_OrAPbBBz9Tlqqq844qQXF` | Monthly creative reports (Sheets) |

## Pick ONE connection method

We already have a Google service account (used for BigQuery). The cleanest
path is to **reuse that same service account** for Drive — no new OAuth.

### Method A (recommended) — Reuse BigQuery service account

**One-time setup (you do this in Google Workspace / Drive UI):**

1. Open the service account email — find it in the JSON at
   `client_email` (looks like `something@project.iam.gserviceaccount.com`).
   The JSON lives in `.env` as `GOOGLE_APPLICATION_CREDENTIALS_JSON` or at
   the path in `GOOGLE_APPLICATION_CREDENTIALS`.
2. Open the Drive folder → **Share** → paste that service-account email →
   give it **Viewer** (read-only) or **Editor** (if we want Claude to write
   back reports). Uncheck "Notify people".
3. In Google Cloud Console → same project as BigQuery → **APIs & Services**
   → Library → enable **"Google Drive API"**.

**Code (we'll add `collectors/drive_reader.py`):**
```python
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os, json

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_ID = "1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74"

def _client():
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw:
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_folder(folder_id: str = FOLDER_ID):
    svc = _client()
    q = f"'{folder_id}' in parents and trashed = false"
    res = svc.files().list(q=q, fields="files(id,name,mimeType,modifiedTime,size)",
                           pageSize=1000).execute()
    return res.get("files", [])

def download(file_id: str, out_path: str):
    from googleapiclient.http import MediaIoBaseDownload
    import io
    svc = _client()
    req = svc.files().get_media(fileId=file_id)
    with open(out_path, "wb") as f:
        dl = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
```

**Add to `requirements.txt`:**
```
google-api-python-client>=2.120
```

### Method B — Official Google Drive MCP server

If we want Claude Code itself (not collectors) to browse/read Drive files
interactively, register an MCP server. Example with the community
`mcp-gdrive` package:

`.mcp.json` (repo root, committed) or `~/.claude.json` (user-level):
```json
{
  "mcpServers": {
    "gdrive": {
      "command": "npx",
      "args": ["-y", "@isaacphi/mcp-gdrive"],
      "env": {
        "CLIENT_ID": "<oauth-client-id>",
        "CLIENT_SECRET": "<oauth-client-secret>",
        "GDRIVE_CREDS_DIR": "C:\\Users\\qoyod\\.mcp-gdrive"
      }
    }
  }
}
```
First run pops an OAuth browser window; tokens cache to `GDRIVE_CREDS_DIR`.

**Pros:** Claude can `list / search / read` Drive from chat.
**Cons:** Needs a separate OAuth client in Google Cloud Console and a
per-user token cache. Can't run unattended on Replit.

### Method C — rclone mount

If we want Drive as a local folder the agent can `ls / read` like any
other path:
```
rclone config   # "gdrive" remote, drive.readonly scope
rclone mount gdrive: D:\NexaDrive --daemon
```
**Pros:** zero code changes; all filesystem tools just work.
**Cons:** only on machines where rclone runs (not Replit).

## Recommended for this project

- **Method A** for collectors and scheduled jobs (reads creative briefs,
  writes back PDF reports). Deterministic, runs on Replit.
- **Method B** for this Claude Code session — so Amar can say "read the
  brief in Drive" and Claude can fetch it inline.
- Method C is a nicety, not required.

## Scopes cheat-sheet

| Need | Scope |
|---|---|
| Read files/folders | `drive.readonly` |
| Create/update files the app owns | `drive.file` |
| Full access (avoid) | `drive` |

Always start with `drive.readonly` unless writing back.

## Folders (to be populated)

Inside `1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74` we expect:
- `/creative-briefs/` — campaign briefs before launch
- `/reports/` — monthly PDFs the agent exports
- `/reference/` — ZATCA docs, brand guidelines, the Playbook PDF
- `/raw-exports/` — ad-hoc CSVs dropped by the team

## Open action items

- [ ] Amar: share Drive folder with the service-account email (Method A)
- [ ] Amar: enable Google Drive API in the same GCP project as BigQuery
- [ ] Claude: add `collectors/drive_reader.py` + requirements entry
- [ ] Amar (optional): create OAuth client + paste into `.mcp.json` for
      Method B so Claude Code can browse Drive interactively
