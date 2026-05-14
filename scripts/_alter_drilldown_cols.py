import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client
c = get_client(); proj=os.environ['BQ_PROJECT_ID']; ds=os.environ['BQ_DATASET']
for tbl in ('hubspot_leads_module_daily', 'hubspot_leads_individual'):
    for col in ('lead_original_traffic_source_drilldown_1',
                'lead_latest_traffic_source_drilldown_1',
                'lead_original_traffic_source_drilldown_2',
                'lead_latest_traffic_source_drilldown_2'):
        try:
            c.query(f'ALTER TABLE `{proj}.{ds}.{tbl}` ADD COLUMN IF NOT EXISTS `{col}` STRING').result()
            print(f'  ✓ {tbl}.{col}')
        except Exception as e:
            print(f'  ✗ {tbl}.{col} — ERR {str(e)[:80]}')
