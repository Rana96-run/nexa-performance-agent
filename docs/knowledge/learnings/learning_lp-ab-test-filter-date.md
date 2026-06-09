---
name: learning_lp-ab-test-filter-date
description: LP A/B test data only valid from 2026-05-04 — never compare HubSpot LP vs WordPress LP using pre-test data
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: HubSpot LP (campaigns.qoyod.com) has been live ~1 year. WordPress LP (lp.qoyod.com) launched for testing starting 2026-05-04. Any CPL/CPQL comparison including pre-May-4 data is biased because HubSpot LP has 1 year of optimization, WordPress LP had zero prior volume.

Outcome: Pre-test data makes the WordPress LP look worse than it is.

Pattern: All LP type comparisons must use `week_start >= '2026-05-04'` as filter. Minimum test window before drawing conclusions: 2 weeks. `v_lp_weekly_summary` and `v_lp_performance_weekly` views collect from that date forward.

Applies to: Any LP performance analysis, CRO recommendations, or LP-type attribution.
