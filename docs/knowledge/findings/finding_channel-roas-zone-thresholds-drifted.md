---
name: finding_channel-roas-zone-thresholds-drifted
description: channel_roas_daily view had hardcoded KPI zone thresholds that drifted from config.py — dashboard showed wrong zone labels
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The CASE WHEN thresholds hardcoded in the `channel_roas_daily` view SQL (CPL/CPQL zone boundaries) had drifted from the canonical values in `config.py`. The view was showing wrong zone labels (acceptable vs warning vs pause) for campaigns.

Source: Session a7de53a6 — raised by marketing-ops seat during codebase review.

Impact: Dashboard KPI zones showed incorrect status colors; campaign decisions could be made on wrong zone classification.

Fix / How to handle: Zone thresholds in views must be derived from or verified against `config.py` values (`CPL_*`, `CPQL_*`). After any config.py threshold change, re-check all views that embed numeric zone boundaries. Commit: 3def888.
