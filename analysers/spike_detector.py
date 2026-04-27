"""
analysers/spike_detector.py
============================
Detects daily anomalies in paid-channel performance and posts ONE Slack
message per day only when something worth noting actually happens.

What counts as a "spike":
  - Spend up   ≥ 30%  vs trailing 7-day average → :money_with_wings:
  - Spend down ≥ 30%                            → :chart_with_downwards_trend:
  - Leads up   ≥ 40%                            → :rocket:
  - Leads down ≥ 40%                            → :warning:
  - Qualified rate change ≥ 20 percentage points → :star: / :thinking_face:
  - Disqualified rate change ≥ 20 percentage points → :x: / :warning:

The detector runs on the most recent full day (yesterday Riyadh) vs the
7 days before that. Only paid channels are checked — organic/SEO are
tracked but not part of the spike alerts.

Called by main.run_cadence("daily") after data has been refreshed.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

# Thresholds — tune in .env without redeploy
SPEND_PCT_THRESHOLD = float(os.getenv("SPIKE_SPEND_PCT", "30"))   # ±30%
LEADS_PCT_THRESHOLD = float(os.getenv("SPIKE_LEADS_PCT", "40"))   # ±40%
QUAL_PP_THRESHOLD   = float(os.getenv("SPIKE_QUAL_PP", "20"))     # ±20 pp
DISQ_PP_THRESHOLD   = float(os.getenv("SPIKE_DISQ_PP", "20"))     # ±20 pp

# Minimum yesterday volume to even compare — avoids "one lead became two"
# triggering a "+100%" alert on a near-empty account.
MIN_SPEND_USD       = float(os.getenv("SPIKE_MIN_SPEND",  "100"))   # $100
MIN_LEADS_COUNT     = int(  os.getenv("SPIKE_MIN_LEADS",  "5"))


# Channels we care about for spike alerts (paid only)
PAID_CHANNELS = ["google_ads", "meta", "snapchat", "linkedin", "microsoft_ads", "tiktok"]

# Map BQ channel slug → human-readable label for Slack
CHANNEL_LABELS = {
    "google_ads":    "Google Ads",
    "meta":          "Meta",
    "snapchat":      "Snapchat",
    "linkedin":      "LinkedIn",
    "microsoft_ads": "Microsoft",
    "tiktok":        "TikTok",
}

# qoyod_source values that map to each channel for HubSpot lead attribution
CHANNEL_TO_QOYOD = {
    "google_ads":    "Google Ads",
    "meta":          "Meta Ads",
    "snapchat":      "Snapchat Ads",
    "linkedin":      "LinkedIn Ads",
    "microsoft_ads": "Microsoft Ads",
    "tiktok":        "TikTok Ads",
}


def _riyadh_today() -> datetime:
    return datetime.now(timezone(timedelta(hours=3)))


def _pct_change(now: float, baseline: float) -> Optional[float]:
    """Percentage change. Returns None if baseline is zero (undefined)."""
    if baseline == 0:
        return None
    return (now - baseline) / baseline * 100.0


def _fetch_metrics() -> dict:
    """
    Pull yesterday + 7-day baseline from BigQuery, per channel.
    Returns {channel: {"yesterday": {...}, "baseline_avg": {...}}}.
    """
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    from google.cloud import bigquery

    client = get_client()
    today = _riyadh_today().date()
    yesterday = today - timedelta(days=1)
    base_start = yesterday - timedelta(days=7)
    base_end   = yesterday - timedelta(days=1)

    out: dict[str, dict] = {ch: {"yesterday": {}, "baseline_avg": {}} for ch in PAID_CHANNELS}

    # Spend, by channel — yesterday
    spend_yest_q = f"""
        SELECT channel, SUM(spend) AS spend, SUM(leads) AS leads
        FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
        WHERE date = @d AND channel IN UNNEST(@chans)
        GROUP BY channel
    """
    spend_base_q = f"""
        SELECT channel,
               AVG(daily_spend) AS spend_avg,
               AVG(daily_leads) AS leads_avg
        FROM (
            SELECT channel, date, SUM(spend) AS daily_spend, SUM(leads) AS daily_leads
            FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
            WHERE date BETWEEN @s AND @e AND channel IN UNNEST(@chans)
            GROUP BY channel, date
        )
        GROUP BY channel
    """

    cfg_y = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d", "DATE", yesterday),
        bigquery.ArrayQueryParameter("chans", "STRING", PAID_CHANNELS),
    ])
    cfg_b = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "DATE", base_start),
        bigquery.ScalarQueryParameter("e", "DATE", base_end),
        bigquery.ArrayQueryParameter("chans", "STRING", PAID_CHANNELS),
    ])

    for r in client.query(spend_yest_q, job_config=cfg_y).result():
        out[r["channel"]]["yesterday"] = {
            "spend": float(r["spend"] or 0),
            "platform_leads": int(r["leads"] or 0),
        }
    for r in client.query(spend_base_q, job_config=cfg_b).result():
        out[r["channel"]]["baseline_avg"] = {
            "spend": float(r["spend_avg"] or 0),
            "platform_leads": float(r["leads_avg"] or 0),
        }

    # HubSpot leads + qualified + disqualified, by qoyod_source
    crm_yest_q = f"""
        SELECT qoyod_source,
               SUM(leads_total)        AS leads,
               SUM(leads_qualified)    AS qualified,
               SUM(leads_disqualified) AS disqualified
        FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
        WHERE date = @d AND qoyod_source IN UNNEST(@srcs)
        GROUP BY qoyod_source
    """
    crm_base_q = f"""
        SELECT qoyod_source,
               AVG(daily_leads) AS leads_avg,
               AVG(daily_qual)  AS qual_avg,
               AVG(daily_disq)  AS disq_avg
        FROM (
            SELECT qoyod_source, date,
                   SUM(leads_total)        AS daily_leads,
                   SUM(leads_qualified)    AS daily_qual,
                   SUM(leads_disqualified) AS daily_disq
            FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
            WHERE date BETWEEN @s AND @e AND qoyod_source IN UNNEST(@srcs)
            GROUP BY qoyod_source, date
        )
        GROUP BY qoyod_source
    """

    qoyod_srcs = list(CHANNEL_TO_QOYOD.values())
    cfg_yc = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("d", "DATE", yesterday),
        bigquery.ArrayQueryParameter("srcs", "STRING", qoyod_srcs),
    ])
    cfg_bc = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "DATE", base_start),
        bigquery.ScalarQueryParameter("e", "DATE", base_end),
        bigquery.ArrayQueryParameter("srcs", "STRING", qoyod_srcs),
    ])

    src_to_channel = {v: k for k, v in CHANNEL_TO_QOYOD.items()}

    for r in client.query(crm_yest_q, job_config=cfg_yc).result():
        ch = src_to_channel.get(r["qoyod_source"])
        if not ch:
            continue
        out[ch]["yesterday"].update({
            "leads":        int(r["leads"] or 0),
            "qualified":    int(r["qualified"] or 0),
            "disqualified": int(r["disqualified"] or 0),
        })
    for r in client.query(crm_base_q, job_config=cfg_bc).result():
        ch = src_to_channel.get(r["qoyod_source"])
        if not ch:
            continue
        out[ch]["baseline_avg"].update({
            "leads":        float(r["leads_avg"] or 0),
            "qualified":    float(r["qual_avg"] or 0),
            "disqualified": float(r["disq_avg"] or 0),
        })

    return out


def detect_spikes() -> list[dict]:
    """
    Compare yesterday vs trailing 7-day average per paid channel.
    Returns a list of spike dicts — empty list = nothing to alert on.
    """
    metrics = _fetch_metrics()
    spikes: list[dict] = []

    for channel, data in metrics.items():
        y = data.get("yesterday", {})
        b = data.get("baseline_avg", {})

        # ── Spend spike (need minimum spend to be meaningful) ────────────────
        spend_y = y.get("spend", 0)
        spend_b = b.get("spend", 0)
        if max(spend_y, spend_b) >= MIN_SPEND_USD:
            pct = _pct_change(spend_y, spend_b)
            if pct is not None and abs(pct) >= SPEND_PCT_THRESHOLD:
                spikes.append({
                    "channel": channel, "metric": "spend",
                    "direction": "up" if pct > 0 else "down",
                    "pct": pct, "yesterday": spend_y, "baseline": spend_b,
                })

        # ── Lead-volume spike (HubSpot leads, not platform-reported) ─────────
        leads_y = y.get("leads", 0)
        leads_b = b.get("leads", 0)
        if max(leads_y, leads_b) >= MIN_LEADS_COUNT:
            pct = _pct_change(leads_y, leads_b)
            if pct is not None and abs(pct) >= LEADS_PCT_THRESHOLD:
                spikes.append({
                    "channel": channel, "metric": "leads",
                    "direction": "up" if pct > 0 else "down",
                    "pct": pct, "yesterday": leads_y, "baseline": leads_b,
                })

        # ── Qualified-rate change (percentage points, not %) ─────────────────
        if leads_y >= MIN_LEADS_COUNT and leads_b >= MIN_LEADS_COUNT:
            qrate_y = (y.get("qualified", 0) / leads_y * 100) if leads_y else 0
            qrate_b = (b.get("qualified", 0) / leads_b * 100) if leads_b else 0
            qrate_diff = qrate_y - qrate_b
            if abs(qrate_diff) >= QUAL_PP_THRESHOLD:
                spikes.append({
                    "channel": channel, "metric": "qualified_rate",
                    "direction": "up" if qrate_diff > 0 else "down",
                    "pp": qrate_diff, "yesterday_pct": qrate_y, "baseline_pct": qrate_b,
                })

            drate_y = (y.get("disqualified", 0) / leads_y * 100) if leads_y else 0
            drate_b = (b.get("disqualified", 0) / leads_b * 100) if leads_b else 0
            drate_diff = drate_y - drate_b
            if abs(drate_diff) >= DISQ_PP_THRESHOLD:
                spikes.append({
                    "channel": channel, "metric": "disqualified_rate",
                    "direction": "up" if drate_diff > 0 else "down",
                    "pp": drate_diff, "yesterday_pct": drate_y, "baseline_pct": drate_b,
                })

    return spikes


def _format_slack(spikes: list[dict]) -> tuple[list, str]:
    """Build a single Slack block + fallback text from a list of spikes."""
    yesterday = (_riyadh_today() - timedelta(days=1)).strftime("%d %b")

    icon_map = {
        ("spend",            "up"):   ":money_with_wings:",
        ("spend",            "down"): ":chart_with_downwards_trend:",
        ("leads",            "up"):   ":rocket:",
        ("leads",            "down"): ":warning:",
        ("qualified_rate",   "up"):   ":star:",
        ("qualified_rate",   "down"): ":thinking_face:",
        ("disqualified_rate", "up"):  ":x:",
        ("disqualified_rate", "down"): ":white_check_mark:",
    }

    metric_label = {
        "spend":             "Spend",
        "leads":             "Leads",
        "qualified_rate":    "Qualified rate",
        "disqualified_rate": "Disqualified rate",
    }

    lines: list[str] = []
    for s in spikes:
        ch = CHANNEL_LABELS.get(s["channel"], s["channel"])
        mtype = s["metric"]
        direction = s["direction"]
        icon = icon_map.get((mtype, direction), ":small_orange_diamond:")
        label = metric_label.get(mtype, mtype)

        if "pct" in s:
            arrow = "▲" if direction == "up" else "▼"
            if mtype == "spend":
                lines.append(
                    f"{icon} *{ch} — {label}* {arrow} `{abs(s['pct']):.0f}%`  "
                    f"(${s['yesterday']:,.0f} vs avg ${s['baseline']:,.0f})"
                )
            else:
                lines.append(
                    f"{icon} *{ch} — {label}* {arrow} `{abs(s['pct']):.0f}%`  "
                    f"({s['yesterday']:.0f} vs avg {s['baseline']:.1f})"
                )
        elif "pp" in s:
            arrow = "▲" if direction == "up" else "▼"
            lines.append(
                f"{icon} *{ch} — {label}* {arrow} `{abs(s['pp']):.0f}pp`  "
                f"({s['yesterday_pct']:.0f}% vs {s['baseline_pct']:.0f}% baseline)"
            )

    body = (
        f":vertical_traffic_light: *Daily Spike Report — {yesterday}*\n"
        f"_{len(spikes)} anomaly(ies) vs trailing 7-day baseline_\n\n"
        + "\n".join(lines)
    )
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": body}}]
    return blocks, f"Daily spike report — {len(spikes)} anomaly(ies)"


def run() -> int:
    """
    Compute spikes and post to Slack only if any are found.
    Returns the number of spikes detected (0 = silent run).
    """
    print("[spike-detector] Computing daily spikes…")
    try:
        spikes = detect_spikes()
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[spike-detector] Failed: {e}")
        return -1

    if not spikes:
        print("[spike-detector] No spikes detected — silent run")
        return 0

    print(f"[spike-detector] {len(spikes)} spike(s) detected:")
    for s in spikes:
        print(f"  {s}")

    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY
        from notifications.quiet import is_quiet, quiet_log
        blocks, text = _format_slack(spikes)
        if is_quiet():
            quiet_log("spike-detector", SLACK_CHANNEL_NOTIFY, text)
        else:
            WebClient(token=SLACK_BOT_TOKEN).chat_postMessage(
                channel=SLACK_CHANNEL_NOTIFY, blocks=blocks, text=text
            )
            print(f"[spike-detector] Posted {len(spikes)} spike(s) to Slack")
    except Exception as e:
        print(f"[spike-detector] Slack post failed: {e}")

    return len(spikes)


if __name__ == "__main__":
    n = run()
    print(f"\nResult: {n} spike(s)")
