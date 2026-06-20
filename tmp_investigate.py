"""Investigation script for Jun 19 Snapchat gap."""
from google.cloud import bigquery
client = bigquery.Client()

print("=" * 60)
print("STEP 1: campaigns_daily for Jun 19 Snapchat")
print("=" * 60)
q = """
SELECT date, channel, COUNT(*) as rows, ROUND(SUM(spend),2) as spend, SUM(impressions) as impr
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat'
GROUP BY date, channel
"""
rows = list(client.query(q))
print(f"Result rows: {len(rows)}")
for r in rows:
    print(f"  date={r.date} channel={r.channel} rows={r.rows} spend={r.spend} impr={r.impr}")
if not rows:
    print("  NO ROWS FOUND")

print()
print("=" * 60)
print("STEP 4: wide_ads for Jun 19 Snapchat")
print("=" * 60)
q = """
SELECT date, channel, COUNT(*) as rows, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date = '2026-06-19' AND channel = 'snapchat'
GROUP BY date, channel
"""
rows = list(client.query(q))
print(f"Snapchat Jun 19 in wide_ads: {len(rows)} result rows")
for r in rows:
    print(f"  date={r.date} channel={r.channel} rows={r.rows} spend={r.spend}")
if not rows:
    print("  NO ROWS FOUND")

print()
print("=" * 60)
print("STEP 5: Raw campaigns_daily rows for Jun 19 Snapchat")
print("=" * 60)
q = """
SELECT date, channel, campaign_id, campaign_name, spend, impressions, account_id
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date = '2026-06-19' AND channel = 'snapchat'
LIMIT 10
"""
rows = list(client.query(q))
print(f"Result rows: {len(rows)}")
for r in rows:
    print(dict(r))
if not rows:
    print("  NO ROWS FOUND")

print()
print("=" * 60)
print("STEP 6: wide_ads for Jun 17-20 Snapchat")
print("=" * 60)
q = """
SELECT date, channel, COUNT(*) as rows, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN '2026-06-17' AND '2026-06-20' AND channel = 'snapchat'
GROUP BY date, channel ORDER BY date
"""
rows = list(client.query(q))
print(f"Result rows: {len(rows)}")
for r in rows:
    print(f"  date={r.date} channel={r.channel} rows={r.rows} spend={r.spend}")
if not rows:
    print("  NO ROWS FOUND")

print()
print("=" * 60)
print("STEP 7: ads_daily for Jun 17-20 Snapchat")
print("=" * 60)
q = """
SELECT date, channel, COUNT(*) as rows, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.ads_daily`
WHERE date BETWEEN '2026-06-17' AND '2026-06-20' AND channel = 'snapchat'
GROUP BY date, channel ORDER BY date
"""
rows = list(client.query(q))
print(f"Result rows: {len(rows)}")
for r in rows:
    print(f"  date={r.date} channel={r.channel} rows={r.rows} spend={r.spend}")
if not rows:
    print("  NO ROWS FOUND")

print()
print("DONE")
