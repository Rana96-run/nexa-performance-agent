"""
collectors/databox_pusher.py

Pushes spend / impressions / clicks from BigQuery to Databox REST API.

Uses the new Databox REST API (api.databox.com) with pre-created datasets,
one per grain. Attribution names match HubSpot UTM fields so Databox can
join them to existing channel-level CPL/CPQL/won-amount custom metrics.

Grains → Dataset IDs (created 2026-06-08 under data source 4983171 "Qoyod BQ"):
  campaign    → 6dbbd9df-4554-4c58-9fe4-9009c43e6e06
  adset       → eec43dfb-fb3b-4f4c-8b71-e39bc9704ebd
  ad          → 73151fba-f7c7-4aaf-a695-2df41ad34833
  keyword     → 8e9dac81-8119-4729-8b93-c31b42381ed3
  asset_group → 4d1cff88-24e3-40c4-8078-a9330de5472e

Auth: x-api-key header with DATABOX_TOKEN (pak_ personal API key).
Max 100 records per request per Databox docs.
"""
import os
import json
import time
import math
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import date, timedelta

DATABOX_TOKEN = os.getenv("DATABOX_TOKEN", "")
_BASE         = "https://api.databox.com"
_BATCH        = 100      # Databox max per ingestion request
_BATCH_DELAY  = 1.2      # pause between batches
_TIMEOUT      = 60       # seconds — SSL handshake + response


def _session() -> requests.Session:
    """Session with automatic retry on connection errors and 429."""
    s       = requests.Session()
    retry   = Retry(
        total=5,
        backoff_factor=3,          # waits 3, 6, 12, 24, 48s
        status_forcelist=[429],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    return s

# Dataset IDs — created 2026-06-08 under data source 4983171 "Qoyod BQ"
_DATASET = {
    "campaign":    "6dbbd9df-4554-4c58-9fe4-9009c43e6e06",
    "adset":       "eec43dfb-fb3b-4f4c-8b71-e39bc9704ebd",
    "ad":          "73151fba-f7c7-4aaf-a695-2df41ad34833",
    "keyword":     "8e9dac81-8119-4729-8b93-c31b42381ed3",
    "asset_group": "4d1cff88-24e3-40c4-8078-a9330de5472e",
}


def _headers():
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")
    return {
        "x-api-key":    DATABOX_TOKEN,
        "Accept":       "application/json",
        "Content-Type": "application/json",
    }


def _flush(grain: str, records: list) -> int:
    """Send all records in ≤100-item batches.

    - Raw UTF-8 bytes (ensure_ascii=False) bypasses WAF that blocks \\uXXXX.
    - Session with urllib3 Retry handles connection drops and 429 automatically.
    """
    dataset_id = _DATASET[grain]
    url     = f"{_BASE}/v1/datasets/{dataset_id}/data"
    headers = {**_headers(), "Content-Type": "application/json; charset=utf-8"}
    sess    = _session()
    sent    = 0
    for i in range(0, len(records), _BATCH):
        batch      = records[i : i + _BATCH]
        body_bytes = json.dumps({"records": batch}, ensure_ascii=False).encode("utf-8")
        resp       = sess.post(url, headers=headers, data=body_bytes, timeout=_TIMEOUT)
        resp.raise_for_status()
        sent += len(batch)
        if i + _BATCH < len(records):
            time.sleep(_BATCH_DELAY)
    return sent


def _v(val):
    """Float or None — discard NaN/Inf."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _row(base: dict, **extra) -> dict:
    """Build a record dict, dropping None values."""
    rec = {**base, **extra}
    return {k: v for k, v in rec.items() if v is not None and v != ""}


# ── Campaign grain ────────────────────────────────────────────────────────────
# campaign_name is normalised (latest name per campaign_id via ANY_VALUE in BQ)
# and matches lead_utm_campaign in HubSpot.

def _push_campaign(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               campaign_name,
               spend, impressions, clicks,
               cpl, cpql, qual_rate_pct, ctr_pct
        FROM `{PROJECT_ID}.{DATASET}.paid_channel_campaign_daily`
        WHERE date >= '{since}'
        ORDER BY date, channel, campaign_id
    """).result()

    records = []
    for r in rows:
        records.append(_row(
            {"date": str(r.date), "channel": r.channel},
            campaign_id   = r.campaign_id or None,
            campaign      = r.campaign_name or None,
            spend         = _v(r.spend),
            impressions   = _v(r.impressions),
            clicks        = _v(r.clicks),
            cpl           = _v(r.cpl),
            cpql          = _v(r.cpql),
            qual_rate_pct = _v(r.qual_rate_pct),
            ctr_pct       = _v(r.ctr_pct),
        ))
    return _flush("campaign", records)


