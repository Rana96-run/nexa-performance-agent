"""List all Google Ads customer accounts accessible under the MCC."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.gclid_clickview import _ads_client
from config import GOOGLE_ADS_CONFIG

ads = _ads_client()
service = ads.get_service("CustomerService")
# list_accessible_customers returns all customer resource names visible to this OAuth token
res = service.list_accessible_customers()
print(f"Accessible customers under MCC {GOOGLE_ADS_CONFIG['login_customer_id']}:\n")
for resource in res.resource_names:
    cid = resource.split("/")[-1]
    print(f"  customer_id = {cid}  (currently used: {cid == GOOGLE_ADS_CONFIG['customer_id']})")
