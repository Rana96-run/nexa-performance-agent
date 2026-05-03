"""
Windsor.ai → BigQuery collector.

Windsor.ai is a managed data pipeline that handles token refresh, pagination,
and rate limits for all ad channels. This collector pulls campaign-level data
from Windsor's unified API and writes it to campaigns_daily — the same table
as all direct collectors, so the rest of the stack (views, Hex, agent) is
completely unaware of the source.

Auth: WINDSOR_API_KEY in .env (from Windsor Settings → API).

Channels Windsor manages (replaces broken direct collectors):
  - google_ads   → Google Ads
  - facebook     → Meta Ads (Facebook + Instagram)
  - snapchat     → Snapchat Ads
  - tiktok       → TikTok Ads
  - linkedin     → LinkedIn Ads
  - bing         → Microsoft Ads

API docs: https://windsor.ai/api-fields/
Endpoint: https://connectors.windsor.ai/all
"""
from __future__ import annotations

import os
from datetime import date, timedelta, datetime, timezone
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

load_dotenv()

WINDSOR_API_KEY = os.getenv("WINDSOR_API_KEY", "")
WINDSOR_BASE    = "https://connectors.windsor.ai/all"

# Windsor source name → our channel slug in campaigns_daily
_CHANNEL_MAP: dict[str, str] = {
    "google_ads":  "google_ads",
    "facebook":    "meta",
    "snapchat":    "snapchat",
    "tiktok":      "tiktok",
    "linkedin":    "linkedin",
    "bing":        "microsoft_ads",
}

# Fields to request from Windsor
_FIELDS = [
    "date",
    "source",           # channel identifier
    "account_id",
    "campaign_id",
    "campaign_name",
    "campaign_status",
    "objective",
    "spend",
    "impressions",
    "clicks",
    "conversions",      # leads / form fills
    "currency",         # native currency of the account
]


def _fetch(start: date, end: date) -> list[dict]:
    """Pull all rows from Windsor for the given date range."""
    if not WINDSOR_API_KEY:
        print("[windsor-bq] WINDSOR_API_KEY not set — skipping")
        return []

    params = {
        "api_key":   WINDSOR_API_KEY,
        "date_from": str(start),
        "date_to":   str(end),
        "fields":    ",".join(_FIELDS),
        "_renderer": "json",
    }

    try:
        r = requests.get(WINDSOR_BASE, params=params, timeout=60)
        if r.status_code >= 400:
            print(f"[windsor-bq] HTTP {r.status_code}: {r.text[:300]}")
            return []
        data = r.json()
        # Windsor returns {"data": [...]} or a raw list
        if isinstance(data, dict):
            return data.get("data", [])
        if isinstance(data, list):
            return data
        print(f"[windsor-bq] Unexpected response shape: {type(data)}")
        return []
    except Exception as e:
        print(f"[windsor-bq] Request failed: {e}")
        return []


def collect_and_write(days: int = None, incremental: bool = False) -> int:
    """
    Fetch Windsor data and upsert into campaigns_daily.

    days=None + incremental=False → YTD (Jan 1 to yesterday)
    incremental=True             → last 3 days only
    days=N                       → last N days
    """
    if not WINDSOR_API_KEY:
        print("[windsor-bq] WINDSOR_API_KEY not set — skipping")
        return 0

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    print(f"[windsor-bq] Fetching {start} → {end}")
    raw_rows = _fetch(start, end)
    print(f"[windsor-bq] {len(raw_rows)} raw rows from Windsor")

    if not raw_rows:
        return 0

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for row in raw_rows:
        source     = (row.get("source") or "").lower()
        channel    = _CHANNEL_MAP.get(source, source)
        day        = (row.get("date") or "")[:10]
        if not day or not channel:
            continue

        native_cur = normalize_currency(row.get("currency"))
        spend_nat  = float(row.get("spend") or 0)
        spend_usd  = to_usd(spend_nat, native_cur)

        impr       = int(row.get("impressions") or 0)
        clicks     = int(row.get("clicks")      or 0)
        conv       = float(row.get("conversions") or 0)
        ctr        = round(clicks / impr, 4) if impr else 0.0
        cpl        = round(spend_usd / conv, 2) if conv else None

        campaign_id   = str(row.get("campaign_id") or "")
        campaign_name = row.get("campaign_name") or campaign_id
        account_id    = str(row.get("account_id") or "")

        rows.append({
            "date":            day,
            "channel":         channel,
            "account_id":      account_id,
            "campaign_id":     campaign_id,
            "campaign_name":   campaign_name,
            "status":          row.get("campaign_status"),
            "objective":       row.get("objective"),
            "spend":           round(spend_usd, 2),
            "impressions":     impr,
            "clicks":          clicks,
            "ctr":             ctr,
            "leads":           int(conv),
            "conversions":     conv,
            "cpl":             cpl,
            "currency":        "USD",
            "spend_native":    round(spend_nat, 2),
            "currency_native": native_cur,
            "updated_at":      now,
        })

    if not rows:
        print("[windsor-bq] No valid rows to write")
        return 0

    # Group summary before writing
    by_channel: dict[str, int] = {}
    for r in rows:
        by_channel[r["channel"]] = by_channel.get(r["channel"], 0) + 1
    for ch, n in sorted(by_channel.items()):
        print(f"[windsor-bq]   {ch}: {n} rows")

    written = upsert_rows("campaigns_daily", rows,
                          key_fields=["date", "channel", "campaign_id"])
    print(f"[windsor-bq] {written} rows upserted to campaigns_daily")
    return written


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"Windsor BQ complete: {n} rows")
