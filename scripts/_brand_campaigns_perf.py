"""Pull 30d + 90d conversion performance for the 3 brand campaigns on Acc 1.
Spend from campaigns_daily, leads/SQLs from hubspot_leads_module_daily
joined on lower(campaign_name) = lead_utm_campaign per KPI rules.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from dotenv import load_dotenv; load_dotenv()
from google.cloud import bigquery

bq = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")

CAMPS = "('22434988923','23032247671','22221111741')"

for window in [14, 30, 90]:
    print(f"\n{'=' * 78}")
    print(f"  Brand campaigns — last {window} days")
    print('=' * 78)
    q = f"""
    WITH hs AS (
      SELECT date, LOWER(lead_utm_campaign) AS camp,
             SUM(leads_total) AS leads,
             SUM(leads_qualified) AS sqls,
             SUM(leads_disqualified) AS junk
      FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL {window} DAY)
      GROUP BY date, camp
    ),
    spend AS (
      SELECT campaign_id, campaign_name, date,
             SUM(spend)  AS spend,
             SUM(clicks) AS clicks,
             SUM(impressions) AS impr
      FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
      WHERE channel = 'google_ads'
        AND account_id = '1513020554'
        AND campaign_id IN {CAMPS}
        AND date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL {window} DAY)
      GROUP BY campaign_id, campaign_name, date
    )
    SELECT s.campaign_id, s.campaign_name,
           SUM(s.spend)    AS spend,
           SUM(s.clicks)   AS clicks,
           SUM(s.impr)     AS impr,
           SUM(hs.leads)   AS leads,
           SUM(hs.sqls)    AS sqls,
           SUM(hs.junk)    AS junk,
           SAFE_DIVIDE(SUM(s.spend), SUM(hs.leads)) AS cpl,
           SAFE_DIVIDE(SUM(s.spend), SUM(hs.sqls))  AS cpql,
           SAFE_DIVIDE(SUM(s.clicks), SUM(s.impr))  AS ctr
    FROM spend s
    LEFT JOIN hs ON s.date = hs.date AND LOWER(s.campaign_name) = hs.camp
    GROUP BY s.campaign_id, s.campaign_name
    ORDER BY spend DESC
    """
    rows = list(bq.query(q).result())
    if not rows:
        print("  (no data)")
        continue
    print(f"  {'campaign':<38} {'spend':>9} {'clk':>6} {'impr':>8} "
          f"{'CTR':>6} {'lds':>5} {'sql':>5} {'CPL':>6} {'CPQL':>7}")
    for r in rows:
        ctr = (r.ctr or 0) * 100
        print(f"  {r.campaign_name[:38]:<38} ${r.spend or 0:>8.0f} "
              f"{r.clicks or 0:>6} {r.impr or 0:>8} {ctr:>5.2f}% "
              f"{r.leads or 0:>5} {r.sqls or 0:>5} "
              f"${r.cpl or 0:>5.0f} ${r.cpql or 0:>6.0f}")
