import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from collectors.bq_writer import get_client
c = get_client(); p = os.getenv("BQ_PROJECT_ID"); d = os.getenv("BQ_DATASET")

PAID = "('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')"

print("=== wide_ads last 7d (channel grain) ===")
for r in c.query(f"""
  SELECT channel, SUM(leads_total) leads, SUM(spend) spend
  FROM `{p}.{d}.wide_ads`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                 AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
  GROUP BY 1 ORDER BY 2 DESC
""").result():
    print(f"  {r.channel:<15s} leads={r.leads}  spend={r.spend:.0f}")

print()
print("=== hubspot_leads_module_daily direct last 7d ===")
total = 0
for r in c.query(f"""
  SELECT qoyod_source, SUM(leads_total) leads
  FROM `{p}.{d}.hubspot_leads_module_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                 AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    AND qoyod_source IN {PAID}
  GROUP BY 1 ORDER BY 2 DESC
""").result():
    print(f"  {r.qoyod_source:<15s} leads={r.leads}")
    total += r.leads
print(f"  TOTAL: {total}")

print()
print("=== ALL distinct qoyod_source in module_daily last 7d ===")
for r in c.query(f"""
  SELECT qoyod_source, SUM(leads_total) leads
  FROM `{p}.{d}.hubspot_leads_module_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                 AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
  GROUP BY 1 ORDER BY 2 DESC
""").result():
    print(f"  {repr(r.qoyod_source):<25s} {r.leads}")

print()
print("=== campaigns_daily channels last 7d (Snapchat) ===")
for r in c.query(f"""
  SELECT channel, COUNT(*) rows, SUM(spend) spend
  FROM `{p}.{d}.campaigns_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                 AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    AND LOWER(channel) LIKE '%snap%'
  GROUP BY 1
""").result():
    print(f"  channel={r.channel!r}  rows={r.rows}  spend={r.spend:.0f}")
