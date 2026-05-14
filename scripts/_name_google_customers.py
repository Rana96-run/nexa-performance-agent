"""Get descriptive names of each customer under the MCC so we can pick
'auto cloud' and 'qoyod new'."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.gclid_clickview import _ads_client
from config import GOOGLE_ADS_CONFIG

ads = _ads_client()
service = ads.get_service("GoogleAdsService")
mcc_id = GOOGLE_ADS_CONFIG["login_customer_id"]

# Use the MCC to query its sub-accounts via customer_client
query = """
    SELECT
        customer_client.id,
        customer_client.descriptive_name,
        customer_client.manager,
        customer_client.test_account,
        customer_client.status
    FROM customer_client
    WHERE customer_client.manager = false
"""
try:
    response = service.search_stream(customer_id=mcc_id, query=query)
    print(f"Sub-accounts under MCC {mcc_id}:\n")
    for batch in response:
        for r in batch.results:
            cc = r.customer_client
            print(f"  cid={cc.id:>12d}  status={cc.status.name:10s}  test={cc.test_account}  name='{cc.descriptive_name}'")
except Exception as e:
    print(f"ERR: {e}")
