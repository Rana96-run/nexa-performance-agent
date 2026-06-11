"""
analysers/ga4_analysis.py
=========================
Week-over-week GA4 session and conversion analysis.

Reads ga4_sessions_daily from BQ; detects significant drops (>20%) in
sessions, engaged sessions, conversions, or average session duration.
Creates an Asana task for project-coordinator when a drop exceeds the threshold.

Entry points:
  analyse_wow(days_current=7) → dict with period comparison + flags
  create_alert_tasks(analysis)  → Asana task GID list if flags exist

Cadence: called by reporting_scheduler on the 6h data refresh cycle.
         The alert fires at most once per 24h (dedup via agent_activity_log).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

_DROP_THRESHOLD = 0.20       # flag if metric drops > 20% WoW
_CONV_DROP_THRESHOLD = 0.15  # conversions are noisier — flag at 15%
_DEDUP_WINDOW_HOURS = 24     # don't re-alert within 24h for same metric


def analyse_wow(days_current: int = 7) -> dict[str, Any]:
    """Compare current N-day window vs prior N-day window for all GA4 metrics.

    Returns:
      {
        "period": {"current": (start, end), "prior": (start, end)},
        "metrics": {
          "sessions":               {"current": int, "prior": int, "pct_change": float},
          "engaged_sessions":       {...},
          "conversions":            {...},
          "avg_session_duration_s": {...},
          "new_users":              {...},
        },
        "flags": [{"metric": str, "drop_pct": float, "direction": "down"|"up"}],
        "source_rows": int,
      }
    """
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET

    today   = date.today()
    cur_end = today - timedelta(days=1)           # yesterday
    cur_st  = cur_end - timedelta(days=days_current - 1)
    pri_end = cur_st - timedelta(days=1)
    pri_st  = pri_end - timedelta(days=days_current - 1)

    sql = f"""
        WITH agg AS (
          SELECT
            CASE
              WHEN date BETWEEN '{cur_st}' AND '{cur_end}' THEN 'current'
              WHEN date BETWEEN '{pri_st}' AND '{pri_end}' THEN 'prior'
            END AS period,
            SUM(sessions)                AS sessions,
            SUM(engaged_sessions)        AS engaged_sessions,
            SUM(new_users)               AS new_users,
            SUM(conversions)             AS conversions,
            SUM(avg_session_duration_s * sessions) AS total_duration_s,
            SUM(sessions) AS sess_for_avg
          FROM `{PROJECT_ID}.{DATASET}.ga4_sessions_daily`
          WHERE date BETWEEN '{pri_st}' AND '{cur_end}'
          GROUP BY period
        )
        SELECT * FROM agg WHERE period IS NOT NULL
    """

    try:
        client = get_client()
        rows   = {r.period: r for r in client.query(sql).result()}
    except Exception as e:
        return {"error": str(e), "flags": []}

    def _val(period: str, col: str) -> float:
        row = rows.get(period)
        if not row:
            return 0.0
        return float(getattr(row, col, 0) or 0)

    def _avg_dur(period: str) -> float:
        sess = _val(period, "sess_for_avg")
        if sess == 0:
            return 0.0
        return _val(period, "total_duration_s") / sess

    metrics: dict[str, dict] = {}
    for key, cur_fn, pri_fn in [
        ("sessions",               lambda: _val("current", "sessions"),           lambda: _val("prior", "sessions")),
        ("engaged_sessions",       lambda: _val("current", "engaged_sessions"),   lambda: _val("prior", "engaged_sessions")),
        ("new_users",              lambda: _val("current", "new_users"),          lambda: _val("prior", "new_users")),
        ("conversions",            lambda: _val("current", "conversions"),        lambda: _val("prior", "conversions")),
        ("avg_session_duration_s", lambda: _avg_dur("current"),                  lambda: _avg_dur("prior")),
    ]:
        cur = cur_fn()
        pri = pri_fn()
        pct = ((cur - pri) / pri) if pri > 0 else 0.0
        metrics[key] = {"current": round(cur, 1), "prior": round(pri, 1), "pct_change": round(pct, 4)}

    # Flag significant drops
    flags: list[dict] = []
    thresholds = {
        "sessions":               _DROP_THRESHOLD,
        "engaged_sessions":       _DROP_THRESHOLD,
        "new_users":              _DROP_THRESHOLD,
        "conversions":            _CONV_DROP_THRESHOLD,
        "avg_session_duration_s": _DROP_THRESHOLD,
    }
    for metric, threshold in thresholds.items():
        pct = metrics[metric]["pct_change"]
        if pct <= -threshold:
            flags.append({"metric": metric, "drop_pct": abs(pct), "direction": "down"})

    return {
        "period": {
            "current": (str(cur_st), str(cur_end)),
            "prior":   (str(pri_st), str(pri_end)),
        },
        "metrics":     metrics,
        "flags":       flags,
        "source_rows": len(rows),
    }


def _already_alerted(window_hours: int = _DEDUP_WINDOW_HOURS) -> bool:
    """True if we already created a GA4 alert Asana task in the last window_hours."""
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        rows = list(get_client().query(f"""
            SELECT COUNT(*) AS n
            FROM `{PROJECT_ID}.{DATASET}.agent_activity_log`
            WHERE role   = 'growth_analyst'
              AND action = 'ga4_alert_created'
              AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_hours} HOUR)
        """).result())
        return (rows[0].n > 0) if rows else False
    except Exception:
        return False


def create_alert_tasks(analysis: dict[str, Any]) -> list[str]:
    """Create an Asana task for project-coordinator when GA4 flags exist.
    Returns list of task GIDs created (empty if no flags or already alerted)."""
    flags = analysis.get("flags", [])
    if not flags or analysis.get("error"):
        return []
    if _already_alerted():
        return []

    from executors.asana import create_task
    from logs.activity_logger import log_activity
    from datetime import date as _date

    today  = _date.today().isoformat()
    period = analysis.get("period", {})
    cur_w  = " – ".join(period.get("current", ["?", "?"]))
    pri_w  = " – ".join(period.get("prior",   ["?", "?"]))

    metric_lines = []
    for f in flags:
        m   = f["metric"].replace("_", " ")
        pct = round(f["drop_pct"] * 100, 1)
        cur = analysis["metrics"][f["metric"]]["current"]
        pri = analysis["metrics"][f["metric"]]["prior"]
        metric_lines.append(f"  - {m}: {pri:.0f} → {cur:.0f}  (-{pct}%)")

    desc_lines = [
        f"GA4 week-over-week drop detected — {today}",
        f"Current period: {cur_w}",
        f"Prior period:   {pri_w}",
        "",
        "FLAGGED METRICS:",
        *metric_lines,
        "",
        "NEXT STEPS:",
        "1. [Project Coordinator] Check GA4 property 517912363 for the same period — confirm the drop is real.",
        "2. [Project Coordinator] Check GTM container GTM-TFH26VC2 for any tag changes (filter by date).",
        "3. [Project Coordinator] Verify Meta pixel Lead event and GA4 config tag are live.",
        "4. [Growth Analyst] Compare against paid channel spend/sessions from campaigns_daily for the same window.",
        "5. [Growth Analyst] Document root cause in memory/14_learning_patterns.md.",
        "",
        f"Created: {today}\nDue: {today}\nPriority: High",
        "Type: Investigation\nChannel: ga4\nAsset level: analytics\nAction: investigate → [Project Coordinator]",
    ]

    gid = create_task(
        title=f"GA4 WoW drop — {len(flags)} metric(s) down >15% — {cur_w}",
        description="\n".join(desc_lines),
        project_key="daily_activity",
        task_type="Investigation",
        channel="ga4",
        asset_level="analytics",
        action="investigate",
        log_role="growth_analyst",
    )

    if gid:
        try:
            log_activity(role="growth_analyst", action="ga4_alert_created",
                         status="success", channel="ga4",
                         details={"flags": len(flags), "task_gid": gid})
        except Exception:
            pass
        return [gid]
    return []
