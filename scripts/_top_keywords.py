"""Top-performing Google Ads keywords with HIGH quality score, HIGH volume,
HIGH intent (proven SQLs), and NOT low-volume. Tiered output."""
import json
from collectors.bq_writer import get_client, DATASET, PROJECT_ID

c = get_client()
DS = f"`{PROJECT_ID}.{DATASET}`"

def run(label, sql, max_rows=999):
    print(f"\n--- {label} ---")
    n = 0
    for r in c.query(sql).result():
        d = dict(r)
        # decode arabic for readability
        if isinstance(d.get("keyword"), str):
            print(f"  {json.dumps(d, ensure_ascii=False, default=str)}")
        else:
            print(f"  {d}")
        n += 1
        if n >= max_rows:
            print(f"  ... (truncated at {max_rows})")
            break

# ── Tier 1: Elite — QS 8+, high vol, proven SQLs, low CPQL ────────────────
print("=" * 78)
print("TIER 1 — ELITE: QS 8+, impr ≥ 2000, SQLs ≥ 5, CPQL ≤ $80")
print("=" * 78)
run("elite kw", f"""
WITH base AS (
  SELECT utm_term AS keyword,
         SUM(spend) AS spend,
         SUM(impressions) AS impressions,
         SUM(clicks) AS clicks,
         SUM(leads) AS leads,
         SUM(leads_qualified) AS sqls,
         AVG(quality_score) AS avg_qs,
         SUM(revenue_won) AS rev,
         AVG(ctr) AS avg_ctr,
         COUNT(DISTINCT utm_campaign) AS in_campaigns
  FROM {DS}.v_keyword_performance
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY utm_term
)
SELECT keyword,
       ROUND(avg_qs, 1) AS qs,
       impressions, clicks,
       ROUND(avg_ctr*100, 2) AS ctr_pct,
       leads, sqls,
       ROUND(spend, 0) AS spend,
       ROUND(SAFE_DIVIDE(spend, NULLIF(leads,0)), 1) AS cpl,
       ROUND(SAFE_DIVIDE(spend, NULLIF(sqls,0)), 1) AS cpql,
       ROUND(SAFE_DIVIDE(rev, NULLIF(spend,0)), 2) AS roas,
       in_campaigns
FROM base
WHERE avg_qs >= 8
  AND impressions >= 2000
  AND sqls >= 5
  AND SAFE_DIVIDE(spend, NULLIF(sqls,0)) <= 80
ORDER BY sqls DESC
LIMIT 30
""")

# ── Tier 2: Strong — QS 7+, decent vol, SQL signal ────────────────────────
print("\n" + "=" * 78)
print("TIER 2 — STRONG: QS 7+, impr ≥ 1000, SQLs ≥ 3, CPQL ≤ $120")
print("=" * 78)
run("strong kw", f"""
WITH base AS (
  SELECT utm_term AS keyword,
         SUM(spend) AS spend,
         SUM(impressions) AS impressions,
         SUM(clicks) AS clicks,
         SUM(leads) AS leads,
         SUM(leads_qualified) AS sqls,
         AVG(quality_score) AS avg_qs,
         SUM(revenue_won) AS rev,
         AVG(ctr) AS avg_ctr,
         COUNT(DISTINCT utm_campaign) AS in_campaigns
  FROM {DS}.v_keyword_performance
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY utm_term
)
SELECT keyword,
       ROUND(avg_qs, 1) AS qs,
       impressions, clicks,
       ROUND(avg_ctr*100, 2) AS ctr_pct,
       leads, sqls,
       ROUND(spend, 0) AS spend,
       ROUND(SAFE_DIVIDE(spend, NULLIF(leads,0)), 1) AS cpl,
       ROUND(SAFE_DIVIDE(spend, NULLIF(sqls,0)), 1) AS cpql,
       ROUND(SAFE_DIVIDE(rev, NULLIF(spend,0)), 2) AS roas,
       in_campaigns
FROM base
WHERE avg_qs >= 7 AND avg_qs < 8
  AND impressions >= 1000
  AND sqls >= 3
  AND SAFE_DIVIDE(spend, NULLIF(sqls,0)) <= 120
ORDER BY sqls DESC
LIMIT 25
""")

# ── Tier 3: Underused gems — high QS + high impressions but few SQLs ──────
# Keywords where if we lift the LP/creative, SQLs should follow
print("\n" + "=" * 78)
print("TIER 3 — UNDERUSED: QS 7+, impr ≥ 2000, SQLs < 3 (LP/creative work needed)")
print("=" * 78)
run("underused kw", f"""
WITH base AS (
  SELECT utm_term AS keyword,
         SUM(spend) AS spend,
         SUM(impressions) AS impressions,
         SUM(clicks) AS clicks,
         SUM(leads) AS leads,
         SUM(leads_qualified) AS sqls,
         AVG(quality_score) AS avg_qs,
         AVG(ctr) AS avg_ctr
  FROM {DS}.v_keyword_performance
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY utm_term
)
SELECT keyword,
       ROUND(avg_qs, 1) AS qs,
       impressions, clicks,
       ROUND(avg_ctr*100, 2) AS ctr_pct,
       leads, sqls,
       ROUND(spend, 0) AS spend,
       ROUND(SAFE_DIVIDE(spend, NULLIF(leads,0)), 1) AS cpl
FROM base
WHERE avg_qs >= 7
  AND impressions >= 2000
  AND sqls < 3
ORDER BY impressions DESC
LIMIT 20
""")

# ── Tier 4: High volume opportunity — anything bidding > 5000 impr with proven any SQLs
print("\n" + "=" * 78)
print("TIER 4 — VOLUME BEASTS: impressions ≥ 5000, regardless of QS, with SQLs ≥ 1")
print("=" * 78)
run("volume kw", f"""
WITH base AS (
  SELECT utm_term AS keyword,
         SUM(spend) AS spend,
         SUM(impressions) AS impressions,
         SUM(clicks) AS clicks,
         SUM(leads) AS leads,
         SUM(leads_qualified) AS sqls,
         AVG(quality_score) AS avg_qs,
         AVG(ctr) AS avg_ctr
  FROM {DS}.v_keyword_performance
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  GROUP BY utm_term
)
SELECT keyword,
       ROUND(avg_qs, 1) AS qs,
       impressions, clicks,
       ROUND(avg_ctr*100, 2) AS ctr_pct,
       leads, sqls,
       ROUND(spend, 0) AS spend,
       ROUND(SAFE_DIVIDE(spend, NULLIF(sqls,0)), 1) AS cpql
FROM base
WHERE impressions >= 5000
  AND sqls >= 1
ORDER BY impressions DESC
LIMIT 20
""")
