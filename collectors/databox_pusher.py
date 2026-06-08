"""
collectors/databox_pusher.py

Pushes merged performance metrics from BigQuery to Databox via the Push API.

Five grains pushed — all attribution logic is pre-computed in BQ views:
  1. channel         — paid_channel_daily
  2. campaign        — paid_channel_campaign_daily
  3. adset/adgroup   — v_adset_performance
  4. ad/creative     — v_ad_performance
  5. keyword         — v_keyword_performance

Databox Push API:
  POST https://push.databox.com/
  Authorization: Token <DATABOX_TOKEN>
  Body: {"data": [{$key, $value, date, ...attrs}, ...]}

Each metric is pushed as a separate data point with a `grain` attribute so
Databox dashboards can filter to one grain at a time (avoids double-counting
spend when multiple grains carry the same metric key).

Idempotent: Databox replaces existing values for the same (date, $key, attrs)
combination on each push, so running with a lookback window is safe.
"""
import os
import time
import math
import requests
from datetime import date, timedelta

DATABOX_TOKEN = os.getenv("DATABOX_TOKEN", "")
_ENDPOINT     = "https://push.databox.com/"
_BATCH        = 1000      # Databox max per request
_BATCH_DELAY  = 0.4       # seconds between batches — polite pacing


def _push_batch(points: list) -> None:
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set — add it to Railway env vars")
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
    """Send all points in ≤1000-item batches. Returns count sent."""
    sent = 0
    for i in range(0, len(points), _BATCH):
        batch = points[i : i + _BATCH]
        _push_batch(batch)
        sent += len(batch)
        if i + _BATCH < len(points):
            time.sleep(_BATCH_DELAY)
    return sent


