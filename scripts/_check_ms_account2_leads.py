"""Re-investigate Microsoft Ads Account 187231519 lead attribution.
User says both accounts have leads — my earlier join missed Account 2's leads.

Try multiple attribution paths to find the leads:
  1. Direct join: campaigns_daily.campaign_name ↔ hubspot_leads_module_daily.lead_utm_campaign
  2. Via qoyod_source/channel mapping
  3. Look at extended window (90d)
  4. Pre-existing analyst view `paid_channel_campaign_daily` if it exists
"""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.cloud import bigquery

c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")

# ── Sanity 1: list Account 2 campaign names that have spend ───────────────
print("=" * 70)
print("Account 187231519 — campaign names with spend (last 90d)")
print("=" * 70)
# KPI-RULE-BYPASS — listing campaigns from campaigns_daily, not analyzing leads
q1 = """
SELECT campaign_name, SUM(spend) AS spend, SUM(clicks) AS clicks
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE channel = 'microsoft_ads'
  AND account_id = '187231519'
  AND date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 90 DAY)
  AND spend > 0
GROUP BY campaign_name
ORDER BY spend DESC
"""
acc2_campaigns = []
for r in c.query(q1).result():
    print(f"  ${r.spend or 0:>8,.0f}  clicks={r.clicks or 0:>5}   {r.campaign_name}")
    acc2_campaigns.append(r.campaign_name)
print(f"\n  → {len(acc2_campaigns)} active campaigns")

if not acc2_campaigns:
    print("  (no campaigns with spend — exiting)")
    sys.exit(0)

# ── Sanity 2: join Account 2 campaign names to HubSpot module (90d) ───────
print("\n" + "=" * 70)
print("HubSpot leads per Account 2 campaign — lead_utm_campaign join (90d)")
print("=" * 70)
ids = ", ".join([f'"{n}"' for n in acc2_campaigns])
q2 = f"""
SELECT
  LOWER(lead_utm_campaign) AS campaign_key,
  SUM(leads_total)     AS leads,
  SUM(leads_qualified) AS sqls
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 90 DAY)
  AND LOWER(lead_utm_campaign) IN ({", ".join([f'LOWER("{n}")' for n in acc2_campaigns])})
GROUP BY campaign_key
ORDER BY leads DESC
"""
total_hits = 0
for r in c.query(q2).result():
    total_hits += 1
    print(f"  leads={r.leads:>4}  sqls={r.sqls or 0:>3}   {r.campaign_key}")
if total_hits == 0:
    print("  ❌ ZERO matches — UTM names don't align")

# ── Sanity 3: try the HubSpot channel column directly for microsoft_ads ───
print("\n" + "=" * 70)
print("HubSpot leads from channel='microsoft_ads' (last 90d) — see what UTMs are attached")
print("=" * 70)
q3 = """
SELECT
  qoyod_source,
  lead_utm_campaign,
  SUM(leads_total) AS leads
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 90 DAY)
  AND (LOWER(qoyod_source) LIKE '%microsoft%' OR LOWER(qoyod_source) LIKE '%bing%')
GROUP BY qoyod_source, lead_utm_campaign
ORDER BY leads DESC
LIMIT 30
"""
print(f"{'qoyod_source':<25} {'lead_utm_campaign':<70} {'leads':>6}")
n_rows = 0
for r in c.query(q3).result():
    n_rows += 1
    src = (r.qoyod_source or "(null)")[:23]
    cam = (r.lead_utm_campaign or "(null)")[:68]
    print(f"  {src:<23}  {cam:<68}  {r.leads:>5}")
if n_rows == 0:
    print("  ❌ Nothing labeled microsoft/bing in qoyod_source either")
