from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

# 1. Schema — find page_url / cta_source / referrer columns
table = client.get_table('angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual')
print("=== Columns ===")
for f in table.schema:
    if any(k in f.name.lower() for k in ['page','url','cta','source','referr','lp','form']):
        print(f"  * {f.name} ({f.field_type})")
print("\nAll columns:")
for f in table.schema:
    print(f"  {f.name}")

# 2. Check lead_utm_content for LP slug hints (it carries ad name / cta_source for WP forms)
q = """
SELECT
  lead_utm_content,
  lead_utm_campaign,
  COUNT(*) as leads,
  COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND lead_utm_source NOT IN ('Snapchat','Tiktok','fb','ig','li')
  AND lead_utm_content IS NOT NULL
GROUP BY 1,2
ORDER BY leads DESC
LIMIT 30
"""
rows = list(client.query(q).result())
print("\n=== lead_utm_content (non-social, last 30d) ===")
print(f"{'utm_content':<50} {'campaign':<40} {'leads':>6} {'sqls':>5}")
print("-"*100)
for r in rows:
    c = str(r.lead_utm_content or '')[:50]
    camp = str(r.lead_utm_campaign or '')[:40]
    print(f"{c:<50} {camp:<40} {r.leads:>6} {r.sqls:>5}".encode('ascii','replace').decode())
