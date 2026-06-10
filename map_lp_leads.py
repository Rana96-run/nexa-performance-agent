import json
from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

# Only leads from _WP suffix ads (WP landing pages) last 30d
q = """
SELECT
  lead_cta_source_sync,
  lead_utm_content,
  lead_utm_audience,
  COUNT(*) as leads,
  COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND (
    lead_utm_content LIKE '%_WP%'
    OR lead_utm_content LIKE '%Website%'
    OR lead_utm_content LIKE '%_WP'
  )
GROUP BY 1,2,3
ORDER BY leads DESC
LIMIT 40
"""
rows = list(client.query(q).result())
out = [{"cta": r.lead_cta_source_sync, "utm_content": r.lead_utm_content,
        "utm_audience": r.lead_utm_audience, "leads": r.leads, "sqls": r.sqls}
       for r in rows]
with open("D:/Nexa Performance Agent/lp_mapped.json","w",encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"Total rows: {len(rows)}")

# Also: total WP-attributed leads last 30d
q2 = """
SELECT COUNT(*) as leads, COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND (lead_utm_content LIKE '%_WP%' OR lead_utm_content LIKE '%Website%')
"""
r = list(client.query(q2).result())[0]
print(f"Total WP LP leads last 30d: {r.leads} (sqls: {r.sqls})")
