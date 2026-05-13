"""Verify deal_*_id_sync columns are populated per channel after backfill."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

sql = f"""
SELECT qoyod_source,
  COUNT(*) AS row_count,
  COUNT(deal_campaign_id_sync) AS with_cid,
  COUNT(deal_adgroup_id_sync)  AS with_aid,
  COUNT(deal_ad_id_sync)       AS with_adid,
  SUM(deals_won) AS won,
  ROUND(SUM(amount_won),0) AS rev_won
FROM `{proj}.{ds}.hubspot_deals_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
GROUP BY 1
ORDER BY won DESC
"""

print(f"{'channel':22s}  rows  cid  aid  adid  won  revenue_won")
print("-"*90)
for r in c.query(sql).result():
    print(f"  {str(r.qoyod_source):20s}  "
          f"{r.row_count:5d}  {r.with_cid:4d}  {r.with_aid:4d}  {r.with_adid:4d}  "
          f"{r.won or 0:4d}  ${r.rev_won or 0:,.0f}")
