"""Daily reconciliation: BQ vs HubSpot — catch silent data drift.

Runs as part of the nightly pipeline after BQ refresh completes. Compares
the last 7 days of paid leads + deals from BigQuery against HubSpot's
Search API counts. Logs results to BQ activity log; raises a Slack alert
if total delta exceeds threshold.

Why 7-day window: settled data (today's mirror lag excluded). Aligns with
weekly reporting cadence — if drift is real, weekly reports would show it.

Threshold: total absolute delta > 5% triggers Slack alert. Per-channel
delta > 10% also triggers but only if absolute count > 20 leads (filter
out small-volume noise on channels like Twitter/LinkedIn).
"""
from __future__ import annotations
import os
import datetime as _dt
import requests
from collectors.bq_writer import get_client

# Channels that count as "paid" in our reporting
PAID_CHANNELS = [
    "Google Ads", "Meta Ads", "Snapchat Ads", "Tiktok Ads",
    "Microsoft Ads", "LinkedIn Ads", "Twitter Ads",
]

# Alert thresholds
TOTAL_DELTA_PCT_THRESHOLD = 5.0          # global delta > 5% → alert
CHANNEL_DELTA_PCT_THRESHOLD = 10.0       # per-channel > 10% → alert
CHANNEL_MIN_COUNT_FOR_ALERT = 20         # only alert per-channel if HubSpot > 20

# Use today-7 to today-1 (exclude today to avoid mirror-lag false positives)
def _riyadh_date_range(days_back: int = 7) -> tuple[str, str]:
    """Returns (start_date, end_date) as ISO strings in Riyadh time, both
    inclusive. end_date = yesterday (excludes today)."""
    today_riyadh = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=3))).date()
    end = today_riyadh - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=days_back - 1)
    return start.isoformat(), end.isoformat()


def _riyadh_to_epoch_ms(date_str: str, hour: int = 0, minute: int = 0, second: int = 0) -> str:
    """Convert Riyadh date+time to UTC epoch-ms (HubSpot Search API format)."""
    dt = _dt.datetime.fromisoformat(date_str).replace(hour=hour, minute=minute, second=second)
    utc = dt - _dt.timedelta(hours=3)
    return str(int(utc.timestamp() * 1000))


def _bq_leads_paid_by_channel(start: str, end: str) -> dict[str, int]:
    """BQ — paid leads grouped by qoyod_source."""
    c = get_client()
    proj = os.environ["BQ_PROJECT_ID"]
    ds = os.environ["BQ_DATASET"]
    sql = f"""
    SELECT qoyod_source, SUM(leads_total) AS leads
    FROM `{proj}.{ds}.hubspot_leads_module_daily`
    WHERE date BETWEEN '{start}' AND '{end}'
      AND qoyod_source IN UNNEST({PAID_CHANNELS})
    GROUP BY 1
    """
    return {r.qoyod_source: r.leads or 0 for r in c.query(sql).result()}


def _bq_deals_all_by_pipeline(start: str, end: str) -> dict[str, int]:
    """BQ — all-source deals grouped by pipeline."""
    c = get_client()
    proj = os.environ["BQ_PROJECT_ID"]
    ds = os.environ["BQ_DATASET"]
    sql = f"""
    SELECT pipeline, SUM(deals_total) AS total
    FROM `{proj}.{ds}.hubspot_deals_daily`
    WHERE date BETWEEN '{start}' AND '{end}'
      AND pipeline IS NOT NULL
    GROUP BY 1
    """
    return {r.pipeline: r.total or 0 for r in c.query(sql).result()}


def _hs_count_leads_for_source(source_value: str, since_ms: str, until_ms: str) -> int:
    """HubSpot Lead Module count for a given qoyod_source."""
    token = os.environ["HUBSPOT_ACCESS_TOKEN"]
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": source_value},
            {"propertyName": "hs_createdate", "operator": "GTE", "value": since_ms},
            {"propertyName": "hs_createdate", "operator": "LT",  "value": until_ms},
        ]}],
        "properties": ["hs_createdate"],
        "limit": 1,
    }
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/0-136/search",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    return r.json().get("total", 0) if r.status_code == 200 else 0


def _hs_count_deals_for_pipeline(pipeline_label: str, since_ms: str, until_ms: str) -> int:
    """HubSpot Deals count for a given pipeline."""
    token = os.environ["HUBSPOT_ACCESS_TOKEN"]
    # First need pipeline ID from label
    pipelines_r = requests.get(
        "https://api.hubapi.com/crm/v3/pipelines/deals",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    pipeline_id = None
    for p in pipelines_r.json().get("results", []):
        if p.get("label") == pipeline_label:
            pipeline_id = p["id"]
            break
    if not pipeline_id:
        return 0

    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "pipeline", "operator": "EQ", "value": pipeline_id},
            {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
            {"propertyName": "createdate", "operator": "LT",  "value": until_ms},
        ]}],
        "properties": ["createdate"],
        "limit": 1,
    }
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/deals/search",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    return r.json().get("total", 0) if r.status_code == 200 else 0


