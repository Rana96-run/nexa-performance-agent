---
name: finding_activity-detail-sql-null-gid-partition
description: "PARTITION BY JSON_VALUE(details, '$.gid') collapsed all null-GID rows into one partition — ROW_NUMBER kept only 1, dropping hundreds of tasks"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The Activity Dashboard SQL used `PARTITION BY gid` in a `ROW_NUMBER()` deduplication window. All rows logged without a GID (null) were grouped into a single partition — `ROW_NUMBER() = 1` then kept only the first null-GID row, silently dropping every other one.

Source: Session e83785ce — Asana tasks section showing only 1 task despite 212 in BQ.

Impact: Hundreds of agent-created tasks invisible in the dashboard.

Fix / How to handle: Use `PARTITION BY COALESCE(gid, CAST(UNIX_MICROS(created_at) AS STRING))` so each null-GID row gets its own unique partition key. Never partition by a nullable field when you want all-rows deduplication behavior.
