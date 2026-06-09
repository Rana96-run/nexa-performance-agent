---
name: finding_double-backtick-bq-table-ref-invalid-sql
description: Double-wrapping already-backtick-quoted BQ table constant in f-string produced invalid SQL — 6 dashboard queries silently returned 0 rows
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: When `T = "\`project.dataset\`"` (already contains backticks), wrapping it in another backtick pair in f-strings produced `` ``project.dataset`.table_name` `` — invalid BigQuery SQL. The non-fatal exception handler swallowed the error, leaving all affected sections showing 0 rows. The issue was in 6 queries across two dashboard sections.

Source: Session e83785ce — Asana Tasks and Campaign Action Outcomes both showing 0.

Impact: Dashboard sections silently zeroed out.

Fix / How to handle: Never double-wrap table identifiers. If a constant already has backticks baked in, use it bare (e.g., `f"{T}.table_name"`). Add BQ SQL syntax validation to the dashboard guard hook.
