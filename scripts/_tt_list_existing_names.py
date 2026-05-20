"""List existing TikTok campaign names to match the naming convention."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.cloud import bigquery

c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")
q = """
SELECT DISTINCT campaign_name
FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
WHERE channel = 'tiktok'
  AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
  AND campaign_name IS NOT NULL
ORDER BY campaign_name
LIMIT 50
"""
for r in c.query(q).result():
    print(f"  {r.campaign_name}")
