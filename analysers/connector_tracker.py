"""
analysers/connector_tracker.py
===============================
System Police — proactive health checks for the ENTIRE stack, not just connectors.

Inbound connector checks (5 per connector, 9 connectors):
  1. freshness      — is yesterday's data in BQ? (per channel)
  2. row_integrity  — zero-row partition despite prior 7d having data?
  3. spend_sanity   — negative sums or implausible spikes (> 5x 7d avg)?
  4. attribution    — leads joined from HubSpot? UTM match rate OK?
  5. credentials    — token expiry check (LinkedIn 60d window)

Outbound / system monitors (1 check each, SYSTEM_MONITORS list):
  6. databox push freshness — did we push to each Databox dataset within 28h?
  7. railway health         — does /health return HTTP 200?
  8. scheduler execution    — did the daily job fire within the last 26h?

Output:
  - Structured dict per connector/monitor: {status, checks_passed, checks_failed, fix_command}
  - Writes results to BQ connector_health_log table
  - Posts to #nexa-health if any surface is BROKEN
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
_DEAL_AMOUNT_SPIKE = 50.0  # daily deal amount_total > N×90d-median → BROKEN (corrupt/fat-finger amount)
_MIN_ATTRIBUTION_RATE = 0.5  # < 50% leads joined → WARNING
_LI_TOKEN_WARN_DAYS = 45   # LinkedIn token warn threshold
_LI_TOKEN_BREAK_DAYS = 60  # LinkedIn token expiry
_WARNING_ESCALATION_RUNS = 3  # consecutive WARNING runs → escalate to BROKEN

# System-monitor thresholds
_DATABOX_STALE_HOURS  = 28   # daily push should land within 28h; warn if older
_DATABOX_BROKEN_HOURS = 52   # 2+ days without push → BROKEN
_SCHEDULER_WINDOW_HOURS = 26 # daily job fires at 08:00 Riyadh; 2h drift → BROKEN
_RAILWAY_HEALTH_URL   = "https://nexa-web-production-6a6b.up.railway.app/health"
_DATABOX_API_BASE     = "https://api.databox.com"


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

# ── System monitor registry ───────────────────────────────────────────────────
# Add a new entry here whenever a new outbound/runtime surface needs watching.
# Each entry produces one row in connector_health_log (channel = name).

SYSTEM_MONITORS = [
    {
        "name":    "railway_health",
        "type":    "railway",
        "label":   "Railway /health",
    },
    {
        "name":    "scheduler_daily",
        "type":    "scheduler",
        "label":   "Daily scheduler",
        "job_role": "daily_digest",
    },
    {
        "name":      "databox_daily_spend",
        "type":      "databox",
        "label":     "Databox: Daily Spend",
        "dataset_id": os.getenv("DATABOX_DATASET_DAILY_SPEND", "199c5297"),
    },
    {
        "name":      "databox_all_grains",
        "type":      "databox",
        "label":     "Databox: All Grains",
        "dataset_id": os.getenv("DATABOX_DATASET_ALL_GRAINS", "6158be78"),
    },
]


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
    except Exception as e:
        # (a) BQ query error — the check could not RUN (rate limit, timeout,
        # transient internal error). This is NOT a data outage; surfacing it as
        # BROKEN raises a false RED #nexa-health alert for channels that in fact
        # have fresh data. Downgrade to WARNING and carry the error text so the
        # operator can see the check failed to execute rather than the connector.
        return {"status": "WARNING", "hours_old": None,
                "error": f"freshness check failed to run: {e}"}

    # An aggregate query (MAX(date)) always returns exactly one row. When the
    # channel has zero rows, MAX(date) is NULL → hours_old is None.
    # (b) Genuinely empty result — the channel truly has no data → real BROKEN.
    raw = rows[0].hours_old if rows else None
    if raw is None:
        return {"status": "BROKEN", "hours_old": None, "error": None,
                "reason": "no rows in BQ for this channel/table"}

    hours_old = int(raw)
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


def _looks_like_phone(amount: float) -> bool:
    """A deal 'amount' that is really a phone number typed into the Amount field.
    KSA numbers: 966 country code + 9 digits (12 total), or 05XXXXXXXX (10), or 5XXXXXXXX (9)."""
    s = str(int(round(amount)))
    return (s.startswith("966") and len(s) in (12, 13)) or \
           (s.startswith("05") and len(s) == 10) or \
           (s.startswith("5") and len(s) == 9)


def check_amount_sanity(table: str) -> dict:
    """Flag corrupt/implausible deal amounts. Deals only. Recognises the common
    human error: a phone number (966… KSA code) typed into the Amount field."""
    proj, ds = _proj_ds()
    sql = f"""
        WITH daily AS (
          SELECT date, SUM(amount_total) AS amt, SUM(amount_total_native) AS amt_nat
          FROM `{proj}.{ds}.{table}`
          WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
          GROUP BY date
        )
        SELECT
          MAX(IF(date = CURRENT_DATE('Asia/Riyadh'), amt, NULL))                       AS today_amt,
          MAX(IF(date = CURRENT_DATE('Asia/Riyadh'), amt_nat, NULL))                   AS today_nat,
          APPROX_QUANTILES(IF(date < CURRENT_DATE('Asia/Riyadh'), amt, NULL), 100)[OFFSET(50)] AS median_amt
        FROM daily
    """
    try:
        rows = _bq_query(sql)
        today = float(rows[0].today_amt or 0) if rows else 0
        today_nat = float(rows[0].today_nat or 0) if rows else 0
        median = float(rows[0].median_amt or 0) if rows else 0
    except Exception as e:
        return {"status": "HEALTHY", "note": f"amount check skipped: {str(e)[:60]}"}
    if median > 0 and today > median * _DEAL_AMOUNT_SPIKE:
        # phone numbers are entered in the native currency (SAR) — test the native value
        phone = _looks_like_phone(today_nat) or _looks_like_phone(today)
        reason = f"deal amount_total ${today:,.0f} is {today/median:.0f}x the 90d median (${median:,.0f})"
        if phone:
            reason += " — pattern of a SAUDI PHONE NUMBER (starts 966 = KSA code) typed into the Amount field, not a deal value (human data-entry error)"
        else:
            reason += " — likely a corrupt/fat-finger deal amount"
        fix = ("A phone number was typed into the deal Amount field. Find the deal in "
               "HubSpot (read-only here → human), set Amount to the real SAR value, "
               "re-run collectors/hubspot_deals_bq.py") if phone else \
              ("Find the outlier deal in HubSpot (read-only here → human) and correct "
               "its amount; then re-run collectors/hubspot_deals_bq.py")
        return {"status": "BROKEN", "reason": reason, "fix": fix, "looks_like_phone": phone}
    return {"status": "HEALTHY", "today_amount_usd": round(today, 0), "median_90d_usd": round(median, 0)}


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


# ── Check 6: Databox Push Freshness ──────────────────────────────────────────

def check_databox_freshness(dataset_id: str, label: str) -> dict:
    """Did we push to this Databox dataset within _DATABOX_STALE_HOURS?

    Uses the Dataset Ingestion API:
      GET api.databox.com/v1/datasets/{id}/ingestions?limit=5
      Auth: x-api-key header (DATABOX_TOKEN = PAK)
    """
    import urllib.request
    import urllib.error

    token = os.getenv("DATABOX_TOKEN")
    if not token:
        return {"status": "WARNING",
                "reason": "DATABOX_TOKEN not set — cannot verify push freshness"}

    url = f"{_DATABOX_API_BASE}/v1/datasets/{dataset_id}/ingestions?limit=5"
    req = urllib.request.Request(
        url,
        headers={"x-api-key": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read(200).decode(errors="ignore")
        return {"status": "BROKEN",
                "reason": f"Databox API HTTP {e.code} for {label}: {body[:80]}",
                "fix": "Check DATABOX_TOKEN in Railway and re-run collectors/databox_pusher.py"}
    except Exception as e:
        return {"status": "BROKEN",
                "reason": f"Databox API unreachable for {label}: {str(e)[:80]}",
                "fix": "Check Railway network / DATABOX_TOKEN"}

    # Response is a list of ingestion objects (most recent first)
    # Each record: {id, status, createdAt, recordsCount, ...}
    ingestions = data if isinstance(data, list) else data.get("ingestions", [])
    if not ingestions:
        return {"status": "WARNING",
                "reason": f"No ingestion history found for {label} (dataset {dataset_id})"}

    latest = ingestions[0]
    status_str = (latest.get("status") or "unknown").lower()
    created_raw = latest.get("createdAt") or latest.get("created_at") or ""

    if not created_raw:
        return {"status": "WARNING",
                "reason": f"No timestamp on latest ingestion for {label}"}

    try:
        ts = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        hours_old = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except Exception:
        return {"status": "WARNING",
                "reason": f"Cannot parse ingestion timestamp for {label}: {created_raw[:30]}"}

    if status_str in ("failed", "error"):
        return {
            "status": "BROKEN",
            "reason": f"{label} last ingestion FAILED at {created_raw[:16]} — "
                      f"{latest.get('errors', '')[:80]}",
            "fix": "railway run python collectors/databox_pusher.py",
        }
    if hours_old > _DATABOX_BROKEN_HOURS:
        return {
            "status": "BROKEN",
            "reason": f"{label} not pushed in {hours_old:.0f}h (>{_DATABOX_BROKEN_HOURS}h)",
            "fix": "railway run python collectors/databox_pusher.py",
        }
    if hours_old > _DATABOX_STALE_HOURS:
        return {
            "status": "WARNING",
            "reason": f"{label} last pushed {hours_old:.0f}h ago (>{_DATABOX_STALE_HOURS}h — expected daily)",
        }

    records = latest.get("recordsCount", latest.get("records_count", "?"))
    return {"status": "HEALTHY", "hours_old": round(hours_old, 1), "records": records}


# ── Check 7: Railway App Health ───────────────────────────────────────────────

def check_railway_health() -> dict:
    """HTTP GET to /health — must return HTTP 200 within 10s."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(_RAILWAY_HEALTH_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
            body = resp.read(200).decode(errors="ignore")
    except urllib.error.HTTPError as e:
        return {
            "status": "BROKEN",
            "reason": f"/health returned HTTP {e.code}",
            "fix": "Check Railway deploy logs: https://railway.app",
        }
    except Exception as e:
        return {
            "status": "BROKEN",
            "reason": f"/health unreachable: {str(e)[:80]}",
            "fix": "Check Railway deploy status: https://railway.app",
        }

    if code != 200:
        return {
            "status": "BROKEN",
            "reason": f"/health returned HTTP {code} (expected 200)",
            "fix": "Check Railway deploy logs",
        }
    return {"status": "HEALTHY", "http_status": code}


