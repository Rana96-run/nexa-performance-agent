import json
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
LIMIT 20
"""
rows = list(client.query(q).result())
out = [{"cta": r.lead_cta_source_sync, "leads": r.leads, "sqls": r.sqls} for r in rows]
with open("D:/Nexa Performance Agent/cta_sources.json","w",encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("Written to cta_sources.json")
