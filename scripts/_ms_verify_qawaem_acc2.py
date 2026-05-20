"""Verify the Qawaem campaign exists on MS Acc 2."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.service_client import ServiceClient
from dotenv import load_dotenv
load_dotenv()

grant = OAuthWebAuthCodeGrant(
    client_id=os.getenv("MS_CLIENT_ID"),
    client_secret=os.getenv("MS_CLIENT_SECRET"),
    redirection_uri="http://localhost:8080/microsoft/callback",
)
grant.request_oauth_tokens_by_refresh_token(os.getenv("MS_REFRESH_TOKEN"))
auth = AuthorizationData(
    account_id=int(os.getenv("MS_ACCOUNT_ID_2")),
    customer_id=int(os.getenv("MS_CUSTOMER_ID_2")),
    developer_token=os.getenv("MS_DEVELOPER_TOKEN"),
    authentication=grant,
)
svc = ServiceClient("CampaignManagementService", "v13", auth, "production")

resp = svc.GetCampaignsByAccountId(AccountId=int(os.getenv("MS_ACCOUNT_ID_2")), CampaignType="Search")
for c in resp.Campaign:
    n = str(c.Name)
    if "FinancialStatemnt" in n or "Qawaem" in n:
        print(f"FOUND id={c.Id}  name={c.Name}  status={c.Status}  budget=${c.DailyBudget}/d")