# ── Check 8: Scheduler Execution ──────────────────────────────────────────────

def check_scheduler_ran(job_role: str = "daily_digest",
                        window_hours: int = _SCHEDULER_WINDOW_HOURS) -> dict:
    """Verify the daily job wrote a success row to agent_activity_log in the last 26h.

    The daily digest fires at 08:00 Riyadh. We allow 2h drift (→ 26h window)
    to avoid false alarms during daylight-saving edge cases.
    """
    proj, ds = _proj_ds()
    sql = f"""
        SELECT COUNT(*)    AS cnt,
               MAX(ts)     AS latest_run
        FROM `{proj}.{ds}.agent_activity_log`
        WHERE role   = '{job_role}'
          AND status = 'success'
          AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_hours} HOUR)
    """
    try:
        rows = _bq_query(sql)
        cnt    = int(rows[0].cnt or 0)       if rows else 0
        latest = str(rows[0].latest_run)     if rows and rows[0].latest_run else None
    except Exception as e:
        return {"status": "WARNING",
                "reason": f"Could not query agent_activity_log: {str(e)[:80]}"}

    if cnt == 0:
        return {
            "status": "BROKEN",
            "reason": f"No successful '{job_role}' run found in last {window_hours}h — daily job may have stalled",
            "fix": "railway run python main.py daily",
        }
    return {"status": "HEALTHY", "runs_in_window": cnt, "latest_run": latest}


