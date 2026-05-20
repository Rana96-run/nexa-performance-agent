"""Check MS Ads account-level UTM tracking on both accounts."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.service_client import ServiceClient
from dotenv import load_dotenv
load_dotenv()


def get_auth(account_id, customer_id):
    grant = OAuthWebAuthCodeGrant(
        client_id=os.getenv("MS_CLIENT_ID"),
        client_secret=os.getenv("MS_CLIENT_SECRET"),
        redirection_uri="http://localhost:8080/microsoft/callback",
    )
    grant.request_oauth_tokens_by_refresh_token(os.getenv("MS_REFRESH_TOKEN"))
    return AuthorizationData(
        account_id=int(account_id), customer_id=int(customer_id),
        developer_token=os.getenv("MS_DEVELOPER_TOKEN"),
        authentication=grant,
    )


for acct_id, cust_id, label in [
    (os.getenv("MS_ACCOUNT_ID"),   os.getenv("MS_CUSTOMER_ID"),   "Acc 1 (188176729)"),
    (os.getenv("MS_ACCOUNT_ID_2"), os.getenv("MS_CUSTOMER_ID_2"), "Acc 2 (187231519)"),
]:
    print(f"\n=== {label} ===")
    auth = get_auth(acct_id, cust_id)
    svc = ServiceClient("CustomerManagementService", "v13", auth, "production")
    acc = svc.GetAccount(AccountId=int(acct_id))
    print(f"  name      : {acc.Name}")
    print(f"  currency  : {acc.CurrencyCode}")
    # account-level tracking fields
    suffix = getattr(acc, "FinalUrlSuffix", "") or ""
    tpl    = getattr(acc, "TrackingUrlTemplate", "") or ""
    print(f"  TrackingUrlTemplate (len={len(tpl)}): {tpl[:300]}")
    print(f"  FinalUrlSuffix (len={len(suffix)}): {suffix[:300]}")
