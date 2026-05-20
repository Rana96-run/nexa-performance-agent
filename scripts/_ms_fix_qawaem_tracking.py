"""Fix Qawaem campaigns on both Bing accounts to match the existing
campaign-level tracking pattern. Was using FinalUrlSuffix; should be
TrackingUrlTemplate matching other Bing campaigns."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.service_client import ServiceClient
from dotenv import load_dotenv
load_dotenv()


def make_auth(acc_id, cust_id):
    g = OAuthWebAuthCodeGrant(
        client_id=os.getenv("MS_CLIENT_ID"),
        client_secret=os.getenv("MS_CLIENT_SECRET"),
        redirection_uri="http://localhost:8080/microsoft/callback",
    )
    g.request_oauth_tokens_by_refresh_token(os.getenv("MS_REFRESH_TOKEN"))
    return AuthorizationData(
        account_id=int(acc_id), customer_id=int(cust_id),
        developer_token=os.getenv("MS_DEVELOPER_TOKEN"),
        authentication=g,
    )


# Canonical Bing tracking template (matches existing Bing campaigns)
TRACKING_TEMPLATE = (
    "{lpurl}?utm_source=Bing&utm_medium=ppc"
    "&utm_audience={_adgroup}&utm_content={_adname}"
    "&utm_term={keyword}&utm_campaign={_campaign}"
    "&hsa_acc=1513020554&hsa_cam={campaignid}&hsa_grp={adgroupid}&hsa_ad={creative}"
)

# Both Qawaem campaigns
TARGETS = [
    {"account_id": os.getenv("MS_ACCOUNT_ID"),   "customer_id": os.getenv("MS_CUSTOMER_ID"),
     "campaign_id": 487816800, "label": "Acc 1"},
    {"account_id": os.getenv("MS_ACCOUNT_ID_2"), "customer_id": os.getenv("MS_CUSTOMER_ID_2"),
     "campaign_id": 524237046, "label": "Acc 2"},
]

for t in TARGETS:
    print(f"\n=== {t['label']} (campaign {t['campaign_id']}) ===")
    auth = make_auth(t["account_id"], t["customer_id"])
    svc = ServiceClient("CampaignManagementService", "v13", auth, "production")

    # Fetch existing campaign
    resp = svc.GetCampaignsByIds(
        AccountId=int(t["account_id"]),
        CampaignIds={"long": [t["campaign_id"]]},
        CampaignType="Search",
    )
    if not resp.Campaigns.Campaign:
        print(f"  ❌ campaign not found")
        continue

    camp = resp.Campaigns.Campaign[0]
    # Update tracking template + clear FinalUrlSuffix
    camp.TrackingUrlTemplate = TRACKING_TEMPLATE
    camp.FinalUrlSuffix = ""

    # Build custom params at campaign level: _adgroup, _adname, _campaign
    # NOTE: For TikTok-style template these are referenced via {_adgroup} etc.
    # The custom param keys must be alphanumeric (no underscore prefix — the
    # underscore in {_xxx} is the syntax marker for "this is a custom param").
    custom_params = svc.factory.create("CustomParameters")
    params_arr = svc.factory.create("ArrayOfCustomParameter")
    for key, value in [
        ("campaign", camp.Name),
        ("adname",   "QawaemRSA_v1"),
        ("adgroup",  "FinancialSt_AR"),
    ]:
        p = svc.factory.create("CustomParameter")
        p.Key = key
        p.Value = value
        params_arr.CustomParameter.append(p)
    custom_params.Parameters = params_arr
    camp.UrlCustomParameters = custom_params

    try:
        r = svc.UpdateCampaigns(
            AccountId=int(t["account_id"]),
            Campaigns={"Campaign": [camp]},
        )
        print(f"  ✅ updated tracking template + custom params")
        if hasattr(r, "PartialErrors") and r.PartialErrors and hasattr(r.PartialErrors, "BatchError"):
            for e in r.PartialErrors.BatchError:
                print(f"    ⚠ {e.ErrorCode}: {e.Message[:200]}")
    except Exception as e:
        print(f"  ❌ {str(e)[:300]}")
