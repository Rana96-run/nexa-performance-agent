---
name: learning_bq-view-dependency-order-matters
description: BQ views that depend on other views must be created first — utm_paid_attribution_daily must precede all sub-grain views
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: `utm_paid_attribution_daily` is a base view that `v_adset_performance`, `v_ad_performance`, and `v_keyword_performance` all SELECT from. When views are refreshed in the wrong order, BQ rejects the dependent views with "view not found."

Outcome: Adding `utm_paid_attribution_daily` first in `_sub_campaign_views()` resolved BQ view creation ordering. It is inserted as the first item so downstream views always have it available.

Pattern: Whenever adding a new base view that others depend on, insert it BEFORE its dependents in the `ALL_VIEWS + _sub_campaign_views()` list. Check for `SELECT FROM <view_name>` references across all view SQL before determining the correct insertion point.

Applies to: `collectors/views.py`, any future BQ view additions to the refresh pipeline.
