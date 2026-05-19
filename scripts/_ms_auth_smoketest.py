"""Smoke test — verify MS Ads OAuth works + we can read account info."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.microsoft_ads import get_service, ACCOUNT_ID

svc = get_service("CustomerManagementService")
print(f"  service URL: {svc.service_url}")

# Try a simple read — get current account info
try:
    response = svc.GetAccount(AccountId=ACCOUNT_ID)
    print(f"  ✅ auth works")
    print(f"     account id  : {response.Id}")
    print(f"     account name: {response.Name}")
    print(f"     account num : {response.Number}")
    print(f"     currency    : {response.CurrencyCode}")
    print(f"     time zone   : {response.TimeZone}")
    print(f"     status      : {response.AccountLifeCycleStatus}")
except Exception as e:
    print(f"  ❌ {type(e).__name__}: {str(e)[:500]}")
