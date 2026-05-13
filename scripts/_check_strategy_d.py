"""
Verify Strategy D is working: check v_adset_performance for TikTok/Meta
adsets that previously showed 0 leads but now have leads via campaign-ID fallback.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

# TikTok adsets with leads in the last 14 days
print("=== TikTok adsets — leads in last 14 days ===")
sql = f"""
SELECT date, utm_audience, spend, leads, leads_qualified, data_source
FROM `{proj}.{ds}.v_adset_performance`
WHERE channel = 'tiktok'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
  AND (spend > 0 OR leads > 0)
ORDER BY date DESC, spend DESC
LIMIT 15
"""
for r in client.query(sql).result():
    print(f"  {r.date}  aud={str(r.utm_audience or 'NULL'):40s}  spend=${r.spend:.0f}  leads={r.leads}  sqls={r.leads_qualified}  src={r.data_source}")

# Meta adsets with leads
print("\n=== Meta adsets — leads in last 7 days ===")
sql2 = f"""
SELECT date, utm_audience, ROUND(spend,0) AS spend, leads, leads_qualified
FROM `{proj}.{ds}.v_adset_performance`
WHERE channel = 'meta'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND spend > 5
ORDER BY date DESC, spend DESC
LIMIT 8
"""
for r in client.query(sql2).result():
    print(f"  {r.date}  aud={str(r.utm_audience or 'NULL'):45s}  spend=${r.spend:.0f}  leads={r.leads}  sqls={r.leads_qualified}")
