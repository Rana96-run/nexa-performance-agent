"""
analysers/connector_tracker.py
===============================
Connector Police — proactive health checks for all 9 Qoyod data connectors.

Runs 5 check categories per connector:
  1. freshness      — is yesterday's data in BQ? (per channel)
  2. row_integrity  — zero-row partition despite prior 7d having data?
  3. spend_sanity   — negative sums or implausible spikes (> 5x 7d avg)?
  4. attribution    — leads joined from HubSpot? UTM match rate OK?
  5. credentials    — token expiry check (LinkedIn 60d window)

Output:
  - Structured dict per connector: {status, checks_passed, checks_failed, fix_command}
  - Writes results to BQ connector_health_log table
  - Posts to #nexa-health if any connector is BROKEN
  - Returns overall status: GREEN / AMBER / RED

Scheduled: 08:30 Riyadh daily (operational_scheduler.py)
Manual: railway run python analysers/connector_tracker.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from collectors.bq_writer import get_client

_RIYADH = timezone(timedelta(hours=3))
_STALE_HOURS = 72          # > this (3d) → STALE warning. <3d is normal: the nightly
                           # collector legitimately lags up to 2 days before 08:00 Riyadh
                           # (per memory/08_pitfalls.md "freshness threshold must be ≥3 days").
_BROKEN_HOURS = 96         # > this (4d) → BROKEN
_SPIKE_MULTIPLIER = 5.0    # spend > N×7d avg → WARNING
_MIN_ATTRIBUTION_RATE = 0.5  # < 50% leads joined → WARNING
_LI_TOKEN_WARN_DAYS = 45   # LinkedIn token warn threshold
_LI_TOKEN_BREAK_DAYS = 60  # LinkedIn token expiry


# ── Connector registry ────────────────────────────────────────────────────────

CONNECTORS = [
    {"channel": "meta",      "bq_table": "campaigns_daily",             "cred_key": "META_ACCESS_TOKEN",          "cred_type": "permanent"},
    {"channel": "google",    "bq_table": "campaigns_daily",             "cred_key": "GOOGLE_ADS_REFRESH_TOKEN",   "cred_type": "permanent"},
    {"channel": "snapchat",  "bq_table": "campaigns_daily",             "cred_key": "SNAPCHAT_REFRESH_TOKEN",     "cred_type": "per_run_refresh"},
    {"channel": "tiktok",    "bq_table": "campaigns_daily",             "cred_key": "TIKTOK_ACCESS_TOKEN",        "cred_type": "permanent"},
    {"channel": "bing",      "bq_table": "campaigns_daily",             "cred_key": "MS_CLIENT_SECRET",           "cred_type": "permanent"},
    {"channel": "linkedin",  "bq_table": "campaigns_daily",             "cred_key": "LI_ACCESS_TOKEN",            "cred_type": "60_day", "known_paused": True},
    {"channel": "hubspot_leads", "bq_table": "hubspot_leads_module_daily", "cred_key": "HUBSPOT_ACCESS_TOKEN",    "cred_type": "permanent"},
    {"channel": "hubspot_deals", "bq_table": "hubspot_deals_daily",    "cred_key": "HUBSPOT_ACCESS_TOKEN",        "cred_type": "permanent"},
    {"channel": "gclid",     "bq_table": "gclid_attribution",           "cred_key": "GOOGLE_ADS_REFRESH_TOKEN",  "cred_type": "permanent"},
]

COLLECTOR_SCRIPTS = {
    "meta":          "collectors/meta_bq.py",
    "google":        "collectors/google_ads_bq.py",
    "snapchat":      "collectors/snap_bq.py",
    "tiktok":        "collectors/tiktok_bq.py",
    "bing":          "collectors/microsoft_ads_bq.py",
    "linkedin":      "collectors/linkedin_bq.py",
    "hubspot_leads": "collectors/hubspot_leads_bq.py",
    "hubspot_deals": "collectors/hubspot_deals_bq.py",
    "gclid":         "collectors/gclid_clickview.py",
}


# ── BQ helpers ────────────────────────────────────────────────────────────────

# campaigns_daily stores channels as google_ads / microsoft_ads; the police labels
# them google / bing for display. Map display label -> BQ channel for WHERE filters.
_BQ_CHANNEL = {"google": "google_ads", "bing": "microsoft_ads"}


def _bq_query(sql: str) -> list:
    c = get_client()
    return list(c.query(sql).result())


def _proj_ds() -> tuple[str, str]:
    return os.environ["BQ_PROJECT_ID"], os.environ["BQ_DATASET"]


# ── Check 1: Freshness ────────────────────────────────────────────────────────

def check_freshness(channel: str, table: str) -> dict:
    """Hours since last successful row for this channel in its BQ table."""
    proj, ds = _proj_ds()

    # Only campaigns_daily has a `channel` column; gclid + hubspot tables don't.
    if table != "campaigns_daily":
        sql = f"""
            SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(),
                   TIMESTAMP(MAX(date)), HOUR) AS hours_old
            FROM `{proj}.{ds}.{table}`
        """
    else:
        sql = f"""
            SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(),
                   TIMESTAMP(MAX(date)), HOUR) AS hours_old
            FROM `{proj}.{ds}.{table}`
            WHERE LOWER(channel) = LOWER('{_BQ_CHANNEL.get(channel, channel)}')
        """
    try:
        rows = _bq_query(sql)
        hours_old = int(rows[0].hours_old or 9999) if rows else 9999
    except Exception as e:
        return {"status": "BROKEN", "hours_old": None, "error": str(e)}

    if hours_old > _BROKEN_HOURS:
        status = "BROKEN"
    elif hours_old > _STALE_HOURS:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {"status": status, "hours_old": hours_old, "error": None}


# ── Check 2: Row Integrity ────────────────────────────────────────────────────

def check_row_integrity(channel: str, table: str) -> dict:
    """Yesterday must have rows if the prior 7 days consistently did."""
    proj, ds = _proj_ds()

    channel_filter = f"AND LOWER(channel) = LOWER('{_BQ_CHANNEL.get(channel, channel)}')" if table == "campaigns_daily" else ""

    sql = f"""
        WITH daily AS (
          SELECT date,
                 COUNT(*) AS row_count
          FROM `{proj}.{ds}.{table}`
          WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 8 DAY)
            AND date < CURRENT_DATE('Asia/Riyadh')
            {channel_filter}
          GROUP BY date
        )
        SELECT
          AVG(IF(date < DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY),
                 row_count, NULL))                     AS avg_7d,
          MAX(IF(date = DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY),
                 row_count, NULL))                     AS yesterday_rows
        FROM daily
    """
    try:
        rows = _bq_query(sql)
        avg_7d = float(rows[0].avg_7d or 0) if rows else 0
        yesterday = int(rows[0].yesterday_rows or 0) if rows else 0
    except Exception as e:
        return {"status": "BROKEN", "yesterday_rows": None, "avg_7d": None, "error": str(e)}

    if avg_7d > 0 and yesterday == 0:
        status = "BROKEN"
    elif avg_7d > 0 and yesterday < avg_7d * 0.5:
        status = "WARNING"
    else:
        status = "HEALTHY"

    return {"status": status, "yesterday_rows": yesterday, "avg_7d": round(avg_7d, 1), "error": None}


# ── Check 3: Spend Sanity ─────────────────────────────────────────────────────

def check_spend_sanity(channel: str) -> dict:
    """Negative spend = corrupt. Spike >5× avg = anomaly."""
    if channel in ("hubspot_leads", "hubspot_deals", "gclid"):
        return {"status": "HEALTHY", "note": "no spend column for this connector"}

    proj, ds = _proj_ds()
    sql = f"""
        WITH daily AS (
          SELECT date, SUM(spend) AS total_spend
          FROM `{proj}.{ds}.campaigns_daily`
          WHERE LOWER(channel) = LOWER('{_BQ_CHANNEL.get(channel, channel)}')
            AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 8 DAY)
            AND date < CURRENT_DATE('Asia/Riyadh')
          GROUP BY date
        )
        SELECT
          SUM(IF(total_spend < 0, 1, 0))        AS negative_days,
          MAX(IF(date = DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY),
                 total_spend, NULL))             AS yesterday_spend,
          AVG(IF(date < DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY),
                 total_spend, NULL))             AS avg_7d_spend
        FROM daily
    """
    try:
        rows = _bq_query(sql)
        negative_days = int(rows[0].negative_days or 0) if rows else 0
        yesterday_spend = float(rows[0].yesterday_spend or 0) if rows else 0
        avg_7d = float(rows[0].avg_7d_spend or 0) if rows else 0
    except Exception as e:
        return {"status": "BROKEN", "error": str(e)}

    if negative_days > 0:
        return {"status": "BROKEN", "reason": f"{negative_days} days with negative spend",
                "fix": f"DELETE partition + railway run python {COLLECTOR_SCRIPTS.get(channel, 'unknown')} 3"}
    if avg_7d > 0 and yesterday_spend > avg_7d * _SPIKE_MULTIPLIER:
        return {"status": "WARNING", "reason": f"Spend spike: ${yesterday_spend:.0f} vs ${avg_7d:.0f} avg (7d)",
                "note": "Verify in platform — may be legitimate"}
    return {"status": "HEALTHY", "yesterday_spend_usd": round(yesterday_spend, 2), "avg_7d_usd": round(avg_7d, 2)}


# ── Check 4: Attribution Health ───────────────────────────────────────────────

def check_attribution(channel: str) -> dict:
    """Lead join rate: HubSpot leads joined vs campaign spend rows in last 7 days."""
    if channel in ("hubspot_leads", "hubspot_deals", "gclid"):
        return {"status": "HEALTHY", "note": "attribution check N/A for this connector"}

    proj, ds = _proj_ds()
    sql = f"""
        WITH spend AS (
          SELECT LOWER(campaign_name) AS camp, SUM(spend) AS total_spend
          FROM `{proj}.{ds}.campaigns_daily`
          WHERE LOWER(channel) = LOWER('{_BQ_CHANNEL.get(channel, channel)}')
            AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
          GROUP BY 1
          HAVING total_spend > 0
        ),
        leads AS (
          SELECT LOWER(lead_utm_campaign) AS camp, SUM(leads_total) AS total_leads
          FROM `{proj}.{ds}.hubspot_leads_module_daily`
          WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
          GROUP BY 1
        )
        SELECT
          COUNT(DISTINCT spend.camp)                       AS campaigns_with_spend,
          COUNT(DISTINCT leads.camp)                       AS campaigns_with_leads,
          SAFE_DIVIDE(COUNT(DISTINCT leads.camp),
                      COUNT(DISTINCT spend.camp))          AS join_rate
        FROM spend
        LEFT JOIN leads ON spend.camp = leads.camp
    """
    try:
        rows = _bq_query(sql)
        campaigns = int(rows[0].campaigns_with_spend or 0) if rows else 0
        with_leads = int(rows[0].campaigns_with_leads or 0) if rows else 0
        join_rate = float(rows[0].join_rate or 0) if rows else 0
    except Exception as e:
        return {"status": "BROKEN", "error": str(e)}

    if campaigns == 0:
        return {"status": "WARNING", "reason": "No campaigns with spend in last 7d"}
    if join_rate < _MIN_ATTRIBUTION_RATE:
        return {"status": "WARNING",
                "reason": f"Only {join_rate:.0%} of campaigns have matched leads ({with_leads}/{campaigns})",
                "note": "Check UTM mismatch — lead_utm_campaign vs campaign_name"}
    return {"status": "HEALTHY", "join_rate": f"{join_rate:.0%}",
            "campaigns_matched": f"{with_leads}/{campaigns}"}


# ── Check 5: Credentials ──────────────────────────────────────────────────────

def check_credentials(connector: dict) -> dict:
    """Check env var presence; LinkedIn gets expiry window check."""
    cred_key = connector["cred_key"]
    cred_type = connector["cred_type"]
    channel = connector["channel"]

    if not os.getenv(cred_key):
        return {"status": "BROKEN", "reason": f"Env var {cred_key} is missing or empty"}

    if cred_type == "60_day":
        # LinkedIn: check LI_TOKEN_ISSUED_DATE env var to track expiry
        issued_str = os.getenv("LI_TOKEN_ISSUED_DATE", "")
        if issued_str:
            try:
                issued = datetime.strptime(issued_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days_old = (datetime.now(timezone.utc) - issued).days
                if days_old >= _LI_TOKEN_BREAK_DAYS:
                    return {"status": "BROKEN", "reason": f"LinkedIn token is {days_old}d old — EXPIRED. Run oauth helper."}
                if days_old >= _LI_TOKEN_WARN_DAYS:
                    return {"status": "WARNING", "reason": f"LinkedIn token is {days_old}d old — expires in {_LI_TOKEN_BREAK_DAYS - days_old}d. Refresh soon."}
            except ValueError:
                return {"status": "WARNING", "reason": "LI_TOKEN_ISSUED_DATE format invalid — cannot verify expiry"}
        else:
            return {"status": "WARNING", "reason": "LI_TOKEN_ISSUED_DATE not set — cannot verify 60d expiry window"}

    return {"status": "HEALTHY", "cred_key": cred_key}


# ── Aggregate per connector ───────────────────────────────────────────────────

def run_connector_check(connector: dict) -> dict:
    """Run all 5 checks for one connector. Return structured result."""
    channel = connector["channel"]
    table = connector["bq_table"]
    known_paused = connector.get("known_paused", False)

    results = {
        "channel": channel,
        "known_paused": known_paused,
        "checks": {},
        "status": "HEALTHY",
        "fix_command": None,
    }

    results["checks"]["freshness"] = check_freshness(channel, table)
    results["checks"]["row_integrity"] = check_row_integrity(channel, table)
    results["checks"]["spend_sanity"] = check_spend_sanity(channel)
    results["checks"]["attribution"] = check_attribution(channel)
    results["checks"]["credentials"] = check_credentials(connector)

    # Idle-aware: a channel with no active campaigns / no spend is HEALTHY-IDLE,
    # not stale/broken (e.g. LinkedIn with no live campaigns). Suppress freshness +
    # row staleness flags for idle channels. Mirrors MS "Success+null = no activity".
    ss = results["checks"].get("spend_sanity", {})
    no_spend = (ss.get("yesterday_spend_usd", 0) or 0) == 0 and (ss.get("avg_7d_usd", 0) or 0) == 0
    is_idle = known_paused or (table == "campaigns_daily" and no_spend)
    if is_idle:
        for cn in ("freshness", "row_integrity"):
            if results["checks"].get(cn, {}).get("status") in ("BROKEN", "WARNING"):
                results["checks"][cn]["status"] = "HEALTHY"
                results["checks"][cn]["note"] = "IDLE — no active campaigns / no spend (not a fault)"
    results["is_idle"] = is_idle

    # Aggregate status: BROKEN > WARNING > HEALTHY
    for check_name, check_result in results["checks"].items():
        check_status = check_result.get("status", "HEALTHY")
        if check_status == "BROKEN":
            results["status"] = "BROKEN"
            results["fix_command"] = (
                check_result.get("fix")
                or f"railway run python {COLLECTOR_SCRIPTS.get(channel, 'unknown')} 3"
            )
            break
        elif check_status == "WARNING" and results["status"] == "HEALTHY":
            results["status"] = "WARNING"

    results["checks_passed"] = sum(
        1 for c in results["checks"].values() if c.get("status") == "HEALTHY"
    )
    results["checks_failed"] = sum(
        1 for c in results["checks"].values() if c.get("status") in ("BROKEN", "WARNING")
    )
    results["last_checked_ts"] = datetime.now(_RIYADH).isoformat()

    return results


# ── Write to BQ ───────────────────────────────────────────────────────────────

def write_health_log(results: list[dict]) -> None:
    """Write connector health results to BQ connector_health_log."""
    from io import BytesIO
    proj, ds = _proj_ds()
    c = get_client()

    rows = []
    for r in results:
        rows.append({
            "check_ts": datetime.utcnow().isoformat(),
            "channel": r["channel"],
            "status": r["status"],
            "checks_passed": r["checks_passed"],
            "checks_failed": r["checks_failed"],
            "fix_command": r.get("fix_command") or "",
            "detail_json": json.dumps(r["checks"]),
        })

    ndjson = "\n".join(json.dumps(row) for row in rows).encode()
    table_ref = f"{proj}.{ds}.connector_health_log"

    from google.cloud.bigquery import LoadJobConfig, SchemaField, SourceFormat
    schema = [
        SchemaField("check_ts",       "TIMESTAMP"),
        SchemaField("channel",         "STRING"),
        SchemaField("status",          "STRING"),
        SchemaField("checks_passed",   "INTEGER"),
        SchemaField("checks_failed",   "INTEGER"),
        SchemaField("fix_command",     "STRING"),
        SchemaField("detail_json",     "STRING"),
    ]
    config = LoadJobConfig(
        schema=schema,
        source_format=SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition="WRITE_APPEND",
        create_disposition="CREATE_IF_NEEDED",
    )
    c.load_table_from_file(BytesIO(ndjson), table_ref, job_config=config).result()


# ── Post to Slack ──────────────────────────────────────────────────────────────

def post_status_board(results: list[dict], overall: str) -> None:
    """Post connector status board to #nexa-health if any BROKEN."""
    broken = [r for r in results if r["status"] == "BROKEN"]
    if not broken:
        return

    from notifications.slack_ping import post_ping
    health_channel = os.getenv("SLACK_CHANNEL_HEALTH", "#nexa-health")
    activity_url = os.getenv("ACTIVITY_SHORT_URL", "https://nexa-web-production-6a6b.up.railway.app/activity")

    lines = [f"*CONNECTOR STATUS — {datetime.now(_RIYADH).strftime('%Y-%m-%d %H:%M')} Riyadh*", ""]
    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "BROKEN": "❌"}
    for r in results:
        fix_note = f" → `{r['fix_command']}`" if r.get("fix_command") else ""
        lines.append(f"{emoji[r['status']]} *{r['channel']}* ({r['checks_passed']}/5 checks passed){fix_note}")

    lines += ["", f"Overall: *{overall}*", f"Dashboard: {activity_url}"]
    headline = f"Connector health {overall}: {len(broken)} BROKEN connector(s)"

    try:
        post_ping(channel=health_channel, status="alert", headline=headline,
                  link=activity_url)
    except Exception as e:
        print(f"[connector_tracker] Slack post failed: {e}")


