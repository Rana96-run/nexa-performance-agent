"""
analysers/display_audit.py
===========================
Per-channel performance audits for the four display/social channels:
Meta, Snapchat, TikTok, LinkedIn.

Unlike Google/Microsoft Ads (search engines), these channels don't expose
Quality Score, Impression Share, or search-term reports. What they DO
expose are creative-quality + saturation signals:

  1. CTR fatigue       — last 7d CTR drop vs trailing 14d baseline
  2. Frequency saturation (Meta + Snap + LinkedIn) — avg freq > 2.5 = fatigue
  3. High-spend zero-conv — ad spent $50+ over 14d with 0 conversions

All findings log under role='performance_audit' with channel as a dimension,
matching Google/MS audit symmetry. Uses ads_daily in BQ as source — no
extra platform API calls needed.

Usage:
  from analysers.display_audit import audit_channel
  findings = audit_channel("meta", days=14)
"""
from __future__ import annotations

from datetime import date, timedelta

from collectors.bq_writer import get_client


# ─── Thresholds ──────────────────────────────────────────────────────────────
CTR_FATIGUE_DROP_PCT      = 0.30   # >30% CTR drop last 7d vs trailing 14d
FREQ_SATURATION_THRESHOLD = 2.5    # avg frequency over 14d
ZERO_CONV_SPEND_USD       = 50.0   # 14d spend floor for zero-conv pause
ZERO_CONV_DAYS            = 14
MIN_RECENT_SPEND_FOR_CTR  = 30.0   # last-7d spend gate before flagging CTR drop

# Frequency is meaningful on these channels (impression-capped audiences)
FREQ_CHANNELS = {"meta", "snapchat", "linkedin"}


def _query_ad_window(channel: str, days: int = 14) -> list[dict]:
    """Pull per-ad aggregates over the last N days.

    Joins ads_daily with hubspot_leads_module_daily (pre-aggregated by
    lead_utm_content) so that zero-conv detection uses HubSpot leads —
    the canonical conversion source per CLAUDE.md — not platform-reported
    conversions which are unreliable across channels.
    """
    client = get_client()
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    half  = end - timedelta(days=6)   # last 7d boundary

    q = """
      -- Pre-aggregate HubSpot leads at ad level (lead_utm_content = ad name).
      -- Must be a CTE to avoid spend fan-out on the outer join.
      WITH hs AS (
        SELECT
          lead_utm_content,
          SUM(leads_total)      AS hs_leads,
          SUM(leads_qualified)  AS hs_sqls
        FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
        WHERE date BETWEEN @start AND @end
          AND lead_utm_content IS NOT NULL
          AND lead_utm_content != ''
        GROUP BY lead_utm_content
      ),
      win AS (
        SELECT
          ad_id, ad_name, adset_name, campaign_name,
          date, spend, impressions, clicks,
          SAFE_DIVIDE(clicks, impressions) AS daily_ctr,
          frequency
        FROM `angular-axle-492812-q4.qoyod_marketing.ads_daily`
        WHERE channel = @channel
          AND date BETWEEN @start AND @end
      )
      SELECT
        w.ad_id,
        ANY_VALUE(w.ad_name)       AS ad_name,
        ANY_VALUE(w.adset_name)    AS adset_name,
        ANY_VALUE(w.campaign_name) AS campaign_name,
        SUM(w.spend)               AS spend_total,
        SUM(w.impressions)         AS impressions_total,
        SUM(w.clicks)              AS clicks_total,
        AVG(w.frequency)           AS avg_frequency,
        -- HubSpot leads are the canonical conversion metric (not platform convs)
        MAX(IFNULL(hs.hs_leads, 0))  AS hs_leads_total,
        MAX(IFNULL(hs.hs_sqls,  0))  AS hs_sqls_total,
        SAFE_DIVIDE(SUM(w.clicks), SUM(w.impressions)) AS ctr_overall,
        SAFE_DIVIDE(
          SUM(IF(w.date >= @half, w.clicks, 0)),
          SUM(IF(w.date >= @half, w.impressions, 0))
        ) AS ctr_last7d,
        SAFE_DIVIDE(
          SUM(IF(w.date < @half, w.clicks, 0)),
          SUM(IF(w.date < @half, w.impressions, 0))
        ) AS ctr_first7d,
        SUM(IF(w.date >= @half, w.spend, 0)) AS spend_last7d
      FROM win w
      LEFT JOIN hs ON LOWER(hs.lead_utm_content) = LOWER(w.ad_name)
      WHERE w.ad_id IS NOT NULL AND w.ad_id != ''
      GROUP BY w.ad_id
      HAVING spend_total > 0
    """
    from google.cloud import bigquery
    job = client.query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("channel", "STRING", channel),
            bigquery.ScalarQueryParameter("start",   "DATE",   start),
            bigquery.ScalarQueryParameter("end",     "DATE",   end),
            bigquery.ScalarQueryParameter("half",    "DATE",   half),
        ]
    ))
    return [dict(r) for r in job.result()]