# ── Aggregate per system monitor ──────────────────────────────────────────────

def run_system_check(monitor: dict) -> dict:
    """Run the appropriate check for one entry in SYSTEM_MONITORS."""
    mtype = monitor["type"]
    name  = monitor["name"]
    label = monitor.get("label", name)

    result = {
        "channel":     name,   # re-use 'channel' key so write_health_log is uniform
        "type":        mtype,
        "label":       label,
        "checks":      {},
        "status":      "HEALTHY",
        "fix_command": None,
    }

    if mtype == "railway":
        result["checks"]["health"] = check_railway_health()
    elif mtype == "scheduler":
        result["checks"]["execution"] = check_scheduler_ran(
            job_role=monitor.get("job_role", "daily_digest")
        )
    elif mtype == "databox":
        result["checks"]["push_freshness"] = check_databox_freshness(
            monitor["dataset_id"], label
        )
    else:
        result["checks"]["unknown"] = {"status": "WARNING",
                                       "reason": f"Unknown monitor type: {mtype}"}

    for _cn, cr in result["checks"].items():
        s = cr.get("status", "HEALTHY")
        if s == "BROKEN":
            result["status"] = "BROKEN"
            result["fix_command"] = cr.get("fix")
            break
        elif s == "WARNING" and result["status"] == "HEALTHY":
            result["status"] = "WARNING"

    result["checks_passed"] = sum(
        1 for c in result["checks"].values() if c.get("status") == "HEALTHY"
    )
    result["checks_failed"] = sum(
        1 for c in result["checks"].values() if c.get("status") in ("BROKEN", "WARNING")
    )
    result["last_checked_ts"] = datetime.now(_RIYADH).isoformat()
    return result


