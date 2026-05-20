"""Verify Qawaem campaign exists on BOTH Bing accounts."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.service_client import ServiceClient
from dotenv import load_dotenv
load_dotenv()


def auth(acc, cust):
    g = OAuthWebAuthCodeGrant(
        client_id=os.getenv("MS_CLIENT_ID"),
        client_secret=os.getenv("MS_CLIENT_SECRET"),
        redirection_uri="http://localhost:8080/microsoft/callback",
    )
    g.request_oauth_tokens_by_refresh_token(os.getenv("MS_REFRESH_TOKEN"))
    return AuthorizationData(
        account_id=int(acc), customer_id=int(cust),
        developer_token=os.getenv("MS_DEVELOPER_TOKEN"),
        authentication=g,
    )


for acc_id, cust_id, label in [
    (os.getenv("MS_ACCOUNT_ID"),   os.getenv("MS_CUSTOMER_ID"),   "Acc 1 (188176729)"),
    (os.getenv("MS_ACCOUNT_ID_2"), os.getenv("MS_CUSTOMER_ID_2"), "Acc 2 (187231519)"),
]:
    print(f"\n=== {label} ===")
    svc = ServiceClient("CampaignManagementService", "v13", auth(acc_id, cust_id), "production")
    resp = svc.GetCampaignsByAccountId(AccountId=int(acc_id), CampaignType="Search")
    found = False
    for camp in resp.Campaign:
        n = str(camp.Name)
        if "Financial" in n or "Qawaem" in n:
            print(f"  ✅ id={camp.Id}  name={camp.Name}  status={camp.Status}  budget=${camp.DailyBudget}/d")
            found = True
    if not found:
        print(f"  ❌ NO Qawaem campaign found on this account")
