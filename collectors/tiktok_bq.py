"""
TikTok Ads -> BigQuery collector.

  collect_and_write()        -> campaigns_daily
  collect_adgroups_and_write() -> adsets_daily  (AUCTION_ADGROUP level)
  collect_ads_and_write()    -> ads_daily       (AUCTION_AD level)

Auth: TIKTOK_ACCESS_TOKEN in .env (long-lived token from Ads Manager).
"""
import os
from datetime import date, timedelta, datetime, timezone
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

load_dotenv()

BASE         = "https://business-api.tiktok.com/open_api/v1.3"
ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")


def _ad_accounts() -> list[str]:
    return [a for a in [
        os.getenv("TIKTOK_AD_ACCOUNT_2024"),
        os.getenv("TIKTOK_AD_ACCOUNT_2025"),
    ] if a]


def _headers() -> dict:
    return {"Access-Token": ACCESS_TOKEN, "Content-Type": "application/json"}


def _advertiser_currency(advertiser_id: str) -> str:
    """Fetch the advertiser's native currency. Defaults to SAR on error."""
    try:
        r = requests.get(
            f"{BASE}/advertiser/info/",
            headers=_headers(),
            params={"advertiser_ids": f'["{advertiser_id}"]',
                    "fields": '["currency"]'},
            timeout=15,
        )
        if r.status_code < 400:
            lst = r.json().get("data", {}).get("list", [])
            if lst:
                return normalize_currency(lst[0].get("currency"))
    except Exception as e:
        print(f"[tiktok-bq] currency lookup failed for {advertiser_id}: {e}")
    return "SAR"


def _date_chunks(start: date, end: date, max_days: int = 30):
    """Yield (chunk_start, chunk_end) tuples of up to max_days each."""
    cur = start
    while cur <= end:
        yield cur, min(cur + timedelta(days=max_days - 1), end)
        cur = cur + timedelta(days=max_days)


def _get_report(advertiser_id: str, start: date, end: date,
                data_level: str = "AUCTION_CAMPAIGN",
                dimensions: list | None = None,
                metrics: list | None = None) -> list[dict]:
    """Fetch paginated report rows for one advertiser account.

    TikTok rules:
    - max 30 days per query when using stat_time_day — chunked automatically
    - AUCTION_CAMPAIGN  → dimensions may include campaign_id
    - AUCTION_ADGROUP   → dimensions must NOT include campaign_id; use adgroup_id only
    - AUCTION_AD        → dimensions must NOT include campaign_id/adgroup_id; use ad_id only
    Parent IDs are obtained via _list_adgroups() / _list_ads() metadata calls.
    """
    import json as _json
    PAGE_SIZE = 1000
    all_rows: list[dict] = []
    _dims = dimensions or ["campaign_id", "stat_time_day"]
    _metrics = metrics or [
        "spend", "impressions", "clicks", "ctr",
        "conversion", "cost_per_conversion",
        "campaign_name",
    ]

    for cs, ce in _date_chunks(start, end, max_days=30):
        page = 1
        while True:
            params = {
                "advertiser_id": advertiser_id,
                "report_type":   "BASIC",
                "dimensions":    _json.dumps(_dims),
                "data_level":    data_level,
                "lifetime":      "false",
                "start_date":    str(cs),
                "end_date":      str(ce),
                "metrics":       _json.dumps(_metrics),
                "page_size":     PAGE_SIZE,
                "page":          page,
            }
            r = requests.get(f"{BASE}/report/integrated/get/",
                             headers=_headers(), params=params, timeout=30)
            if r.status_code >= 400:
                print(f"[tiktok-bq] report {r.status_code} (page {page}): {r.text[:200]}")
                break
            data = r.json()
            if data.get("code", 0) != 0:
                print(f"[tiktok-bq] API error {data.get('code')}: {data.get('message','')} (page {page})")
                break
            batch = data.get("data", {}).get("list", [])
            all_rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page += 1
    return all_rows


def _list_adgroups(advertiser_id: str) -> dict[str, dict]:
    """Return {adgroup_id: {campaign_id, name}} for all ad groups in account."""
    out: dict[str, dict] = {}
    page = 1
    while True:
        r = requests.get(f"{BASE}/adgroup/get/", headers=_headers(),
                         params={"advertiser_id": advertiser_id,
                                 "page_size": 1000, "page": page},
                         timeout=30)
        if r.status_code >= 400:
            print(f"[tiktok-bq] adgroup/get {r.status_code}: {r.text[:120]}")
            break
        data = r.json()
        if data.get("code", 0) != 0:
            print(f"[tiktok-bq] adgroup/get error {data.get('code')}: {data.get('message','')}")
            break
        items = data.get("data", {}).get("list", [])
        for item in items:
            out[str(item.get("adgroup_id", ""))] = {
                "campaign_id": str(item.get("campaign_id", "")),
                "name":        item.get("adgroup_name", ""),
            }
        if len(items) < 1000:
            break
        page += 1
    return out


