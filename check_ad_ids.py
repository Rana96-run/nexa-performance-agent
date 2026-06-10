from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

q = """
SELECT
  lead_utm_source,
  lead_utm_campaign,
  lead_campaign_id_sync,
  lead_adgroup_id_sync,
  lead_ad_id_sync,
  lead_google_ad_click_id,
  COUNT(*) as cnt
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND (
    lead_adgroup_id_sync IS NOT NULL
    OR lead_campaign_id_sync IS NOT NULL
    OR lead_ad_id_sync IS NOT NULL
    OR lead_google_ad_click_id IS NOT NULL
  )
GROUP BY 1,2,3,4,5,6
ORDER BY cnt DESC
LIMIT 20
"""

rows = list(client.query(q).result())
print(f"Rows with at least one ID populated: {sum(r.cnt for r in rows)} leads")
print(f"\n{'source':<12} {'campaign':<40} {'campaign_id':<22} {'adgroup_id':<22} {'ad_id':<22} {'gclid':<10} cnt")
print("-"*140)
for r in rows:
    src   = str(r.lead_utm_source or '')[:12]
    camp  = str(r.lead_utm_campaign or '')[:40]
    cid   = str(r.lead_campaign_id_sync or '')[:22]
    agid  = str(r.lead_adgroup_id_sync or '')[:22]
    adid  = str(r.lead_ad_id_sync or '')[:22]
    gclid = str(r.lead_google_ad_click_id or '')[:10]
    print(f"{src:<12} {camp:<40} {cid:<22} {agid:<22} {adid:<22} {gclid:<10} {r.cnt}")

# Summary: which sources have adgroup_id populated
print("\n\n=== adgroup_id coverage by source ===")
q2 = """
SELECT
  lead_utm_source,
  COUNTIF(lead_adgroup_id_sync IS NOT NULL) as with_adgroup,
  COUNT(*) as total,
  ROUND(COUNTIF(lead_adgroup_id_sync IS NOT NULL) / COUNT(*) * 100, 1) as pct
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
GROUP BY 1
ORDER BY total DESC
"""
for r in client.query(q2).result():
    print(f"  {str(r.lead_utm_source or 'NULL'):<15} {r.with_adgroup:>6} / {r.total:>6} ({r.pct}%)")
