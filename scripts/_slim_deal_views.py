"""Recreate the 3 slimmed views in BQ:
- paid_channel_campaign_daily
- v_adset_performance
- v_ad_performance

These are currently materialised as TABLE in some cases — drop first if so,
then CREATE OR REPLACE VIEW.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client, V_ADSET_PERFORMANCE_SQL, V_AD_PERFORMANCE_SQL
from collectors.views   import PAID_CHANNEL_CAMPAIGN_DAILY_SQL

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

VIEWS = [
    ("paid_channel_campaign_daily", PAID_CHANNEL_CAMPAIGN_DAILY_SQL),
    ("v_adset_performance",         V_ADSET_PERFORMANCE_SQL),
    ("v_ad_performance",            V_AD_PERFORMANCE_SQL),
]

for name, sql in VIEWS:
    table_id = f"{proj}.{ds}.{name}"
    # Drop if currently materialised as TABLE
    try:
        t = client.get_table(table_id)
        if t.table_type == "TABLE":
            client.delete_table(table_id)
            print(f"[INFO] Dropped materialised TABLE {name}")
    except Exception:
        pass  # doesn't exist, fine
    try:
        client.query(sql).result()
        print(f"[OK]   {name} — recreated as VIEW")
        # Print the new schema
        t = client.get_table(table_id)
        cols = ",".join(f.name for f in t.schema)
        print(f"       cols: {cols}")
    except Exception as e:
        print(f"[ERR]  {name}: {e}")
