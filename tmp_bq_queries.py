from google.cloud import bigquery
client = bigquery.Client()

print("=" * 60)
print("QUERY 1 - campaigns_daily Snapchat Jun 19")
print("=" * 60)
q1 = """
SELECT date, channel, COUNT(*) as row_count, ROUND(SUM(spend),2) as spend, SUM(impressions) as impr
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat'
GROUP BY date, channel
"""
results1 = list(client.query(q1))
if not results1:
    print("(no rows returned)")
for r in results1:
    print(r.date, r.channel, r.row_count, r.spend, r.impr)

print()
print("=" * 60)
print("QUERY 2 - wide_ads Snapchat Jun 19")
print("=" * 60)
q2 = """
SELECT date, channel, COUNT(*) as row_count, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date = '2026-06-19' AND channel = 'snapchat'
GROUP BY date, channel
"""
results2 = list(client.query(q2))
print('Snapchat Jun 19 in wide_ads:', len(results2), 'rows')
for r in results2:
    print(r.date, r.channel, r.row_count, r.spend)

print()
print("=" * 60)
print("QUERY 3 - Raw campaigns_daily rows Snapchat Jun 19")
print("=" * 60)
q3 = """
SELECT date, channel, campaign_id, campaign_name, spend, impressions, account_id
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat'
LIMIT 10
"""
results3 = list(client.query(q3))
if not results3:
    print("(no rows returned)")
for r in results3:
    print(dict(r))

print()
print("=" * 60)
print("QUERY 4 - wide_ads Snapchat Jun 17-20")
print("=" * 60)
q4 = """
SELECT date, channel, COUNT(*) as row_count, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN '2026-06-17' AND '2026-06-20' AND channel = 'snapchat'
GROUP BY date, channel ORDER BY date
"""
results4 = list(client.query(q4))
if not results4:
    print("(no rows returned)")
for r in results4:
    print(r.date, r.channel, r.row_count, r.spend)

print()
print("=" * 60)
print("QUERY 5 - ads_daily Snapchat Jun 17-20")
print("=" * 60)
q5 = """
SELECT date, channel, COUNT(*) as row_count, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.ads_daily`
WHERE date BETWEEN '2026-06-17' AND '2026-06-20' AND channel = 'snapchat'
GROUP BY date, channel ORDER BY date
"""
results5 = list(client.query(q5))
if not results5:
    print("(no rows returned)")
for r in results5:
    print(r.date, r.channel, r.row_count, r.spend)

print()
print("ALL QUERIES COMPLETE")
