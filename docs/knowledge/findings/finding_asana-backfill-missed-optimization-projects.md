---
name: finding_asana-backfill-missed-optimization-projects
description: Asana task backfill only scanned 4 env-var project GIDs — missed 13 optimization/daily projects with all the real team tasks
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `backfill_from_projects()` only scanned `ASANA_PROJECTS` (4 env-var keys, most `None`). The actual tasks for Rana and Donia live across 13 projects in `ASANA_OPTIMIZATION_PROJECTS` (per-channel: Google Ads, Meta, Snap, TikTok, LinkedIn, YouTube, Microsoft) and `ASANA_DAILY_PROJECTS` (Daily Performance Review, Keyword Audit, etc.).

Source: Session e83785ce — Activity Dashboard showed incorrect historical task counts.

Impact: Completion tracking was missing hundreds of tasks; team's work was invisible in the dashboard.

Fix / How to handle: Backfill must scan all known project lists: `ASANA_PROJECTS`, `ASANA_OPTIMIZATION_PROJECTS`, and `ASANA_DAILY_PROJECTS`. The `_all_projects()` helper skips `None` values safely. After fixing, backfill ran across 6 projects finding 335+ tasks.
