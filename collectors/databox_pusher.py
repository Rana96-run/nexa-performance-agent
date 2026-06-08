"""
collectors/databox_pusher.py

Pushes spend / CPL / CPQL from BigQuery to Databox REST API.

One unified dataset, four grains. Use the `grain` dimension in Databox
widgets to filter to the desired level.

  grain=campaign    → campaign level       → lead_utm_campaign
  grain=adset       → adset/adgroup/adsquad/asset_group level → lead_utm_audience
                       (Meta adsets, Google adgroups + PMax asset groups,
                        Snapchat adsquads, TikTok adgroups — all via utm_audience)
  grain=ad          → ad/creative level    → lead_utm_content
  grain=keyword     → keyword level        → lead_utm_term  (Google + Microsoft only)

Dataset:
  "Qoyod Spend - All Grains"  →  739cde4e-3ba5-4ba9-98e8-701fa33111b7
  Data source: 4983171 "Qoyod BQ"  (account 756469, Mohammad Irsheid's company)

Auth: x-api-key header with DATABOX_TOKEN (pak_ personal API key).
Max 100 records per request per Databox docs.

Superseded per-grain dataset IDs (kept for reference / rollback):
  campaign    → 6dbbd9df-4554-4c58-9fe4-9009c43e6e06
  adset       → eec43dfb-fb3b-4f4c-8b71-e39bc9704ebd
  ad          → 73151fba-f7c7-4aaf-a695-2df41ad34833
  keyword     → 8e9dac81-8119-4729-8b93-c31b42381ed3
  asset_group → 4d1cff88-24e3-40c4-8078-a9330de5472e  (merged into adset grain)
"""
import os
import json
import time
import math
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import date, timedelta
try:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATABOX_TOKEN = os.getenv("DATABOX_TOKEN", "")
_BASE         = "https://api.databox.com"
_DATASET_ID   = "739cde4e-3ba5-4ba9-98e8-701fa33111b7"   # "Qoyod Spend - All Grains"
_BATCH        = 100     # Databox max per ingestion request
_BATCH_DELAY  = 1.2     # seconds between batches
_TIMEOUT      = 60      # seconds — SSL handshake + response

# Databox WAF/quota limit is ~85 batches per session.
# Large backfills chunk into ≤30-day windows (each window stays under quota).
_CHUNK_DAYS  = 30
_CHUNK_SLEEP = 3.0      # seconds between chunks

ALL_GRAINS = ["campaign", "adset", "ad", "keyword"]
# Note: asset_group is NOT a separate grain — PMax asset groups appear in the
# adset grain (v_adset_performance includes them via utm_audience).

# BQ channel slug → HubSpot qoyod_source / lead_utm_source label.
# Must match hubspot_leads_module_daily.qoyod_source exactly (case-sensitive).
# "Tiktok Ads" has lowercase 'i' — matches HubSpot property editor value.
_SOURCE_NAME = {
    "google_ads":    "Google Ads",
    "meta":          "Meta Ads",
    "snapchat":      "Snapchat Ads",
    "tiktok":        "Tiktok Ads",
    "microsoft_ads": "Microsoft Ads",
    "linkedin":      "LinkedIn Ads",
}

def _channel_to_source(channel: str) -> str:
    """Map BQ channel slug to HubSpot source label, case/space/underscore insensitive.

    Normalises the lookup key (lowercase, strip spaces + underscores) so that
    variants like 'Google_Ads', 'GOOGLE ADS', 'google ads' all resolve correctly.
    Falls back to the raw channel value if no match found.
    """
    if not channel:
        return channel
    # Build normalised lookup on first call (cached in closure)
    norm_map = {"".join(k.lower().split("_")).replace(" ", ""): v
                for k, v in _SOURCE_NAME.items()}
    key = "".join(channel.lower().split("_")).replace(" ", "")
    return norm_map.get(key, channel)


def _session() -> requests.Session:
    """Session with automatic retry on connection errors and 429."""
    s     = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=3,           # waits 3, 6, 12, 24, 48s
        status_forcelist=[429],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _headers():
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")
    return {
        "x-api-key":    DATABOX_TOKEN,
        "Accept":       "application/json",
        "Content-Type": "application/json; charset=utf-8",
    }


