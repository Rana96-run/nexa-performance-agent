from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

# Use cta_source_url to map leads directly to LP pages
q = """
SELECT
  lead_cta_source_url,
  lead_cta_source_sync,
  COUNT(*) as leads,
  COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND lead_cta_source_url IS NOT NULL
GROUP BY 1,2
ORDER BY leads DESC
LIMIT 50
"""
rows = list(client.query(q).result())
print("=== LP Attribution via cta_source_url (last 90d) ===")
print(f"{'cta_source_url':<55} {'cta_source_sync':<35} {'leads':>6} {'sqls':>5}")
print("-"*105)
for r in rows:
    url   = str(r.lead_cta_source_url or '')[:55]
    cta   = str(r.lead_cta_source_sync or '')[:35]
    print(f"{url:<55} {cta:<35} {r.leads:>6} {r.sqls:>5}".encode('ascii','replace').decode())

# Also check coverage
q2 = """
SELECT
  COUNTIF(lead_cta_source_url IS NOT NULL) as with_url,
  COUNTIF(lead_cta_source_sync IS NOT NULL) as with_cta,
  COUNT(*) as total
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
"""
row = list(client.query(q2).result())[0]
print(f"\nCoverage (last 90d): url={row.with_url}/{row.total} | cta={row.with_cta}/{row.total}")
