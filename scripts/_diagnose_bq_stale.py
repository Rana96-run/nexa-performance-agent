"""Diagnose BQ freshness for the 2 tables flagged by the recon alert."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

print("=" * 70)
print("Per-table freshness (last 7 days)")
print("=" * 70)
tables = [
    ("hubspot_deals_daily",        "date"),
    ("hubspot_leads_module_daily", "date"),
    ("campaigns_daily",            "date"),
]
for tbl, dfield in tables:
    sql = f"""
    SELECT {dfield} AS d,
           COUNT(*) AS row_count,
           MAX(updated_at) AS last_write
    FROM `{proj}.{ds}.{tbl}`
    WHERE {dfield} >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
    GROUP BY 1 ORDER BY 1 DESC
    """
    print(f"\n  {tbl}:")
    for r in c.query(sql).result():
        print(f"    {r.d}: rows={r.row_count:>4}  last_write={r.last_write}")