def run_system_checks() -> list[dict]:
    """Run all SYSTEM_MONITORS. Return list of structured results."""
    return [run_system_check(m) for m in SYSTEM_MONITORS]


# ── Check: Persistent WARNING escalation ─────────────────────────────────────

def check_persistent_warning(channel: str) -> dict:
    """If the last N consecutive health-log rows for this channel are all WARNING,
    escalate to BROKEN. Idle channels are exempt (they legitimately stay WARNING-
    suppressed). Returns HEALTHY when history is too short or mixed."""
    proj, ds = _proj_ds()
    sql = f"""
        SELECT status
        FROM `{proj}.{ds}.connector_health_log`
        WHERE channel = '{channel}'
        ORDER BY check_ts DESC
        LIMIT {_WARNING_ESCALATION_RUNS}
    """
    try:
        rows = _bq_query(sql)
    except Exception as e:
        # History unavailable — don't false-escalate
        return {"status": "HEALTHY", "note": f"escalation history check skipped: {str(e)[:60]}"}

    if len(rows) < _WARNING_ESCALATION_RUNS:
        return {"status": "HEALTHY", "note": f"only {len(rows)} history rows — need {_WARNING_ESCALATION_RUNS} to escalate"}

    statuses = [r.status for r in rows]
    if all(s == "WARNING" for s in statuses):
        return {
            "status": "BROKEN",
            "reason": (
                f"Channel has been WARNING for {_WARNING_ESCALATION_RUNS} consecutive "
                f"daily checks — escalated to BROKEN. Last statuses: {statuses}. "
                f"Fix: investigate root cause, then re-run the collector."
            ),
            "fix": f"railway run python {COLLECTOR_SCRIPTS.get(channel, 'collectors/' + channel + '_bq.py')} 3",
        }
    return {"status": "HEALTHY", "recent_statuses": statuses}


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
    if channel == "hubspot_deals":
        results["checks"]["amount_sanity"] = check_amount_sanity(table)
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

    # Persistent-WARNING escalation: only for active (non-idle) connectors.
    # Idle channels are exempt — they legitimately sit in WARNING-suppressed state.
    if not is_idle:
        results["checks"]["escalation"] = check_persistent_warning(channel)

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
    """Post health board to #nexa-health if any surface is BROKEN.

    Accepts a combined list of connector results + system monitor results.
    Both use the same {status, channel, checks_passed, fix_command} shape.
    """
    broken = [r for r in results if r["status"] == "BROKEN"]
    if not broken:
        return

    from notifications.slack_ping import post_ping
    health_channel = os.getenv("SLACK_CHANNEL_HEALTH", "#nexa-health")
    activity_url = os.getenv("ACTIVITY_SHORT_URL", "https://nexa-web-production-6a6b.up.railway.app/activity")

    # Split into sections for readability
    connector_results = [r for r in results if "bq_table" in r or r.get("type") is None]
    monitor_results   = [r for r in results if r.get("type") in ("railway", "scheduler", "databox")]

    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "BROKEN": "❌"}

    lines = [f"*SYSTEM HEALTH — {datetime.now(_RIYADH).strftime('%Y-%m-%d %H:%M')} Riyadh*", ""]

    if connector_results:
        lines.append("*Inbound connectors:*")
        for r in connector_results:
            n_checks = r["checks_passed"] + r["checks_failed"]
            fix_note = f" → `{r['fix_command']}`" if r.get("fix_command") else ""
            lines.append(f"  {emoji[r['status']]} *{r['channel']}* "
                         f"({r['checks_passed']}/{n_checks} passed){fix_note}")

    if monitor_results:
        lines.append("")
        lines.append("*Outbound / system monitors:*")
        for r in monitor_results:
            label = r.get("label", r["channel"])
            fix_note = f" → `{r['fix_command']}`" if r.get("fix_command") else ""
            lines.append(f"  {emoji[r['status']]} *{label}*{fix_note}")

    lines += ["", f"Overall: *{overall}*", f"Dashboard: {activity_url}"]
    headline = f"System health {overall}: {len(broken)} BROKEN surface(s)"

    try:
        post_ping(channel=health_channel, status="alert", headline=headline,
                  link=activity_url, role="health_monitor")
    except Exception as e:
        print(f"[connector_tracker] Slack post failed: {e}")


