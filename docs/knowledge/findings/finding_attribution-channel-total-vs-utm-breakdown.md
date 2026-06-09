---
name: finding_attribution-channel-total-vs-utm-breakdown
description: Channel total from qoyod_source ≠ sum of UTM campaign breakdown — gap is click-ID leads with no campaign UTM; show as explicit __no_utm__ row
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Some leads attribute to a channel via click ID (gclid, fbclid) but have no campaign name in UTM. So UTM-campaign breakdown sums will always be less than the qoyod_source channel total.

Source: memory/07_attribution.md "Key insight (user-stated)".

Impact: If the gap is hidden, users wonder why tables don't sum to channel totals — causes confusion and distrust of dashboard numbers.

Fix / How to handle: Channel KPI tile uses count from `qoyod_source`. Campaign breakdown table uses `utm_campaign`. Always emit an explicit `utm_campaign = '__no_utm__'` row for the difference: `leads_unattributed_to_campaign = channel_total - sum(utm_breakdown)`. Show it as "(no UTM — click-ID attribution only)". Use COALESCE(exact match, slug match) for join strategy, recording `match_method` column for debugging.
