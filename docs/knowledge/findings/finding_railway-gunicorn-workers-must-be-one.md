---
name: finding_railway-gunicorn-workers-must-be-one
description: "gunicorn must use --workers 1 to prevent duplicate scheduler runs — multiple workers spawn N nightly collectors, N Slack posts, N Asana tasks"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Multiple gunicorn workers each spawn their own `operational_scheduler` thread → N duplicate nightly runs, double Slack posts, double Asana tasks. Also: with Teardown OFF, old and new deployments overlap during transitions → same duplication. Confirmed by Snapchat 429 storms (5,000 duplicate API calls in one nightly window).

Source: memory/08_pitfalls.md "Railway deployment (extended)".

Impact: Double API calls to Meta/Snap/TikTok/HubSpot; duplicate Slack posts; duplicate Asana tasks; Snapchat 429 storms.

Fix / How to handle: Always: `gunicorn app_server:app --workers 1 --threads 4`. Set `teardown = true` in `railway.toml` AND enable Teardown in Railway UI deploy tab. Never write persistent state to `/tmp` — use BQ or repo volume (wiped on redeploy).

[[finding_pending-approvals-json-wiped-on-redeploy]]
