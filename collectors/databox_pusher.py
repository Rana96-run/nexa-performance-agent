"""
collectors/databox_pusher.py

Pushes spend / CPL / CPQL from BigQuery to Databox REST API.

One unified dataset, four grains. Use the `grain` dimension in Databox
widgets to filter to the desired level.

  grain=campaign  → utm_campaign  (lead_utm_campaign in HubSpot)
  grain=adset     → utm_audience  (Meta adsets, Google adgroups + PMax asset groups,
                                   Snapchat adsquads, TikTok adgroups — all via utm_audience)
  grain=ad        → utm_content   (lead_utm_content in HubSpot)
  grain=keyword   → utm_term      (lead_utm_term — Google + Microsoft only)

  Dimension naming follows UTM convention throughout:
    channel       = utm_source (BQ slug: google_ads, meta, snapchat …)
    qoyod_source  = HubSpot qoyod_source label (Google Ads, Meta Ads …)
    utm_campaign  = campaign name
    utm_audience  = adset / adgroup / adsquad / asset group name
    utm_content   = ad / creative name
    utm_term      = keyword text
    utm_medium    = form name / placement (from hubspot_leads_module_daily)

Datasets (active):
  "Qoyod Spend - Daily Spend"  →  199c5297  (channel-day grain, leads/sqls/cpl/cpql)
  "Qoyod Spend - All Grains"   →  6158be78  (4 grains unified; datetime date; minimal schema)
  Data source: 4983171 (PAK-linked "Qoyod BQ").
  Schema with NUMBER types defined at creation time — spend/impressions/clicks/leads/sqls/
  cpl/cpql/qual_rate_pct are NUMBER; date is DATETIME; grain/channel/utm_campaign are STRING.
  Use SUM for volume fields (spend/impressions/clicks/leads/sqls), AVG for ratio fields (cpl/cpql).

Auth: x-api-key header with DATABOX_TOKEN (pak_ personal API key).
Max 100 records per request per Databox docs.

Superseded dataset IDs (kept for rollback reference):
  v1 all-grains (wrong field names, all-string) → 739cde4e-3ba5-4ba9-98e8-701fa33111b7
  v2 all-grains (correct names, all-string)     → 9ec1816a-f7a6-4ba5-b898-349718242d96
  v3 all-grains (eff4621e — bad schema wrapper) → eff4621e-a0ef-4e93-bcf6-9c48f6e8d4ae
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
_DATASET_ID   = "6158be78"   # "Qoyod Spend - All Grains" (v4 — correct datetime type, minimal schema)
_BATCH        = 100     # Databox max per ingestion request
_BATCH_DELAY  = 0.5     # seconds between batches (0.5s = ~120 req/min, well within Databox limits)
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

# utm_medium values to EXCLUDE from the dominant-medium pick.
# These are generic channel-type labels, not meaningful form/placement names.
_MEDIUM_JUNK = (
    "ppc", "cpc", "paidsocial", "paid_social", "paid", "social",
    "none", "organic", "email", "-", ".", "__placement__",
    "unknown", "offline", "referral", "internal", "test_medium",
    "sms", "whatsapp", "twitter", "comment", "others",
)

def _medium_cte(since: str, until: str, proj: str, ds: str,
                join_cols: list, hs_cols: list) -> str:
    """Return a BQ CTE that picks the dominant (non-generic) utm_medium from
    hubspot_leads_module_daily for the given join keys.

    join_cols: column names in the outer query to join ON (e.g. ['channel','utm_campaign'])
    hs_cols:   matching column names in hubspot_leads_module_daily
               (e.g. ['hs_channel','lead_utm_campaign'])
    The CTE is named `medium_cte`.
    """
    junk_list = ", ".join(f"'{v}'" for v in _MEDIUM_JUNK)
    # group_cols: prefixed with 'hs.' for the inner medium_raw SELECT
    # partition_cols: bare column names for PARTITION BY (no table alias in that scope)
    group_cols     = ", ".join(f"hs.{c}" for c in hs_cols)
    partition_cols = ", ".join(hs_cols)
    return f"""
    medium_raw AS (
      -- Dominant non-generic utm_medium per join key from HubSpot
      SELECT
        hs.date,
        CASE hs.qoyod_source
          WHEN 'Google Ads'    THEN 'google_ads'
          WHEN 'Meta Ads'      THEN 'meta'
          WHEN 'Snapchat Ads'  THEN 'snapchat'
          WHEN 'Tiktok Ads'    THEN 'tiktok'
          WHEN 'Microsoft Ads' THEN 'microsoft_ads'
          WHEN 'LinkedIn Ads'  THEN 'linkedin'
          ELSE LOWER(REPLACE(hs.qoyod_source, ' ', '_'))
        END AS hs_channel,
        {group_cols},
        hs.lead_utm_medium,
        SUM(hs.leads_total) AS med_leads
      FROM `{proj}.{ds}.hubspot_leads_module_daily` hs
      WHERE hs.date >= '{since}' AND hs.date < '{until}'
        AND hs.lead_utm_medium IS NOT NULL
        AND LOWER(TRIM(hs.lead_utm_medium)) NOT IN ({junk_list})
      GROUP BY 1, 2, {", ".join(str(i+3) for i in range(len(hs_cols)))}, {len(hs_cols)+3}
    ),
    medium_cte AS (
      -- Pick the medium with the most leads per join key
      SELECT * EXCEPT(med_leads, row_n)
      FROM (
        SELECT *, ROW_NUMBER() OVER (
          PARTITION BY date, hs_channel, {partition_cols}
          ORDER BY med_leads DESC
        ) AS row_n
        FROM medium_raw
      )
      WHERE row_n = 1
    )"""


def _grain_sql(grain: str, since: str, until: str, proj: str, ds: str) -> str:
    """Return BQ SQL for one grain over [since, until), with utm_medium attached."""
    if grain == "campaign":
        med = _medium_cte(since, until, proj, ds,
                          join_cols=["campaign_name"],
                          hs_cols=["lead_utm_campaign"])
        return f"""
            WITH {med},
            camp AS (
              SELECT date, channel,
                     CAST(campaign_id AS STRING) AS campaign_id,
                     campaign_name,
                     spend, impressions, clicks,
                     cpl, cpql, qual_rate_pct, ctr_pct
              FROM `{proj}.{ds}.paid_channel_campaign_daily`
              WHERE date >= '{since}' AND date < '{until}'
            )
            SELECT c.*, m.lead_utm_medium AS utm_medium
            FROM camp c
            LEFT JOIN medium_cte m
              ON c.date = m.date AND c.channel = m.hs_channel
              AND LOWER(TRIM(c.campaign_name)) = LOWER(TRIM(m.lead_utm_campaign))
            ORDER BY c.date, c.channel, c.campaign_id
        """
    if grain == "adset":
        med = _medium_cte(since, until, proj, ds,
                          join_cols=["utm_campaign", "utm_audience"],
                          hs_cols=["lead_utm_campaign", "lead_utm_audience"])
        return f"""
            WITH {med},
            adset AS (
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
            )
            SELECT a.*, m.lead_utm_medium AS utm_medium
            FROM adset a
            LEFT JOIN medium_cte m
              ON a.date = m.date AND a.channel = m.hs_channel
              AND LOWER(TRIM(a.campaign_name)) = LOWER(TRIM(m.lead_utm_campaign))
              AND LOWER(TRIM(a.adset_name))    = LOWER(TRIM(m.lead_utm_audience))
            ORDER BY a.date, a.channel, a.campaign_id, a.adset_id
        """
    if grain == "ad":
        med = _medium_cte(since, until, proj, ds,
                          join_cols=["utm_campaign", "utm_audience"],
                          hs_cols=["lead_utm_campaign", "lead_utm_audience"])
        return f"""
            WITH {med},
            ad AS (
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
            )
            SELECT a.*, m.lead_utm_medium AS utm_medium
            FROM ad a
            LEFT JOIN medium_cte m
              ON a.date = m.date AND a.channel = m.hs_channel
              AND LOWER(TRIM(a.campaign_name)) = LOWER(TRIM(m.lead_utm_campaign))
              AND LOWER(TRIM(a.adset_name))    = LOWER(TRIM(m.lead_utm_audience))
            ORDER BY a.date, a.channel, a.campaign_id, a.ad_id
        """
    if grain == "keyword":
        # Keywords: utm_medium is mostly 'ppc' for search — still expose it
        # but join at campaign+adgroup level (no finer join available)
        med = _medium_cte(since, until, proj, ds,
                          join_cols=["utm_campaign", "utm_audience"],
                          hs_cols=["lead_utm_campaign", "lead_utm_audience"])
        return f"""
            WITH {med},
            kw AS (
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
            )
            SELECT k.*, m.lead_utm_medium AS utm_medium
            FROM kw k
            LEFT JOIN medium_cte m
              ON k.date = m.date AND k.channel = m.hs_channel
              AND LOWER(TRIM(k.campaign_name)) = LOWER(TRIM(m.lead_utm_campaign))
              AND LOWER(TRIM(k.adset_name))    = LOWER(TRIM(m.lead_utm_audience))
            ORDER BY k.date, k.channel, k.campaign_name, k.keyword
        """
    raise ValueError(f"Unknown grain: {grain}  (valid: {ALL_GRAINS})")


def _build_records(grain: str, rows) -> list:
    """Convert BQ rows to Databox record dicts.

    All dimension names follow UTM convention:
      channel      = utm_source (BQ slug)
      qoyod_source = HubSpot qoyod_source label
      utm_campaign = campaign name
      utm_audience = adset / adgroup / adsquad / asset group name
      utm_content  = ad / creative name
      utm_term     = keyword text
      utm_medium   = form name / placement
      grain        = campaign | adset | ad | keyword
    """
    records = []
    for r in rows:
        utm_medium = getattr(r, "utm_medium", None) or None
        base = {
            "date":         str(r.date),
            "channel":      r.channel,                       # utm_source (BQ slug)
            "qoyod_source": _channel_to_source(r.channel),  # HubSpot qoyod_source label
            "utm_medium":   utm_medium,                      # form name / placement
            "grain":        grain,
        }

        if grain == "campaign":
            rec = _row(base,
                campaign_id  = r.campaign_id or None,
                utm_campaign = r.campaign_name or None,
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
                utm_campaign = r.campaign_name or None,
                adset_id     = r.adset_id or None,
                utm_audience = r.adset_name or None,
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
                utm_campaign = r.campaign_name or None,
                adset_id     = r.adset_id or None,
                utm_audience = r.adset_name or None,
                ad_id        = r.ad_id or None,
                utm_content  = r.ad_name or None,
                creative_type= r.creative_type or None,
                spend        = _v(r.spend),
                impressions  = _v(r.impressions),
                clicks       = _v(r.clicks),
                cpl          = _v(r.cpl),
                cpql         = _v(r.cpql),
                qual_rate_pct= _v(r.qual_rate_pct),
            )

        elif grain == "keyword":
            rec = _row(base,
                utm_campaign = r.campaign_name or None,
                utm_audience = r.adset_name or None,
                utm_term     = r.keyword or None,
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
                print(f"[databox] {name}: {n:,} records pushed", flush=True)
            except Exception as e:
                print(f"[databox] {name} FAILED: {e}", flush=True)
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
                          f" ({w_since} to {w_until}): {n:,} records", flush=True)
                    if i + 1 < len(windows):
                        time.sleep(_CHUNK_SLEEP)
                except Exception as e:
                    print(f"[databox] {name} chunk {i+1} ({w_since}→{w_until}) FAILED: {e}",
                          flush=True)
                    raise
            print(f"[databox] {name} total: {n_g:,} records", flush=True)

    print(f"[databox] grand total: {total:,} records", flush=True)
    return total


def push_custom_metrics(days: int = 90) -> int:
    """Push daily spend (+ CPL / CPQL / leads) as Databox Push API custom metrics.

    Uses the Databox Push API (push.databox.com) which requires a PUSH CONNECTOR TOKEN
    — this is DIFFERENT from the PAK (DATABOX_TOKEN).

    How to get the push connector token:
      1. Go to app.databox.com → Connect Data → Custom → Push Custom Data
      2. Create a new connector (e.g. "Qoyod Push Metrics") or find an existing one
      3. Copy the connector token (looks like a 32-char hex string, NOT pak_...)
      4. Store it in Railway as DATABOX_PUSH_TOKEN
         (railway run railway variables set DATABOX_PUSH_TOKEN=<token>)

    Metrics pushed (one value per day, all channels combined):
      $spend       — total daily spend USD (SUM across all channels)
      $leads       — total HubSpot leads  (SUM)
      $sqls        — total SQLs / qualified leads (SUM)
      $cpl         — blended Cost Per Lead  (spend / leads)
      $cpql        — blended Cost Per SQL   (spend / sqls)

    Also pushes per-channel spend:
      $spend_google_ads, $spend_meta, $spend_snapchat,
      $spend_tiktok, $spend_microsoft_ads, $spend_linkedin

    Args:
        days: How many days back to push (default 90).
    """
    DATABOX_PUSH_TOKEN = os.getenv("DATABOX_PUSH_TOKEN", "")
    if not DATABOX_PUSH_TOKEN:
        raise RuntimeError(
            "DATABOX_PUSH_TOKEN not set.\n"
            "The Push API uses a connector token (NOT the PAK).\n"
            "Go to app.databox.com → Connect Data → Custom → Push Custom Data,\n"
            "create/find the connector, copy its token, and set it in Railway:\n"
            "  railway variables set DATABOX_PUSH_TOKEN=<your_connector_token>"
        )

    import base64
    from google.cloud import bigquery

    bq      = bigquery.Client()
    today   = date.today()
    since   = (today - timedelta(days=days)).isoformat()

    _proj = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    _ds   = os.getenv("BQ_DATASET",    "qoyod_marketing")

    sql = f"""
    SELECT
        date,
        channel,
        SUM(spend)       AS spend,
        SUM(leads_total) AS leads,
        SUM(qualified)   AS sqls
    FROM `{_proj}.{_ds}.paid_channel_daily`
    WHERE date >= '{since}'
      AND date  < '{today.isoformat()}'
    GROUP BY date, channel
    ORDER BY date
    """
    rows = list(bq.query(sql).result())
    if not rows:
        print("[databox-push] no rows returned from BQ", flush=True)
        return 0

    # Aggregate per date across channels
    from collections import defaultdict
    by_date    = defaultdict(lambda: {"spend": 0.0, "leads": 0, "sqls": 0})
    by_ch_date = defaultdict(float)   # (channel, date) → spend

    for r in rows:
        d   = str(r.date)
        ch  = r.channel or "unknown"
        sp  = float(r.spend  or 0)
        lx  = int(r.leads    or 0)
        sq  = int(r.sqls     or 0)
        by_date[d]["spend"] += sp
        by_date[d]["leads"] += lx
        by_date[d]["sqls"]  += sq
        by_ch_date[(ch, d)] += sp

    # Build Push API payload — each item is one metric value
    PUSH_URL = "https://push.databox.com"
    creds    = base64.b64encode(f"{DATABOX_PUSH_TOKEN}:".encode()).decode()
    headers  = {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/vnd.databox.v2+json",
    }

    payload_items = []
    for d_str, agg in sorted(by_date.items()):
        sp  = round(agg["spend"], 2)
        lx  = agg["leads"]
        sq  = agg["sqls"]
        cpl  = round(sp / lx,  2) if lx  > 0 else None
        cpql = round(sp / sq, 2) if sq > 0 else None
        item: dict = {
            "date":   f"{d_str}T00:00:00",
            "$spend": sp,
            "$leads": lx,
            "$sqls":  sq,
        }
        if cpl  is not None: item["$cpl"]  = cpl
        if cpql is not None: item["$cpql"] = cpql
        payload_items.append(item)

    # Per-channel spend
    for (ch, d_str), sp in sorted(by_ch_date.items()):
        key = "$spend_" + ch.replace("-", "_").replace(" ", "_")
        payload_items.append({"date": f"{d_str}T00:00:00", key: round(sp, 2)})

    # Push in batches of 100
    sess  = _session()
    total = 0
    for i in range(0, len(payload_items), _BATCH):
        batch = payload_items[i:i + _BATCH]
        r = sess.post(
            PUSH_URL,
            headers=headers,
            data=json.dumps({"data": batch}, ensure_ascii=False).encode("utf-8"),
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        total += len(batch)
        print(f"[databox-push] batch {i // _BATCH + 1}: {len(batch)} items sent", flush=True)
        time.sleep(0.3)

    print(f"[databox-push] done — {total} metric values pushed ({len(by_date)} days)", flush=True)
    return total


if __name__ == "__main__":
    import sys
    # Usage: python collectors/databox_pusher.py [days] [grain]
    # e.g.:  python collectors/databox_pusher.py 7
    #        python collectors/databox_pusher.py 365 campaign
    #        python collectors/databox_pusher.py push 90   ← custom metrics via Push API
    if len(sys.argv) > 1 and sys.argv[1] == "push":
        d = int(sys.argv[2]) if len(sys.argv) > 2 else 90
        push_custom_metrics(days=d)
    else:
        d = int(sys.argv[1]) if len(sys.argv) > 1 else 7
        g = [sys.argv[2]] if len(sys.argv) > 2 else None
        run_push(days=d, grains=g)
