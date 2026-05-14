import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client
c=get_client(); proj=os.environ['BQ_PROJECT_ID']; ds=os.environ['BQ_DATASET']
for tbl in ('hubspot_leads_individual', 'hubspot_leads_module_daily'):
    print(f"\n=== {tbl} columns matching drilldown/source ===")
    sql=f"SELECT column_name FROM `{proj}.{ds}.INFORMATION_SCHEMA.COLUMNS` WHERE table_name = '{tbl}' AND (column_name LIKE '%drilldown%' OR column_name LIKE '%source%' OR column_name LIKE '%traffic%')"
    for r in c.query(sql).result():
        print(f"  {r.column_name}")
