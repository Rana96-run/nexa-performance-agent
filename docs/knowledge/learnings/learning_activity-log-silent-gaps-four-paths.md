---
name: learning_activity-log-silent-gaps-four-paths
description: Four execution paths fired without writing to agent_activity_log — Activity Dashboard showed permanent zeros for those action categories
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: The Activity Dashboard relies on `agent_activity_log` for all metric cards. Four code paths executed without any log call: (1) Asana task creation in `executors/asana.py`, (2) negative keywords added in `executors/keyword_approval.py`, (3) campaign creation in `executors/google_ads.py`, (4) keywords paused in `analysers/google_ads_audit.py`.

Outcome: Cards for these 4 categories showed 0 permanently. Required discovery of the gap + 4 new `log_activity_async` calls to fix.

Pattern: Every execution path that represents an agent action must call `log_activity_async`. When adding a new executor or execution branch, immediately add a log call as step 1 — not as an afterthought. The pattern: `await log_activity_async(action='<verb>_<noun>', role='<agent_role>', details={...})`.

Applies to: All executor files (`executors/*.py`), any new analyser that auto-executes, any scheduler-triggered action.
