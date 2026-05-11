# Skill — Google Drive doc creation & updates

Use whenever Rana asks to create, update, or write a file on Google Drive.

## Non-negotiables

- **Never ask for connection** — the Drive MCP (`mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__*`) is always connected. Use it directly.
- **Always use the standard HTML theme** — see below. Never create plain-text docs.
- **Use `create_file` with `contentMimeType: "text/html"`** — Google Drive auto-converts to a styled Google Doc.
- **The Drive MCP cannot edit existing files** — always create a new file. Mention the new URL to the user so they can replace the old one.

## Standard doc theme (always apply this)

```html
<!-- Header band -->
<div style="background:#1a56db;padding:28px 32px;border-radius:8px 8px 0 0;">
  <h1 style="color:#fff;margin:0;font-size:26px;">{Title}</h1>
  <p style="color:#bfdbfe;margin:6px 0 0;font-size:13px;">{subtitle / date / status}</p>
</div>

<!-- Section header -->
<h2 style="color:#1a56db;border-bottom:2px solid #1a56db;padding-bottom:6px;margin-top:32px;">{Section}</h2>

<!-- Standard table -->
<table style="width:100%;border-collapse:collapse;margin:12px 0;">
  <thead>
    <tr style="background:#1a56db;">
      <th style="color:#fff;padding:10px 14px;text-align:left;border:1px solid #e5e7eb;">{col}</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="padding:10px 14px;border:1px solid #e5e7eb;">{value}</td>
    </tr>
    <!-- alternating rows: odd rows get background:#f0f7ff -->
  </tbody>
</table>

<!-- Status badge — Live -->
<span style="background:#dcfce7;color:#15803d;padding:3px 10px;border-radius:12px;font-weight:600;font-size:13px;">✅ Live</span>

<!-- Status badge — Warning -->
<span style="background:#fef9c3;color:#a16207;padding:3px 10px;border-radius:12px;font-weight:600;font-size:13px;">⚠️ Warning</span>

<!-- Status badge — Blocked -->
<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;border-radius:12px;font-weight:600;font-size:13px;">❌ Blocked</span>

<!-- Callout box -->
<div style="background:#eff6ff;border-left:4px solid #1a56db;padding:12px 16px;border-radius:4px;margin:16px 0;">
  <strong>{label}:</strong> {text}
</div>

<!-- Warning callout -->
<div style="background:#fef9c3;border-left:4px solid #d97706;padding:12px 16px;border-radius:4px;margin:16px 0;">
  <strong>⚠️ {label}:</strong> {text}
</div>

<!-- Section divider -->
<hr style="border:none;border-top:1px solid #e5e7eb;margin:28px 0;">
```

## Color palette

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

## Table rules

- **All `<td>` and `<th>` must have `border:1px solid #e5e7eb`** — without this Google Docs splits the table.
- Header row: `background:#1a56db`, white text.
- Alternate rows: odd = white, even = `background:#f0f7ff`.
- Never use `background` on alternating rows without the explicit border — it causes table splits.

## MCP tool to use

```
mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__create_file
  title: "Doc title"
  textContent / base64Content: <HTML string>
  contentMimeType: "text/html"
```

To read an existing doc before updating:
```
mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__read_file_content
  fileId: "<id from URL>"
```

To search for a doc by name:
```
mcp__b4369235-4166-4720-ac11-fb1d027ea7a7__search_files
  query: "title contains 'Qoyod' and mimeType = 'application/vnd.google-apps.document'"
```

## Doc structure template

1. Header band (blue, title + date/status)
2. Section: What This Is / What Problem It Solves
3. Section: Live Dashboards (table)
4. Section: Active Channels (table with status badges)
5. Section: KPI Thresholds (tables — campaign CPL, campaign CPQL, ad CPL, ad CPQL)
6. Section: How Approvals Work (table)
7. Section: Schedule (table)
8. Section: Numbers to Trust / Traps to Avoid (callout boxes)
9. Section: Open Issues (table — or "No blockers" callout if clear)
