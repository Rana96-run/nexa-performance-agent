---
name: learning_role-double-counting-in-team-defs
description: Agent role overlap in _TEAM_DEFS double-counted activity stats — each BQ role must map to exactly one agent in the dashboard
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: The Activity Dashboard's team roster defined which BQ `role` values belong to which agent card. Four roles appeared in two agents' sets simultaneously: `spike_detector` (CRO Specialist + Growth Analyst), `bq_refresh` (Developer + Growth Analyst), `llm_cadence` (Creative Strategist + Growth Analyst), `daily_digest` (Project Coordinator + Growth Analyst). Every `agent_activity_log` row for those roles was summed into two different agent cards.

Outcome: Every affected agent's stats were inflated; the Growth Analyst was credited for work belonging to 4 other agents.

Pattern: In `_TEAM_DEFS` (or any role-to-agent mapping), each role string must appear in exactly one agent's `roles` set. A `dashboard_guard.py` hook now catches this by scanning for role overlap on every edit to `reports/app.py`. Canonical assignment: `daily_digest` → Project Coordinator; `spike_detector`, `bq_refresh`, `llm_cadence` → Growth Analyst; `cro_analysis` → CRO Specialist; `lp_deploy` → Developer.

Applies to: Any mapping structure where rows are summed by membership (role → agent, category → bucket).
