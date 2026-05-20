import os, requests, json
from dotenv import load_dotenv
load_dotenv(override=True)

TOKEN       = os.getenv("LI_ACCESS_TOKEN")
ACCOUNT_URN = os.getenv("LI_AD_ACCOUNT_URN", "")
ACCOUNT_ID  = ACCOUNT_URN.split(":")[-1]

headers_v2 = {
    "Authorization": "Bearer " + TOKEN,
    "X-Restli-Protocol-Version": "2.0.0",
}

# v2 API - fetch creatives by campaign
for cid in ["187839134", "217541784"]:
    r = requests.get(
        "https://api.linkedin.com/v2/adCreativesV2",
        headers=headers_v2,
        params={
            "q": "search",
            "search.campaign.values[0]": "urn:li:sponsoredCampaign:" + cid,
            "count": 3,
        },
        timeout=15
    )
    print(f"Campaign {cid}: {r.status_code}")
    try:
        data = r.json()
        for el in data.get("elements", []):
            ref = el.get("reference", "")
            print(f"  Creative ID: {el.get('id')}  | Status: {el.get('status')} | Reference: {ref}")
    except Exception:
        print("  Raw:", r.text[:300])
    print("---")
