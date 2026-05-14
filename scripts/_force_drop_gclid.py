import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client
c = get_client(); proj=os.environ['BQ_PROJECT_ID']; ds=os.environ['BQ_DATASET']
table_id = f'{proj}.{ds}.gclid_attribution'
c.delete_table(table_id, not_found_ok=True)
print('Deleted (or did not exist)')
try:
    t = c.get_table(table_id)
    print(f'Still exists: cols={[f.name for f in t.schema]}')
except Exception:
    print('Confirmed gone')
