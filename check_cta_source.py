from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

q = """
SELECT
  lead_cta_source_sync,
  COUNT(*) as leads,
  COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND lead_cta_source_sync IS NOT NULL
GROUP BY 1
ORDER BY leads DESC
"""
rows = list(client.query(q).result())
print(f"{'cta_source_sync':<60} {'leads':>6} {'sqls':>5}")
print("-"*75)
for r in rows:
    cta = str(r.lead_cta_source_sync or '')[:60]
    print(f"{cta:<60} {r.leads:>6} {r.sqls:>5}".encode('ascii','replace').decode())
