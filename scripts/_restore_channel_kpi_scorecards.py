"""Restore all-pipeline metrics to the 6 channel-level KPI scorecard files.
These files query channel_roas_daily which has BOTH all-pipeline AND new_biz_*
columns. The slim removed the all-pipeline ones. We add them back BEFORE the
new_biz block so the new line gets the comma and the new_biz line stays last.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

CTE_INSERT = """    -- All-pipeline deal metrics
    SUM(d.deals_won)              AS deals_won,
    SUM(d.deals_lost)             AS deals_lost,
    SUM(d.deals_open)             AS deals_open,
    SUM(d.amount_total)           AS amount_total,
    SUM(d.revenue_won)            AS revenue_won,
    SUM(d.amount_lost)            AS amount_lost,
    SUM(d.pipeline_open)          AS amount_open,
    """

SELECT_INSERT = """  -- Deal counts (all pipelines)
  COALESCE(deals_won,  0)                                                                 AS deals_won,
  COALESCE(deals_lost, 0)                                                                 AS deals_lost,
  COALESCE(deals_open, 0)                                                                 AS deals_open,
  -- Deal amounts (all pipelines)
  ROUND(COALESCE(amount_total, 0), 2)                                                     AS total_deal_amount,
  ROUND(COALESCE(revenue_won,  0), 2)                                                     AS closed_won_amount,
  ROUND(COALESCE(amount_lost,  0), 2)                                                     AS closed_lost_amount,
  ROUND(COALESCE(amount_open,  0), 2)                                                     AS open_deal_amount,
  """

ROAS_INSERT = """  -- ROAS — two flavors side-by-side
  ROUND(SAFE_DIVIDE(revenue_won,         NULLIF(spend, 0)), 2)                            AS roas,
"""

for path in Path(".claude/hex_drilldown/by_channel").glob("*/0_kpi_scorecard.sql"):
    text = path.read_text(encoding="utf-8")
    if "SUM(d.deals_won)" in text:
        print(f"  [skip] {path} — already restored")
        continue

    # Insert into CTE (before "-- New business" comment)
    text = text.replace(
        "    -- New business: Sales Pipeline + Bookkeeping + Qflavours — full parallel set\n",
        CTE_INSERT + "-- New business: Sales Pipeline + Bookkeeping + Qflavours — full parallel set\n",
    )
    # Insert into SELECT (before "-- New business metrics" comment)
    text = text.replace(
        "  -- New business metrics (Sales Pipeline + Bookkeeping + Qflavours only) — full parallel set\n",
        SELECT_INSERT + "-- New business metrics (Sales Pipeline + Bookkeeping + Qflavours only) — full parallel set\n",
    )
    # Insert ROAS line before the new_biz_roas line
    text = text.replace(
        "  ROUND(SAFE_DIVIDE(new_biz_revenue_won, NULLIF(spend, 0)), 2)                            AS new_biz_roas",
        ROAS_INSERT + "  ROUND(SAFE_DIVIDE(new_biz_revenue_won, NULLIF(spend, 0)), 2)                            AS new_biz_roas",
    )

    path.write_text(text, encoding="utf-8")
    print(f"  [restore] {path}")
