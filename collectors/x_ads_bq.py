"""
X (Twitter) Ads -> BigQuery collector.
Pulls per-day campaign and ad stats from the X Ads API v12 -> campaigns_daily + ads_daily.

Auth: OAuth 1.0a via requests-oauthlib.
Spend: billed_charge_local_micro (microcurrency) / 1_000_000 -> native -> to_usd().
Stats endpoint caps at 7 days per call -> chunk into <=7-day pieces.
Stats endpoint accepts up to 20 entity IDs per call -> batch them.
"""
import os
import time as _time
import types
from datetime import date, timedelta, datetime, timezone
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

load_dotenv(override=True)

_RIYADH = timezone(timedelta(hours=3))

BASE = "https://ads-api.twitter.com/12"

_X_TIMEOUT    = 60
_X_RETRIES    = 5
_X_RETRY_WAIT = 15


def _auth():
    return OAuth1(
        os.getenv("X_ADS_CONSUMER_KEY"),
        os.getenv("X_ADS_CONSUMER_SECRET"),
        os.getenv("X_ADS_ACCESS_TOKEN"),
        os.getenv("X_ADS_ACCESS_TOKEN_SECRET"),
    )


def _ad_accounts():
    return [a for a in [
        os.getenv("X_ADS_ACCOUNT_ID"),
    ] if a]


def _x_get(url, auth, params=None, timeout=_X_TIMEOUT):
    """GET with retry on 429/timeout/connection error. Tries up to _X_RETRIES times."""
    last_exc = None
    for attempt in range(_X_RETRIES):
        try:
            r = requests.get(url, auth=auth, params=params, timeout=timeout)
            if r.status_code == 429:
                print(f"[x_ads]  429 rate limit attempt {attempt+1}/{_X_RETRIES}, "
                      f"waiting {_X_RETRY_WAIT}s...")
                _time.sleep(_X_RETRY_WAIT)
                continue
            return r
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt < _X_RETRIES - 1:
                print(f"[x_ads]  network error attempt {attempt+1}/{_X_RETRIES} "
                      f"({type(exc).__name__}), retry in {_X_RETRY_WAIT}s...")
                _time.sleep(_X_RETRY_WAIT)
    if last_exc:
        raise last_exc
    fake = types.SimpleNamespace(status_code=429, text="[rate limited after retries]")
    return fake


def _date_chunks(start, end, max_days=7):
    """Yield (chunk_start, chunk_end) inclusive tuples of up to max_days each."""
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def _get_account(account_id, auth):
    """Fetch account metadata; fall back to currency from funding instruments."""
    r = _x_get(f"{BASE}/accounts/{account_id}", auth)
    if r.status_code >= 400:
        print(f"[x_ads]  account fetch {r.status_code}: {r.text[:160]}")
        return {"currency": "SAR"}
    meta = r.json().get("data", {})
    # Account endpoint doesn't expose currency — fetch from funding instruments
    if not meta.get("currency"):
        fr = _x_get(f"{BASE}/accounts/{account_id}/funding_instruments", auth)
        if fr.status_code < 400:
            instruments = fr.json().get("data", [])
            if instruments:
                meta["currency"] = instruments[0].get("currency", "SAR")
    if not meta.get("currency"):
        meta["currency"] = "SAR"
    return meta


def _list_campaigns(account_id, auth):
    """Return {campaign_id: {name, status, objective}} with cursor pagination."""
    out = {}
    params = {"count": 200}
    while True:
        r = _x_get(f"{BASE}/accounts/{account_id}/campaigns", auth, params)
        if r.status_code >= 400:
            print(f"[x_ads]  campaigns {r.status_code}: {r.text[:160]}")
            break
        body = r.json()
        for c in body.get("data", []):
            out[c["id"]] = {
                "name":      c.get("name", ""),
                "status":    c.get("entity_status", ""),
                "objective": c.get("objective", ""),
            }
        cursor = body.get("request", {}).get("params", {}).get("cursor")
        if not cursor or not body.get("data"):
            break
        params = {"count": 200, "cursor": cursor}
    return out