def _flush(records: list) -> int:
    """Send all records to the unified dataset in ≤100-item batches.

    - Raw UTF-8 bytes (ensure_ascii=False) bypasses WAF that blocks \\uXXXX.
    - Session with urllib3 Retry handles connection drops and 429 automatically.
    """
    if not records:
        return 0
    url  = f"{_BASE}/v1/datasets/{_DATASET_ID}/data"
    sess = _session()
    sent = 0
    for i in range(0, len(records), _BATCH):
        batch      = records[i : i + _BATCH]
        body_bytes = json.dumps({"records": batch}, ensure_ascii=False).encode("utf-8")
        resp       = sess.post(url, headers=_headers(), data=body_bytes, timeout=_TIMEOUT)
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


# ── Per-grain BQ queries ──────────────────────────────────────────────────────

def _grain_sql(grain: str, since: str, until: str, proj: str, ds: str) -> str:
    """Return BQ SQL for one grain over [since, until)."""
    if grain == "campaign":
        return f"""
            SELECT date, channel,
                   CAST(campaign_id AS STRING) AS campaign_id,
                   campaign_name,
                   spend, impressions, clicks,
                   cpl, cpql, qual_rate_pct, ctr_pct
            FROM `{proj}.{ds}.paid_channel_campaign_daily`
            WHERE date >= '{since}' AND date < '{until}'
            ORDER BY date, channel, campaign_id
        """
    if grain == "adset":
        return f"""
            SELECT date, channel,
                   CAST(campaign_id AS STRING) AS campaign_id,
                   utm_campaign  AS campaign_name,
                   CAST(adset_id AS STRING)   AS adset_id,
                   utm_audience  AS adset_name,
                   spend, impressions, clicks,
                   CPL AS cpl, CPQL AS cpql,
                   ROUND(IFNULL(qual_rate,0)*100,2) AS qual_rate_pct
            FROM `{proj}.{ds}.v_adset_performance`
            WHERE date >= '{since}' AND date < '{until}'
            ORDER BY date, channel, campaign_id, adset_id
        """
    if grain == "ad":
        return f"""
            SELECT date, channel,
                   CAST(campaign_id AS STRING) AS campaign_id,
                   utm_campaign  AS campaign_name,
                   CAST(adset_id AS STRING)   AS adset_id,
                   utm_audience  AS adset_name,
                   CAST(ad_id AS STRING)      AS ad_id,
                   utm_content   AS ad_name,
                   creative_type,
                   spend, impressions, clicks,
                   CPL AS cpl, CPQL AS cpql,
                   ROUND(IFNULL(qual_rate,0)*100,2) AS qual_rate_pct
            FROM `{proj}.{ds}.v_ad_performance`
            WHERE date >= '{since}' AND date < '{until}'
            ORDER BY date, channel, campaign_id, ad_id
        """
    if grain == "keyword":
        return f"""
            SELECT date, channel,
                   utm_campaign AS campaign_name,
                   utm_audience AS adset_name,
                   utm_term     AS keyword,
                   match_type,
                   quality_score,
                   spend, impressions, clicks,
                   ROUND(ctr*100,4) AS ctr_pct,
                   CPL AS cpl, CPQL AS cpql
            FROM `{proj}.{ds}.v_keyword_performance`
            WHERE date >= '{since}' AND date < '{until}'
            ORDER BY date, channel, utm_campaign, utm_term
        """
    raise ValueError(f"Unknown grain: {grain}  (valid: {ALL_GRAINS})")


