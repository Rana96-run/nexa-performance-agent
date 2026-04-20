"""
Snapchat Ads -> BigQuery collector.
Pulls per-day per-campaign stats from all Snap ad accounts -> campaigns_daily.

Uses OAuth refresh token flow. Refreshes access token each run so we never
trip the 30-min access-token expiry on scheduled runs.
"""
import os
from datetime import date, timedelta, datetime, timezone
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows

load_dotenv()

BASE = "https://adsapi.snapchat.com/v1"
TOKEN_URL = "https://accounts.snapchat.com/login/oauth2/access_token"


def _refresh_access_token():
    r = requests.post(TOKEN_URL, data={
        "refresh_token": os.getenv("SNAPCHAT_REFRESH_TOKEN"),
        "client_id": os.getenv("SNAPCHAT_CLIENT_ID"),
        "client_secret": os.getenv("SNAPCHAT_CLIENT_SECRET"),
        "grant_type": "refresh_token",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def _ad_accounts():
    return [a for a in [
        os.getenv("SNAPCHAT_AD_ACCOUNT_2024"),
        os.getenv("SNAPCHAT_AD_ACCOUNT_2025"),
    ] if a]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _list_campaigns(token, ad_account_id):
    r = requests.get(f"{BASE}/adaccounts/{ad_account_id}/campaigns",
                     headers=_headers(token))
    r.raise_for_status()
    out = {}
    for c in r.json().get("campaigns", []):
        cp = c.get("campaign", {})
        out[cp["id"]] = cp
    return out


def _campaign_stats(token, campaign_id, start, end):
    """Daily breakdown stats for a single campaign."""
    params = {
        "granularity": "DAY",
        "start_time": f"{start}T00:00:00Z",
        "end_time": f"{end}T00:00:00Z",
        "fields": "impressions,swipes,spend,conversion_purchases,conversion_sign_ups,conversion_lead",
    }
    r = requests.get(f"{BASE}/campaigns/{campaign_id}/stats",
                     headers=_headers(token), params=params)
    if r.status_code >= 400:
        print(f"[snap]   stats error {r.status_code} for campaign {campaign_id}: {r.text[:200]}")
        return []
    data = r.json()
    series = data.get("timeseries_stats", [])
    if not series:
        return []
    return series[0].get("timeseries_stat", {}).get("timeseries", [])


def collect_and_write(days: int = None, incremental: bool = False):
    """
    incremental=True -> last 2 days (12h scheduled runs)
    days=N            -> last N days
    default           -> YTD
    """
    token = _refresh_access_token()

    end = date.today()  # Snap stats available same-day
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _ad_accounts()
    print(f"[snap] Window {start} -> {end} across {len(accounts)} account(s)")

    for acct in accounts:
        campaigns = _list_campaigns(token, acct)
        acct_count = 0
        for cid, c in campaigns.items():
            series = _campaign_stats(token, cid, start, end)
            for pt in series:
                stats = pt.get("stats", {})
                spend_micro = float(stats.get("spend", 0) or 0)
                spend = spend_micro / 1_000_000  # Snap spend is in micro-currency
                leads = int(stats.get("conversion_lead", 0) or 0)
                impressions = int(stats.get("impressions", 0) or 0)
                clicks = int(stats.get("swipes", 0) or 0)
                ctr = (clicks / impressions * 100) if impressions else 0.0
                d = (pt.get("start_time") or "")[:10]
                if not d:
                    continue
                rows.append({
                    "date": d,
                    "channel": "snapchat",
                    "account_id": acct,
                    "campaign_id": cid,
                    "campaign_name": c.get("name"),
                    "status": c.get("status"),
                    "objective": c.get("objective"),
                    "spend": round(spend, 2),
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": round(ctr, 4),
                    "leads": leads,
                    "conversions": float(leads),
                    "cpl": round(spend / leads, 2) if leads > 0 else None,
                    "updated_at": now,
                })
                acct_count += 1
        print(f"[snap]   account {acct}: {acct_count} rows across {len(campaigns)} campaigns")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"Snapchat backfill complete: {n} rows")