# ── Adset / adgroup grain ─────────────────────────────────────────────────────
# utm_audience matches lead_utm_audience in HubSpot.

def _push_adset(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               utm_campaign  AS campaign,
               CAST(adset_id AS STRING)   AS adset_id,
               utm_audience  AS adset,
               spend, impressions, clicks,
               CPL AS cpl, CPQL AS cpql,
               ROUND(IFNULL(qual_rate,0)*100,2) AS qual_rate_pct
        FROM `{PROJECT_ID}.{DATASET}.v_adset_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, campaign_id, adset_id
    """).result()

    records = []
    for r in rows:
        records.append(_row(
            {"date": str(r.date), "channel": r.channel},
            campaign_id   = r.campaign_id or None,
            campaign      = r.campaign or None,
            adset_id      = r.adset_id or None,
            adset         = r.adset or None,
            spend         = _v(r.spend),
            impressions   = _v(r.impressions),
            clicks        = _v(r.clicks),
            cpl           = _v(r.cpl),
            cpql          = _v(r.cpql),
            qual_rate_pct = _v(r.qual_rate_pct),
        ))
    return _flush("adset", records)


# ── Ad / creative grain ───────────────────────────────────────────────────────
# utm_content matches lead_utm_content in HubSpot.

def _push_ad(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               campaign_id,
               utm_campaign AS campaign,
               adset_id,
               utm_audience AS adset,
               ad_id,
               utm_content  AS ad,
               creative_type,
               spend, impressions, clicks,
               CPL AS cpl, CPQL AS cpql,
               ROUND(IFNULL(qual_rate,0)*100,2) AS qual_rate_pct
        FROM `{PROJECT_ID}.{DATASET}.v_ad_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, campaign_id, ad_id
    """).result()

    records = []
    for r in rows:
        records.append(_row(
            {"date": str(r.date), "channel": r.channel},
            campaign_id   = r.campaign_id or None,
            campaign      = r.campaign or None,
            adset_id      = r.adset_id or None,
            adset         = r.adset or None,
            ad_id         = r.ad_id or None,
            ad            = r.ad or None,
            creative_type = r.creative_type or None,
            spend         = _v(r.spend),
            impressions   = _v(r.impressions),
            clicks        = _v(r.clicks),
            cpl           = _v(r.cpl),
            cpql          = _v(r.cpql),
            qual_rate_pct = _v(r.qual_rate_pct),
        ))
    return _flush("ad", records)


# ── Keyword grain (Google Ads + Microsoft Ads) ────────────────────────────────
# utm_term matches lead_utm_term in HubSpot.

def _push_keyword(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               utm_campaign AS campaign,
               utm_audience AS adgroup,
               utm_term     AS keyword,
               match_type,
               quality_score,
               spend, impressions, clicks,
               ROUND(ctr*100,4) AS ctr_pct,
               CPL AS cpl, CPQL AS cpql
        FROM `{PROJECT_ID}.{DATASET}.v_keyword_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, utm_campaign, utm_term
    """).result()

    records = []
    for r in rows:
        records.append(_row(
            {"date": str(r.date), "channel": r.channel},
            campaign      = r.campaign or None,
            adgroup       = r.adgroup or None,
            keyword       = r.keyword or None,
            match_type    = r.match_type or None,
            quality_score = _v(r.quality_score),
            spend         = _v(r.spend),
            impressions   = _v(r.impressions),
            clicks        = _v(r.clicks),
            ctr_pct       = _v(r.ctr_pct),
            cpl           = _v(r.cpl),
            cpql          = _v(r.cpql),
        ))
    return _flush("keyword", records)


