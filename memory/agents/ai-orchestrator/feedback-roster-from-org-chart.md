---
name: feedback-roster-from-org-chart
description: The team roster comes from the "Nexa Operations HQ — The Team" dashboard/org-chart (9 agents) — NOT from agent_activity_log role labels
metadata:
  type: feedback
---

User feedback (2026-06-08): when rebuilding the team, I first invented paid-media
seats, then read `agent_activity_log` and got 13 "roles" — both wrong. The real
roster is the **9 agents** on the "NEXA OPERATIONS HQ — The Team" dashboard.

**Why:** `agent_activity_log` is a *logging* taxonomy (infra labels like
health_monitor/bq_refresh + the human `user` + function buckets), not the team.
The org chart is the only source of the roster.

**How to apply:** always build/verify the roster from `docs/_shared/org-chart.md`
(synced to the dashboard). If asked "what are the roles?", read the org chart, not
the log table. See [[../../../11_agent_roles.md]] (the 9-vs-13 mapping).
