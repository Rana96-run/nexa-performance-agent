"""
Snapchat Ads -> BigQuery collector.
Pulls per-day per-campaign stats from all Snap ad accounts -> campaigns_daily.

Uses OAuth refresh token flow. Refreshes access token each run so we never
trip the 30-min access-token expiry on scheduled runs.

API constraints (learned the hard way):
  - DAY granularity queries are capped at 31 days per call
    -> we chunk longer windows into 30-day pieces.
  - start_time / end_time MUST be midnight in the ad account's timezone,
    not UTC midnight. For a USD account in America/Los_Angeles, "T00:00:00Z"
    is 4–5 PM local — Snap rejects it.
    -> we fetch the account's `timezone` field and convert local midnight -> UTC.
"""
import os
from datetime import date, timedelta, datetime, timezone
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

load_dotenv(override=True)

BASE      = "https://adsapi.snapchat.com/v1"
TOKEN_URL = "https://accounts.snapchat.com/login/oauth2/access_token"


def _refresh_access_token():
    r = requests.post(TOKEN_URL, data={
        "refresh_token": os.getenv("SNAPCHAT_REFRESH_TOKEN"),
        "client_id":     os.getenv("SNAPCHAT_CLIENT_ID"),
        "client_secret": os.getenv("SNAPCHAT_CLIENT_SECRET"),
        "grant_type":    "refresh_token",
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


# DON'T add conversion_lead / total_conversions — rejected by Snap API.
SNAP_STATS_FIELDS = (
    "impressions,swipes,spend,"
    "conversion_sign_ups,conversion_purchases,conversion_add_cart,"
    "conversion_page_views,conversion_save,conversion_start_checkout,"
    "conversion_subscribe,conversion_app_installs"
)
SNAP_STATS_FIELDS_SAFE = "impressions,swipes,spend,conversion_sign_ups"


def _day_start_iso(d: date, tz_name: str) -> str:
    """
    Midnight of `d` in timezone `tz_name`, expressed as a UTC ISO-8601 string
    that Snap accepts (e.g. '2026-01-01T08:00:00Z' for an LA-tz day).
    """
    # timezone.utc is always available; ZoneInfo("UTC") fails on Windows
    # when the tzdata package is absent from the system tz database.
    if not tz_name or tz_name.upper() == "UTC":
        tz = timezone.utc
    else:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
    local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    utc   = local.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_chunks(start: date, end: date, max_days: int = 30):
    """Yield (chunk_start, chunk_end) inclusive tuples of up to max_days each."""
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def _get_account(token, ad_account_id):
    """Fetch one ad account to get currency + timezone."""
    r = requests.get(f"{BASE}/adaccounts/{ad_account_id}",
                     headers=_headers(token))
    if r.status_code >= 400:
        return {}
    elts = r.json().get("adaccounts", [])
    return elts[0].get("adaccount", {}) if elts else {}


def _list_campaigns(token, ad_account_id):
    r = requests.get(f"{BASE}/adaccounts/{ad_account_id}/campaigns",
                     headers=_headers(token))
    r.raise_for_status()
    out = {}
    for c in r.json().get("campaigns", []):
        cp = c.get("campaign", {})
        out[cp["id"]] = cp
    return out


_SNAP_TIMEOUT  = 120   # seconds per request — Snap API can be slow on Railway
_SNAP_RETRIES  = 5    # attempts before giving up on a single request
_SNAP_RETRY_WAIT = 15  # seconds between retries (fixed — avoids long exponential waits)


def _snap_get(url, headers, params) -> requests.Response:
    """GET with retry on timeout/connection error. Tries up to _SNAP_RETRIES times."""
    import time as _time
    last_exc = None
    for attempt in range(_SNAP_RETRIES):
        try:
            return requests.get(url, headers=headers, params=params,
                                timeout=_SNAP_TIMEOUT)
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt < _SNAP_RETRIES - 1:
                print(f"[snap]   network error attempt {attempt+1}/{_SNAP_RETRIES} "
                      f"({type(exc).__name__}), retry in {_SNAP_RETRY_WAIT}s...")
                _time.sleep(_SNAP_RETRY_WAIT)
    raise last_exc


def _stats_single_call(token, campaign_id, start, end, tz_name, fields):
    """One Snap stats request for a ≤30-day window. Returns list of timeseries points.
    Timeouts after all retries return [] (skip campaign, don't crash the whole run).
    """
    end_exclusive = end + timedelta(days=1)
    params = {
        "granularity": "DAY",
        "start_time":  _day_start_iso(start, tz_name),
        "end_time":    _day_start_iso(end_exclusive, tz_name),
        "fields":      fields,
    }
    try:
        r = _snap_get(f"{BASE}/campaigns/{campaign_id}/stats", _headers(token), params)
    except Exception as exc:
        print(f"[snap]   skipping campaign {campaign_id} ({start}..{end}) "
              f"after {_SNAP_RETRIES} retries: {exc}")
        return []

    # If the error looks like a field-support problem (not a time/window problem),
    # retry with minimal safe fields.
    if r.status_code >= 400 and fields != SNAP_STATS_FIELDS_SAFE:
        body = r.text.lower()
        looks_like_field_issue = (
            "field" in body or "unsupported" in body and "granularity" not in body
        )
        if looks_like_field_issue:
            params["fields"] = SNAP_STATS_FIELDS_SAFE
            try:
                r = _snap_get(f"{BASE}/campaigns/{campaign_id}/stats",
                              _headers(token), params)
            except Exception as exc:
                print(f"[snap]   skipping campaign {campaign_id} on safe-fields retry: {exc}")
                return []

    if r.status_code >= 400:
        print(f"[snap]   stats error {r.status_code} for campaign {campaign_id} "
              f"({start}..{end}): {r.text[:160]}")
        return []
    data = r.json()
    series = data.get("timeseries_stats", [])
    if not series:
        return []
    return series[0].get("timeseries_stat", {}).get("timeseries", [])


def _campaign_stats(token, campaign_id, start, end, tz_name,
                    fields=SNAP_STATS_FIELDS):
    """Full-window stats — chunks into ≤30-day pieces to stay under Snap's cap."""
    all_points = []
    for cs, ce in _date_chunks(start, end, max_days=30):
        all_points.extend(
            _stats_single_call(token, campaign_id, cs, ce, tz_name, fields)
        )
    return all_points


def collect_and_write(days: int = None, incremental: bool = False):
    """
    incremental=True -> last 2 days (12h scheduled runs)
    days=N            -> last N days
    default           -> YTD
    """
    token = _refresh_access_token()

    # Snap DAY-granularity queries reject end_time in the future.
    # Use yesterday as the ceiling so end_exclusive (end+1) = today midnight.
    end = date.today() - timedelta(days=1)
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
        meta = _get_account(token, acct)
        cur  = normalize_currency(meta.get("currency"))
        tz   = meta.get("timezone") or "UTC"
        print(f"[snap]   account {acct} tz={tz} native={cur} -> converting to USD")

        campaigns = _list_campaigns(token, acct)
        acct_count = 0
        for cid, c in campaigns.items():
            series = _campaign_stats(token, cid, start, end, tz)
            for pt in series:
                stats        = pt.get("stats", {})
                spend_micro  = float(stats.get("spend", 0) or 0)
                spend_native = spend_micro / 1_000_000   # micro-currency -> native currency
                spend        = to_usd(spend_native, cur)  # -> USD
                impressions = int(stats.get("impressions", 0) or 0)
                clicks      = int(stats.get("swipes", 0) or 0)
                sign_ups    = int(stats.get("conversion_sign_ups", 0) or 0)
                purchases   = int(stats.get("conversion_purchases", 0) or 0)
                conversions_total = (
                    sign_ups + purchases
                    + int(stats.get("conversion_add_cart", 0) or 0)
                    + int(stats.get("conversion_save", 0) or 0)
                    + int(stats.get("conversion_start_checkout", 0) or 0)
                    + int(stats.get("conversion_subscribe", 0) or 0)
                    + int(stats.get("conversion_app_installs", 0) or 0)
                )
                # leads = 0 here; source of truth is HubSpot (by channel attribution).
                # Platform conversion metrics are stored in conversions field.
                leads       = 0
                ctr         = (clicks / impressions * 100) if impressions else 0.0
                d           = (pt.get("start_time") or "")[:10]
                if not d:
                    continue
                rows.append({
                    "date":          d,
                    "channel":       "snapchat",
                    "account_id":    acct,
                    "campaign_id":   cid,
                    "campaign_name": c.get("name"),
                    "status":        c.get("status"),
                    "objective":     c.get("objective"),
                    "spend":         round(spend, 2),
                    "impressions":   impressions,
                    "clicks":        clicks,
                    "ctr":           round(ctr, 4),
                    "leads":         leads,
                    "conversions":   float(conversions_total),
                    "cpl":           round(spend / leads, 2) if leads > 0 else None,
                    "currency":      "USD",
                    "updated_at":    now,
                })
                acct_count += 1
        print(f"[snap]   account {acct}: {acct_count} rows across {len(campaigns)} campaigns")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


# ── Ad Squad level → adsets_daily ────────────────────────────────────────────

def _list_adsquads(token: str, ad_account_id: str) -> dict:
    """Return {adsquad_id: {name, campaign_id, status}} for the account."""
    r = requests.get(f"{BASE}/adaccounts/{ad_account_id}/adsquads",
                     headers=_headers(token), timeout=15)
    if r.status_code >= 400:
        print(f"[snap]   adsquads {r.status_code}: {r.text[:160]}")
        return {}
    out = {}
    for item in r.json().get("adsquads", []):
        sq = item.get("adsquad", {})
        out[sq["id"]] = {
            "name":        sq.get("name", ""),
            "campaign_id": sq.get("campaign_id", ""),
            "status":      sq.get("status", ""),
        }
    return out


def _adsquad_stats_single_call(token: str, adsquad_id: str,
                                start: date, end: date, tz_name: str,
                                fields: str = SNAP_STATS_FIELDS) -> list:
    end_exclusive = end + timedelta(days=1)
    params = {
        "granularity": "DAY",
        "start_time":  _day_start_iso(start, tz_name),
        "end_time":    _day_start_iso(end_exclusive, tz_name),
        "fields":      fields,
    }
    try:
        r = _snap_get(f"{BASE}/adsquads/{adsquad_id}/stats", _headers(token), params)
    except Exception as exc:
        print(f"[snap]   skipping adsquad {adsquad_id} ({start}..{end}) "
              f"after {_SNAP_RETRIES} retries: {exc}")
        return []
    if r.status_code >= 400 and fields != SNAP_STATS_FIELDS_SAFE:
        body = r.text.lower()
        if "field" in body or ("unsupported" in body and "granularity" not in body):
            params["fields"] = SNAP_STATS_FIELDS_SAFE
            try:
                r = _snap_get(f"{BASE}/adsquads/{adsquad_id}/stats",
                              _headers(token), params)
            except Exception as exc:
                print(f"[snap]   skipping adsquad {adsquad_id} on safe-fields retry: {exc}")
                return []
    if r.status_code >= 400:
        print(f"[snap]   adsquad stats {r.status_code} for {adsquad_id}: {r.text[:120]}")
        return []
    series = r.json().get("timeseries_stats", [])
    if not series:
        return []
    return series[0].get("timeseries_stat", {}).get("timeseries", [])


def collect_adsets_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad Squad grain → adsets_daily. Same token as campaign collector."""
    token = _refresh_access_token()

    end = date.today() - timedelta(days=1)   # cap at yesterday — same reason as campaigns
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _ad_accounts()
    print(f"[snap] adsets window {start} -> {end} across {len(accounts)} account(s)")

    for acct in accounts:
        meta    = _get_account(token, acct)
        cur     = normalize_currency(meta.get("currency"))
        tz      = meta.get("timezone") or "UTC"
        campaigns = _list_campaigns(token, acct)
        adsquads  = _list_adsquads(token, acct)
        acct_count = 0

        for sq_id, sq in adsquads.items():
            camp_id = sq.get("campaign_id", "")
            camp    = campaigns.get(camp_id, {})
            for cs, ce in _date_chunks(start, end, max_days=30):
                pts = _adsquad_stats_single_call(token, sq_id, cs, ce, tz)
                for pt in pts:
                    stats        = pt.get("stats", {})
                    spend_micro  = float(stats.get("spend", 0) or 0)
                    spend_native = spend_micro / 1_000_000
                    spend        = to_usd(spend_native, cur)
                    impressions  = int(stats.get("impressions", 0) or 0)
                    clicks       = int(stats.get("swipes", 0) or 0)
                    conversions_total = (
                        int(stats.get("conversion_sign_ups", 0) or 0)
                        + int(stats.get("conversion_purchases", 0) or 0)
                        + int(stats.get("conversion_add_cart", 0) or 0)
                        + int(stats.get("conversion_save", 0) or 0)
                        + int(stats.get("conversion_start_checkout", 0) or 0)
                        + int(stats.get("conversion_subscribe", 0) or 0)
                        + int(stats.get("conversion_app_installs", 0) or 0)
                    )
                    ctr = (clicks / impressions * 100) if impressions else 0.0
                    d   = (pt.get("start_time") or "")[:10]
                    if not d:
                        continue
                    rows.append({
                        "date":          d,
                        "channel":       "snapchat",
                        "account_id":    acct,
                        "campaign_id":   camp_id,
                        "campaign_name": camp.get("name"),
                        "adset_id":      sq_id,
                        "adset_name":    sq.get("name"),
                        "status":        sq.get("status"),
                        "spend":         round(spend, 2),
                        "impressions":   impressions,
                        "clicks":        clicks,
                        "ctr":           round(ctr, 4),
                        "leads":         0,
                        "conversions":   float(conversions_total),
                        "currency":      "USD",
                        "updated_at":    now,
                    })
                    acct_count += 1
        print(f"[snap]   adsets account {acct}: {acct_count} rows across {len(adsquads)} ad squads")

    return upsert_rows("adsets_daily", rows,
                       key_fields=["date", "channel", "adset_id"])


# ── Ad (Creative) level → ads_daily ──────────────────────────────────────────

def _list_ads(token: str, ad_account_id: str) -> dict:
    """Return {ad_id: {name, adsquad_id, campaign_id}} for all ads in account."""
    r = requests.get(f"{BASE}/adaccounts/{ad_account_id}/ads",
                     headers=_headers(token), timeout=30)
    if r.status_code >= 400:
        print(f"[snap]   ads list {r.status_code}: {r.text[:160]}")
        return {}
    # Also need adsquad → campaign mapping for campaign_id lookups
    adsquads = _list_adsquads(token, ad_account_id)
    out = {}
    for item in r.json().get("ads", []):
        ad = item.get("ad", {})
        sq_id = ad.get("ad_squad_id", "")
        out[ad["id"]] = {
            "name":        ad.get("name", ""),
            "adsquad_id":  sq_id,
            "campaign_id": adsquads.get(sq_id, {}).get("campaign_id", ""),
        }
    return out


def _ad_stats_single_call(token: str, ad_id: str,
                           start: date, end: date, tz_name: str) -> list:
    end_exclusive = end + timedelta(days=1)
    params = {
        "granularity": "DAY",
        "start_time":  _day_start_iso(start, tz_name),
        "end_time":    _day_start_iso(end_exclusive, tz_name),
        "fields":      SNAP_STATS_FIELDS,
    }
    try:
        r = _snap_get(f"{BASE}/ads/{ad_id}/stats", _headers(token), params)
    except Exception as exc:
        print(f"[snap]   skipping ad {ad_id} after {_SNAP_RETRIES} retries: {exc}")
        return []
    if r.status_code >= 400 and SNAP_STATS_FIELDS != SNAP_STATS_FIELDS_SAFE:
        body = r.text.lower()
        if "field" in body or ("unsupported" in body and "granularity" not in body):
            params["fields"] = SNAP_STATS_FIELDS_SAFE
            try:
                r = _snap_get(f"{BASE}/ads/{ad_id}/stats", _headers(token), params)
            except Exception as exc:
                print(f"[snap]   skipping ad {ad_id} on safe-fields retry: {exc}")
                return []
    if r.status_code >= 400:
        print(f"[snap]   ad stats {r.status_code} for {ad_id}: {r.text[:120]}")
        return []
    series = r.json().get("timeseries_stats", [])
    if not series:
        return []
    return series[0].get("timeseries_stat", {}).get("timeseries", [])


def collect_ads_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad/Creative grain → ads_daily. Exact spend per ad from Snap API."""
    token = _refresh_access_token()

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _ad_accounts()
    print(f"[snap] ads window {start} -> {end} across {len(accounts)} account(s)")

    for acct in accounts:
        meta   = _get_account(token, acct)
        cur    = normalize_currency(meta.get("currency"))
        tz     = meta.get("timezone") or "UTC"
        adsquads = _list_adsquads(token, acct)
        ads    = _list_ads(token, acct)
        print(f"[snap]   ads account {acct}: {len(ads)} ads in metadata")
        acct_count = 0

        for ad_id, ad_meta in ads.items():
            sq_id    = ad_meta.get("adsquad_id", "")
            camp_id  = ad_meta.get("campaign_id", "")
            sq       = adsquads.get(sq_id, {})
            for cs, ce in _date_chunks(start, end, max_days=30):
                pts = _ad_stats_single_call(token, ad_id, cs, ce, tz)
                for pt in pts:
                    stats        = pt.get("stats", {})
                    spend_micro  = float(stats.get("spend", 0) or 0)
                    spend_native = spend_micro / 1_000_000
                    spend        = to_usd(spend_native, cur)
                    impressions  = int(stats.get("impressions", 0) or 0)
                    clicks       = int(stats.get("swipes", 0) or 0)
                    conversions_total = (
                        int(stats.get("conversion_sign_ups", 0) or 0)
                        + int(stats.get("conversion_purchases", 0) or 0)
                        + int(stats.get("conversion_add_cart", 0) or 0)
                        + int(stats.get("conversion_save", 0) or 0)
                        + int(stats.get("conversion_start_checkout", 0) or 0)
                        + int(stats.get("conversion_subscribe", 0) or 0)
                        + int(stats.get("conversion_app_installs", 0) or 0)
                    )
                    ctr = (clicks / impressions * 100) if impressions else 0.0
                    d   = (pt.get("start_time") or "")[:10]
                    if not d:
                        continue
                    rows.append({
                        "date":          d,
                        "channel":       "snapchat",
                        "account_id":    acct,
                        "campaign_id":   camp_id,
                        "campaign_name": None,   # not at ad grain
                        "adset_id":      sq_id,
                        "adset_name":    sq.get("name"),
                        "ad_id":         ad_id,
                        "ad_name":       ad_meta.get("name"),
                        "status":        None,
                        "spend":         round(spend, 2),
                        "impressions":   impressions,
                        "clicks":        clicks,
                        "ctr":           round(ctr, 4),
                        "leads":         0,
                        "conversions":   float(conversions_total),
                        "currency":      "USD",
                        "updated_at":    now,
                    })
                    acct_count += 1
        print(f"[snap]   ads account {acct}: {acct_count} rows across {len(ads)} ads")

    return upsert_rows("ads_daily", rows,
                       key_fields=["date", "channel", "ad_id"])


if __name__ == "__main__":
    import sys
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "all"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in ("all", "campaigns"):
        print(f"campaigns: {collect_and_write(days=days)} rows")
    if cmd in ("all", "adsets"):
        print(f"adsets:    {collect_adsets_and_write(days=days)} rows")
    if cmd in ("all", "ads"):
        print(f"ads:       {collect_ads_and_write(days=days)} rows")
