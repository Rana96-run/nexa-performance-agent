from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

q = """
SELECT
  lead_utm_source,
  lead_utm_campaign,
  lead_utm_medium,
  lead_cta_source_url,
  COUNT(*) as cnt
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1,2,3,4
ORDER BY cnt DESC
LIMIT 30
"""

rows = list(client.query(q).result())
print(f"Total groups: {len(rows)}")
print(f"\n{'utm_source':<20} {'utm_campaign':<35} {'utm_medium':<15} {'cta_source_url':<55} {'cnt'}")
print("-" * 135)
for r in rows:
    src  = str(r.lead_utm_source or '')[:20]
    camp = str(r.lead_utm_campaign or '')[:35]
    med  = str(r.lead_utm_medium or '')[:15]
    url  = str(r.lead_cta_source_url or '')[:55]
    print(f"{src:<20} {camp:<35} {med:<15} {url:<55} {r.cnt}")

# Also check specifically for lp.qoyod.com in cta_source_url
print("\n\n=== Leads with lp.qoyod.com in cta_source_url ===")
q2 = """
SELECT
  lead_cta_source_url,
  lead_utm_campaign,
  lead_utm_source,
  COUNT(*) as cnt
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE lead_cta_source_url LIKE '%lp.qoyod.com%'
AND hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1,2,3
ORDER BY cnt DESC
LIMIT 20
"""
lp_rows = list(client.query(q2).result())
print(f"LP-attributed leads: {sum(r.cnt for r in lp_rows)}")
for r in lp_rows:
    print(f"  {str(r.lead_cta_source_url or '')[:70]} | {r.lead_utm_campaign} | {r.cnt}")
