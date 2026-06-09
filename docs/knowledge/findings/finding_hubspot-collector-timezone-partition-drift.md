---
name: finding_hubspot-collector-timezone-partition-drift
description: HubSpot collectors truncated timestamps to UTC date — leads created 21:00-23:59 Riyadh landed in wrong BQ partition
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The HubSpot leads and deals collectors used `createdate[:10]` to extract the date partition, which truncates to UTC. HubSpot UI filters by Riyadh time (UTC+3). This caused leads created between 21:00–23:59 Riyadh (= next UTC day) to land in the wrong BQ partition, producing a consistent ~3–10 lead gap per day vs HubSpot UI.

Source: Session 80e55918 — confirmed by per-day comparison: after fix, BQ matched HubSpot on 5 of 7 days with 0 diff; remaining 2 within 1 lead (mutation noise).

Impact: Any date-filtered analysis comparing BQ to HubSpot UI appeared to show data loss. CPL/CPQL for the most recent day of a period was systematically understated.

Fix / How to handle: Both collectors now convert `createdate` to Riyadh (UTC+3) before truncating to date. Pattern: `datetime.fromisoformat(ts.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Riyadh')).date().isoformat()`. Committed as `09a6f18`.
