---
name: finding_pending-approvals-json-wiped-on-redeploy
description: "pending_approvals.json defaulted to /tmp — wiped on every Railway redeploy, silently breaking the ✅/❌ approval flow"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The approval metadata file (`pending_approvals.json`) defaulted to `/tmp/pending_approvals.json`. Railway wipes `/tmp` on every redeploy. If anyone pushes code between the 03:00 nightly approval post and the morning ✅ reaction, the approval metadata is gone and the reaction executes nothing — silently.

Source: Session c78afcf1 — audit of the approval loop, confirmed `DATA_DIR` was never set so it always fell back to `/tmp`.

Impact: Any approval reaction between a redeploy and the morning reaction would silently do nothing, making the entire ✅/❌ flow unreliable.

Fix / How to handle: Move `pending_approvals.json` to the `memory/` directory (persists between restarts within a deployment). For full protection across redeploys, the permanent fix is Railway Volumes or storing pending approvals in BigQuery. As a practical rule: do not push to `main` between 03:00–08:00 Riyadh.

[[finding_railway-deployment-gunicorn-workers]]