def reconcile_daily(post_slack: bool = True) -> dict:
    """Main entry point. Returns a dict with results + alert flags."""
    start, end = _riyadh_date_range(7)
    # end is the LAST day inclusive — for HubSpot range we need until = end+1 00:00
    since_ms = _riyadh_to_epoch_ms(start, 0, 0, 0)
    end_plus_1 = (_dt.date.fromisoformat(end) + _dt.timedelta(days=1)).isoformat()
    until_ms = _riyadh_to_epoch_ms(end_plus_1, 0, 0, 0)

    print(f"[reconcile] Window {start} → {end} (Riyadh)")

    # ── LEADS ──────────────────────────────────────────────────────────────
    bq_leads = _bq_leads_paid_by_channel(start, end)
    hs_leads = {ch: _hs_count_leads_for_source(ch, since_ms, until_ms) for ch in PAID_CHANNELS}

    leads_total_bq = sum(bq_leads.values())
    leads_total_hs = sum(hs_leads.values())
    leads_total_delta = leads_total_bq - leads_total_hs
    leads_total_pct = (leads_total_delta / leads_total_hs * 100) if leads_total_hs else 0

    leads_channel_alerts = []
    for ch in PAID_CHANNELS:
        bq = bq_leads.get(ch, 0)
        hs = hs_leads.get(ch, 0)
        if hs >= CHANNEL_MIN_COUNT_FOR_ALERT:
            pct = ((bq - hs) / hs * 100) if hs else 0
            if abs(pct) > CHANNEL_DELTA_PCT_THRESHOLD:
                leads_channel_alerts.append((ch, bq, hs, pct))

    # ── DEALS ──────────────────────────────────────────────────────────────
    bq_deals = _bq_deals_all_by_pipeline(start, end)
    # For deals reconciliation we only check Sales Pipeline (highest volume)
    # — full per-pipeline matching is slower because requires pipeline lookups.
    hs_sales_pipeline = _hs_count_deals_for_pipeline("Sales Pipeline", since_ms, until_ms)
    bq_sales_pipeline = bq_deals.get("Sales Pipeline", 0)
    deals_delta = bq_sales_pipeline - hs_sales_pipeline
    deals_pct = (deals_delta / hs_sales_pipeline * 100) if hs_sales_pipeline else 0

    # ── Log to BQ activity log ────────────────────────────────────────────
    results = {
        "window": f"{start} to {end}",
        "leads": {
            "bq_total": leads_total_bq,
            "hs_total": leads_total_hs,
            "delta": leads_total_delta,
            "delta_pct": round(leads_total_pct, 2),
            "by_channel": {ch: {"bq": bq_leads.get(ch, 0), "hs": hs_leads.get(ch, 0)}
                           for ch in PAID_CHANNELS},
        },
        "deals_sales_pipeline": {
            "bq": bq_sales_pipeline,
            "hs": hs_sales_pipeline,
            "delta": deals_delta,
            "delta_pct": round(deals_pct, 2),
        },
        "alerts": {
            "leads_total_over_threshold": abs(leads_total_pct) > TOTAL_DELTA_PCT_THRESHOLD,
            "leads_channel_alerts": leads_channel_alerts,
            "deals_sales_over_threshold": abs(deals_pct) > TOTAL_DELTA_PCT_THRESHOLD,
        },
    }

    # ── Log to BQ activity ─────────────────────────────────────────────────
    has_alert = (
        abs(leads_total_pct) > TOTAL_DELTA_PCT_THRESHOLD
        or bool(leads_channel_alerts)
        or abs(deals_pct) > TOTAL_DELTA_PCT_THRESHOLD
    )
    try:
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="ops_scheduler",
            action="daily_reconciliation",
            status="alert" if has_alert else "success",
            details=results,
        )
    except Exception as e:
        print(f"[reconcile] BQ log failed (non-fatal): {e}")

    # ── Slack alert if anything tripped threshold ─────────────────────────
    if has_alert and post_slack:
        try:
            from slack_sdk import WebClient
            from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_HEALTH
            client = WebClient(token=SLACK_BOT_TOKEN)
            client.chat_postMessage(channel=SLACK_CHANNEL_HEALTH,
                                    text=_format_alert_message(results))
        except Exception as e:
            print(f"[reconcile] Slack alert failed (non-fatal): {e}")

    print(f"[reconcile] leads: BQ={leads_total_bq} HS={leads_total_hs} Δ={leads_total_delta} ({leads_total_pct:+.1f}%)")
    print(f"[reconcile] deals_sales_pipeline: BQ={bq_sales_pipeline} HS={hs_sales_pipeline} Δ={deals_delta} ({deals_pct:+.1f}%)")
    if has_alert:
        print(f"[reconcile] ⚠ ALERT — drift over threshold (see results)")
    else:
        print(f"[reconcile] ✓ no drift alerts")
    return results


def _format_alert_message(results: dict) -> str:
    lines = [
        "⚠ *Daily reconciliation alert — BQ vs HubSpot drift detected*",
        f"Window: {results['window']}",
        "",
        f"*Paid leads total:* BQ {results['leads']['bq_total']} vs HS {results['leads']['hs_total']} "
        f"(Δ {results['leads']['delta']:+d}, {results['leads']['delta_pct']:+.1f}%)",
        f"*Sales Pipeline deals:* BQ {results['deals_sales_pipeline']['bq']} vs HS "
        f"{results['deals_sales_pipeline']['hs']} (Δ {results['deals_sales_pipeline']['delta']:+d}, "
        f"{results['deals_sales_pipeline']['delta_pct']:+.1f}%)",
    ]
    if results["alerts"]["leads_channel_alerts"]:
        lines.append("")
        lines.append("*Per-channel drift:*")
        for ch, bq, hs, pct in results["alerts"]["leads_channel_alerts"]:
            lines.append(f"  • {ch}: BQ {bq} vs HS {hs} ({pct:+.1f}%)")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    reconcile_daily(post_slack=False)