def _list_line_items(account_id, auth):
    """Return {line_item_id: {name, campaign_id, status}} (ad groups in X Ads)."""
    out = {}
    params = {"count": 200}
    while True:
        r = _x_get(f"{BASE}/accounts/{account_id}/line_items", auth, params)
        if r.status_code >= 400:
            print(f"[x_ads]  line_items {r.status_code}: {r.text[:160]}")
            break
        body = r.json()
        for li in body.get("data", []):
            out[li["id"]] = {
                "name":        li.get("name", ""),
                "campaign_id": li.get("campaign_id", ""),
                "status":      li.get("entity_status", ""),
            }
        cursor = body.get("request", {}).get("params", {}).get("cursor")
        if not cursor or not body.get("data"):
            break
        params = {"count": 200, "cursor": cursor}
    return out


def _list_promoted_tweets(account_id, auth, line_items=None):
    """Return {pt_id: {line_item_id, campaign_id, status}} for all promoted tweets."""
    out = {}
    if line_items is None:
        line_items = _list_line_items(account_id, auth)
    params = {"count": 200}
    while True:
        r = _x_get(f"{BASE}/accounts/{account_id}/promoted_tweets", auth, params)
        if r.status_code >= 400:
            print(f"[x_ads]  promoted_tweets {r.status_code}: {r.text[:160]}")
            break
        body = r.json()
        for pt in body.get("data", []):
            li_id   = pt.get("line_item_id", "")
            camp_id = line_items.get(li_id, {}).get("campaign_id", "")
            out[pt["id"]] = {
                "line_item_id": li_id,
                "campaign_id":  camp_id,
                "status":       pt.get("entity_status", ""),
            }
        cursor = body.get("request", {}).get("params", {}).get("cursor")
        if not cursor or not body.get("data"):
            break
        params = {"count": 200, "cursor": cursor}
    return out


