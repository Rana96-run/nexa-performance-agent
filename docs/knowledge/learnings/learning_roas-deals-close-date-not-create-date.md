---
name: learning_roas-deals-close-date-not-create-date
description: ROAS must use deal close_date or lifetime attribution — filtering deals by createdate to match spend window understates revenue
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: The original deals join used `createdate` (when the deal entered the pipeline) for ROAS calculations. If you filter deals to "the same 30-day window as spend," deals created before the window but closed within it are excluded, understating ROAS.

Outcome: Deals now use lifetime attribution per campaign for ROAS — no date filter on the deals join. Spend is date-filtered; deals are not (or are filtered by close date). Committed as part of the BQ view corrections.

Pattern: For ROAS: join deals with NO date filter (lifetime attribution) OR filter by `closedate` (revenue recognition date). Never filter deals by `createdate` when computing revenue-vs-spend ratios — the sales cycle delay breaks the math.

Applies to: Any BQ SQL computing `revenue_won / spend`, all Hex ROAS cells, `hubspot_deals_daily` joins.
