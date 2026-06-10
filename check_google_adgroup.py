from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

q = """
SELECT
  lead_utm_campaign,
  lead_campaign_id_sync,
  lead_adgroup_id_sync,
  COUNT(*) as cnt
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE lead_utm_source = 'Google'
  AND hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
GROUP BY 1,2,3
ORDER BY cnt DESC
LIMIT 30
"""

rows = list(client.query(q).result())
print(f"{'campaign':<45} {'campaign_id':<20} {'adgroup_id':<20} cnt")
print("-"*95)
for r in rows:
    camp  = str(r.lead_utm_campaign or '')[:45]
    cid   = str(r.lead_campaign_id_sync or 'NULL')[:20]
    agid  = str(r.lead_adgroup_id_sync or 'NULL')[:20]
    print(f"{camp:<45} {cid:<20} {agid:<20} {r.cnt}")