# ── Asset group grain (Google PMax) ───────────────────────────────────────────
# PMax asset group names flow into lead_utm_audience in HubSpot (same as regular
# adsets). v_adset_performance already captures them — we filter to PMax campaigns
# (campaign_name LIKE 'PMax_%') to build a dedicated asset-group grain in Databox.
# utm_audience = asset_group_name matches lead_utm_audience for attribution.

def _push_asset_group(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               utm_campaign  AS campaign,
               CAST(adset_id AS STRING)   AS asset_group_id,
               utm_audience  AS asset_group,
               spend, impressions, clicks,
               CPL AS cpl, CPQL AS cpql,
               ROUND(IFNULL(qual_rate, 0) * 100, 2) AS qual_rate_pct
        FROM `{PROJECT_ID}.{DATASET}.v_adset_performance`
        WHERE date >= '{since}'
          AND channel = 'google_ads'
          AND UPPER(utm_campaign) LIKE '%PMAX%'
        ORDER BY date, campaign_id, adset_id
    """).result()

    records = []
    for r in rows:
        records.append(_row(
            {"date": str(r.date), "channel": r.channel},
            campaign_id    = r.campaign_id or None,
            campaign       = r.campaign or None,
            asset_group_id = r.asset_group_id or None,
            asset_group    = r.asset_group or None,
            spend          = _v(r.spend),
            impressions    = _v(r.impressions),
            clicks         = _v(r.clicks),
            cpl            = _v(r.cpl),
            cpql           = _v(r.cpql),
            qual_rate_pct  = _v(r.qual_rate_pct),
        ))
    if not records:
        return 0
    return _flush("asset_group", records)


# ── Public entry point ────────────────────────────────────────────────────────

_GRAIN_FNS = {
    "campaign":    _push_campaign,
    "adset":       _push_adset,
    "ad":          _push_ad,
    "keyword":     _push_keyword,
    "asset_group": _push_asset_group,
}


def run_push(days: int = 7, grains: list = None) -> int:
    """
    Push spend data to Databox.

    Args:
        days:   Lookback window. Default 7. Use 365 for one-time backfill.
        grains: Which grains to push. Default = all. Use a single grain to
                work around Databox's per-session request quota (~85 batches).
                e.g. grains=["ad"] runs only the ad grain in a fresh session.

    Returns:
        Total records pushed.

    Backfill strategy (quota workaround):
        Run each grain separately:
          python collectors/databox_pusher.py 365 campaign
          python collectors/databox_pusher.py 365 adset
          python collectors/databox_pusher.py 365 ad
          python collectors/databox_pusher.py 365 keyword
          python collectors/databox_pusher.py 365 asset_group
    """
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")

    targets = grains or list(_GRAIN_FNS.keys())
    total   = 0
    for name in targets:
        fn = _GRAIN_FNS[name]
        try:
            n = fn(days)
            total += n
            print(f"[databox] {name}: {n:,} records pushed")
        except Exception as e:
            print(f"[databox] {name} FAILED: {e}")
            raise

    print(f"[databox] total: {total:,} records")
    return total


if __name__ == "__main__":
    import sys
    # Usage: python collectors/databox_pusher.py [days] [grain]
    # e.g.:  python collectors/databox_pusher.py 365 campaign
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    g = [sys.argv[2]] if len(sys.argv) > 2 else None
    run_push(days=d, grains=g)