def audit_channel(channel: str, days: int = 14) -> dict:
    """
    Run all three audits for one channel. Returns a dict with three buckets:
      {
        "ctr_fatigue":    [...],   # ads with CTR dropping ≥ 30%
        "frequency_sat":  [...],   # ads with avg freq > 2.5 (Meta/Snap/LI only)
        "zero_conv_pause":[...],   # ads spent $50+, 0 conv, 14d
      }
    """
    rows = _query_ad_window(channel, days=days)

    ctr_fatigue: list[dict]    = []
    freq_sat: list[dict]       = []
    zero_conv_pause: list[dict] = []

    for r in rows:
        ad_id        = r.get("ad_id")
        ad_name      = r.get("ad_name") or "(unnamed)"
        adset        = r.get("adset_name") or "—"
        campaign     = r.get("campaign_name") or "—"
        spend_total  = float(r.get("spend_total") or 0)
        spend_last7d = float(r.get("spend_last7d") or 0)
        # HubSpot leads are the canonical conversion metric (CLAUDE.md golden rule)
        hs_leads     = float(r.get("hs_leads_total") or 0)
        hs_sqls      = float(r.get("hs_sqls_total")  or 0)
        ctr_first    = float(r.get("ctr_first7d") or 0)
        ctr_last     = float(r.get("ctr_last7d")  or 0)
        avg_freq     = float(r.get("avg_frequency") or 0)

        base = {
            "channel":    channel,
            "ad_id":      ad_id,
            "ad_name":    ad_name,
            "adset":      adset,
            "campaign":   campaign,
            "spend_14d":  round(spend_total, 2),
            "hs_leads_14d": int(hs_leads),   # HubSpot leads, not platform convs
            "hs_sqls_14d":  int(hs_sqls),
            "ctr_first7d": round(ctr_first, 4),
            "ctr_last7d":  round(ctr_last,  4),
            "avg_freq":    round(avg_freq,  2),
        }

        # 1. CTR fatigue — last 7d CTR drop > 30% AND meaningful recent spend
        if ctr_first > 0 and spend_last7d >= MIN_RECENT_SPEND_FOR_CTR:
            drop = (ctr_first - ctr_last) / ctr_first
            if drop >= CTR_FATIGUE_DROP_PCT:
                row = dict(base)
                row["ctr_drop_pct"] = round(drop * 100, 1)
                row["verdict"]      = "creative_fatigue_refresh_creative"
                ctr_fatigue.append(row)

        # 2. Frequency saturation — Meta/Snap/LinkedIn only
        if channel in FREQ_CHANNELS and avg_freq > FREQ_SATURATION_THRESHOLD:
            row = dict(base)
            row["verdict"] = "frequency_saturated_expand_audience_or_pause"
            freq_sat.append(row)

        # 3. High-spend zero-conv → pause candidate
        # Uses HubSpot leads (not platform conversions) per CLAUDE.md golden rule:
        # "Leads and SQLs come from HubSpot Lead Module only"
        if spend_total >= ZERO_CONV_SPEND_USD and hs_leads == 0:
            row = dict(base)
            row["verdict"] = "zero_conv_high_spend_pause"
            zero_conv_pause.append(row)

    # Sort each bucket by spend desc so the highest-impact items surface first
    ctr_fatigue.sort(key=lambda x: -x["spend_14d"])
    freq_sat.sort(key=lambda x: -x["spend_14d"])
    zero_conv_pause.sort(key=lambda x: -x["spend_14d"])

    return {
        "ctr_fatigue":     ctr_fatigue,
        "frequency_sat":   freq_sat,
        "zero_conv_pause": zero_conv_pause,
    }


def run_full_audit(days: int = 14) -> dict[str, dict]:
    """Run audits for all 4 display/social channels. Returns
    {channel: {bucket: [findings]}}."""
    out = {}
    for ch in ("meta", "snapchat", "tiktok", "linkedin"):
        try:
            out[ch] = audit_channel(ch, days=days)
            counts = {k: len(v) for k, v in out[ch].items()}
            print(f"[display-audit] {ch}: {counts}")
        except Exception as e:
            print(f"[display-audit] {ch} failed: {e}")
            out[ch] = {"ctr_fatigue": [], "frequency_sat": [], "zero_conv_pause": []}
    return out


if __name__ == "__main__":
    import json
    result = run_full_audit()
    print(json.dumps({ch: {k: len(v) for k, v in buckets.items()}
                       for ch, buckets in result.items()}, indent=2))
