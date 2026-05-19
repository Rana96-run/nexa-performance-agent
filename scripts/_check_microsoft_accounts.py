"""Compare the 2 Microsoft Ads accounts on last-30d performance to pick
the better one for the Qawaem campaign clone."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.cloud import bigquery

c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")

# Microsoft Ads in BQ — check campaign_account or account_id field
print("=" * 70)
print("Microsoft Ads accounts in BQ campaigns_daily (last 30d)")
print("=" * 70)
q = """
SELECT account_id,
       SUM(spend) AS spend,
       SUM(impressions) AS impressions,
       SUM(clicks) AS clicks,
       SUM(leads) AS leads,
       AVG(impression_share) AS avg_is,
       COUNT(DISTINCT campaign_id) AS campaigns,
       COUNT(DISTINCT date) AS active_days
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE channel = 'microsoft_ads'
  AND date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
              AND DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
GROUP BY account_id
ORDER BY spend DESC
"""
for row in c.query(q).result():
    sp = row.spend or 0
    lds = row.leads or 0
    imp = row.impressions or 0
    clk = row.clicks or 0
    isv = row.avg_is or 0
    cpl = sp/lds if lds else 0
    cpc = sp/clk if clk else 0
    ctr = (clk/imp*100) if imp else 0
    print(f"\n  account_id={row.account_id}")
    print(f"    spend=${sp:>8,.0f}  impr={imp:>10,}  clicks={clk:>6,}  leads={lds:>4}")
    print(f"    campaigns={row.campaigns}  active_days={row.active_days}")
    print(f"    CPL=${cpl:.2f}  CPC=${cpc:.2f}  CTR={ctr:.2f}%  avg_IS={isv*100:.1f}%")
