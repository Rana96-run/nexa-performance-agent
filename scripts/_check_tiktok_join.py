"""
Diagnose TikTok 0 leads: compare adsets_daily utm_audience vs HubSpot lead_utm_audience.
Also check if there are recent TikTok leads in hubspot_leads_module_daily.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

# 1. TikTok adsets in BQ — what utm_audience values do they have?
print("=== TikTok adsets_daily (last 3 days) ===")
sql = f"""
SELECT date, adset_name, utm_audience, spend, leads
FROM `{proj}.{ds}.adsets_daily`
WHERE channel = 'tiktok'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 3 DAY)
ORDER BY date DESC, spend DESC
LIMIT 10
"""
for r in client.query(sql).result():
    print(f"  {r.date}  adset={str(r.adset_name or '')[:40]:40s}  utm={str(r.utm_audience or 'NULL'):40s}  spend=${r.spend:.2f}  leads={r.leads}")

# 2. TikTok leads in HubSpot BQ — what utm_audience values?
print("\n=== TikTok leads in hubspot_leads_module_daily (last 3 days) ===")
sql2 = f"""
SELECT date, lead_utm_campaign, lead_utm_audience, leads_total
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE qoyod_source = 'TikTok Ads'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 3 DAY)
ORDER BY date DESC, leads_total DESC
LIMIT 10
"""
rows = list(client.query(sql2).result())
if rows:
    for r in rows:
        print(f"  {r.date}  cmp={str(r.lead_utm_campaign or '')[:40]:40s}  aud={str(r.lead_utm_audience or 'NULL'):40s}  leads={r.leads_total}")
else:
    print("  (no rows)")

# 3. Check v_adset_performance for TikTok (last 3 days)
print("\n=== v_adset_performance TikTok rows (last 3 days) ===")
sql3 = f"""
SELECT date, utm_audience, spend, leads, leads_qualified
FROM `{proj}.{ds}.v_adset_performance`
WHERE channel = 'tiktok'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 3 DAY)
ORDER BY date DESC, spend DESC
LIMIT 10
"""
for r in client.query(sql3).result():
    print(f"  {r.date}  aud={str(r.utm_audience or 'NULL'):40s}  spend=${r.spend:.2f}  leads={r.leads}  sqls={r.leads_qualified}")