def _list_ads(advertiser_id: str) -> dict[str, dict]:
    """Return {ad_id: {adgroup_id, campaign_id, ad_name}} for all ads in account."""
    out: dict[str, dict] = {}
    page = 1
    while True:
        r = requests.get(f"{BASE}/ad/get/", headers=_headers(),
                         params={"advertiser_id": advertiser_id,
                                 "page_size": 1000, "page": page},
                         timeout=30)
        if r.status_code >= 400:
            print(f"[tiktok-bq] ad/get {r.status_code}: {r.text[:120]}")
            break
        data = r.json()
        if data.get("code", 0) != 0:
            print(f"[tiktok-bq] ad/get error {data.get('code')}: {data.get('message','')}")
            break
        items = data.get("data", {}).get("list", [])
        for item in items:
            out[str(item.get("ad_id", ""))] = {
                "adgroup_id":  str(item.get("adgroup_id", "")),
                "campaign_id": str(item.get("campaign_id", "")),
                "name":        item.get("ad_name", ""),
            }
        if len(items) < 1000:
            break
        page += 1
    return out


def collect_and_write(days: int = None, incremental: bool = False) -> int:
    if not ACCESS_TOKEN:
        print("[tiktok-bq] TIKTOK_ACCESS_TOKEN not set — skipping")
        return 0

    end = date.today() - timedelta(days=1)   # TikTok lags 1 day
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for account_id in _ad_accounts():
        native_cur  = _advertiser_currency(account_id)
        print(f"[tiktok-bq] account {account_id} native={native_cur} -> converting to USD")
        report_rows = _get_report(account_id, start, end)
        for row in report_rows:
            dims    = row.get("dimensions", {})
            metrics = row.get("metrics", {})
            day     = (dims.get("stat_time_day") or "")[:10]
            if not day:
                continue
            cid          = str(dims.get("campaign_id", ""))
            spend_native = float(metrics.get("spend", 0) or 0)
            spend        = to_usd(spend_native, native_cur)
            impr         = int(metrics.get("impressions", 0) or 0)
            clicks       = int(metrics.get("clicks", 0) or 0)
            leads        = int(metrics.get("conversion", 0) or 0)
            cpl_native   = float(metrics.get("cost_per_conversion", 0) or 0) or None
            cpl          = to_usd(cpl_native, native_cur) if cpl_native else None

            rows.append({
                "date":           day,
                "channel":        "tiktok",
                "account_id":     account_id,
                "campaign_id":    cid,
                "campaign_name":  metrics.get("campaign_name", cid),
                "status":         None,
                "objective":      None,
                "spend":          round(spend, 2),
                "impressions":    impr,
                "clicks":         clicks,
                "ctr":            float(metrics.get("ctr", 0) or 0),
                "leads":          leads,
                "conversions":    float(leads),
                "cpl":            round(cpl, 2) if cpl else None,
                "currency":       "USD",
                "spend_native":   round(spend_native, 2),
                "currency_native": native_cur,
                "updated_at":     now,
            })
        print(f"[tiktok-bq] account {account_id}: {len(report_rows)} rows")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


# ── Ad Group level → adsets_daily ────────────────────────────────────────────

