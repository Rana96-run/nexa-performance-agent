from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adset import AdSet
from config import META_ACCESS_TOKEN, META_AD_ACCOUNTS
from datetime import date, timedelta


def init():
    FacebookAdsApi.init(access_token=META_ACCESS_TOKEN)


def get_ad_performance(days=4):
    """Pull ad-level performance across all Meta accounts."""
    init()
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    all_results = []
    for account_id in META_AD_ACCOUNTS:
        account = AdAccount(account_id)
        ads = account.get_insights(
            params={
                "level": "ad",
                "date_preset": "last_7d",
                "time_range": {
                    "since": str(start_date),
                    "until": str(end_date),
                },
                "fields": [
                    "ad_id", "ad_name", "adset_id", "adset_name",
                    "campaign_id", "campaign_name",
                    "spend", "actions", "cpm", "ctr", "frequency",
                    "impressions", "clicks",
                ],
            }
        )
        for ad in ads:
            spend = float(ad.get("spend", 0))
            actions = ad.get("actions", [])
            leads = next(
                (int(a["value"]) for a in actions if a["action_type"] == "lead"),
                0
            )
            cpl = round(spend / leads, 2) if leads > 0 else None
            all_results.append({
                "account_id": account_id,
                "ad_id": ad.get("ad_id"),
                "ad_name": ad.get("ad_name"),
                "adset_id": ad.get("adset_id"),
                "adset_name": ad.get("adset_name"),
                "campaign_name": ad.get("campaign_name"),
                "spend": spend,
                "leads": leads,
                "cpl": cpl,
                "ctr": float(ad.get("ctr", 0)),
                "frequency": float(ad.get("frequency", 0)),
                "impressions": int(ad.get("impressions", 0)),
            })
    return all_results


def pause_ad(ad_id: str):
    """Pause a Meta ad by ID. Only call after approval."""
    init()
    ad = Ad(ad_id)
    ad.api_update(fields=[], params={"status": Ad.Status.paused})
    return {"paused": ad_id}


def pause_adset(adset_id: str):
    """Pause a Meta ad set by ID. Only call after approval."""
    init()
    adset = AdSet(adset_id)
    adset.api_update(fields=[], params={"status": AdSet.Status.paused})
    return {"paused": adset_id}
