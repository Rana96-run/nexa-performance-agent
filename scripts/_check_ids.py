import os, sys
sys.stdout.reconfigure(encoding="utf-8")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

# Check what adset/ad IDs look like for Google and Microsoft vs TikTok/Meta
for tbl, id_col, name_col, chan_col in [
    ("adsets_daily", "adset_id", "utm_audience", "channel"),
    ("ads_daily",    "ad_id",    "utm_content",  "channel"),
]:
    print(f"\n--- {tbl} (sample ids, 2026-05-12) ---")
    sql = f"""
    SELECT channel, {id_col}, {name_col}
    FROM `{proj}.{ds}.{tbl}`
    WHERE date = '2026-05-12'
      AND channel IN ('google_ads','microsoft_ads','tiktok','meta')
    LIMIT 8
    """
    for r in client.query(sql).result():
        print(f"  {r[0]:14s}  id={str(r[1])[:30]:30s}  name={str(r[2] or '')[:30]}")

# Check what HubSpot has in campaign_id / ad_group_id / ad_id
print("\n--- hubspot_leads_module_daily (id columns, last 7 days) ---")
sql2 = f"""
SELECT qoyod_source, lead_campaign_id, lead_ad_group_id, lead_ad_id, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND (lead_campaign_id IS NOT NULL OR lead_ad_group_id IS NOT NULL OR lead_ad_id IS NOT NULL)
GROUP BY 1,2,3,4
ORDER BY leads DESC
LIMIT 10
"""
try:
    rows = list(client.query(sql2).result())
    if rows:
        for r in rows:
            print(f"  {str(r.qoyod_source):14s}  cid={str(r.lead_campaign_id or '')[:20]:20s}  agid={str(r.lead_ad_group_id or '')[:20]:20s}  aid={str(r.lead_ad_id or '')[:20]:20s}  leads={r.leads}")
    else:
        print("  (no rows yet — ID columns just added, cursor sync needed)")
except Exception as e:
    print(f"  error: {e}")