def _build_records(grain: str, rows) -> list:
    """Convert BQ rows to Databox record dicts with grain + source fields.

    Every record carries:
      channel  — BQ internal slug (google_ads, meta, snapchat …)
      source   — HubSpot-compatible label (Google Ads, Meta Ads, Snapchat Ads …)
                 matches qoyod_source / lead_utm_source in hubspot_leads_module_daily
      grain    — campaign | adset | ad | keyword
    """
    records = []
    for r in rows:
        base = {
            "date":    str(r.date),
            "channel": r.channel,
            "source":  _channel_to_source(r.channel),   # HubSpot-compatible label
            "grain":   grain,
        }

        if grain == "campaign":
            rec = _row(base,
                campaign_id  = r.campaign_id or None,
                campaign     = r.campaign_name or None,
                spend        = _v(r.spend),
                impressions  = _v(r.impressions),
                clicks       = _v(r.clicks),
                cpl          = _v(r.cpl),
                cpql         = _v(r.cpql),
                qual_rate_pct= _v(r.qual_rate_pct),
                ctr_pct      = _v(r.ctr_pct),
            )

        elif grain == "adset":
            rec = _row(base,
                campaign_id  = r.campaign_id or None,
                campaign     = r.campaign_name or None,
                adset_id     = r.adset_id or None,
                adset        = r.adset_name or None,
                spend        = _v(r.spend),
                impressions  = _v(r.impressions),
                clicks       = _v(r.clicks),
                cpl          = _v(r.cpl),
                cpql         = _v(r.cpql),
                qual_rate_pct= _v(r.qual_rate_pct),
            )

        elif grain == "ad":
            rec = _row(base,
                campaign_id  = r.campaign_id or None,
                campaign     = r.campaign_name or None,
                adset_id     = r.adset_id or None,
                adset        = r.adset_name or None,
                ad_id        = r.ad_id or None,
                ad           = r.ad_name or None,
                creative_type= r.creative_type or None,
                spend        = _v(r.spend),
                impressions  = _v(r.impressions),
                clicks       = _v(r.clicks),
                cpl          = _v(r.cpl),
                cpql         = _v(r.cpql),
                qual_rate_pct= _v(r.qual_rate_pct),
            )

        elif grain == "keyword":
            # Keywords have no numeric IDs — attribution is text-based via utm_term
            rec = _row(base,
                campaign     = r.campaign_name or None,
                adset        = r.adset_name or None,
                keyword      = r.keyword or None,
                match_type   = r.match_type or None,
                quality_score= _v(r.quality_score),
                spend        = _v(r.spend),
                impressions  = _v(r.impressions),
                clicks       = _v(r.clicks),
                ctr_pct      = _v(r.ctr_pct),
                cpl          = _v(r.cpl),
                cpql         = _v(r.cpql),
            )

        else:
            continue

        records.append(rec)
    return records


def _push_grain_window(grain: str, since: str, until: str) -> int:
    """Push one grain for one date window [since, until)."""
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client  = get_client()
    sql     = _grain_sql(grain, since, until, PROJECT_ID, DATASET)
    rows    = client.query(sql).result()
    records = _build_records(grain, rows)
    return _flush(records)


# ── Public entry point ────────────────────────────────────────────────────────

def run_push(days: int = 7, grains: list = None) -> int:
    """
    Push spend data to Databox unified dataset.

    For daily incremental runs (days ≤ _CHUNK_DAYS) runs straight through.
    For large backfills (days > _CHUNK_DAYS) splits into 30-day windows so
    each window stays under Databox's per-session batch quota.

    Args:
        days:   Lookback window in days. Default 7.
        grains: Grain list. Default = all five grains.
                Pass a single grain for per-grain backfill:
                  python collectors/databox_pusher.py 365 campaign

    Returns:
        Total records pushed across all grains and chunks.
    """
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")

    targets = grains or ALL_GRAINS
    today   = date.today()
    total   = 0

    if days <= _CHUNK_DAYS:
        # Small window — single pass
        since = (today - timedelta(days=days)).isoformat()
        until = today.isoformat()
        for name in targets:
            try:
                n = _push_grain_window(name, since, until)
                total += n
                print(f"[databox] {name}: {n:,} records pushed")
            except Exception as e:
                print(f"[databox] {name} FAILED: {e}")
                raise
    else:
        # Large backfill — chunk into _CHUNK_DAYS windows, newest-first
        windows = []
        end = today
        remaining = days
        while remaining > 0:
            chunk = min(remaining, _CHUNK_DAYS)
            start = end - timedelta(days=chunk)
            windows.append((start.isoformat(), end.isoformat()))
            end = start
            remaining -= chunk

        for name in targets:
            n_g = 0
            for i, (w_since, w_until) in enumerate(windows):
                try:
                    n = _push_grain_window(name, w_since, w_until)
                    n_g  += n
                    total += n
                    print(f"[databox] {name} chunk {i+1}/{len(windows)}"
                          f" ({w_since} to {w_until}): {n:,} records")
                    if i + 1 < len(windows):
                        time.sleep(_CHUNK_SLEEP)
                except Exception as e:
                    print(f"[databox] {name} chunk {i+1} ({w_since}→{w_until}) FAILED: {e}")
                    raise
            print(f"[databox] {name} total: {n_g:,} records")

    print(f"[databox] grand total: {total:,} records")
    return total


if __name__ == "__main__":
    import sys
    # Usage: python collectors/databox_pusher.py [days] [grain]
    # e.g.:  python collectors/databox_pusher.py 7
    #        python collectors/databox_pusher.py 365 campaign
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    g = [sys.argv[2]] if len(sys.argv) > 2 else None
    run_push(days=d, grains=g)
