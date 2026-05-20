"""Microsoft Ads campaign-level last-30d using HUBSPOT as lead source of truth.

Per CLAUDE.md non-negotiable rule:
  - Cost comes from the channel (campaigns_daily.spend)
  - Leads + SQLs come from HubSpot Lead Module ONLY (hubspot_leads_module_daily)
  - Pre-aggregate HubSpot before joining to avoid spend fan-out

Channel-reported 'leads' on WebsiteTraffic objectives are page-views, not
real form submissions. This script corrects the earlier analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.cloud import bigquery

c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")

q = """
WITH hs AS (
  SELECT
    LOWER(lead_utm_campaign) AS campaign_key,
    SUM(leads_total)         AS hs_leads,
    SUM(leads_qualified)     AS hs_sqls
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
                AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
    AND lead_utm_campaign IS NOT NULL
  GROUP BY campaign_key
),
spend AS (
  SELECT
    campaign_name,
    SUM(spend)            AS spend,
    SUM(clicks)           AS clicks,
    SUM(impressions)      AS impressions,
    AVG(impression_share) AS avg_is,
    AVG(lost_is_budget)   AS lost_budget,
    AVG(lost_is_rank)     AS lost_rank,
    COUNT(DISTINCT date)  AS active_days
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
  WHERE channel = 'microsoft_ads'
    AND account_id = '188176729'
    AND date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
                AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
    AND status = 'Active'
  GROUP BY campaign_name
)
SELECT
  s.campaign_name,
  s.spend, s.clicks, s.impressions,
  s.avg_is, s.lost_budget, s.lost_rank, s.active_days,
  COALESCE(hs.hs_leads, 0) AS hs_leads,
  COALESCE(hs.hs_sqls,  0) AS hs_sqls
FROM spend s
LEFT JOIN hs ON LOWER(s.campaign_name) = hs.campaign_key
ORDER BY s.spend DESC
"""

print(f"{'Campaign':<55} {'Spend':>8} {'Clicks':>7} {'HS_Lds':>7} {'HS_SQL':>7} {'CPL':>9} {'CPQL':>9} {'IS%':>5} {'L-Bud':>6} {'L-Rnk':>6}")
print("-" * 130)
for r in c.query(q).result():
    sp   = r.spend or 0
    clk  = r.clicks or 0
    lds  = r.hs_leads or 0
    sqls = r.hs_sqls or 0
    cpl  = sp/lds if lds else 0
    cpql = sp/sqls if sqls else 0
    isv  = (r.avg_is or 0) * 100
    lbud = (r.lost_budget or 0) * 100
    lrnk = (r.lost_rank or 0) * 100
    print(f"{(r.campaign_name or '?')[:53]:<53} ${sp:>7,.0f} {clk:>7,} {lds:>7} {sqls:>7} "
          f"${cpl:>7.2f} ${cpql:>7.2f} {isv:>4.1f}% {lbud:>5.1f}% {lrnk:>5.1f}%")
