"""Query Google Ads click_view for a specific unresolved gclid across 90 days
to find its actual click date. Helps decide whether to widen the backfill."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from datetime import date, timedelta
from collectors.gclid_clickview import _ads_client
from config import GOOGLE_ADS_CONFIG
from google.ads.googleads.errors import GoogleAdsException

# Take one of the unresolved gclids from earlier
# These are from contacts that have NOT been recovered
import requests
H = {"Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}"}
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=72)).timestamp() * 1000))
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_analytics_source", "operator": "EQ", "value": "DIRECT_TRAFFIC"},
        {"propertyName": "hs_google_click_id", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": ["hs_google_click_id"],
    "limit": 3,
}
r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/search",
                  headers={**H, "Content-Type": "application/json"}, json=body, timeout=30)
gclids = [c["properties"]["hs_google_click_id"] for c in r.json().get("results", [])]
print(f"Testing 3 unresolved gclids in 90-day window\n")

ads = _ads_client()
svc = ads.get_service("GoogleAdsService")
end = date.today() - timedelta(days=1)
start = end - timedelta(days=89)

# Search across both customer accounts
for cust_id in ["5753494964", "1513020554"]:
    print(f"--- customer {cust_id} ---")
    for g in gclids[:3]:
        # Need single-day filter — but we'd have to loop 90 days. Instead,
        # use a weekly batch (still violates click_view rule, hmm).
        # Workaround: loop day by day for ~30 days backwards from today,
        # break when found.
        found = False
        for offset in range(0, 90):
            d = end - timedelta(days=offset)
            q = f"""
                SELECT click_view.gclid, segments.date, campaign.id, campaign.name
                FROM click_view
                WHERE segments.date = '{d.isoformat()}'
                  AND click_view.gclid = '{g}'
            """
            try:
                response = svc.search_stream(customer_id=cust_id, query=q)
                for batch in response:
                    for row in batch.results:
                        if row.click_view.gclid == g:
                            print(f"  gclid {g[:20]}... FOUND in cust={cust_id}  date={row.segments.date}  campaign='{row.campaign.name}'")
                            found = True
                            break
                    if found: break
                if found: break
            except GoogleAdsException as e:
                # Some sub-accounts may reject the query for older dates
                pass
        if not found:
            print(f"  gclid {g[:20]}... NOT FOUND in cust={cust_id} (0-90 days)")
