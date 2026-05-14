"""Check if gclid_attribution table exists and has data."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]
try:
    t = c.get_table(f"{proj}.{ds}.gclid_attribution")
    print(f"Table exists ({t.table_type})")
    cnt_q = f"SELECT COUNT(*) AS n, COUNT(DISTINCT gclid) AS uniq_gclids, MIN(date) AS first_d, MAX(date) AS last_d FROM `{proj}.{ds}.gclid_attribution`"
    # `date` is a BigQuery reserved keyword; backtick if needed
    for r in c.query(cnt_q).result():
        print(f"  rows={r.n}  unique_gclids={r.uniq_gclids}  first={r.first_d}  last={r.last_d}")
except Exception as e:
    print(f"NOT READY YET: {e}")
