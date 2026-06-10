import os, requests

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
headers = {"Authorization": f"Bearer {TOKEN}"}

# Search for leads where lead_google_ad_click_id is not empty
payload = {
    "filterGroups": [{
        "filters": [{
            "propertyName": "lead_google_ad_click_id",
            "operator": "HAS_PROPERTY"
        }]
    }],
    "properties": ["lead_google_ad_click_id", "lead_utm_campaign", "lead_utm_source", "hs_createdate"],
    "limit": 10,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}]
}

r = requests.post(
    "https://api.hubapi.com/crm/v3/objects/leads/search",
    json=payload, headers=headers, timeout=30
)
data = r.json()
results = data.get("results", [])
print(f"Leads with lead_google_ad_click_id populated: {data.get('total', 0)}")
for lead in results[:10]:
    p = lead.get("properties", {})
    print(f"  gclid={str(p.get('lead_google_ad_click_id',''))[:40]}  campaign={p.get('lead_utm_campaign','')}  date={p.get('hs_createdate','')[:10]}")
