"""Dump our entire active Google Ads keyword inventory so we can cross-ref
against competitors to find what they target and we don't."""
from collectors.bq_writer import get_client, DATASET, PROJECT_ID
c = get_client()
DS = f"`{PROJECT_ID}.{DATASET}`"

sql = f"""
WITH base AS (
  SELECT keyword_text,
         MAX(status)        AS status,
         MAX(match_type)    AS match_type,
         SUM(impressions)   AS impressions,
         SUM(spend)         AS spend,
         AVG(quality_score) AS avg_qs
  FROM {DS}.keywords_daily
  WHERE channel = 'google_ads'
    AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
  GROUP BY keyword_text
)
SELECT keyword_text, status, match_type, impressions, ROUND(spend, 0) AS spend,
       ROUND(avg_qs, 1) AS qs
FROM base
WHERE keyword_text IS NOT NULL
ORDER BY impressions DESC
LIMIT 500
"""
rows = list(c.query(sql).result())
print(f"Total active keywords: {len(rows)}")
print()
# Just keyword text — for cross-ref
with open("scripts/_our_keywords.txt", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(f"{r.keyword_text}\n")
print(f"Wrote keyword list to scripts/_our_keywords.txt")
print()
print("Sample (top 30 by impressions):")
for r in rows[:30]:
    print(f"  {r.keyword_text!r}  status={r.status}  match={r.match_type}  impr={r.impressions}  qs={r.qs}")
