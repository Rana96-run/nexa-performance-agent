from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

# Count non-null gclids in BQ
q = """
SELECT
  COUNTIF(lead_google_ad_click_id IS NOT NULL) as with_gclid,
  COUNT(*) as total,
  MAX(hs_createdate) as latest_date
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
"""
row = list(client.query(q).result())[0]
print(f"Total leads in BQ: {row.total}")
print(f"With gclid: {row.with_gclid}")
print(f"Latest date: {row.latest_date}")

# Sample recent leads with gclid
q2 = """
SELECT lead_google_ad_click_id, lead_utm_campaign, lead_utm_source, hs_createdate
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE lead_google_ad_click_id IS NOT NULL
ORDER BY hs_createdate DESC
LIMIT 5
"""
rows = list(client.query(q2).result())
print(f"\nSample BQ rows with gclid ({len(rows)}):")
for r in rows:
    print(f"  {str(r.lead_google_ad_click_id)[:40]}  {r.lead_utm_campaign}  {r.hs_createdate}")
