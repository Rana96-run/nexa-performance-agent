from google.cloud import bigquery
c = bigquery.Client(project='angular-axle-492812-q4')
def q1(sql): return list(c.query(sql).result())
out = []

# For each NULL-channel view row, find the qoyod_source(s) of those exact leads in hubspot.
# Match on (date, utm_campaign, utm_audience) where the source is non-paid.
out.append("=== NULL-channel view rows mapped to their HubSpot qoyod_source (non-paid sources) ===")
for r in q1("""
SELECT h.qoyod_source, h.lead_utm_campaign, h.lead_utm_audience, h.date, SUM(h.leads_total) leads
FROM qoyod_marketing.hubspot_leads_module_daily h
WHERE h.qoyod_source NOT IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','TikTok Ads','LinkedIn Ads','Microsoft Ads','Organic Search')
  AND h.lead_utm_audience IS NOT NULL
  AND h.lead_utm_campaign IS NOT NULL AND TRIM(h.lead_utm_campaign) != ''
GROUP BY 1,2,3,4
ORDER BY h.date DESC, leads DESC
LIMIT 60
"""):
    out.append(f"  src={r.qoyod_source!r} d={r.date} camp={r.lead_utm_campaign!r} aud={r.lead_utm_audience!r} leads={r.leads}")

out.append("\n=== summary: NULL-channel-with-audience leads by source ===")
for r in q1("""
SELECT h.qoyod_source, SUM(h.leads_total) leads, COUNT(*) nrows
FROM qoyod_marketing.hubspot_leads_module_daily h
WHERE h.qoyod_source NOT IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','TikTok Ads','LinkedIn Ads','Microsoft Ads','Organic Search')
  AND h.lead_utm_audience IS NOT NULL
  AND h.lead_utm_campaign IS NOT NULL AND TRIM(h.lead_utm_campaign) != ''
GROUP BY 1 ORDER BY 2 DESC
"""):
    out.append(f"  src={r.qoyod_source!r} leads={r.leads} rows={r.nrows}")

open(r'D:\Nexa Performance Agent\_diag_out.txt','w',encoding='utf-8').write('\n'.join(out))
print("ok")
