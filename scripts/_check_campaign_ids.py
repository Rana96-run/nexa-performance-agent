"""Check campaign_id column in campaigns_daily for TikTok/Google/Microsoft."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

sql = f"""
SELECT channel, campaign_id, campaign_name
FROM `{proj}.{ds}.campaigns_daily`
WHERE date = '2026-05-12'
  AND channel IN ('tiktok','microsoft_ads','google_ads')
LIMIT 8
"""
for r in client.query(sql).result():
    print(f"  {r.channel:14s}  cid={str(r.campaign_id or '')[:25]:25s}  name={str(r.campaign_name or '')[:40]}")
