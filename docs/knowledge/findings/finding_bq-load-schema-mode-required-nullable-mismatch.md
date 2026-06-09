---
name: finding_bq-load-schema-mode-required-nullable-mismatch
description: "BQ table created with NOT NULL but load job specified NULLABLE — silent row rejection, 0 rows landed despite apparent success"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The `asana_task_status` table was created with `gid STRING NOT NULL` (REQUIRED mode in DDL) but every load job specified `gid STRING` (NULLABLE by default in Python schema). BigQuery rejected the schema mismatch silently — the load appeared to succeed, but 0 rows landed. The table had 0 rows despite 333 matching GIDs existing in `agent_activity_log`.

Source: Session e83785ce — debugging zero completion counts in Activity Dashboard.

Impact: All Asana task completion syncs silently dropped data for weeks.

Fix / How to handle: Explicitly add `mode="REQUIRED"` to the field definition in both the write schema and the DDL when the column is NOT NULL. Better: use NULLABLE throughout (simpler to manage). When BQ writes appear to succeed but show 0 rows, always check schema mode mismatches first.
