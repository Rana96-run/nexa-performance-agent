---
name: drive
description: |
  Skill Library — Google Drive operations (read AND write).
  Replaces drive-read.md + drive-docs.md.
  Load when reading a brief from Drive, creating a report doc,
  updating an existing file, or searching for a file by name.
---

# Google Drive Skill

## Reading from Drive

### Shared folder
`1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74`

### Code path (reuses BQ service account)
```python
from collectors.drive_reader import list_folder, download

# List all files in shared folder
for f in list_folder():
    print(f["name"], f["id"], f["mimeType"])

# Download any file (PDFs, images, binary)
download(file_id="<id>", out_path="tmp/brief.pdf")
```

For Google-native files, export with a MIME type:
```python
# Doc → plain text or PDF
# Sheet → CSV
# Slides → PDF
```

### MCP path (faster, no code needed)
If `.mcp.json` has `gdrive` registered, call directly:
```
mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__search_files
  query: "name contains 'brief' and mimeType = 'application/vnd.google-apps.document'"

mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__read_file_content
  fileId: "<id from URL>"
```

### Read rules
- Use `drive.readonly` scope — never request full `drive`
- Never download whole folders in a loop — list first, filter, download only the file needed
- Never commit downloaded files — `tmp/` is gitignored scratch space
- See `memory/10_google_drive.md` for service account setup

---

## Writing to Drive

**The Drive MCP cannot edit existing files** — always create a new file and
share the new URL with the user so they can replace the old one.

### MCP tool
```
mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__create_file
  title: "Doc title"
  textContent: <HTML string>
  contentMimeType: "text/html"
```
Google Drive auto-converts HTML → styled Google Doc.

### Standard doc template (always apply)
```html
<!-- Header band -->
<div style="background:#1a56db;padding:28px 32px;border-radius:8px 8px 0 0;">
  <h1 style="color:#fff;margin:0;font-size:26px;">{Title}</h1>
  <p style="color:#bfdbfe;margin:6px 0 0;font-size:13px;">{subtitle / date / status}</p>
</div>

<!-- Section header -->
<h2 style="color:#1a56db;border-bottom:2px solid #1a56db;padding-bottom:6px;margin-top:32px;">{Section}</h2>

<!-- Standard table (ALL td/th must have border) -->
<table style="width:100%;border-collapse:collapse;margin:12px 0;">
  <thead>
    <tr style="background:#1a56db;">
      <th style="color:#fff;padding:10px 14px;text-align:left;border:1px solid #e5e7eb;">{col}</th>
    </tr>
  </thead>
  <tbody>
    <tr><td style="padding:10px 14px;border:1px solid #e5e7eb;">{value}</td></tr>
    <!-- odd rows: white | even rows: background:#f0f7ff -->
  </tbody>
</table>

<!-- Status badges -->
<span style="background:#dcfce7;color:#15803d;padding:3px 10px;border-radius:12px;font-weight:600;font-size:13px;">✅ Live</span>
<span style="background:#fef9c3;color:#a16207;padding:3px 10px;border-radius:12px;font-weight:600;font-size:13px;">⚠️ Warning</span>
<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;border-radius:12px;font-weight:600;font-size:13px;">❌ Blocked</span>

<!-- Callout boxes -->
<div style="background:#eff6ff;border-left:4px solid #1a56db;padding:12px 16px;border-radius:4px;margin:16px 0;">
  <strong>{label}:</strong> {text}
</div>
<div style="background:#fef9c3;border-left:4px solid #d97706;padding:12px 16px;border-radius:4px;margin:16px 0;">
  <strong>⚠️ {label}:</strong> {text}
</div>

<!-- Section divider -->
<hr style="border:none;border-top:1px solid #e5e7eb;margin:28px 0;">
```

### Color palette
| Use | Hex |
|---|---|
| Primary blue (headers, accents) | `#1a56db` |
| Light blue bg (callouts, alt rows) | `#eff6ff` / `#f0f7ff` |
| Green (live/success) | `#dcfce7` / `#15803d` |
| Yellow (warning) | `#fef9c3` / `#a16207` |
| Red (blocked/error) | `#fee2e2` / `#991b1b` |
| Border / divider | `#e5e7eb` |
| Body text | `#0f172a` |
| Muted text | `#64748b` |

### Table rules (critical)
- Every `<td>` and `<th>` **must** have `border:1px solid #e5e7eb` — without it Google Docs splits the table
- Header row: `background:#1a56db`, white text
- Alternating rows: odd = white, even = `background:#f0f7ff`

### Standard doc structure
1. Header band (blue, title + date/status)
2. What This Is / Problem It Solves
3. Live Dashboards (table)
4. Active Channels (table with status badges)
5. KPI Thresholds (tables — campaign CPL, campaign CPQL, ad CPL, ad CPQL)
6. How Approvals Work (table)
7. Schedule (table)
8. Numbers to Trust / Traps to Avoid (callout boxes)
9. Open Issues (table — or "No blockers" callout if clear)
