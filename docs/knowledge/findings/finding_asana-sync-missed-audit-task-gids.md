---
name: finding_asana-sync-missed-audit-task-gids
description: Asana sync only looked for asana_task_created action — all audit-generated tasks (scale/pause/optimize) were invisible to completion sync
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `collectors/asana_sync.py` only queried `action = 'asana_task_created'` with `details.gid` to find which tasks to sync. All audit-generated tasks are logged as `scale_task_created`, `pause_task_created`, etc. with `details.asana_gid` (different field name). When those tasks were marked ✅ done in Asana, the completion never synced back to BQ.

Source: Session e83785ce — discovered while debugging zero completion counts.

Impact: Activity dashboard showed 0 completions despite team actively closing tasks; user-created task scan incorrectly classified completed audit tasks as user-created.

Fix / How to handle: The sync must UNION ALL both `action = 'asana_task_created'` (field: `gid`) and `action IN ('scale_task_created','pause_task_created','optimize_task_created','drilldown_task_created')` (field: `asana_gid`). Apply same fix to the "known agent GIDs" list to prevent double-counting.
