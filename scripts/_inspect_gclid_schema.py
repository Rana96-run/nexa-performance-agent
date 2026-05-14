import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client
c = get_client(); proj=os.environ['BQ_PROJECT_ID']; ds=os.environ['BQ_DATASET']
try:
    t = c.get_table(f'{proj}.{ds}.gclid_attribution')
    print('SCHEMA:')
    for f in t.schema:
        print(f'  {f.name:25s} {f.field_type} mode={f.mode}')
except Exception as e:
    print(f'ERROR: {e}')
