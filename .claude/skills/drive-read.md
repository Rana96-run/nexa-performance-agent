# Skill — Read from the shared Google Drive folder

Use when Amar says "check the brief in Drive" / "pull the creative from
Drive" / "read the X file".

Shared folder: `1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74`

## Fastest path (code, reuses BQ service account)

1. Confirm the service account email has Viewer access on the folder
   (`memory/10_google_drive.md` step 1-3)
2. Use `collectors/drive_reader.py`:

```python
from collectors.drive_reader import list_folder, download
for f in list_folder():
    print(f["name"], f["id"], f["mimeType"])
download(file_id="<id>", out_path="tmp/brief.pdf")
```

3. For Google-native files (Docs/Sheets/Slides), use `export_media` with
   a MIME type:
   - Doc → `text/plain` or `application/pdf`
   - Sheet → `text/csv`
   - Slides → `application/pdf`

## Interactive path (MCP)

If `.mcp.json` has the `gdrive` server registered, Claude Code can call
`gdrive:search` and `gdrive:read` tools directly without writing code.
See `memory/10_google_drive.md` → Method B.

## Don't

- Don't request `drive` full scope — `drive.readonly` is enough for
  99% of our needs.
- Don't download whole folders in a loop — list first, filter by name
  or modifiedTime, then download the one file needed.
- Don't commit downloaded Drive files to the repo. Treat `tmp/` as
  gitignored scratch space.
