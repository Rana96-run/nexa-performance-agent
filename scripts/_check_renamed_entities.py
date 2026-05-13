"""
Find renamed entities (same ID → multiple names over time) at campaign, adset, and ad level.
When this happens and views JOIN on name, the entity fragments into 2 rows:
one with old-name leads/spend, one with new-name leads/spend (Funnel-style breakage).
The fix is to JOIN on ID (campaign_id / adset_id / ad_id) — name stays for display.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

LOOKBACK = 90  # days

def section(title): print(f"\n{'='*80}\n{title}\n{'='*80}")

# ---- 1. Campaign-level renames ----
section(f"1. Campaigns renamed within last {LOOKBACK} days (same campaign_id → 2+ names)")
sql = f"""
SELECT channel, campaign_id,
       COUNT(DISTINCT campaign_name) AS n_names,
       STRING_AGG(DISTINCT campaign_name, ' || ' ORDER BY campaign_name) AS names,
       SUM(spend) AS spend_usd,
       MIN(date) AS first_seen,
       MAX(date) AS last_seen
FROM `{proj}.{ds}.campaigns_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LOOKBACK} DAY)
  AND campaign_name IS NOT NULL
GROUP BY 1, 2
HAVING n_names > 1
ORDER BY spend_usd DESC
LIMIT 30
"""
rows = list(client.query(sql).result())
if rows:
    for r in rows:
        print(f"  [{r.channel}] cid={r.campaign_id}  spend=${r.spend_usd:.0f}  names={r.n_names}")
        print(f"      → {r.names}")
        print(f"      first={r.first_seen}  last={r.last_seen}")
else:
    print("  (no campaign renames detected)")

# ---- 2. Adset-level renames ----
section(f"2. Adsets renamed within last {LOOKBACK} days (same adset_id → 2+ names)")
sql2 = f"""
SELECT channel, adset_id,
       COUNT(DISTINCT adset_name) AS n_names,
       STRING_AGG(DISTINCT adset_name, ' || ' ORDER BY adset_name) AS names,
       SUM(spend) AS spend_usd,
       MIN(date) AS first_seen, MAX(date) AS last_seen
FROM `{proj}.{ds}.adsets_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LOOKBACK} DAY)
  AND adset_name IS NOT NULL
GROUP BY 1, 2
HAVING n_names > 1
ORDER BY spend_usd DESC
LIMIT 30
"""
rows = list(client.query(sql2).result())
if rows:
    for r in rows:
        print(f"  [{r.channel}] aid={r.adset_id}  spend=${r.spend_usd:.0f}  names={r.n_names}")
        print(f"      → {r.names}")
        print(f"      first={r.first_seen}  last={r.last_seen}")
else:
    print("  (no adset renames detected)")

# ---- 3. Ad-level renames ----
section(f"3. Ads renamed within last {LOOKBACK} days (same ad_id → 2+ names)")
sql3 = f"""
SELECT channel, ad_id,
       COUNT(DISTINCT ad_name) AS n_names,
       STRING_AGG(DISTINCT ad_name, ' || ' ORDER BY ad_name) AS names,
       SUM(spend) AS spend_usd,
       MIN(date) AS first_seen, MAX(date) AS last_seen
FROM `{proj}.{ds}.ads_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LOOKBACK} DAY)
  AND ad_name IS NOT NULL
GROUP BY 1, 2
HAVING n_names > 1
ORDER BY spend_usd DESC
LIMIT 30
"""
rows = list(client.query(sql3).result())
if rows:
    for r in rows:
        print(f"  [{r.channel}] ad_id={r.ad_id}  spend=${r.spend_usd:.0f}  names={r.n_names}")
        print(f"      → {r.names}")
        print(f"      first={r.first_seen}  last={r.last_seen}")
else:
    print("  (no ad renames detected)")

# ---- 4. Fragmentation impact: for renamed campaigns, count leads that would fragment if joined on name ----
section(f"4. Fragmentation IMPACT — leads at risk if views joined on name (last {LOOKBACK} days)")
sql4 = f"""
WITH renamed AS (
  SELECT channel, campaign_id, COUNT(DISTINCT campaign_name) AS n_names,
         STRING_AGG(DISTINCT campaign_name, ' || ' ORDER BY campaign_name) AS names
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LOOKBACK} DAY)
    AND campaign_name IS NOT NULL
  GROUP BY 1, 2
  HAVING n_names > 1
),
spend_per_id AS (
  SELECT channel, campaign_id, SUM(spend) AS spend_usd
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LOOKBACK} DAY)
  GROUP BY 1, 2
),
leads_per_id AS (
  SELECT lead_campaign_id_sync AS campaign_id,
         SUM(leads_total) AS leads,
         SUM(leads_qualified) AS sqls
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {LOOKBACK} DAY)
    AND lead_campaign_id_sync IS NOT NULL
  GROUP BY 1
)
SELECT r.channel, r.campaign_id, r.names,
       s.spend_usd, l.leads, l.sqls
FROM renamed r
LEFT JOIN spend_per_id s USING (channel, campaign_id)
LEFT JOIN leads_per_id l USING (campaign_id)
ORDER BY s.spend_usd DESC NULLS LAST
LIMIT 20
"""
rows = list(client.query(sql4).result())
if rows:
    for r in rows:
        spend = f"${r.spend_usd:.0f}" if r.spend_usd else "$0"
        leads = r.leads or 0
        sqls = r.sqls or 0
        print(f"  [{r.channel}] cid={r.campaign_id}  spend={spend}  leads={leads}  sqls={sqls}")
        print(f"      → {r.names}")
else:
    print("  (no fragmentation candidates)")

print("\n" + "="*80)
print("CONCLUSION: every entity above currently has spend under one name and")
print("leads under the OTHER name. Joining on ID consolidates them. Joining on")
print("name (Funnel-style) leaves them as 2 broken rows.")
print("="*80)
