"""
LinkedIn -> BigQuery.
Pulls:
  - Organization (Page) daily share statistics + follower snapshot -> organic_page_daily
  - Ad Account campaign stats (if LI ads is used) -> campaigns_daily

Needs in .env:
  LI_ACCESS_TOKEN      OAuth 2.0 token with r_organization_social, rw_organization_admin,
                       r_ads, r_ads_reporting
  LI_ORGANIZATION_URN  e.g. urn:li:organization:12345678
  LI_AD_ACCOUNT_URN    (optional) urn:li:sponsoredAccount:506000000
"""
import os
from datetime import date, datetime, timedelta, timezone
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows

load_dotenv()
BASE = "https://api.linkedin.com/rest"
TOKEN = os.getenv("LI_ACCESS_TOKEN")
ORG_URN = os.getenv("LI_ORGANIZATION_URN")
AD_ACCT_URN = os.getenv("LI_AD_ACCOUNT_URN")


def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "LinkedIn-Version": "202410",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _ms(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _fetch_page_share_stats(start, end):
    """Daily share statistics (impressions, clicks, engagements, shares)."""
    params = {
        "q": "organizationalEntity",
        "organizationalEntity": ORG_URN,
        "timeIntervals.timeGranularityType": "DAY",
        "timeIntervals.timeRange.start": _ms(start),
        "timeIntervals.timeRange.end": _ms(end + timedelta(days=1)),
    }
    r = requests.get(f"{BASE}/organizationalEntityShareStatistics",
                     headers=_headers(), params=params)
    if r.status_code >= 400:
        print(f"[li] page-stats {r.status_code}: {r.text[:300]}")
        return []
    return r.json().get("elements", [])


def _fetch_follower_count():
    r = requests.get(f"{BASE}/networkSizes/{ORG_URN}",
                     headers=_headers(),
                     params={"edgeType": "CompanyFollowedByMember"})
    if r.status_code >= 400:
        return 0
    return int(r.json().get("firstDegreeSize", 0))


def _fetch_ads_daily(start, end):
    if not AD_ACCT_URN:
        return []
    params = {
        "q": "analytics",
        "pivot": "CAMPAIGN",
        "timeGranularity": "DAILY",
        "accounts[0]": AD_ACCT_URN,
        "dateRange.start.day": start.day,
        "dateRange.start.month": start.month,
        "dateRange.start.year": start.year,
        "dateRange.end.day": end.day,
        "dateRange.end.month": end.month,
        "dateRange.end.year": end.year,
        "fields": "dateRange,impressions,clicks,costInLocalCurrency,externalWebsiteConversions,pivotValues",
    }
    r = requests.get(f"{BASE}/adAnalytics", headers=_headers(), params=params)
    if r.status_code >= 400:
        print(f"[li] ads {r.status_code}: {r.text[:300]}")
        return []
    return r.json().get("elements", [])


def collect_and_write(days: int = None, incremental: bool = False):
    if not TOKEN or not ORG_URN:
        print("[li] missing LI_ACCESS_TOKEN or LI_ORGANIZATION_URN — skipping")
        return 0

    end = date.today()
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)
    print(f"[li] Window {start} -> {end}")

    # Organic page
    elements = _fetch_page_share_stats(start, end)
    followers = _fetch_follower_count()
    now = datetime.now(timezone.utc).isoformat()
    organic_rows = []
    for e in elements:
        ts = e.get("timeRange", {}).get("start")
        if not ts:
            continue
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
        s = e.get("totalShareStatistics", {})
        organic_rows.append({
            "date": d,
            "channel": "linkedin",
            "li_impressions":  int(s.get("impressionCount", 0) or 0),
            "li_clicks":       int(s.get("clickCount", 0) or 0),
            "li_engagement":   int(s.get("engagement", 0) or 0) if isinstance(s.get("engagement"), (int, float)) else (
                               int(s.get("likeCount", 0) or 0) + int(s.get("commentCount", 0) or 0) + int(s.get("shareCount", 0) or 0)),
            "li_followers":    followers,
            "updated_at": now,
        })

    organic_n = 0
    if organic_rows:
        organic_n = upsert_rows("organic_page_daily", organic_rows,
                                 key_fields=["date", "channel"])

    # Paid ads (if configured)
    ads_rows = []
    for el in _fetch_ads_daily(start, end):
        dr = el.get("dateRange", {}).get("start", {})
        d = f"{dr.get('year')}-{dr.get('month', 1):02d}-{dr.get('day', 1):02d}"
        pivots = el.get("pivotValues", [])
        campaign_urn = pivots[0] if pivots else "unknown"
        campaign_id = campaign_urn.split(":")[-1] if ":" in campaign_urn else campaign_urn
        spend = float(el.get("costInLocalCurrency", 0) or 0)
        clicks = int(el.get("clicks", 0) or 0)
        impr = int(el.get("impressions", 0) or 0)
        leads = int(el.get("externalWebsiteConversions", 0) or 0)
        ads_rows.append({
            "date": d,
            "channel": "linkedin",
            "account_id": AD_ACCT_URN,
            "campaign_id": str(campaign_id),
            "campaign_name": None,
            "status": None,
            "objective": None,
            "spend": round(spend, 2),
            "impressions": impr,
            "clicks": clicks,
            "ctr": round((clicks / impr * 100) if impr else 0, 4),
            "leads": leads,
            "conversions": float(leads),
            "cpl": round(spend / leads, 2) if leads > 0 else None,
            "updated_at": now,
        })

    ads_n = 0
    if ads_rows:
        ads_n = upsert_rows("campaigns_daily", ads_rows,
                             key_fields=["date", "channel", "campaign_id"])

    print(f"[li] organic={organic_n} ads={ads_n}")
    return organic_n + ads_n


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"LinkedIn backfill complete: {n} rows")
