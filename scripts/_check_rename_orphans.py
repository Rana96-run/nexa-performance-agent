"""
Find leads orphaned by campaign/adset/ad RENAMES:
- Lead's UTM name no longer matches any campaign_name in campaigns_daily
- BUT lead's lead_*_id_sync DOES match a campaign_id/adset_id/ad_id
â†’ proves the entity was renamed; name-join loses the lead, ID-join recovers it.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]
LB = 90

def sec(t): print(f"\n{'='*80}\n{t}\n{'='*80}")

# ---- CAMPAIGN-level rename orphans ----
sec(f"1. CAMPAIGN-level rename orphans (last {LB} days)")
sql = f"""
WITH ld AS (
  SELECT lead_campaign_id_sync AS id, lead_utm_campaign AS old_name,
         qoyod_source, SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
    AND lead_campaign_id_sync IS NOT NULL
    AND lead_utm_campaign IS NOT NULL
  GROUP BY 1, 2, 3
),
camp AS (
  SELECT campaign_id, ANY_VALUE(campaign_name) AS cur_name, ANY_VALUE(channel) AS channel,
         SUM(spend) AS spend
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
  GROUP BY 1
),
name_index AS (
  SELECT DISTINCT LOWER(TRIM(campaign_name)) AS n
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
)
SELECT camp.channel, ld.id, ld.old_name AS lead_utm_name,
       camp.cur_name AS current_campaign_name,
       camp.spend, ld.leads, ld.sqls
FROM ld
JOIN camp ON ld.id = camp.campaign_id
LEFT JOIN name_index ni ON LOWER(TRIM(ld.old_name)) = ni.n
WHERE ni.n IS NULL                          -- old UTM name no longer exists in campaigns_daily
  AND LOWER(TRIM(ld.old_name)) != LOWER(TRIM(camp.cur_name))  -- and differs from current
ORDER BY ld.leads DESC
LIMIT 30
"""
rows = list(client.query(sql).result())
if rows:
    total_l = sum(r.leads for r in rows); total_s = sum(r.sqls or 0 for r in rows)
    for r in rows:
        spend = f"${r.spend:.0f}" if r.spend else "$0"
        print(f"  [{r.channel}] cid={r.id}  spend={spend}  leads={r.leads}  sqls={r.sqls}")
        print(f"      OLD utm_campaign = {r.lead_utm_name}")
        print(f"      NEW campaign_name = {r.current_campaign_name}")
    print(f"\n  TOTAL RECOVERED BY ID JOIN: {total_l} leads, {total_s} SQLs")
else:
    print("  (no campaign rename orphans)")

# ---- ADSET-level rename orphans ----
sec(f"2. ADSET-level rename orphans (last {LB} days)")
sql2 = f"""
WITH ld AS (
  SELECT lead_adgroup_id_sync AS id, lead_utm_medium AS old_name,
         qoyod_source, SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
    AND lead_adgroup_id_sync IS NOT NULL
  GROUP BY 1, 2, 3
),
ads AS (
  SELECT adset_id, ANY_VALUE(adset_name) AS cur_name, ANY_VALUE(channel) AS channel,
         SUM(spend) AS spend
  FROM `{proj}.{ds}.adsets_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
  GROUP BY 1
)
SELECT ads.channel, ld.id,
       ld.old_name AS lead_utm_medium,
       ads.cur_name AS current_adset_name,
       ads.spend, ld.leads, ld.sqls
FROM ld
JOIN ads ON ld.id = ads.adset_id
ORDER BY ld.leads DESC
LIMIT 30
"""
rows = list(client.query(sql2).result())
if rows:
    total_l = sum(r.leads for r in rows); total_s = sum(r.sqls or 0 for r in rows)
    for r in rows:
        spend = f"${r.spend:.0f}" if r.spend else "$0"
        print(f"  [{r.channel}] aid={r.id}  spend={spend}  leads={r.leads}  sqls={r.sqls}")
        print(f"      adset name = {r.current_adset_name}")
    print(f"\n  TOTAL leads matchable by adset_id: {total_l} leads, {total_s} SQLs")
else:
    print("  (no adset-id leads found)")

# ---- AD-level rename orphans ----
sec(f"3. AD-level rename orphans (last {LB} days)")
sql3 = f"""
WITH ld AS (
  SELECT lead_ad_id_sync AS id, lead_utm_content AS old_name,
         qoyod_source, SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
    AND lead_ad_id_sync IS NOT NULL
  GROUP BY 1, 2, 3
),
ads AS (
  SELECT ad_id, ANY_VALUE(ad_name) AS cur_name, ANY_VALUE(channel) AS channel,
         SUM(spend) AS spend
  FROM `{proj}.{ds}.ads_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
  GROUP BY 1
),
name_index AS (
  SELECT DISTINCT LOWER(TRIM(ad_name)) AS n
  FROM `{proj}.{ds}.ads_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LB} DAY)
    AND ad_name IS NOT NULL
)
SELECT ads.channel, ld.id,
       ld.old_name AS lead_utm_content,
       ads.cur_name AS current_ad_name,
       ads.spend, ld.leads, ld.sqls
FROM ld
JOIN ads ON ld.id = ads.ad_id
LEFT JOIN name_index ni ON LOWER(TRIM(ld.old_name)) = ni.n
WHERE ni.n IS NULL                                    -- ad name in UTM no longer exists
  AND LOWER(TRIM(IFNULL(ld.old_name,''))) != LOWER(TRIM(IFNULL(ads.cur_name,'')))
ORDER BY ld.leads DESC
LIMIT 30
"""
rows = list(client.query(sql3).result())
if rows:
    total_l = sum(r.leads for r in rows); total_s = sum(r.sqls or 0 for r in rows)
    for r in rows:
        spend = f"${r.spend:.0f}" if r.spend else "$0"
        print(f"  [{r.channel}] ad_id={r.id}  spend={spend}  leads={r.leads}  sqls={r.sqls}")
        print(f"      OLD utm_content = {r.lead_utm_content}")
        print(f"      NEW ad_name = {r.current_ad_name}")
    print(f"\n  TOTAL RECOVERED BY AD-ID JOIN: {total_l} leads, {total_s} SQLs")
else:
    print("  (no ad rename orphans)")

