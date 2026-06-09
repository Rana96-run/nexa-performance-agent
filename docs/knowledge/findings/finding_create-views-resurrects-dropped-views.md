---
name: finding_create-views-resurrects-dropped-views
description: create_views() in bq_writer.py re-creates dropped BQ views on every bootstrap run — dropped entries must be removed from the loop
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: After 17 dead BQ objects were dropped from the dataset, they were still listed in the `create_views()` dispatch loop in `collectors/bq_writer.py`. Running `python collectors/bq_writer.py views` or any bootstrap command would silently re-create all the dead views on every run, undoing the cleanup.

Source: Session a7de53a6 — codebase review by named-seat agents.

Impact: Dead tables kept coming back after every deploy; stale code was misleading and wasted BQ quota.

Fix / How to handle: Remove dropped view entries from the `create_views()` for-loop. Keep the dropped table names only in `memory/01_architecture.md` under the "Dropped tables — do not recreate" list. That list exists to prevent accidental recreation.
