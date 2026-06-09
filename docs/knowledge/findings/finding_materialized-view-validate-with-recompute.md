---
name: finding_materialized-view-validate-with-recompute
description: "v_adset_performance and v_ad_performance are materialized TABLEs — always compare two fresh recomputes when validating a fix, never stale TABLE vs live"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: When validating a view-SQL fix, comparing against the materialized TABLE gives misleading results — the table holds yesterday's data. A fix attempt for v_adset_performance appeared to "change leads" when it hadn't — the difference was materialized vs freshly computed data. Also discovered: `materialize_heavy_views` lives in `collectors/views.py`, NOT `bq_writer`.

Source: memory/08_pitfalls.md v_adset_performance GOTCHA block.

Impact: False positive/negative on fix validation; wasted debugging time.

Fix / How to handle: When validating a view-SQL fix on a materialized table, compare a fresh live recompute (using `CREATE OR REPLACE TABLE`) vs another fresh live recompute — NOT against the stale materialized TABLE. Two independent live recomputes in sequence is the correct validation approach.
