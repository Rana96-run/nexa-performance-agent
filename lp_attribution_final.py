import json
from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

# Map utm_content patterns to LP pages
# Brand/MainSite campaigns are EXCLUDED (they go to qoyod.com, not lp.qoyod.com)
q = """
SELECT
  CASE
    -- ZATCA Phase 2 LP: /zatca-einvoice/
    WHEN lead_utm_content LIKE '%Phase2_WP%'     THEN 'zatca-einvoice'
    WHEN lead_utm_content LIKE '%ZatcaPhase2_WP' THEN 'zatca-einvoice'
    -- E-Invoice Integration LP: /einvoice-integration/
    WHEN lead_utm_content LIKE '%E-invoice%WP%'   THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%Invoice_WP%'     THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%Vendor_Invoice_WP%' THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%ZATCA_WP%'       THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%Invoice_Pmax_Website%' THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%Pmax_AR_Feature_Invoice_WP%' THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%Bing_AR_Feature_Invoice_WP%' THEN 'einvoice-integration'
    WHEN lead_utm_content LIKE '%Bing_AR_Feature_Traffic_Invoice_WP%' THEN 'einvoice-integration'
    -- Cloud Accounting LP: /accounting-system/
    WHEN lead_utm_content LIKE '%CloudAccounting_WP%' THEN 'accounting-system'
    -- Accounting (best solution) LP: /accounting/
    WHEN lead_utm_content LIKE '%Generic_WP%'          THEN 'accounting'
    WHEN lead_utm_content LIKE '%AccountingSoftware_WP%' THEN 'accounting'
    -- Qawaem LP: /qawaem/
    WHEN lead_utm_content LIKE '%FinancialSt%WP%'  THEN 'qawaem'
    -- POS LP (draft): /pos/
    WHEN lead_utm_content LIKE '%POS_WP%'          THEN 'pos-draft'
    -- Bookkeeping (draft):
    WHEN lead_utm_content LIKE '%BK_WP%'           THEN 'bookkeeping-draft'
    -- Pricing page (not an LP in tracker)
    WHEN lead_utm_content LIKE '%PricingOffer_WP%' THEN 'pricing-page'
    -- Brand → main site (exclude from LP tracker)
    WHEN lead_utm_content LIKE '%Branding%WP%'     THEN 'brand-mainsite'
    WHEN lead_utm_content LIKE '%Bing_AR_Branding%WP%' THEN 'brand-mainsite'
    ELSE 'other'
  END AS lp_slug,
  COUNT(*) as leads,
  COUNTIF(is_qualified) as sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND (lead_utm_content LIKE '%_WP%' OR lead_utm_content LIKE '%Website%')
GROUP BY 1
ORDER BY leads DESC
"""
rows = list(client.query(q).result())
out = [{"lp_slug": r.lp_slug, "leads": r.leads, "sqls": r.sqls} for r in rows]
with open("D:/Nexa Performance Agent/lp_final_attribution.json","w",encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"{'lp_slug':<30} {'leads':>6} {'sqls':>5}")
print("-"*45)
for r in rows:
    print(f"{r.lp_slug:<30} {r.leads:>6} {r.sqls:>5}")
