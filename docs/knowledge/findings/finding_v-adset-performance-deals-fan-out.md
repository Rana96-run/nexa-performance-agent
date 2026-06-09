---
name: finding_v-adset-performance-deals-fan-out
description: v_adset_performance and v_ad_performance had revenue fan-out — deals join missing utm_campaign column inflated ROAS at adset/ad grain
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The `deals_by_name` join in both views was missing `dn.utm_campaign` in the JOIN condition, which caused the same deal row to match multiple adset/ad rows sharing a name. Revenue figures (`revenue_won`) were inflated in these views.

Source: Session a7de53a6 — found during named-seat review (developer + growth-analyst).

Impact: ROAS and revenue numbers were overstated at adset and ad grain.

Fix / How to handle: Add `AND c.utm_campaign = dn.utm_campaign` (or equivalent) to the `deals_by_name` join. Always include all relevant dimensions in deal joins to prevent fan-out. Pattern: pre-aggregate HubSpot before joining (same rule already documented for leads joins).

[[learning_strategy-cd-leads-double-count]]
