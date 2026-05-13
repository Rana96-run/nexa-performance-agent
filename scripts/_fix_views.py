"""
Check table types for our views, drop if they're tables, then recreate as views.
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import (
    get_client, V_ADSET_PERFORMANCE_SQL, V_AD_PERFORMANCE_SQL,
    UTM_PAID_ATTRIBUTION_VIEW_SQL,
)

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

for name in ("v_adset_performance", "v_ad_performance", "utm_paid_attribution_daily"):
    table_id = f"{proj}.{ds}.{name}"
    try:
        t = client.get_table(table_id)
        print(f"  {name}: table_type={t.table_type}")
    except Exception as e:
        print(f"  {name}: not found — {e}")

# Drop and recreate v_adset_performance and v_ad_performance
for name, sql in [("v_adset_performance", V_ADSET_PERFORMANCE_SQL),
                   ("v_ad_performance",    V_AD_PERFORMANCE_SQL)]:
    table_id = f"{proj}.{ds}.{name}"
    try:
        t = client.get_table(table_id)
        if t.table_type == "TABLE":
            print(f"\nDropping {name} (was TABLE)...")
            client.delete_table(table_id)
            print(f"  Dropped. Recreating as VIEW...")
        else:
            print(f"\n{name} is already a {t.table_type} — recreating in-place...")
    except Exception:
        print(f"\n{name} doesn't exist — creating fresh...")
    try:
        client.query(sql).result()
        print(f"  [OK] {name} created as VIEW.")
    except Exception as e:
        print(f"  [ERR] {e}")
