"""
Diagnose lead attribution issues:
1. Leads with NULL utm_campaign (no name)
2. Same utm_campaign name on multiple channels (cross-channel collision)
3. TikTok/Google leads whose utm_campaign matches no campaigns_daily row
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

# 1. Leads with no utm_campaign (last 30 days)
print("=== 1. Leads with NULL/empty utm_campaign (last 30 days) ===")
sql = f"""
SELECT qoyod_source, COUNT(*) AS row_count, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND (lead_utm_campaign IS NULL OR TRIM(lead_utm_campaign) = '')
GROUP BY 1
ORDER BY leads DESC
"""
for r in client.query(sql).result():
    print(f"  {str(r.qoyod_source or 'unknown'):20s}  rows={r.row_count:4d}  leads={r.leads}")

# 2. utm_campaign names that appear on 2+ channels (collision risk)
print("\n=== 2. utm_campaign names shared across multiple channels (last 30 days) ===")
sql2 = f"""
SELECT lead_utm_campaign, STRING_AGG(DISTINCT qoyod_source ORDER BY qoyod_source) AS channels,
       COUNT(DISTINCT qoyod_source) AS n_channels, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND lead_utm_campaign IS NOT NULL
  AND TRIM(lead_utm_campaign) != ''
GROUP BY 1
HAVING n_channels > 1
ORDER BY leads DESC
LIMIT 15
"""
rows = list(client.query(sql2).result())
if rows:
    for r in rows:
        print(f"  {str(r.lead_utm_campaign)[:55]:55s}  channels={r.channels}  leads={r.leads}")
else:
    print("  (none — good)")

# 3. TikTok leads whose utm_campaign name matches NO row in campaigns_daily (last 30 days)
print("\n=== 3. TikTok leads with utm_campaign NOT in campaigns_daily (last 30 days) ===")
sql3 = f"""
WITH hs AS (
  SELECT lead_utm_campaign, SUM(leads_total) AS leads
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
    AND qoyod_source = 'Tiktok Ads'
    AND lead_utm_campaign IS NOT NULL
  GROUP BY 1
),
bq AS (
  SELECT DISTINCT LOWER(TRIM(campaign_name)) AS name
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE channel = 'tiktok'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
)
SELECT hs.lead_utm_campaign, hs.leads
FROM hs
LEFT JOIN bq ON LOWER(TRIM(hs.lead_utm_campaign)) = bq.name
WHERE bq.name IS NULL
ORDER BY hs.leads DESC
LIMIT 10
"""
rows3 = list(client.query(sql3).result())
if rows3:
    for r in rows3:
        print(f"  {str(r.lead_utm_campaign)[:60]:60s}  leads={r.leads}")
else:
    print("  (all TikTok utm_campaigns match campaigns_daily — good)")

# 4. Google Ads leads whose utm_campaign matches NO row in campaigns_daily (last 30 days)
print("\n=== 4. Google leads with utm_campaign NOT in campaigns_daily (last 30 days) ===")
sql4 = f"""
WITH hs AS (
  SELECT lead_utm_campaign, SUM(leads_total) AS leads
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
    AND qoyod_source = 'Google Ads'
    AND lead_utm_campaign IS NOT NULL
  GROUP BY 1
),
bq AS (
  SELECT DISTINCT LOWER(TRIM(campaign_name)) AS name
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
)
SELECT hs.lead_utm_campaign, hs.leads
FROM hs
LEFT JOIN bq ON LOWER(TRIM(hs.lead_utm_campaign)) = bq.name
WHERE bq.name IS NULL
ORDER BY hs.leads DESC
LIMIT 10
"""
for r in client.query(sql4).result():
    print(f"  {str(r.lead_utm_campaign)[:60]:60s}  leads={r.leads}")

# 5. Leads grouped under duplicate utm_campaign names (same name, different actual campaigns)
# Detects when BQ has 2+ campaign_ids with the same campaign_name
print("\n=== 5. Duplicate campaign names in campaigns_daily (same name, 2+ IDs) ===")
sql5 = f"""
SELECT channel, campaign_name,
       COUNT(DISTINCT campaign_id) AS n_ids,
       STRING_AGG(DISTINCT campaign_id ORDER BY campaign_id LIMIT 3) AS ids
FROM `{proj}.{ds}.campaigns_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND campaign_name IS NOT NULL
GROUP BY 1, 2
HAVING n_ids > 1
ORDER BY n_ids DESC, channel
LIMIT 15
"""
rows5 = list(client.query(sql5).result())
if rows5:
    for r in rows5:
        print(f"  {r.channel:14s}  name={str(r.campaign_name)[:45]:45s}  n_ids={r.n_ids}  ids={r.ids}")
else:
    print("  (no duplicate campaign names — good)")