def _v(val):
    """Return float or None; discard NaN/Inf/None so Databox doesn't choke."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _dp(key: str, value, date_str: str, **attrs):
    """Build one data point dict, or None when value is empty/zero."""
    v = _v(value)
    if v is None:
        return None
    return {"$key": key, "$value": v, "date": f"{date_str}T00:00:00", **attrs}


def _add(pts: list, key: str, value, date_str: str, **attrs) -> None:
    """Append a data point if value is non-null."""
    dp = _dp(key, value, date_str, **attrs)
    if dp:
        pts.append(dp)


# ── 1. Channel grain ────────────────────────────────────────────────────────

def _push_channel(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               spend, impressions, clicks,
               leads_total  AS leads,
               qualified    AS sqls,
               disqualified,
               cpl, cpql, qual_rate_pct,
               roas, new_biz_roas,
               new_biz_deals_won,
               new_biz_revenue_won
        FROM `{PROJECT_ID}.{DATASET}.paid_channel_daily`
        WHERE date >= '{since}'
        ORDER BY date, channel
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {"grain": "channel", "channel": r.channel}
        for key, val in [
            ("spend",               r.spend),
            ("impressions",         r.impressions),
            ("clicks",              r.clicks),
            ("leads",               r.leads),
            ("sqls",                r.sqls),
            ("disqualified",        r.disqualified),
            ("cpl",                 r.cpl),
            ("cpql",                r.cpql),
            ("qual_rate_pct",       r.qual_rate_pct),
            ("roas",                r.roas),
            ("new_biz_roas",        r.new_biz_roas),
            ("new_biz_deals_won",   r.new_biz_deals_won),
            ("new_biz_revenue_won", r.new_biz_revenue_won),
        ]:
            _add(pts, key, val, ds, **base)

    return _flush(pts)


# ── 2. Campaign grain ────────────────────────────────────────────────────────

def _push_campaign(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               campaign_name,
               spend, impressions, clicks,
               leads,
               qualified    AS sqls,
               disqualified,
               cpl, cpql,
               qual_rate_pct, ctr_pct, cvr_pct,
               new_biz_roas,
               new_biz_deals_won,
               new_biz_revenue_won
        FROM `{PROJECT_ID}.{DATASET}.paid_channel_campaign_daily`
        WHERE date >= '{since}'
        ORDER BY date, channel, campaign_id
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":         "campaign",
            "channel":       r.channel,
            "campaign_id":   r.campaign_id or "",
            "campaign":      r.campaign_name or "",
        }
        for key, val in [
            ("spend",               r.spend),
            ("impressions",         r.impressions),
            ("clicks",              r.clicks),
            ("leads",               r.leads),
            ("sqls",                r.sqls),
            ("disqualified",        r.disqualified),
            ("cpl",                 r.cpl),
            ("cpql",                r.cpql),
            ("qual_rate_pct",       r.qual_rate_pct),
            ("ctr_pct",             r.ctr_pct),
            ("cvr_pct",             r.cvr_pct),
            ("new_biz_roas",        r.new_biz_roas),
            ("new_biz_deals_won",   r.new_biz_deals_won),
            ("new_biz_revenue_won", r.new_biz_revenue_won),
        ]:
            _add(pts, key, val, ds, **base)

    return _flush(pts)


# ── 3. Adset / adgroup grain ─────────────────────────────────────────────────

def _push_adset(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(campaign_id AS STRING) AS campaign_id,
               utm_campaign      AS campaign,
               CAST(adset_id    AS STRING) AS adset_id,
               utm_audience      AS adset_name,
               spend, impressions, clicks,
               leads,
               leads_qualified   AS sqls,
               leads_disqualified AS disqualified,
               CPL               AS cpl,
               CPQL              AS cpql,
               ROUND(IFNULL(qual_rate, 0) * 100, 2) AS qual_rate_pct,
               ROUND(IFNULL(disq_rate,  0) * 100, 2) AS disq_rate_pct,
               new_biz_roas,
               new_biz_deals_won,
               new_biz_revenue_won
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
            "adset":       r.adset_name or "",
        }
        for key, val in [
            ("spend",               r.spend),
            ("impressions",         r.impressions),
            ("clicks",              r.clicks),
            ("leads",               r.leads),
            ("sqls",                r.sqls),
            ("disqualified",        r.disqualified),
            ("cpl",                 r.cpl),
            ("cpql",                r.cpql),
            ("qual_rate_pct",       r.qual_rate_pct),
            ("disq_rate_pct",       r.disq_rate_pct),
            ("new_biz_roas",        r.new_biz_roas),
            ("new_biz_deals_won",   r.new_biz_deals_won),
            ("new_biz_revenue_won", r.new_biz_revenue_won),
        ]:
            _add(pts, key, val, ds, **base)

    return _flush(pts)


# ── 4. Ad / creative grain ───────────────────────────────────────────────────

def _push_ad(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               CAST(platform_campaign_id AS STRING) AS campaign_id,
               utm_campaign          AS campaign,
               CAST(platform_adset_id AS STRING)   AS adset_id,
               utm_audience          AS adset_name,
               CAST(platform_ad_id   AS STRING)    AS ad_id,
               utm_content           AS ad_name,
               creative_type,
               spend, impressions, clicks,
               leads,
               leads_qualified       AS sqls,
               leads_disqualified    AS disqualified,
               CPL                   AS cpl,
               CPQL                  AS cpql,
               ROUND(IFNULL(qual_rate, 0) * 100, 2) AS qual_rate_pct,
               ROUND(IFNULL(disq_rate,  0) * 100, 2) AS disq_rate_pct,
               new_biz_roas,
               new_biz_deals_won,
               new_biz_revenue_won
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
            "adset":         r.adset_name or "",
            "ad_id":         r.ad_id or "",
            "ad":            r.ad_name or "",
            "creative_type": r.creative_type or "",
        }
        for key, val in [
            ("spend",               r.spend),
            ("impressions",         r.impressions),
            ("clicks",              r.clicks),
            ("leads",               r.leads),
            ("sqls",                r.sqls),
            ("disqualified",        r.disqualified),
            ("cpl",                 r.cpl),
            ("cpql",                r.cpql),
            ("qual_rate_pct",       r.qual_rate_pct),
            ("disq_rate_pct",       r.disq_rate_pct),
            ("new_biz_roas",        r.new_biz_roas),
            ("new_biz_deals_won",   r.new_biz_deals_won),
            ("new_biz_revenue_won", r.new_biz_revenue_won),
        ]:
            _add(pts, key, val, ds, **base)

    return _flush(pts)


# ── 5. Keyword grain (Google Ads + Microsoft Ads only) ───────────────────────

def _push_keyword(days: int) -> int:
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    since  = (date.today() - timedelta(days=days)).isoformat()
    rows = client.query(f"""
        SELECT date, channel,
               utm_campaign     AS campaign,
               utm_audience     AS adgroup,
               utm_term         AS keyword,
               match_type,
               quality_score,
               spend, impressions, clicks,
               ROUND(ctr * 100, 4) AS ctr_pct,
               leads,
               leads_qualified  AS sqls,
               leads_disqualified AS disqualified,
               CPL              AS cpl,
               CPQL             AS cpql,
               ROAS             AS roas,
               ROUND(IFNULL(qual_rate, 0) * 100, 2) AS qual_rate_pct,
               revenue_won
        FROM `{PROJECT_ID}.{DATASET}.v_keyword_performance`
        WHERE date >= '{since}'
        ORDER BY date, channel, utm_campaign, utm_term
    """).result()

    pts = []
    for r in rows:
        ds   = str(r.date)
        base = {
            "grain":       "keyword",
            "channel":     r.channel,
            "campaign":    r.campaign or "",
            "adgroup":     r.adgroup or "",
            "keyword":     r.keyword or "",
            "match_type":  r.match_type or "",
        }
        for key, val in [
            ("spend",         r.spend),
            ("impressions",   r.impressions),
            ("clicks",        r.clicks),
            ("ctr_pct",       r.ctr_pct),
            ("leads",         r.leads),
            ("sqls",          r.sqls),
            ("disqualified",  r.disqualified),
            ("cpl",           r.cpl),
            ("cpql",          r.cpql),
            ("roas",          r.roas),
            ("qual_rate_pct", r.qual_rate_pct),
            ("quality_score", r.quality_score),
            ("revenue_won",   r.revenue_won),
        ]:
            _add(pts, key, val, ds, **base)

    return _flush(pts)


# ── Public entry point ────────────────────────────────────────────────────────

def run_push(days: int = 7) -> int:
    """
    Push all 5 grains to Databox for the last `days` days.

    Args:
        days: Lookback window. Default 7 for daily incremental. Use 365 for
              a one-time historical backfill.

    Returns:
        Total data points pushed across all grains.
    """
    if not DATABOX_TOKEN:
        raise RuntimeError("DATABOX_TOKEN not set")

    total = 0
    grains = [
        ("channel",  _push_channel),
        ("campaign", _push_campaign),
        ("adset",    _push_adset),
        ("ad",       _push_ad),
        ("keyword",  _push_keyword),
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
