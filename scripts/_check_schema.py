"""Check adsets_daily and campaigns_daily schema."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

for tbl in ("adsets_daily", "campaigns_daily"):
    t = client.get_table(f"{proj}.{ds}.{tbl}")
    print(f"\n{tbl}: {[f.name for f in t.schema]}")