def _campaign_stats(account_id, campaign_ids_batch, start, end, auth):
    """Fetch stats for a batch of up to 20 campaign IDs over a <=7-day window; returns list of (campaign_id, date_str, metrics_dict)."""
    if not campaign_ids_batch:
        return []
    params = {
        "entity":         "CAMPAIGN",
        "entity_ids":     ",".join(campaign_ids_batch),
        "start_time":     start.strftime("%Y-%m-%dT00:00:00Z"),
        "end_time":       (end + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
        "granularity":    "DAY",
        "metric_groups":  ["ENGAGEMENT", "BILLING"],
        "placement":      "ALL_ON_TWITTER",
    }
    r = _x_get(f"{BASE}/stats/accounts/{account_id}", auth, params)
    if r.status_code >= 400:
        print(f"[x_ads]  campaign stats {r.status_code} batch={campaign_ids_batch[:3]}…: {r.text[:160]}")
        return []
    out = []
    for item in r.json().get("data", []):
        cid = item.get("id", "")
        for id_data in item.get("id_data", []):
            metrics = id_data.get("metrics", {})
            # Each metric is a parallel array — one value per day in the window
            # Build per-day rows by zipping the arrays
            spend_arr  = metrics.get("billed_charge_local_micro") or []
            imps_arr   = metrics.get("impressions") or []
            clicks_arr = metrics.get("clicks") or []
            url_arr    = metrics.get("url_clicks") or []
            conv_arr   = metrics.get("conversions_total") or []
            max_len    = max(len(spend_arr), len(imps_arr), len(clicks_arr), 1)
            # Generate the date sequence for this window
            day_seq    = [start + timedelta(days=i) for i in range(max_len)]
            def _v(arr, idx):
                try:
                    v = arr[idx]
                    return v if v is not None else 0
                except IndexError:
                    return 0
            for i, day in enumerate(day_seq):
                out.append((cid, day.strftime("%Y-%m-%d"), {
                    "spend_micro":  _v(spend_arr, i),
                    "impressions":  _v(imps_arr, i),
                    "clicks":       _v(url_arr, i) or _v(clicks_arr, i),
                    "conversions":  _v(conv_arr, i),
                }))
    return out


def _promoted_tweet_stats(account_id, pt_ids_batch, start, end, auth):
    """Fetch stats for a batch of up to 20 promoted tweet IDs over a <=7-day window; returns list of (pt_id, date_str, metrics_dict)."""
    if not pt_ids_batch:
        return []
    params = {
        "entity":        "PROMOTED_TWEET",
        "entity_ids":    ",".join(pt_ids_batch),
        "start_time":    start.strftime("%Y-%m-%dT00:00:00Z"),
        "end_time":      (end + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
        "granularity":   "DAY",
        "metric_groups": ["ENGAGEMENT", "BILLING"],
        "placement":     "ALL_ON_TWITTER",
    }
    r = _x_get(f"{BASE}/stats/accounts/{account_id}", auth, params)
    if r.status_code >= 400:
        print(f"[x_ads]  promoted_tweet stats {r.status_code}: {r.text[:160]}")
        return []
    out = []
    for item in r.json().get("data", []):
        pt_id = item.get("id", "")
        for id_data in item.get("id_data", []):
            metrics    = id_data.get("metrics", {})
            spend_arr  = metrics.get("billed_charge_local_micro") or []
            imps_arr   = metrics.get("impressions") or []
            clicks_arr = metrics.get("clicks") or []
            url_arr    = metrics.get("url_clicks") or []
            conv_arr   = metrics.get("conversions_total") or []
            max_len    = max(len(spend_arr), len(imps_arr), len(clicks_arr), 1)
            day_seq    = [start + timedelta(days=i) for i in range(max_len)]
            def _v(arr, idx):
                try:
                    v = arr[idx]
                    return v if v is not None else 0
                except IndexError:
                    return 0
            for i, day in enumerate(day_seq):
                out.append((pt_id, day.strftime("%Y-%m-%d"), {
                    "spend_micro": _v(spend_arr, i),
                    "impressions": _v(imps_arr, i),
                    "clicks":      _v(url_arr, i) or _v(clicks_arr, i),
                    "conversions": _v(conv_arr, i),
                }))
    return out


def _batches(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def collect_and_write(days=None, incremental=False):
    """
    incremental=True -> last 30 days
    days=N            -> last N days
    default           -> from 2025-01-01
    """
    auth = _auth()
    end = datetime.now(_RIYADH).date() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=29)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(2025, 1, 1)

    now      = datetime.now(timezone.utc).isoformat()
    rows     = []
    accounts = _ad_accounts()
    print(f"[x_ads] campaigns window {start} -> {end} across {len(accounts)} account(s)")

    for acct in accounts:
        meta = _get_account(acct, auth)
        cur  = normalize_currency(meta.get("currency", "SAR"))
        print(f"[x_ads]  account {acct} native={cur} -> converting to USD")

        campaigns = _list_campaigns(acct, auth)
        print(f"[x_ads]  {len(campaigns)} campaigns found")

        # Accumulate per-campaign per-day stats across all chunks
        stats_map = {}   # {(campaign_id, date_str): metrics_dict}

        for cs, ce in _date_chunks(start, end, max_days=7):
            camp_ids = list(campaigns.keys())
            for batch in _batches(camp_ids, 20):
                try:
                    points = _campaign_stats(acct, batch, cs, ce, auth)
                except Exception as exc:
                    print(f"[x_ads]  skipping batch {batch[:3]}… ({cs}..{ce}): {exc}")
                    continue
                for cid, d_str, m in points:
                    stats_map[(cid, d_str)] = m

        acct_count = 0
        for (cid, d_str), m in stats_map.items():
            c            = campaigns.get(cid, {})
            spend_micro  = float(m.get("spend_micro", 0) or 0)
            spend_native = spend_micro / 1_000_000
            spend        = to_usd(spend_native, cur)
            impressions  = int(m.get("impressions", 0) or 0)
            clicks       = int(m.get("clicks", 0) or 0)
            conversions  = float(m.get("conversions", 0) or 0)
            ctr          = (clicks / impressions * 100) if impressions else 0.0

            # Skip zero-activity rows from PAUSED campaigns
            if (spend == 0.0 and impressions == 0
                    and (c.get("status") or "").upper() == "PAUSED"):
                continue

            rows.append({
                "date":            d_str,
                "channel":         "x_ads",
                "account_id":      acct,
                "campaign_id":     cid,
                "campaign_name":   c.get("name"),
                "status":          c.get("status"),
                "objective":       c.get("objective"),
                "spend":           round(spend, 2),
                "impressions":     impressions,
                "clicks":          clicks,
                "ctr":             round(ctr, 4),
                "leads":           0,
                "conversions":     conversions,
                "cpl":             None,
                "currency":        "USD",
                "spend_native":    round(spend_native, 2),
                "currency_native": cur,
                "updated_at":      now,
            })
            acct_count += 1
        print(f"[x_ads]  account {acct}: {acct_count} campaign rows")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


def collect_ads_and_write(days=None, incremental=False):
    """
    Promoted tweet grain -> ads_daily.
    Uses ThreadPoolExecutor(max_workers=8) to parallelize per-batch stat calls.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    auth = _auth()
    end  = datetime.now(_RIYADH).date() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=29)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(2025, 1, 1)

    now      = datetime.now(timezone.utc).isoformat()
    rows     = []
    accounts = _ad_accounts()
    print(f"[x_ads] ads window {start} -> {end} across {len(accounts)} account(s)")

    for acct in accounts:
        meta       = _get_account(acct, auth)
        cur        = normalize_currency(meta.get("currency", "SAR"))
        line_items = _list_line_items(acct, auth)
        pts_map    = _list_promoted_tweets(acct, auth, line_items=line_items)
        print(f"[x_ads]  ads account {acct}: {len(pts_map)} promoted tweets, native={cur}")

        # Build work: list of (pt_ids_batch, chunk_start, chunk_end)
        pt_ids = list(pts_map.keys())
        work   = [
            (batch, cs, ce)
            for cs, ce in _date_chunks(start, end, max_days=7)
            for batch in _batches(pt_ids, 20)
        ]

        # Accumulate: {(pt_id, date_str): metrics_dict}
        stats_map = {}

        def _fetch(item):
            batch, cs, ce = item
            thread_auth = _auth()   # fresh OAuth1 per thread call (OAuth1 is not thread-safe)
            return _promoted_tweet_stats(acct, batch, cs, ce, thread_auth)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch, w): w for w in work}
            for fut in as_completed(futures):
                try:
                    points = fut.result()
                    for pt_id, d_str, m in points:
                        stats_map[(pt_id, d_str)] = m
                except Exception as exc:
                    print(f"[x_ads]  future error: {exc}")

        acct_count = 0
        for (pt_id, d_str), m in stats_map.items():
            pt          = pts_map.get(pt_id, {})
            li_id       = pt.get("line_item_id", "")
            camp_id     = pt.get("campaign_id", "")
            li          = line_items.get(li_id, {})
            spend_micro = float(m.get("spend_micro", 0) or 0)
            spend_native = spend_micro / 1_000_000
            spend       = to_usd(spend_native, cur)
            impressions = int(m.get("impressions", 0) or 0)
            clicks      = int(m.get("clicks", 0) or 0)
            conversions = float(m.get("conversions", 0) or 0)
            ctr         = (clicks / impressions * 100) if impressions else 0.0
            ad_name     = pt_id   # X Ads doesn't surface ad text in list endpoint
            status      = pt.get("status")

            if (spend == 0.0 and impressions == 0
                    and (status or "").upper() == "PAUSED"):
                continue

            rows.append({
                "date":          d_str,
                "channel":       "x_ads",
                "account_id":    acct,
                "campaign_id":   camp_id,
                "campaign_name": None,
                "adset_id":      li_id,
                "adset_name":    li.get("name"),
                "ad_id":         pt_id,
                "ad_name":       ad_name,
                "utm_content":   ad_name,
                "spend":         round(spend, 2),
                "impressions":   impressions,
                "clicks":        clicks,
                "ctr":           round(ctr, 4),
                "leads":         0,
                "conversions":   conversions,
                "currency":      "USD",
                "creative_type": None,
                "status":        status,
                "updated_at":    now,
            })
            acct_count += 1
        print(f"[x_ads]  ads account {acct}: {acct_count} rows across {len(pts_map)} promoted tweets")

    return upsert_rows("ads_daily", rows,
                       key_fields=["date", "channel", "ad_id"])


if __name__ == "__main__":
    import sys
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "all"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in ("all", "campaigns"):
        print(f"campaigns: {collect_and_write(days=days)} rows")
    if cmd in ("all", "ads"):
        print(f"ads:       {collect_ads_and_write(days=days)} rows")
