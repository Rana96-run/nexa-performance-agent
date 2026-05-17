"""Compare the 2 Google Ads accounts on last 60d performance.
Account 1: 1513020554
Account 2: 5753494964
Goal: pick the better-performing one for the new campaigns."""
import json
from collectors.bq_writer import get_client, DATASET, PROJECT_ID
c = get_client()
DS = f"`{PROJECT_ID}.{DATASET}`"

sql = f"""
WITH camp AS (
  SELECT account_id,
         SUM(spend) AS spend,
         SUM(impressions) AS impressions,
         SUM(clicks) AS clicks,
         AVG(impression_share) AS avg_is,
         AVG(top_impression_share) AS avg_top_is,
         AVG(lost_is_budget) AS avg_lost_budget,
         AVG(lost_is_rank) AS avg_lost_rank,
         COUNT(DISTINCT campaign_id) AS campaigns
  FROM {DS}.campaigns_daily
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY account_id
),
hs AS (
  SELECT date, lead_utm_campaign,
         SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM {DS}.hubspot_leads_module_daily
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY date, lead_utm_campaign
),
attrib AS (
  SELECT c.account_id, SUM(hs.leads) AS leads, SUM(hs.sqls) AS sqls
  FROM {DS}.campaigns_daily c
  LEFT JOIN hs ON c.date = hs.date
              AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
  WHERE c.channel = 'google_ads'
    AND c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY c.account_id
),
deals AS (
  SELECT c.account_id, SUM(d.deals_won) AS deals_won, SUM(d.amount_won) AS rev
  FROM {DS}.campaigns_daily c
  LEFT JOIN {DS}.hubspot_deals_daily d
         ON c.date = d.date
        AND LOWER(c.campaign_name) = LOWER(d.deal_utm_campaign)
  WHERE c.channel = 'google_ads'
    AND c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY c.account_id
)
SELECT camp.account_id,
       camp.campaigns,
       ROUND(camp.spend, 0) AS spend,
       camp.impressions, camp.clicks,
       ROUND(camp.avg_is*100, 1) AS avg_is_pct,
       ROUND(camp.avg_top_is*100, 1) AS avg_top_is_pct,
       ROUND(camp.avg_lost_budget*100, 1) AS avg_lost_budget_pct,
       ROUND(camp.avg_lost_rank*100, 1) AS avg_lost_rank_pct,
       attrib.leads, attrib.sqls,
       deals.deals_won,
       ROUND(deals.rev, 0) AS rev,
       ROUND(SAFE_DIVIDE(camp.spend, NULLIF(attrib.leads,0)), 1) AS cpl,
       ROUND(SAFE_DIVIDE(camp.spend, NULLIF(attrib.sqls,0)), 1) AS cpql,
       ROUND(SAFE_DIVIDE(deals.rev, NULLIF(camp.spend,0)), 2) AS roas
FROM camp
LEFT JOIN attrib USING (account_id)
LEFT JOIN deals  USING (account_id)
ORDER BY spend DESC
"""

for r in c.query(sql).result():
    print(json.dumps(dict(r), default=str, ensure_ascii=False, indent=2))
