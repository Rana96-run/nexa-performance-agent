"""
collectors/databox_pusher.py

Pushes spend (+ impressions, clicks) to Databox broken down by the same
attribution names HubSpot uses — so Databox can join them to your existing
channel-level CPL/CPQL/won-amount custom metrics.

Grains: campaign, adset, ad, keyword, asset_group (PMax).

Attribution logic is pre-computed in BQ views (ID-sync for Meta/Snap/TikTok,
UTM name-match for Google/LinkedIn/Microsoft). Names here match
lead_utm_campaign / lead_utm_audience / lead_utm_content in HubSpot.

Databox Push API:
  POST https://push.databox.com/
  Authorization: Token <DATABOX_TOKEN>
  Body: {"data": [{$key, $value, date, ...attrs}]}
"""
import os
import time
import math
import requests
from datetime import date, timedelta

DATABOX_TOKEN = os.getenv("DATABOX_TOKEN", "")
_ENDPOINT     = "https://push.databox.com/"
_BATCH        = 1000
_BATCH_DELAY  = 0.4


def _push_batch(points: list) -> None:
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")
    resp = requests.post(
        _ENDPOINT,
        json={"data": points},
        headers={
            "Authorization": f"Token {DATABOX_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.databox.v2+json",
        },
        timeout=30,
    )
    resp.raise_for_status()


def _flush(points: list) -> int:
    sent = 0
    for i in range(0, len(points), _BATCH):
        batch = points[i : i + _BATCH]
        _push_batch(batch)
        sent += len(batch)
        if i + _BATCH < len(points):
            time.sleep(_BATCH_DELAY)
    return sent


def _v(val):
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _add(pts: list, key: str, value, date_str: str, **attrs) -> None:
    v = _v(value)
    if v is None:
        return
    pts.append({"$key": key, "$value": v, "date": f"{date_str}T00:00:00", **attrs})


# ── Campaign grain ────────────────────────────────────────────────────────────
# Source: paid_channel_campaign_daily
# campaign_name here is normalized (latest name per campaign_id) and matches
# lead_utm_campaign in HubSpot.

def _push_campaign(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               campaign_name,
               spend, impressions, clicks
        FROM `{PROJECT_ID}.{DATASET}.paid_channel_campaign_daily`
        WHERE date >= '{since}'
        ORDER BY date, channel, campaign_id
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":       "campaign",
            "channel":     r.channel,
            "campaign_id": r.campaign_id or "",
            "campaign":    r.campaign_name or "",
        }
        _add(pts, "spend",       r.spend,       ds, **base)
        _add(pts, "impressions", r.impressions, ds, **base)
        _add(pts, "clicks",      r.clicks,      ds, **base)

    return _flush(pts)


# ── Adset / adgroup grain ─────────────────────────────────────────────────────
# Source: v_adset_performance
# utm_audience matches lead_utm_audience in HubSpot.

def _push_adset(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               utm_campaign   AS campaign,
               CAST(adset_id  AS STRING)   AS adset_id,
               utm_audience   AS adset,
               spend, impressions, clicks
        FROM `{PROJECT_ID}.{DATASET}.v_adset_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, campaign_id, adset_id
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":       "adset",
            "channel":     r.channel,
            "campaign_id": r.campaign_id or "",
            "campaign":    r.campaign or "",
            "adset_id":    r.adset_id or "",
            "adset":       r.adset or "",
        }
        _add(pts, "spend",       r.spend,       ds, **base)
        _add(pts, "impressions", r.impressions, ds, **base)
        _add(pts, "clicks",      r.clicks,      ds, **base)

    return _flush(pts)


# ── Ad / creative grain ───────────────────────────────────────────────────────
# Source: v_ad_performance
# utm_content matches lead_utm_content in HubSpot.

def _push_ad(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(platform_campaign_id AS STRING) AS campaign_id,
               utm_campaign              AS campaign,
               CAST(platform_adset_id   AS STRING)  AS adset_id,
               utm_audience              AS adset,
               CAST(platform_ad_id      AS STRING)  AS ad_id,
               utm_content               AS ad,
               creative_type,
               spend, impressions, clicks
        FROM `{PROJECT_ID}.{DATASET}.v_ad_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, platform_campaign_id, platform_ad_id
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":         "ad",
            "channel":       r.channel,
            "campaign_id":   r.campaign_id or "",
            "campaign":      r.campaign or "",
            "adset_id":      r.adset_id or "",
            "adset":         r.adset or "",
            "ad_id":         r.ad_id or "",
            "ad":            r.ad or "",
            "creative_type": r.creative_type or "",
        }
        _add(pts, "spend",       r.spend,       ds, **base)
        _add(pts, "impressions", r.impressions, ds, **base)
        _add(pts, "clicks",      r.clicks,      ds, **base)

    return _flush(pts)


