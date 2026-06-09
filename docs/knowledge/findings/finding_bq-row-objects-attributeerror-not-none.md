---
name: finding_bq-row-objects-attributeerror-not-none
description: BigQuery Row objects raise AttributeError on missing fields — not None like a dict — causes Flask 500 on new columns
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: When a BQ query doesn't select a column (e.g., `role` was missing from `infra_sql`), accessing `row.role` in Python raises `AttributeError`, not silently returning `None` as a dict would. This caused a Flask 500 crash on every Activity Dashboard page load after a new feature added `r.role` access without adding `role` to the underlying SQL.

Source: Session e83785ce — Activity Dashboard 500 crash, commit after team-roster feature.

Impact: Dashboard was fully broken (500 error) until fixed.

Fix / How to handle: Always use `getattr(row, 'field_name', default)` for BQ Row attribute access, especially when the query schema may be extended or columns may be optional. Never assume a missing column returns None.