def collect_adgroups_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad group grain → adsets_daily. Same token, AUCTION_ADGROUP level."""
    if not ACCESS_TOKEN:
        print("[tiktok-bq] TIKTOK_ACCESS_TOKEN not set — skipping adgroups")
        return 0

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for account_id in _ad_accounts():
        native_cur = _advertiser_currency(account_id)
        # Metadata lookup: adgroup_id -> {campaign_id, name}
        adgroup_meta = _list_adgroups(account_id)
        print(f"[tiktok-bq] adgroups account {account_id}: {len(adgroup_meta)} adgroups in metadata")
        # dimensions must NOT include campaign_id at AUCTION_ADGROUP level
        report_rows = _get_report(
            account_id, start, end,
            data_level="AUCTION_ADGROUP",
            dimensions=["adgroup_id", "stat_time_day"],
            metrics=["spend", "impressions", "clicks", "ctr",
                     "conversion", "adgroup_name"],
        )
        for row in report_rows:
            dims    = row.get("dimensions", {})
            metrics = row.get("metrics", {})
            day     = (dims.get("stat_time_day") or "")[:10]
            if not day:
                continue
            adgroup_id   = str(dims.get("adgroup_id", ""))
            meta         = adgroup_meta.get(adgroup_id, {})
            spend_native = float(metrics.get("spend", 0) or 0)
            spend        = to_usd(spend_native, native_cur)
            rows.append({
                "date":          day,
                "channel":       "tiktok",
                "account_id":    account_id,
                "campaign_id":   meta.get("campaign_id", ""),
                "campaign_name": None,   # not available at adgroup grain
                "adset_id":      adgroup_id,
                "adset_name":    metrics.get("adgroup_name") or meta.get("name"),
                "status":        None,
                "spend":         round(spend, 2),
                "impressions":   int(metrics.get("impressions", 0) or 0),
                "clicks":        int(metrics.get("clicks", 0) or 0),
                "ctr":           float(metrics.get("ctr", 0) or 0),
                "leads":         int(metrics.get("conversion", 0) or 0),
                "conversions":   float(metrics.get("conversion", 0) or 0),
                "currency":      "USD",
                "updated_at":    now,
            })
        print(f"[tiktok-bq] adgroups account {account_id}: {len(report_rows)} stat rows")

    return upsert_rows("adsets_daily", rows,
                       key_fields=["date", "channel", "adset_id"])


# ── Ad level → ads_daily ──────────────────────────────────────────────────────

def collect_ads_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad grain → ads_daily. Same token, AUCTION_AD level."""
    if not ACCESS_TOKEN:
        print("[tiktok-bq] TIKTOK_ACCESS_TOKEN not set — skipping ads")
        return 0

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for account_id in _ad_accounts():
        native_cur = _advertiser_currency(account_id)
        # Metadata lookup: ad_id -> {adgroup_id, campaign_id, name}
        ad_meta = _list_ads(account_id)
        print(f"[tiktok-bq] ads account {account_id}: {len(ad_meta)} ads in metadata")
        # dimensions must NOT include campaign_id or adgroup_id at AUCTION_AD level
        report_rows = _get_report(
            account_id, start, end,
            data_level="AUCTION_AD",
            dimensions=["ad_id", "stat_time_day"],
            metrics=["spend", "impressions", "clicks", "ctr",
                     "conversion", "ad_name"],
        )
        for row in report_rows:
            dims    = row.get("dimensions", {})
            metrics = row.get("metrics", {})
            day     = (dims.get("stat_time_day") or "")[:10]
            if not day:
                continue
            ad_id        = str(dims.get("ad_id", ""))
            meta         = ad_meta.get(ad_id, {})
            spend_native = float(metrics.get("spend", 0) or 0)
            spend        = to_usd(spend_native, native_cur)
            rows.append({
                "date":          day,
                "channel":       "tiktok",
                "account_id":    account_id,
                "campaign_id":   meta.get("campaign_id", ""),
                "campaign_name": None,   # not available at ad grain
                "adset_id":      meta.get("adgroup_id", ""),
                "adset_name":    None,
                "ad_id":         ad_id,
                "ad_name":       metrics.get("ad_name") or meta.get("name"),
                "status":        None,
                "spend":         round(spend, 2),
                "impressions":   int(metrics.get("impressions", 0) or 0),
                "clicks":        int(metrics.get("clicks", 0) or 0),
                "ctr":           float(metrics.get("ctr", 0) or 0),
                "leads":         int(metrics.get("conversion", 0) or 0),
                "conversions":   float(metrics.get("conversion", 0) or 0),
                "currency":      "USD",
                "updated_at":    now,
            })
        print(f"[tiktok-bq] ads account {account_id}: {len(report_rows)} stat rows")

    return upsert_rows("ads_daily", rows,
                       key_fields=["date", "channel", "ad_id"])


if __name__ == "__main__":
    import sys
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "all"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in ("all", "campaigns"):
        print(f"campaigns: {collect_and_write(days=days)} rows")
    if cmd in ("all", "adgroups"):
        print(f"adgroups:  {collect_adgroups_and_write(days=days)} rows")
    if cmd in ("all", "ads"):
        print(f"ads:       {collect_ads_and_write(days=days)} rows")
