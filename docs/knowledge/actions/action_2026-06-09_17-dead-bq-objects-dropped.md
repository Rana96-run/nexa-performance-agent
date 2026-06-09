---
name: action_2026-06-09_17-dead-bq-objects-dropped
description: Dropped 17 dead BQ objects and ~650 lines of dead SQL from bq_writer.py and views.py — 2026-06-09
metadata: 
  node_type: memory
  type: action
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was done: Removed 17 dead BigQuery tables/views from the BQ dataset and from all code paths in `collectors/bq_writer.py` and `collectors/views.py`: `hubspot_leads_daily` (legacy, replaced by hubspot_leads_module_daily), `channel_roas_monthly`, `campaign_performance`, `campaign_performance_daily`, `campaign_performance_monthly`, `disqualification_matrix`, `pipeline_funnel`, `lead_funnel_by_pipeline`, `lead_utm_performance`, 7× `v_lp_*/v_ga4_*/v_session_*` views (GA4 connector never connected). Also removed ~650 lines of dead SQL constants.

Date: 2026-06-09

Trigger: Named-seat codebase review found 16 objects with zero code references.

Expected outcome: Cleaner dataset, no phantom table recreation on bootstrap, reduced confusion.

Actual outcome: `create_views()` loop now has only 4 live entries; all stale doc references cleaned; `memory/01_architecture.md` updated with "Dropped tables — do not recreate" list.

Follow-up: Check `create_views()` after any future BQ cleanup to ensure dropped views are removed from the loop.

[[finding_create-views-resurrects-dropped-views]]
