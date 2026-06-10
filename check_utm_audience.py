from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

q = """
SELECT
  lead_utm_source,
  lead_utm_campaign,
  lead_utm_audience,
  COUNT(*) as leads,
  COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND lead_utm_audience IS NOT NULL
GROUP BY 1,2,3
ORDER BY leads DESC
LIMIT 40
"""

rows = list(client.query(q).result())
print(f"{'source':<12} {'campaign':<45} {'utm_audience':<50} {'leads':>6} {'sqls':>5}")
print("-"*125)
for r in rows:
    src  = str(r.lead_utm_source or '')[:12]
    camp = str(r.lead_utm_campaign or '')[:45]
    aud  = str(r.lead_utm_audience or '')[:50]
    print(f"{src:<12} {camp:<45} {aud:<50} {r.leads:>6} {r.sqls:>5}".encode('ascii','replace').decode())
