"""Inspect how existing Bing campaigns do UTM tracking — at what level."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.service_client import ServiceClient
from dotenv import load_dotenv
load_dotenv()


def make_auth(acc_id, cust_id):
    grant = OAuthWebAuthCodeGrant(
        client_id=os.getenv("MS_CLIENT_ID"),
        client_secret=os.getenv("MS_CLIENT_SECRET"),
        redirection_uri="http://localhost:8080/microsoft/callback",
    )
    grant.request_oauth_tokens_by_refresh_token(os.getenv("MS_REFRESH_TOKEN"))
    return AuthorizationData(
        account_id=int(acc_id), customer_id=int(cust_id),
        developer_token=os.getenv("MS_DEVELOPER_TOKEN"),
        authentication=grant,
    )


for acc_id, cust_id, label in [
    (os.getenv("MS_ACCOUNT_ID"),   os.getenv("MS_CUSTOMER_ID"),   "Acc 1"),
    (os.getenv("MS_ACCOUNT_ID_2"), os.getenv("MS_CUSTOMER_ID_2"), "Acc 2"),
]:
    print(f"\n=== {label} ({acc_id}) ===")
    auth = make_auth(acc_id, cust_id)
    svc  = ServiceClient("CampaignManagementService", "v13", auth, "production")
    resp = svc.GetCampaignsByAccountId(AccountId=int(acc_id), CampaignType="Search")
    for camp in resp.Campaign[:4]:  # first 4 campaigns
        print(f"\n  Campaign: {camp.Name} (id={camp.Id})")
        tpl = getattr(camp, "TrackingUrlTemplate", None) or ""
        suf = getattr(camp, "FinalUrlSuffix", None) or ""
        print(f"    TrackingUrlTemplate: {tpl[:200] if tpl else '(empty)'}")
        print(f"    FinalUrlSuffix     : {suf[:200] if suf else '(empty)'}")
        # Check one ad to see if tracking lives at ad level
        try:
            ag_resp = svc.GetAdGroupsByCampaignId(CampaignId=camp.Id)
            if hasattr(ag_resp, "AdGroup") and ag_resp.AdGroup:
                first_ag = ag_resp.AdGroup[0]
                ads_resp = svc.GetAdsByAdGroupId(
                    AdGroupId=first_ag.Id,
                    AdTypes={"AdType": ["ResponsiveSearch", "ExpandedText"]},
                )
                if hasattr(ads_resp, "Ad") and ads_resp.Ad:
                    ad = ads_resp.Ad[0]
                    final_urls = getattr(ad, "FinalUrls", None)
                    if final_urls and hasattr(final_urls, "string"):
                        print(f"    Sample ad FinalUrl: {final_urls.string[0][:200] if final_urls.string else '(none)'}")
                    ad_suffix = getattr(ad, "FinalUrlSuffix", None) or ""
                    if ad_suffix:
                        print(f"    Sample ad FinalUrlSuffix: {ad_suffix[:200]}")
        except Exception as e:
            print(f"    (couldn't inspect ad: {str(e)[:100]})")