# ── Main entry point ──────────────────────────────────────────────────────────

def run_all_checks(post_slack: bool = True, write_bq: bool = True) -> dict:
    """
    Run all checks: 5 per inbound connector + 1 per system monitor.

    Returns:
        {
          "overall": "GREEN" | "AMBER" | "RED",
          "connectors": [...],   # inbound connector results
          "monitors": [...],     # system monitor results
          "broken_count": int,
          "warning_count": int,
          "healthy_count": int,
        }
    """
    connector_results = [run_connector_check(c) for c in CONNECTORS]
    monitor_results   = run_system_checks()
    all_results       = connector_results + monitor_results

    broken  = sum(1 for r in all_results if r["status"] == "BROKEN")
    warning = sum(1 for r in all_results if r["status"] == "WARNING")
    healthy = sum(1 for r in all_results if r["status"] == "HEALTHY")

    overall = "RED" if broken > 0 else ("AMBER" if warning > 0 else "GREEN")

    if write_bq:
        try:
            write_health_log(all_results)
        except Exception as e:
            print(f"[connector_tracker] BQ write failed: {e}")

    if post_slack and broken > 0:
        post_status_board(all_results, overall)

    return {
        "overall":       overall,
        "connectors":    connector_results,
        "monitors":      monitor_results,
        "broken_count":  broken,
        "warning_count": warning,
        "healthy_count": healthy,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Running system health checks (connectors + outbound monitors)...\n")
    summary = run_all_checks(post_slack=False, write_bq=False)

    emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "BROKEN": "❌"}

    print("── Inbound connectors ──────────────────────────────────────────")
    for r in summary["connectors"]:
        n_checks = r["checks_passed"] + r["checks_failed"]
        print(f"{emoji[r['status']]} {r['channel']:18s} — {r['status']} "
              f"({r['checks_passed']}/{n_checks} passed)")
        if r.get("fix_command"):
            print(f"   Fix: {r['fix_command']}")
        for check_name, check_result in r["checks"].items():
            cs = check_result.get("status", "?")
            if cs != "HEALTHY":
                reason = check_result.get("reason") or check_result.get("error") or check_result.get("note", "")
                print(f"   ⚠ {check_name}: {cs} — {reason}")

    print()
    print("── Outbound / system monitors ──────────────────────────────────")
    for r in summary["monitors"]:
        label = r.get("label", r["channel"])
        print(f"{emoji[r['status']]} {label:30s} — {r['status']}")
        if r.get("fix_command"):
            print(f"   Fix: {r['fix_command']}")
        for check_name, check_result in r["checks"].items():
            cs = check_result.get("status", "?")
            if cs != "HEALTHY":
                reason = check_result.get("reason") or check_result.get("error") or check_result.get("note", "")
                print(f"   ⚠ {check_name}: {cs} — {reason}")

    print(f"\nOverall: {summary['overall']} | "
          f"✅ {summary['healthy_count']} healthy | "
          f"⚠️ {summary['warning_count']} warning | "
          f"❌ {summary['broken_count']} broken")
