"""Pull TikTok current state from BQ — campaigns, spend, leads, SQLs over
last 30d and 7d to inform June strategy."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.cloud import bigquery

PROJECT = "angular-axle-492812-q4"

c = bigquery.Client(project=PROJECT, location="me-central1")

print("=" * 78)
print("TIKTOK 30-DAY BLENDED + 7-DAY DETAIL")
print("=" * 78)

# 30-day blended for TikTok
q1 = """
SELECT
  SUM(spend)        AS spend,
  SUM(impressions)  AS impressions,
  SUM(clicks)       AS clicks,
  SUM(leads_total)  AS leads,
  SUM(qualified) AS sqls
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE channel = 'tiktok'
  AND date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
              AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
"""
for row in c.query(q1).result():
    spend = row.spend or 0
    leads = row.leads or 0
    sqls  = row.sqls or 0
    print(f"\n  Last 30d:  spend=${spend:,.0f}  impr={row.impressions or 0:,}  clicks={row.clicks or 0:,}  leads={leads}  SQLs={sqls}")
    if leads:  print(f"             CPL  = ${spend/leads:.2f}")
    if sqls:   print(f"             CPQL = ${spend/sqls:.2f}")

# Per-campaign last 30d
print("\n" + "=" * 78)
print("Per-campaign — last 30d")
print("=" * 78)
q2 = """
SELECT
  campaign_name,
  SUM(spend) AS spend,
  SUM(clicks) AS clicks,
  SUM(leads_total) AS leads,
  SUM(qualified) AS sqls,
  COUNT(DISTINCT date) AS active_days
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE channel = 'tiktok'
  AND date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
              AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
GROUP BY campaign_name
ORDER BY spend DESC
"""
print(f"{'Campaign':<55} {'Spend':>10} {'Clicks':>8} {'Leads':>6} {'SQLs':>5} {'Days':>5}")
total_spend = total_leads = total_sqls = 0
for row in c.query(q2).result():
    spend = row.spend or 0
    leads = row.leads or 0
    sqls  = row.sqls or 0
    total_spend += spend
    total_leads += leads
    total_sqls  += sqls
    print(f"  {(row.campaign_name or '?')[:53]:<53} ${spend:>8,.0f} {row.clicks or 0:>8,} {leads:>6} {sqls:>5} {row.active_days:>5}")

print(f"\n  TOTAL  spend=${total_spend:,.0f}  leads={total_leads}  SQLs={total_sqls}")
if total_leads:  print(f"  CPL   = ${total_spend/total_leads:.2f}")
if total_sqls:   print(f"  CPQL  = ${total_spend/total_sqls:.2f}")

# 7-day trend
print("\n" + "=" * 78)
print("Last 7 days vs prior 7")
print("=" * 78)
q3 = """
WITH p AS (
  SELECT
    CASE WHEN date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
                       AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
         THEN 'last7'
         WHEN date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 14 DAY)
                       AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 8 DAY)
         THEN 'prior7'
    END AS bucket,
    spend, leads_total, qualified
  FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
  WHERE channel = 'tiktok'
)
SELECT bucket, SUM(spend) sp, SUM(leads_total) lds, SUM(qualified) sqls
FROM p WHERE bucket IS NOT NULL
GROUP BY bucket
ORDER BY bucket
"""
for row in c.query(q3).result():
    sp = row.sp or 0
    lds = row.lds or 0
    sqls = row.sqls or 0
    print(f"  {row.bucket:<8}  spend=${sp:,.0f}  leads={lds}  SQLs={sqls}", end="")
    if lds:  print(f"  CPL=${sp/lds:.2f}", end="")
    if sqls: print(f"  CPQL=${sp/sqls:.2f}", end="")
    print()
