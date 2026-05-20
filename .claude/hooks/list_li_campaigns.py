import os, requests
from dotenv import load_dotenv
load_dotenv(override=True)

TOKEN      = os.getenv("LI_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("LI_AD_ACCOUNT_URN", "").split(":")[-1]
BASE       = "https://api.linkedin.com/rest"

headers = {
    "Authorization": "Bearer " + TOKEN,
    "LinkedIn-Version": "202502",
    "X-Restli-Protocol-Version": "2.0.0",
}

r = requests.get(
    BASE + "/adAccounts/" + ACCOUNT_ID + "/adCampaigns",
    headers=headers,
    params={"q": "search", "count": 15},
    timeout=15
)
print("Status:", r.status_code)
data = r.json()
for el in data.get("elements", []):
    print("ID:", el.get("id"), "| Name:", el.get("name"), "| Status:", el.get("status"))