# ── Main entry point ──────────────────────────────────────────────────────────

def run_all_checks(post_slack: bool = True, write_bq: bool = True) -> dict:
    """
    Run all 5 checks for all 9 connectors.

    Returns:
        {
          "overall": "GREEN" | "AMBER" | "RED",
          "connectors": [...],
          "broken_count": int,
          "warning_count": int,
          "healthy_count": int,
        }
    """
    results = [run_connector_check(c) for c in CONNECTORS]

    broken = sum(1 for r in results if r["status"] == "BROKEN")
    warning = sum(1 for r in results if r["status"] == "WARNING")
    healthy = sum(1 for r in results if r["status"] == "HEALTHY")

    overall = "RED" if broken > 0 else ("AMBER" if warning > 0 else "GREEN")

    if write_bq:
        try:
            write_health_log(results)
        except Exception as e:
            print(f"[connector_tracker] BQ write failed: {e}")

    if post_slack and broken > 0:
        post_status_board(results, overall)

    return {
        "overall": overall,
        "connectors": results,
        "broken_count": broken,
        "warning_count": warning,
        "healthy_count": healthy,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Running connector health checks...\n")
    summary = run_all_checks(post_slack=False, write_bq=False)

    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "BROKEN": "❌"}
    for r in summary["connectors"]:
        print(f"{emoji[r['status']]} {r['channel']:16s} — {r['status']} "
              f"({r['checks_passed']}/5 passed)")
        if r.get("fix_command"):
            print(f"   Fix: {r['fix_command']}")
        for check_name, check_result in r["checks"].items():
            cs = check_result.get("status", "?")
            if cs != "HEALTHY":
                reason = check_result.get("reason") or check_result.get("error") or check_result.get("note", "")
                print(f"   ⚠ {check_name}: {cs} — {reason}")
        print()

    print(f"\nOverall: {summary['overall']} | "
          f"✅ {summary['healthy_count']} healthy | "
          f"⚠️ {summary['warning_count']} warning | "
          f"❌ {summary['broken_count']} broken")
