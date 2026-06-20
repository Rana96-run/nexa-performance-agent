"""Follow-up investigation: Why is wide_ads missing Jun 19 Snapchat?"""
from google.cloud import bigquery
client = bigquery.Client()

print("=" * 60)
print("ads_daily Jun 19 Snapchat: spend distribution")
print("=" * 60)
q = """
SELECT
  CASE WHEN spend > 0 THEN 'spend>0' ELSE 'spend=0' END as spend_bucket,
  COUNT(*) as ad_count,
  ROUND(SUM(spend),2) as total_spend
FROM `angular-axle-492812-q4.qoyod_marketing.ads_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat'
GROUP BY 1
ORDER BY 1
"""
results = list(client.query(q))
for r in results:
    print(f"  {r.spend_bucket}: {r.ad_count} ads, total_spend={r.total_spend}")

print()
print("=" * 60)
print("ads_daily Jun 19 Snapchat: sample of spend>0 rows")
print("=" * 60)
q = """
SELECT date, channel, ad_id, ad_name, campaign_name, adset_name, spend, impressions
FROM `angular-axle-492812-q4.qoyod_marketing.ads_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat' AND spend > 0
LIMIT 10
"""
results = list(client.query(q))
print(f"Result rows: {len(results)}")
for r in results:
    print(f"  ad_id={r.ad_id} ad_name={r.ad_name} campaign_name={r.campaign_name} spend={r.spend}")
if not results:
    print("  NO ROWS WITH spend>0 IN ads_daily FOR JUN 19 SNAPCHAT")

print()
print("=" * 60)
print("campaigns_daily Jun 17-20 Snapchat: spend distribution")
print("=" * 60)
q = """
SELECT date, ROUND(SUM(spend),2) as spend, SUM(impressions) as impr
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date BETWEEN '2026-06-17' AND '2026-06-20' AND channel = 'snapchat'
GROUP BY date ORDER BY date
"""
results = list(client.query(q))
for r in results:
    print(f"  date={r.date} spend={r.spend} impr={r.impr}")

print()
print("=" * 60)
print("Jun 19 Snapchat in campaigns_daily: spend>0 campaigns")
print("=" * 60)
q = """
SELECT campaign_id, campaign_name, spend, impressions
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat' AND spend > 0
ORDER BY spend DESC
LIMIT 10
"""
results = list(client.query(q))
print(f"Result rows: {len(results)}")
for r in results:
    print(f"  campaign_id={r.campaign_id} campaign_name={r.campaign_name} spend={r.spend}")
if not results:
    print("  NO spend>0 CAMPAIGNS IN campaigns_daily FOR JUN 19 SNAPCHAT")

print()
print("DONE")
