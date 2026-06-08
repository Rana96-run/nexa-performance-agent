---
name: reconcile-7day-sample
description: After any deal/lead schema/view/attribution change, reconcile BQ to HubSpot on a SMALL 7-day one-channel sample, not a wide one
metadata:
  type: critical
---

After any change touching hubspot_deals_daily, hubspot_leads_module_daily, or a
view that aggregates them, reconcile BQ to HubSpot on a 7-day, one-pipeline,
one-channel sample — pulled via the HubSpot API myself, not a screenshot.

**Why:** small samples make discrepancies obvious; wide samples hide them. A
deals createdate drift once hit 1.84x duplication that a wide check missed.

**How to apply:** pull both sides for the same channel x pipeline x createdate
window, compare counts + amounts, match within ~1% sync timing or it is NOT done.
Verification is my job, never the user's. Verified end-to-end 2026-06-08.