# ── Keyword grain (Google Ads + Microsoft Ads) ────────────────────────────────
# Source: v_keyword_performance
# utm_term matches lead_utm_term in HubSpot.

def _push_keyword(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               utm_campaign  AS campaign,
               utm_audience  AS adgroup,
               utm_term      AS keyword,
               match_type,
               spend, impressions, clicks,
               quality_score
        FROM `{PROJECT_ID}.{DATASET}.v_keyword_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, utm_campaign, utm_term
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":      "keyword",
            "channel":    r.channel,
            "campaign":   r.campaign or "",
            "adgroup":    r.adgroup or "",
            "keyword":    r.keyword or "",
            "match_type": r.match_type or "",
        }
        _add(pts, "spend",         r.spend,         ds, **base)
        _add(pts, "impressions",   r.impressions,   ds, **base)
        _add(pts, "clicks",        r.clicks,        ds, **base)
        _add(pts, "quality_score", r.quality_score, ds, **base)

    return _flush(pts)


# ── Asset group grain (Google PMax) ───────────────────────────────────────────
# Source: google_ads_pmax_asset_groups (if populated)

def _push_asset_group(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()

    # Check table exists before querying — PMax may not be set up yet
    try:
        rows = client.query(f"""
            SELECT date, channel,
                   CAST(campaign_id   AS STRING) AS campaign_id,
                   campaign_name,
                   CAST(asset_group_id AS STRING) AS asset_group_id,
                   asset_group_name,
                   spend, impressions, clicks
            FROM `{PROJECT_ID}.{DATASET}.google_ads_pmax_asset_groups`
            WHERE date >= '{since}'
            ORDER BY date, campaign_id, asset_group_id
        """).result()
    except Exception:
        return 0   # table not ready yet — skip silently

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":           "asset_group",
            "channel":         r.channel,
            "campaign_id":     r.campaign_id or "",
            "campaign":        r.campaign_name or "",
            "asset_group_id":  r.asset_group_id or "",
            "asset_group":     r.asset_group_name or "",
        }
        _add(pts, "spend",       r.spend,       ds, **base)
        _add(pts, "impressions", r.impressions, ds, **base)
        _add(pts, "clicks",      r.clicks,      ds, **base)

    return _flush(pts)


# ── Public entry point ────────────────────────────────────────────────────────

def run_push(days: int = 7) -> int:
    """
    Push spend / impressions / clicks at 5 sub-channel grains to Databox.

    Args:
        days: Lookback window. Default 7. Use 365 for one-time backfill.

    Returns:
        Total data points pushed.
    """
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")

    total  = 0
    grains = [
        ("campaign",    _push_campaign),
        ("adset",       _push_adset),
        ("ad",          _push_ad),
        ("keyword",     _push_keyword),
        ("asset_group", _push_asset_group),
    ]
    for name, fn in grains:
        try:
            n = fn(days)
            total += n
            print(f"[databox] {name}: {n:,} data points pushed")
        except Exception as e:
            print(f"[databox] {name} FAILED: {e}")
            raise

    print(f"[databox] total: {total:,} data points across {len(grains)} grains")
    return total


if __name__ == "__main__":
    import sys
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    run_push(days=d)
