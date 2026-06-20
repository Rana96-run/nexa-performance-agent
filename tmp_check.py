from google.cloud import bigquery
client = bigquery.Client()

# Check Meta coverage specifically for Jun 16-20
q = """
SELECT date, channel, COUNT(*) as row_count, ROUND(SUM(spend),2) as spend
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE date >= '2026-06-16' AND channel = 'meta'
GROUP BY date, channel ORDER BY date
"""
print("=== campaigns_daily Meta from Jun 16 ===")
results = list(client.query(q).result())
if results:
    for r in results:
        print(f"  {r.date}  {r.channel:20s}  {r.row_count:5d} rows  ${r.spend:.2f}")
else:
    print("  NO DATA")
