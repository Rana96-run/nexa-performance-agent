"""
reports/app.py
==============
Thin Flask app for the Nexa Performance Agent activity dashboard.

Routes:
  GET  /health                      → {"status": "ok"}
  GET  /                            → redirect to /activity
  GET  /activity                    → self-contained HTML dashboard

No secrets, no subprocesses, no background threads.
On-demand runs are triggered manually in the n8n UI.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, redirect, Response


# BQ coordinates (fallback to known defaults)
BQ_PROJECT = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
BQ_DATASET = os.getenv("BQ_DATASET", "qoyod_marketing")

# n8n Cloud base URL
N8N_BASE = "https://qoyod.app.n8n.cloud/workflow"

# n8n workflow IDs
N8N_WORKFLOWS = {
    "orchestrator":    "T8icImtZFLYeCa7e",
    "weekly":          "iNSdpXH7Rc9Lb8h8",
    "monthly":         "0Zh45UoTtjjhRn8U",
    "growth_analyst":  "MHCdIiAtKzHNve1x",
    "perf_lead":       "Qd5SoGxZbgT1ohYP",
    "cro":             "jfE5KKnPJQBf7MCj",
    "qual":            "PxFBmtXDVgcNGzIM",
    "campaign_mgr":    "eL0V6ReftV2U1wNf",
    "creative":        "smHaEhWloComRQyz",
    "qa":              "ug3niLKrjPfO9Iz7",
    "data_collection": "jOnJxdpdaO3Vbi0B",
    "approval":        "5Acqsbxsk0XQ5k9e",
}

# Connectors tracked in the health cards
# (name, display_key) — display_key is used as the dict key in _get_connector_health()
CONNECTORS = [
    ("Meta",            "Meta"),
    ("Google Ads",      "Google Ads"),
    ("Snapchat",        "Snapchat"),
    ("TikTok",          "TikTok"),
    ("LinkedIn",        "LinkedIn"),
    ("Microsoft Ads",   "Microsoft Ads"),
    ("GA4",             "GA4"),
    ("GSC",             "GSC"),
    ("HubSpot Leads",   "HubSpot Leads"),
    ("HubSpot Deals",   "HubSpot Deals"),
    ("GTM Audit",       "GTM Audit"),
]


# ─── BigQuery helper ──────────────────────────────────────────────────────────

def _bq_query(sql: str) -> list[dict[str, Any]]:
    """Run a BQ query and return rows as list-of-dicts.

    Uses google-cloud-bigquery (already in requirements.txt).
    Returns [] silently on any error so the page never crashes.
    """
    try:
        from google.oauth2 import service_account
        from google.cloud import bigquery

        # Prefer JSON blob (Railway env var), then file path (local dev)
        creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if creds_json:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            client = bigquery.Client(project=BQ_PROJECT, credentials=creds)
        elif creds_path:
            client = bigquery.Client(project=BQ_PROJECT)
        else:
            return []

        rows = client.query(sql).result()
        return [dict(row) for row in rows]
    except Exception as e:
        import logging
        logging.getLogger("reports.app").error(f"[dashboard] BQ query failed: {e}\nSQL: {sql[:200]}")
        return []  # keep returning [] so dashboard doesn't crash, but now it's visible in logs


# ─── Monitoring data fetchers ─────────────────────────────────────────────────

def _get_system_health() -> dict[str, Any]:
    """Return freshness info for the health bar."""
    rows = _bq_query(f"""
        SELECT MAX(ts) AS last_ts
        FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
    """)
    last_ts = None
    if rows and rows[0].get("last_ts"):
        last_ts = rows[0]["last_ts"]
    return {"last_ts": last_ts}


def _get_connector_health() -> dict[str, dict[str, Any]]:
    """Return freshness info per connector from all source tables.

    Returns a dict keyed by display name (matching CONNECTORS), each value is
    {"last_date": date_obj_or_None, "days_stale": int_or_None}.

    Sources:
    - campaigns_daily (GROUP BY channel) → Meta, Google Ads, Snapchat, TikTok, LinkedIn, Microsoft Ads
    - youtube_daily, ga4_daily, gsc_daily → YouTube, GA4, GSC
    - hubspot_leads_module_daily → HubSpot Leads
    - hubspot_deals_daily → HubSpot Deals
    - agent_activity_log (GTM audit entries) → GTM Audit
    """
    result: dict[str, dict[str, Any]] = {}

    # ── 1. Paid channels from campaigns_daily (GROUP BY channel) ──────────────
    ad_rows = _bq_query(f"""
        SELECT channel, MAX(date) AS last_date,
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY) AS days_stale
        FROM `{BQ_PROJECT}.{BQ_DATASET}.campaigns_daily`
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
        GROUP BY channel
    """)
    # campaigns_daily.channel stores lowercase slugs (e.g. 'meta', 'google_ads').
    # Map them to the display names used in CONNECTORS so the health cards populate.
    _SLUG_TO_DISPLAY = {
        "meta":          "Meta",
        "google_ads":    "Google Ads",
        "snapchat":      "Snapchat",
        "tiktok":        "TikTok",
        "linkedin":      "LinkedIn",
        "microsoft_ads": "Microsoft Ads",
        "hubspot_leads": "HubSpot Leads",
    }
    for r in ad_rows:
        ch = r.get("channel")
        if ch:
            display_key = _SLUG_TO_DISPLAY.get(ch, ch)
            result[display_key] = {"last_date": r.get("last_date"), "days_stale": r.get("days_stale")}

    # ── 2. Organic / analytics tables ─────────────────────────────────────────
    organic_rows = _bq_query(f"""
        SELECT 'YouTube' AS channel, MAX(date) AS last_date,
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY) AS days_stale
        FROM `{BQ_PROJECT}.{BQ_DATASET}.youtube_daily`
        UNION ALL
        SELECT 'GA4', MAX(date),
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY)
        FROM `{BQ_PROJECT}.{BQ_DATASET}.ga4_daily`
        UNION ALL
        SELECT 'GSC', MAX(date),
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY)
        FROM `{BQ_PROJECT}.{BQ_DATASET}.gsc_daily`
    """)
    for r in organic_rows:
        ch = r.get("channel")
        if ch:
            result[ch] = {"last_date": r.get("last_date"), "days_stale": r.get("days_stale")}

    # ── 3. HubSpot tables ─────────────────────────────────────────────────────
    hs_rows = _bq_query(f"""
        SELECT 'HubSpot Leads' AS channel, MAX(date) AS last_date,
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY) AS days_stale
        FROM `{BQ_PROJECT}.{BQ_DATASET}.hubspot_leads_module_daily`
        UNION ALL
        SELECT 'HubSpot Deals', MAX(date),
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY)
        FROM `{BQ_PROJECT}.{BQ_DATASET}.hubspot_deals_daily`
    """)
    for r in hs_rows:
        ch = r.get("channel")
        if ch:
            result[ch] = {"last_date": r.get("last_date"), "days_stale": r.get("days_stale")}

    # ── 4. GTM Audit — check agent_activity_log for GTM entries ───────────────
    gtm_rows = _bq_query(f"""
        SELECT MAX(DATE(ts, 'Asia/Riyadh')) AS last_date,
               DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(DATE(ts, 'Asia/Riyadh')), DAY) AS days_stale
        FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
        WHERE action LIKE '%gtm%' OR action LIKE '%GTM%' OR details LIKE '%GTM%'
    """)
    if gtm_rows:
        result["GTM Audit"] = {
            "last_date": gtm_rows[0].get("last_date"),
            "days_stale": gtm_rows[0].get("days_stale"),
        }
    else:
        result["GTM Audit"] = {"last_date": None, "days_stale": None}

    return result


def _get_heatmap_data() -> list[dict[str, Any]]:
    """Return activity counts grouped by day-of-week and hour for last 7 days."""
    return _bq_query(f"""
        SELECT
            EXTRACT(DAYOFWEEK FROM ts AT TIME ZONE 'Asia/Riyadh') AS dow,
            EXTRACT(HOUR     FROM ts AT TIME ZONE 'Asia/Riyadh') AS hr,
            COUNT(*) AS cnt
        FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        GROUP BY dow, hr
        ORDER BY dow, hr
    """)


def _get_recent_activity() -> list[dict[str, Any]]:
    """Return last 20 activity log rows."""
    return _bq_query(f"""
        SELECT
            ts,
            role,
            action,
            status,
            channel,
            details
        FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
        ORDER BY ts DESC
        LIMIT 20
    """)


# ─── Status helpers ───────────────────────────────────────────────────────────

def _freshness_status(ts: Any) -> tuple[str, str]:
    """Return (css_color_var, label) from a timestamp."""
    if ts is None:
        return "var(--muted)", "No data"
    now = datetime.now(timezone.utc)
    if hasattr(ts, "replace"):
        ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    delta_h = (now - ts).total_seconds() / 3600
    if delta_h < 12:
        return "var(--green)", f"{int(delta_h)}h ago"
    elif delta_h < 24:
        return "var(--orange)", f"{int(delta_h)}h ago"
    else:
        return "#e05c5c", f"{int(delta_h)}h ago"


def _staleness_color(days_stale: Any, lag: int = 0) -> str:
    """Return CSS color for a days-stale integer.
    lag: expected natural lag (e.g. 1 for TikTok which always writes yesterday).
    Effective stale = days_stale - lag; green ≤0, yellow 1, red ≥2."""
    if days_stale is None:
        return "var(--muted)"
    try:
        d = int(days_stale) - lag
    except (TypeError, ValueError):
        return "var(--muted)"
    if d <= 0:
        return "var(--green)"
    elif d == 1:
        return "var(--orange)"
    else:
        return "#e05c5c"


def _ts_fmt(ts: Any) -> str:
    """Format a BQ timestamp for display."""
    if ts is None:
        return "—"
    if hasattr(ts, "strftime"):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.strftime("%b %d %H:%M UTC")
    return str(ts)


# ─── App factory ─────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "nexa-activity-dashboard"})

    @app.get("/")
    def root():
        return redirect("/activity", code=302)

    @app.get("/activity")
    def activity():
        system_health      = _get_system_health()
        connector_map      = _get_connector_health()
        heatmap_rows       = _get_heatmap_data()
        activity_rows      = _get_recent_activity()
        recent_actions     = _get_recent_actions()
        open_tasks         = _get_open_asana_tasks()
        done_tasks         = _get_done_asana_tasks()
        rescheduled_tasks  = _get_rescheduled_asana_tasks()
        return _render_dashboard(
            system_health, connector_map, heatmap_rows, activity_rows,
            recent_actions, open_tasks, done_tasks, rescheduled_tasks,
        )

    @app.get("/api/day-detail/<date>")
    def day_detail(date: str):
        import re
        # Basic validation — YYYY-MM-DD
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return jsonify({"rows": [], "error": "Invalid date format"})
        try:
            rows = _bq_query(f"""
                SELECT role, action, channel, status, details,
                       FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', ts) AS created_at
                FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
                WHERE DATE(ts, 'Asia/Riyadh') = '{date}'
                ORDER BY ts DESC
                LIMIT 50
            """)
            return jsonify({"rows": rows})
        except Exception as exc:
            return jsonify({"rows": [], "error": str(exc)})

    return app


# ─── Monitoring HTML builders ─────────────────────────────────────────────────

def _build_health_bar(system_health: dict[str, Any]) -> str:
    last_ts = system_health.get("last_ts")
    color, label = _freshness_status(last_ts)
    bq_dot = f'<span class="hdot" style="background:{color};box-shadow:0 0 5px {color}"></span>'

    import datetime as _dt
    import pytz as _pytz
    _riyadh = _pytz.timezone("Asia/Riyadh")
    _now_riyadh = _dt.datetime.now(_riyadh)
    _next_8am = _now_riyadh.replace(hour=8, minute=0, second=0, microsecond=0)
    if _now_riyadh >= _next_8am:
        _next_8am += _dt.timedelta(days=1)
    _diff = _next_8am - _now_riyadh
    _next_run_h = int(_diff.total_seconds() // 3600)
    _next_run_m = int((_diff.total_seconds() % 3600) // 60)
    next_run_label = f"{_next_run_h}h {_next_run_m}m"

    return f"""
<div class="hbar">
  <div class="hchip">
    {bq_dot}
    <span class="hlabel">BQ Activity</span>
    <span class="hval" style="color:{color}">{label}</span>
  </div>
  <div class="hchip">
    <span class="hdot" style="background:var(--green);box-shadow:0 0 5px var(--green)"></span>
    <span class="hlabel">n8n Master</span>
    <span class="hval" style="color:var(--muted)">Daily 08:00 AST</span>
  </div>
  <div class="hchip">
    <span class="hdot" style="background:var(--green);box-shadow:0 0 5px var(--green)"></span>
    <span class="hlabel">GitHub Actions</span>
    <span class="hval" style="color:var(--muted)">Every 6h</span>
  </div>
  <div class="hchip">
    <span class="hdot" style="background:var(--green);box-shadow:0 0 5px var(--green)"></span>
    <span class="hlabel">Railway</span>
    <span class="hval" style="color:var(--green)">Serving</span>
  </div>
  <div class="hchip">
    <span class="hlabel">⏱ Next run in</span>
    <span class="hval" style="color:var(--muted)">{next_run_label}</span>
  </div>
  <div class="hchip">
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['data_collection']}" target="_blank" class="n8n-link">Data Collection &rarr;</a>
  </div>
  <div class="hchip">
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['approval']}" target="_blank" class="n8n-link">Approval Listener &rarr;</a>
  </div>
</div>"""


def _build_connector_cards(connector_map: dict[str, Any]) -> str:
    cards = []
    for name, key in CONNECTORS:
        # key == name in the new scheme; fall back to name if key not found
        info = connector_map.get(key) or connector_map.get(name) or {}
        last_date  = info.get("last_date")
        days_stale = info.get("days_stale")

        # TikTok always writes yesterday by design — 1d stale is normal
        lag = 1 if name == "TikTok" else 0
        color = _staleness_color(days_stale, lag=lag)

        if last_date is None:
            date_str   = "No data"
            stale_str  = "—"
        else:
            # last_date may be a datetime.date or datetime.datetime object
            if hasattr(last_date, "strftime"):
                date_str = last_date.strftime("%Y-%m-%d")
            else:
                date_str = str(last_date)
            d = int(days_stale) if days_stale is not None else 0
            effective = d - lag
            stale_str = "Fresh" if effective <= 0 else f"{d}d stale"

        cards.append(f"""
    <div class="conn-card">
      <div class="conn-top">
        <span class="conn-name">{name}</span>
        <span class="conn-dot" style="background:{color};box-shadow:0 0 4px {color}"></span>
      </div>
      <div class="conn-ts">{date_str}</div>
      <div class="conn-status" style="color:{color}">{stale_str}</div>
    </div>""")
    return "\n".join(cards)


def _build_heatmap(heatmap_rows: list[dict[str, Any]]) -> str:
    import datetime as _dt
    import pytz as _pytz

    # dow: 1=Sun … 7=Sat in BQ DAYOFWEEK. We show Mon–Sun (2–7, 1).
    DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    DOW_ORDER  = [2, 3, 4, 5, 6, 7, 1]  # Mon=2 … Sat=7, Sun=1

    lookup: dict[tuple[int, int], int] = {}
    for r in heatmap_rows:
        lookup[(int(r["dow"]), int(r["hr"]))] = int(r["cnt"])

    max_cnt = max(lookup.values(), default=1)

    # Build a dow → YYYY-MM-DD mapping for the last 7 days (Riyadh time)
    _riyadh = _pytz.timezone("Asia/Riyadh")
    _today = _dt.datetime.now(_riyadh).date()
    dow_to_date: dict[int, str] = {}
    for delta in range(7):
        d = _today - _dt.timedelta(days=delta)
        # Python isoweekday: Mon=1…Sun=7; BQ DAYOFWEEK: Sun=1…Sat=7
        py_dow = d.isoweekday()  # 1=Mon … 7=Sun
        bq_dow = (py_dow % 7) + 1  # convert: Mon→2, Tue→3, … Sun→1
        dow_to_date[bq_dow] = d.strftime("%Y-%m-%d")

    hour_headers = "".join(
        f'<th class="hm-h">{h:02d}</th>' for h in range(24)
    )

    rows_html = []
    for i, dow in enumerate(DOW_ORDER):
        date_str = dow_to_date.get(dow, "")
        cells = []
        for hr in range(24):
            cnt = lookup.get((dow, hr), 0)
            intensity = int((cnt / max_cnt) * 255) if max_cnt else 0
            bg = f"rgba(0,255,136,{intensity/255:.2f})" if cnt else "var(--border)"
            title_attr = f"{cnt} events" if cnt else "no activity"
            if cnt > 0 and date_str:
                cells.append(
                    f'<td class="hm-cell" style="background:{bg};cursor:pointer" '
                    f'title="{title_attr}" data-date="{date_str}" '
                    f'onclick="showDayDetail(\'{date_str}\')"></td>'
                )
            else:
                cells.append(
                    f'<td class="hm-cell" style="background:{bg};cursor:default" title="{title_attr}"></td>'
                )
        rows_html.append(
            f'<tr><th class="hm-row">{DOW_LABELS[i]}</th>{"".join(cells)}</tr>'
        )

    return f"""
<div class="hm-wrap">
  <table class="hm-table">
    <thead><tr><th></th>{hour_headers}</tr></thead>
    <tbody>{"".join(rows_html)}</tbody>
  </table>
  <div class="hm-legend">
    <span style="color:var(--muted);font-size:11px">Less</span>
    <div class="hm-grad"></div>
    <span style="color:var(--muted);font-size:11px">More</span>
    <span style="color:var(--muted);font-size:11px;margin-left:16px">Asia/Riyadh &middot; last 7 days &middot; click a cell to drill down</span>
  </div>
</div>
<div id="day-detail-panel" style="display:none"></div>"""


def _get_recent_actions() -> list[dict[str, Any]]:
    """Return last 10 entries from agent_activity_log for the Actions panel."""
    return _bq_query(f"""
        SELECT role, action, status, channel, ts
        FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
        ORDER BY ts DESC
        LIMIT 10
    """)


def _get_open_asana_tasks() -> list[dict[str, Any]]:
    """Return open Asana tasks from asana_task_status."""
    return _bq_query(f"""
        SELECT title, assignee_name, due_on, project_key, completed
        FROM `{BQ_PROJECT}.{BQ_DATASET}.asana_task_status`
        WHERE completed = FALSE
        AND title IS NOT NULL
        AND title != ''
        AND title NOT LIKE '[Direct Log]%'
        AND title NOT LIKE '[Agent Connection Test]%'
        ORDER BY due_on ASC
        LIMIT 10
    """)


def _get_done_asana_tasks() -> list[dict[str, Any]]:
    """Return Asana tasks completed in the last 7 days."""
    return _bq_query(f"""
        SELECT title, assignee_name, due_on, project_key, completed_at
        FROM `{BQ_PROJECT}.{BQ_DATASET}.asana_task_status`
        WHERE completed = TRUE
        AND completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        AND title IS NOT NULL
        AND title != ''
        AND title NOT LIKE '[Direct Log]%'
        AND title NOT LIKE '[Agent Connection Test]%'
        ORDER BY completed_at DESC
        LIMIT 10
    """)


def _get_rescheduled_asana_tasks() -> list[dict[str, Any]]:
    """Return open rescheduled Asana tasks (rescheduled = TRUE column).

    Returns empty list if the column does not exist — caller handles gracefully.
    """
    return _bq_query(f"""
        SELECT title, assignee_name, due_on, project_key
        FROM `{BQ_PROJECT}.{BQ_DATASET}.asana_task_status`
        WHERE completed = FALSE
        AND rescheduled = TRUE
        AND title IS NOT NULL
        AND title != ''
        AND title NOT LIKE '[Direct Log]%'
        AND title NOT LIKE '[Agent Connection Test]%'
        ORDER BY due_on ASC
        LIMIT 10
    """)


def _build_activity_feed(activity_rows: list[dict[str, Any]]) -> str:
    if not activity_rows:
        return '<div class="feed-empty">No activity in the last 7 days — BQ may be unreachable</div>'

    STATUS_COLOR = {
        "success":          "var(--green)",
        "failed":           "#e05c5c",
        "skipped":          "var(--muted)",
        "pending_approval": "var(--orange)",
        "approved":         "var(--green)",
        "rejected":         "#e05c5c",
    }

    items = []
    for r in activity_rows:
        ts_str  = _ts_fmt(r.get("ts"))
        role    = r.get("role") or "—"
        action  = r.get("action") or "—"
        status  = r.get("status") or "—"
        channel = r.get("channel") or ""
        color   = STATUS_COLOR.get(status, "var(--dim)")
        ch_tag  = f'<span class="feed-ch">{channel}</span>' if channel else ""
        items.append(f"""
    <div class="feed-row">
      <span class="feed-ts">{ts_str}</span>
      <span class="feed-role">{role}</span>
      {ch_tag}
      <span class="feed-action">{action}</span>
      <span class="feed-badge" style="color:{color};border-color:{color}">{status}</span>
    </div>""")

    return "\n".join(items)


def _build_actions_tasks(
    recent_actions: list[dict[str, Any]],
    open_tasks: list[dict[str, Any]],
    done_tasks: list[dict[str, Any]] | None = None,
    rescheduled_tasks: list[dict[str, Any]] | None = None,
) -> str:
    """Build the Actions & Tasks section."""
    import datetime as _dt
    import pytz as _pytz
    _riyadh = _pytz.timezone("Asia/Riyadh")
    _today = _dt.datetime.now(_riyadh).date()

    done_tasks        = done_tasks or []
    rescheduled_tasks = rescheduled_tasks or []

    # Column 1 — Recent Actions
    if recent_actions:
        action_items = []
        _now_utc = datetime.now(timezone.utc)
        for r in recent_actions:
            role    = r.get("role") or "—"
            action  = r.get("action") or "—"
            status  = (r.get("status") or "—").lower()
            channel = r.get("channel") or ""
            ts      = r.get("ts")
            if ts is not None:
                if hasattr(ts, "replace"):
                    ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
                delta_m = int((_now_utc - ts).total_seconds() / 60)
                if delta_m < 60:
                    ago = f"{delta_m}m ago"
                elif delta_m < 1440:
                    ago = f"{delta_m // 60}h ago"
                else:
                    ago = f"{delta_m // 1440}d ago"
            else:
                ago = "—"
            ch_part = f" &middot; {channel}" if channel else ""
            if status == "success":
                sc = "at-status-ok"
            elif status in ("failed", "error"):
                sc = "at-status-fail"
            else:
                sc = "at-status-pend"
            action_items.append(
                f'<div class="at-row">'
                f'<span class="at-role">{role}</span>'
                f'<span style="flex:1">{action}{ch_part}</span>'
                f'<span class="{sc}">{status}</span>'
                f'<span style="color:var(--muted);font-size:10px;margin-left:6px">{ago}</span>'
                f'</div>'
            )
        actions_html = "\n".join(action_items)
    else:
        actions_html = '<div class="at-empty">No recent actions — Daily workflow has not completed yet</div>'

    def _task_due_str(due: Any, today: Any) -> tuple[str, bool]:
        """Return (due_str, is_overdue)."""
        if due is None:
            return "—", False
        if hasattr(due, "strftime"):
            due_str = due.strftime("%Y-%m-%d")
            d = due.date() if hasattr(due, "date") else due
            return due_str, d < today
        return str(due), False

    # Open tasks column
    if open_tasks:
        task_items = []
        for r in open_tasks:
            name       = r.get("title") or "—"
            assign     = r.get("assignee_name") or ""
            due_str, overdue = _task_due_str(r.get("due_on"), _today)
            proj       = r.get("project_key") or ""
            overdue_cls = " at-overdue" if overdue else ""
            assign_part = f" &middot; {assign}" if assign else ""
            proj_part   = f'<span style="color:var(--muted);font-size:10px">{proj}</span>' if proj else ""
            task_items.append(
                f'<div class="at-row">'
                f'<span style="flex:1">{name}{assign_part} {proj_part}</span>'
                f'<span class="at-status-pend{overdue_cls}">{due_str}</span>'
                f'</div>'
            )
        open_html = "\n".join(task_items)
    else:
        open_html = '<div class="at-empty">No open tasks found</div>'

    # Rescheduled tasks column (may be empty if column absent in BQ)
    if rescheduled_tasks:
        rescheduled_items = []
        for r in rescheduled_tasks:
            name    = r.get("title") or "—"
            assign  = r.get("assignee_name") or ""
            due_str, _ = _task_due_str(r.get("due_on"), _today)
            assign_part = f" &middot; {assign}" if assign else ""
            rescheduled_items.append(
                f'<div class="at-row">'
                f'<span style="flex:1">{name}{assign_part}</span>'
                f'<span class="at-status-pend">{due_str}</span>'
                f'</div>'
            )
        rescheduled_html = "\n".join(rescheduled_items)
    else:
        rescheduled_html = '<div class="at-empty">No rescheduled tasks</div>'

    # Done tasks column (last 7d)
    if done_tasks:
        done_items = []
        for r in done_tasks:
            name       = r.get("title") or "—"
            completed  = r.get("completed_at")
            if completed is not None and hasattr(completed, "strftime"):
                comp_str = completed.strftime("%Y-%m-%d")
            elif completed is not None:
                comp_str = str(completed)[:10]
            else:
                comp_str = "—"
            done_items.append(
                f'<div class="at-row">'
                f'<span style="flex:1">{name}</span>'
                f'<span class="at-status-ok">{comp_str}</span>'
                f'</div>'
            )
        done_html = "\n".join(done_items)
    else:
        done_html = '<div class="at-empty">No tasks completed in last 7 days</div>'

    return f"""
<div class="at-grid at-grid-tasks">

  <!-- Recent Actions -->
  <div class="at-card">
    <div class="at-title">Recent Actions</div>
    {actions_html}
  </div>

  <!-- Open Tasks -->
  <div class="at-card at-scrollable">
    <div class="at-title">Open Tasks</div>
    {open_html}
  </div>

  <!-- Rescheduled Tasks -->
  <div class="at-card at-scrollable">
    <div class="at-title">Rescheduled</div>
    {rescheduled_html}
  </div>

  <!-- Done (last 7d) -->
  <div class="at-card at-scrollable">
    <div class="at-title">Done — Last 7d</div>
    {done_html}
  </div>

  <!-- Pending Approvals -->
  <div class="at-card">
    <div class="at-title">Pending Approvals</div>
    <div style="font-size:12px;color:var(--dim);line-height:1.7">
      Approvals are managed in Slack <strong>#approvals</strong>.<br>
      React <strong>&#10003;</strong> to execute all scale + pause items.<br>
      React <strong>&#10007;</strong> to skip.
    </div>
    <div style="margin-top:10px">
      <a href="#" class="n8n-link">Open #approvals in Slack &rarr;</a>
    </div>
    <div style="margin-top:14px;font-size:11px;color:var(--muted)">
      optimize / junk / drilldown items are review-only &mdash; Asana tasks already created, no further execution needed.
    </div>
  </div>

</div>"""


# ─── Agent Profiles ──────────────────────────────────────────────────────────

AGENT_PROFILES = {
    "ai-orchestrator": {
        "role": "Manager over all 3 departments. Routes tasks, runs daily 8-step loop, queues decisions.",
        "department": "Operations HQ",
        "capabilities": ["Daily intelligence loop", "Cross-dept routing", "Approval queue management", "Outcome monitoring"],
        "escalates_to": "Amar (human) via Slack #approvals",
    },
    "qa-auditor": {
        "role": "Output gatekeeper. Validates all agent work before it reaches the Orchestrator.",
        "department": "Operations HQ",
        "capabilities": ["Checklist validation", "Live output verification", "QA_PASSED / QA_FAILED stamps", "Return to originating agent on failure"],
        "escalates_to": "AI Orchestrator",
    },
    "project-coordinator": {
        "role": "Cross-cutting ops layer: UTM policy, pixel health, HubSpot mapping, Railway env vars, connector failures.",
        "department": "Operations HQ",
        "capabilities": ["UTM structure policy", "Meta pixel health", "Railway credential rotation", "GTM audit", "Overdue task reminders"],
        "escalates_to": "AI Orchestrator",
    },
    "growth-analyst": {
        "role": "Data analyst. Runs 8-step intelligence loop on live BQ. Owns memory/.",
        "department": "Operations HQ",
        "capabilities": ["Period-over-period BQ analysis", "CRO A/B result reads", "Monthly forecasting", "memory/08_pitfalls.md maintenance", "Sunday hygiene scan"],
        "escalates_to": "AI Orchestrator + CRO Specialist (on qual issues)",
    },
    "performance-lead": {
        "role": "Strategic lead for budget reallocation, channel launch/sunset, and KPI threshold changes.",
        "department": "Performance",
        "capabilities": ["Budget reallocation across channels", "Channel launch & sunset decisions", "KPI threshold changes in config.py", "Weekly channel mix review"],
        "escalates_to": "AI Orchestrator",
    },
    "campaign-manager": {
        "role": "Builds and configures paid campaigns. Applies naming spec, Meta pixels, keyword policy, audiences.",
        "department": "Performance",
        "capabilities": ["12-field campaign naming spec", "Meta pixel configuration", "Keyword-policy bucketing", "Audience setup", "Pause/scale execution post-✓"],
        "escalates_to": "Performance Lead",
    },
    "creative-strategist": {
        "role": "Owns copy and creative strategy. OCEAN persona mapping, A/B creative variants, LP asset alignment.",
        "department": "Performance",
        "capabilities": ["OCEAN persona mapping", "A/B creative variant scoping", "Channel-specific copy", "LP asset alignment with CRO"],
        "escalates_to": "Performance Lead",
    },
    "cro-specialist": {
        "role": "Leads CRO / LP chain. LP briefs, OCEAN-aligned design spec, qual ratio decisions, A/B test results.",
        "department": "CRO Chain",
        "capabilities": ["8-section LP brief", "OCEAN-aligned design spec", "Qual ratio decisions (<30% redirect)", "A/B test hypotheses", "Weekly pixel audit"],
        "escalates_to": "AI Orchestrator",
    },
    "developer": {
        "role": "Builds and ships LP variant. UTM passthrough, Meta pixels, mobile QA, deploy to production.",
        "department": "CRO Chain",
        "capabilities": ["LP implementation", "UTM hidden fields on all forms", "Meta pixel wiring + Events Manager verify", "Mobile 375px QA", "Production deploy"],
        "escalates_to": "CRO Specialist",
    },
}


def _build_agent_profile(slug: str, n8n_key: str | None = None) -> str:
    """Return the collapsible agent profile card HTML for a given agent slug."""
    p = AGENT_PROFILES.get(slug)
    if not p:
        return ""

    caps_html = "\n".join(f"<li>{c}</li>" for c in p.get("capabilities", []))
    n8n_html = ""
    if n8n_key and n8n_key in N8N_WORKFLOWS:
        n8n_html = f'<a href="{N8N_BASE}/{N8N_WORKFLOWS[n8n_key]}" target="_blank" class="profile-link">Open in n8n &rarr;</a>'
    else:
        n8n_html = '<span style="color:var(--muted);font-size:11px">—</span>'

    return f"""
<div class="profile-card">
  <div class="profile-toggle" onclick="toggleSection('profile-{slug}')">
    <span class="profile-title">&#128203; Agent Profile</span>
    <span class="toggle-arrow" id="arr-profile-{slug}" style="margin-left:auto">&#9660;</span>
  </div>
  <div class="profile-body" id="profile-{slug}">
    <div class="profile-grid">
      <div class="profile-field" style="grid-column:1/-1">
        <span class="profile-label">Role</span>
        <span class="profile-value">{p['role']}</span>
      </div>
      <div class="profile-field">
        <span class="profile-label">Department</span>
        <span class="profile-value">{p['department']}</span>
      </div>
      <div class="profile-field">
        <span class="profile-label">Escalates to</span>
        <span class="profile-value">{p['escalates_to']}</span>
      </div>
      <div class="profile-field">
        <span class="profile-label">Playbook</span>
        <span class="profile-value"><a href="https://github.com/Rana96-run/nexa-performance-agent/blob/main/docs/PLAYBOOK.md" target="_blank" class="profile-link">docs/PLAYBOOK.md &rarr;</a></span>
      </div>
      <div class="profile-field">
        <span class="profile-label">Memory Index</span>
        <span class="profile-value"><a href="https://github.com/Rana96-run/nexa-performance-agent/blob/main/memory/00_index.md" target="_blank" class="profile-link">memory/00_index.md &rarr;</a></span>
      </div>
      <div class="profile-field">
        <span class="profile-label">n8n Workflow</span>
        <span class="profile-value">{n8n_html}</span>
      </div>
      <div class="profile-field" style="grid-column:1/-1">
        <span class="profile-label">Capabilities</span>
        <ul class="profile-caps">{caps_html}</ul>
      </div>
    </div>
  </div>
</div>"""


# ─── Dashboard HTML ───────────────────────────────────────────────────────────

def _render_dashboard(
    system_health: dict[str, Any],
    connector_map: dict[str, Any],
    heatmap_rows: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]],
    recent_actions: list[dict[str, Any]],
    open_tasks: list[dict[str, Any]],
    done_tasks: list[dict[str, Any]] | None = None,
    rescheduled_tasks: list[dict[str, Any]] | None = None,
) -> str:
    health_bar       = _build_health_bar(system_health)
    connector_cards  = _build_connector_cards(connector_map)
    heatmap          = _build_heatmap(heatmap_rows)
    activity_feed    = _build_activity_feed(activity_rows)
    actions_tasks    = _build_actions_tasks(
        recent_actions, open_tasks,
        done_tasks or [], rescheduled_tasks or [],
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nexa Performance Agent</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d0d0d;--card:#1a1a1a;--panel:#141414;--border:#2a2a2a;
  --text:#e6e6e6;--dim:#aaa;--muted:#888;
  --blue:#58a6ff;--lblue:#79c0ff;--purple:#d2a8ff;
  --orange:#f0883e;--warm-orange:#ffa657;--green:#3fb950;--lgreen:#7ee787;
  --grey:#8b949e;--red:#f85149;--accent:#00ff88;
}}
body{{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  font-size:14px;line-height:1.5;min-height:100vh}}
header{{display:flex;align-items:center;gap:10px;padding:16px 24px;
  border-bottom:1px solid var(--border);background:#111;
  position:sticky;top:0;z-index:100}}
header h1{{font-size:16px;font-weight:600;letter-spacing:.3px}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 6px var(--accent);flex-shrink:0}}
.htag{{margin-left:auto;font-size:11px;color:var(--muted);background:#222;
  padding:3px 8px;border-radius:4px;border:1px solid var(--border)}}
main{{max-width:1160px;margin:0 auto;padding:28px 20px 60px}}
.sec{{font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:1.2px;color:var(--muted);margin:32px 0 14px;
  display:flex;align-items:center;gap:8px}}
.sec::after{{content:"";flex:1;height:1px;background:var(--border)}}

/* ── Health bar ── */
.hbar{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:4px}}
.hchip{{display:flex;align-items:center;gap:7px;background:var(--card);
  border:1px solid var(--border);border-radius:20px;padding:6px 14px;
  font-size:12px}}
.hdot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.hlabel{{color:var(--dim)}}
.hval{{font-weight:600}}

/* ── Connector cards ── */
.conn-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
@media(max-width:1100px){{.conn-grid{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:800px){{.conn-grid{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:520px){{.conn-grid{{grid-template-columns:1fr}}}}
.conn-card{{background:var(--card);border:1px solid var(--border);
  border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:5px}}
.conn-top{{display:flex;align-items:center;justify-content:space-between}}
.conn-name{{font-size:13px;font-weight:600}}
.conn-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.conn-ts{{font-size:11px;color:var(--muted)}}
.conn-status{{font-size:11px;font-weight:600}}

/* ── Heatmap ── */
.hm-wrap{{overflow-x:auto}}
.hm-table{{border-collapse:collapse;font-size:10px}}
.hm-h{{color:var(--muted);padding:2px 3px;text-align:center;font-weight:400;width:22px}}
.hm-row{{color:var(--dim);padding:2px 8px 2px 0;text-align:right;
  font-size:11px;white-space:nowrap;font-weight:500}}
.hm-cell{{width:22px;height:18px;border-radius:3px;cursor:default}}
.hm-legend{{display:flex;align-items:center;gap:8px;margin-top:8px}}
.hm-grad{{width:80px;height:10px;border-radius:4px;
  background:linear-gradient(to right,var(--border),var(--accent))}}

/* ── Activity feed ── */
.feed-row{{display:flex;align-items:center;gap:10px;padding:8px 12px;
  border-bottom:1px solid var(--border);font-size:12px;flex-wrap:wrap}}
.feed-row:last-child{{border-bottom:none}}
.feed-ts{{color:var(--muted);white-space:nowrap;min-width:110px}}
.feed-role{{color:var(--blue);font-weight:600;min-width:120px}}
.feed-ch{{background:#1f1f1f;color:var(--dim);border:1px solid var(--border);
  border-radius:4px;padding:1px 6px;font-size:10px}}
.feed-action{{flex:1;color:var(--text)}}
.feed-badge{{font-size:10px;font-weight:700;text-transform:uppercase;
  padding:2px 7px;border-radius:10px;border:1px solid;white-space:nowrap}}
.feed-empty{{color:var(--muted);font-size:12px;padding:16px;
  background:var(--card);border:1px solid var(--border);border-radius:8px}}
.feed-wrap{{background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden}}

/* ── Cadence ── */
.cgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
@media(max-width:700px){{.cgrid{{grid-template-columns:1fr}}}}
.ccard{{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:14px 16px;display:flex;justify-content:space-between;
  align-items:flex-start;gap:12px}}
.cname{{font-size:13px;font-weight:600}}
.cdesc{{font-size:11px;color:var(--muted);margin-top:3px}}
.csched{{font-size:11px;color:var(--muted);background:#111;
  padding:3px 8px;border-radius:4px;font-family:monospace;white-space:nowrap;flex-shrink:0}}

/* ── Agent panels ── */
.agent-panel{{border-left:4px solid var(--panel-color,#444);
  background:var(--panel);border-radius:8px;margin-bottom:18px;overflow:hidden}}
.agent-header{{display:flex;align-items:center;gap:10px;
  padding:14px 18px;border-bottom:1px solid var(--border);
  background:color-mix(in srgb,var(--panel-color,#444) 8%,var(--panel))}}
.agent-icon{{font-size:18px}}
.agent-name{{font-size:15px;font-weight:700;color:var(--panel-color,#e6e6e6)}}
.agent-desc{{font-size:12px;color:var(--dim);flex:1}}
.dept-chip{{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;padding:2px 8px;border-radius:10px;
  border:1px solid currentColor;color:var(--panel-color,#888);opacity:.8;white-space:nowrap}}
.agent-body{{padding:16px 18px}}

/* Orchestrator info card (no run buttons) */
.orch-card{{background:color-mix(in srgb,#f0883e 6%,#111);
  border:1px solid color-mix(in srgb,#f0883e 20%,var(--border));
  border-radius:8px;padding:16px 20px}}
.orch-title{{font-size:13px;font-weight:700;color:#f0883e;margin-bottom:8px}}
.orch-loop{{list-style:none;counter-reset:loop;display:flex;flex-direction:column;gap:5px}}
.orch-loop li{{counter-increment:loop;display:flex;align-items:flex-start;gap:8px;
  font-size:12px;color:var(--dim)}}
.orch-loop li::before{{content:counter(loop);min-width:18px;height:18px;
  border-radius:50%;background:color-mix(in srgb,#f0883e 25%,#222);
  color:#f0883e;font-size:10px;font-weight:700;display:flex;align-items:center;
  justify-content:center;flex-shrink:0;margin-top:1px}}

/* Sub-panels */
.sub-panel{{border-left:2px solid var(--sub-color,#444);
  background:color-mix(in srgb,var(--sub-color,#444) 5%,#0f0f0f);
  border-radius:6px;margin-bottom:14px;overflow:hidden;margin-left:24px}}
.sub-header{{display:flex;align-items:center;gap:8px;
  padding:10px 14px;border-bottom:1px solid var(--border)}}
.sub-arrow{{font-size:14px;color:var(--dim);flex-shrink:0}}
.sub-name{{font-size:13px;font-weight:700;color:var(--sub-color,#e6e6e6)}}
.sub-desc{{font-size:11px;color:var(--muted);flex:1}}
.sub-chip{{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;padding:2px 8px;border-radius:10px;
  border:1px solid currentColor;color:var(--sub-color,#888);opacity:.8;white-space:nowrap}}
.sub-body{{padding:12px 14px}}

/* Task grids and cards */
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
.grid-2{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}
@media(max-width:600px){{.grid-2{{grid-template-columns:1fr}}}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:7px;
  padding:14px;display:flex;flex-direction:column;gap:8px;
  transition:border-color .15s}}
.card:hover{{border-color:#3a3a3a}}
.ctitle{{font-size:13px;font-weight:600}}
.cdesc2{{font-size:12px;color:var(--dim);flex:1}}
.cfoot{{display:flex;align-items:center;justify-content:space-between;
  margin-top:4px;gap:6px}}
.cnote{{font-size:11px;color:var(--muted)}}

/* ── n8n links ── */
.n8n-link{{color:#f0883e;font-size:11px;text-decoration:none;
  border:1px solid #f0883e44;padding:2px 8px;border-radius:4px;white-space:nowrap}}
.n8n-link:hover{{background:#f0883e22}}
.n8n-run-btn{{color:#111;background:#f0883e;font-size:12px;font-weight:700;
  text-decoration:none;border:none;padding:5px 14px;border-radius:6px;
  white-space:nowrap;display:inline-block;margin-top:10px}}
.n8n-run-btn:hover{{background:#ffa657}}

/* ── Actions & Tasks section ── */
.at-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
.at-grid-tasks{{grid-template-columns:repeat(3,1fr)}}
@media(max-width:1100px){{.at-grid-tasks{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:900px){{.at-grid{{grid-template-columns:1fr}};.at-grid-tasks{{grid-template-columns:1fr}}}}
.at-card{{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:16px;display:flex;flex-direction:column;gap:6px}}
.at-scrollable{{max-height:300px;overflow-y:auto}}
.at-title{{font-size:13px;font-weight:700;margin-bottom:4px}}
.at-row{{font-size:11px;color:var(--dim);padding:4px 0;
  border-bottom:1px solid var(--border);display:flex;flex-wrap:wrap;gap:6px;
  align-items:center}}
.at-row:last-child{{border-bottom:none}}
.at-role{{color:var(--blue);font-weight:600;min-width:90px}}
.at-status-ok{{color:var(--green);font-weight:600}}
.at-status-fail{{color:#e05c5c;font-weight:600}}
.at-status-pend{{color:var(--orange);font-weight:600}}
.at-overdue{{color:#e05c5c;font-weight:600}}
.at-empty{{color:var(--muted);font-size:12px;font-style:italic}}

/* ── Collapsible sections ── */
.agent-header,.sub-header{{cursor:pointer;user-select:none}}
.agent-header:hover,.sub-header:hover{{opacity:0.9}}
.toggle-arrow{{margin-left:auto;font-size:11px;color:#888;flex-shrink:0}}

/* ── Day detail panel ── */
#day-detail-panel{{background:#1a1a2e;border:1px solid var(--border);
  border-radius:8px;padding:16px;margin-top:16px}}
#day-detail-panel table th{{text-align:left;padding:4px 8px;
  border-bottom:1px solid var(--border)}}
#day-detail-panel table td{{padding:4px 8px;border-bottom:1px solid #222;
  vertical-align:top}}

/* ── Data Hygiene section ── */
.section-header{{font-size:13px;font-weight:700;color:var(--accent);
  margin-bottom:12px;display:flex;align-items:center;gap:8px}}

/* ── Team Structure ── */
.team-dept{{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:16px 18px;margin-bottom:14px}}
.team-dept-name{{font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:1.2px;margin-bottom:12px;padding-bottom:6px;
  border-bottom:1px solid var(--border)}}
.team-dept-name.ops{{color:var(--orange)}}
.team-dept-name.perf{{color:var(--blue)}}
.team-dept-name.cro{{color:var(--lgreen)}}
.team-agents{{display:flex;flex-wrap:wrap;gap:10px;align-items:center}}
.team-agent{{display:flex;align-items:center;gap:6px}}
.agent-pill{{background:#1f1f1f;border:1px solid var(--border);border-radius:20px;
  padding:5px 12px;font-size:12px;font-weight:600;white-space:nowrap}}
.agent-pill.ops{{color:var(--orange);border-color:color-mix(in srgb,var(--orange) 35%,var(--border))}}
.agent-pill.perf{{color:var(--blue);border-color:color-mix(in srgb,var(--blue) 35%,var(--border))}}
.agent-pill.cro{{color:var(--lgreen);border-color:color-mix(in srgb,var(--lgreen) 35%,var(--border))}}
.agent-pill.mgr{{color:var(--warm-orange);border-color:color-mix(in srgb,var(--warm-orange) 35%,var(--border))}}
.team-arrow{{color:var(--muted);font-size:12px;font-weight:700;flex-shrink:0}}
.team-row{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px}}
.team-row:last-child{{margin-bottom:0}}

/* ── Agent Profile card ── */
.profile-card{{background:#0d0d1a;border:1px solid color-mix(in srgb,var(--panel-color,#444) 25%,var(--border));
  border-radius:7px;padding:14px 16px;margin-bottom:16px}}
.profile-toggle{{display:flex;align-items:center;gap:8px;cursor:pointer;
  user-select:none;margin-bottom:0}}
.profile-toggle:hover{{opacity:.85}}
.profile-title{{font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:1px;color:var(--panel-color,#888)}}
.profile-body{{margin-top:12px}}
.profile-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
@media(max-width:600px){{.profile-grid{{grid-template-columns:1fr}}}}
.profile-field{{display:flex;flex-direction:column;gap:3px}}
.profile-label{{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;color:var(--muted)}}
.profile-value{{font-size:12px;color:var(--dim);line-height:1.5}}
.profile-caps{{list-style:none;padding:0;display:flex;flex-direction:column;gap:2px}}
.profile-caps li{{font-size:11px;color:var(--dim)}}
.profile-caps li::before{{content:"› ";color:var(--panel-color,#888)}}
.profile-link{{color:var(--orange);font-size:11px;text-decoration:none}}
.profile-link:hover{{text-decoration:underline}}
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>Nexa Performance Agent</h1>
  <span class="htag">n8n Cloud &bull; Railway</span>
</header>
<main>

<!-- ── SYSTEM HEALTH BAR ── -->
<div class="sec">System Health</div>
{health_bar}

<!-- ── DATA HYGIENE ── -->
<div class="sec" onclick="toggleSection('ab-data-hygiene')" style="cursor:pointer;user-select:none">
  Data Hygiene &mdash; Collector Status
  <span class="toggle-arrow" id="arr-ab-data-hygiene">&#9660;</span>
</div>
<div id="ab-data-hygiene">
  <div class="conn-grid">
  {connector_cards}
  </div>
</div>

<!-- ── TEAM STRUCTURE ── -->
<div class="sec" onclick="toggleSection('ab-team-structure')" style="cursor:pointer;user-select:none">
  &#127959; Team Structure
  <span class="toggle-arrow" id="arr-ab-team-structure">&#9660;</span>
</div>
<div id="ab-team-structure">

  <!-- OPERATIONS HQ -->
  <div class="team-dept">
    <div class="team-dept-name ops">Operations HQ</div>
    <div class="team-row">
      <span class="agent-pill mgr">&#127775; AI Orchestrator</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill ops">Performance Lead</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill cro">CRO Specialist</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill ops">Growth Analyst</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill ops">Project Coordinator</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill ops">QA Auditor</span>
    </div>
    <div class="team-row" style="margin-top:6px">
      <span class="agent-pill ops">&#128270; QA Auditor</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill mgr">AI Orchestrator</span>
    </div>
    <div class="team-row" style="margin-top:4px">
      <span class="agent-pill ops">&#128295; Project Coordinator</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill perf">Campaign Manager</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill perf">Creative Strategist</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill cro">Developer</span>
    </div>
    <div class="team-row" style="margin-top:4px">
      <span class="agent-pill ops">&#128202; Growth Analyst</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill cro">CRO Specialist</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill mgr">AI Orchestrator</span>
    </div>
  </div>

  <!-- PERFORMANCE -->
  <div class="team-dept">
    <div class="team-dept-name perf">Performance</div>
    <div class="team-row">
      <span class="agent-pill perf">&#127919; Performance Lead</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill perf">Campaign Manager</span>
      <span class="team-arrow">&middot;</span>
      <span class="agent-pill perf">Creative Strategist</span>
    </div>
    <div class="team-row" style="margin-top:6px">
      <span class="agent-pill perf">Campaign Manager</span>
      <span class="team-arrow">&#8646;</span>
      <span class="agent-pill perf">Creative Strategist</span>
      <span style="font-size:10px;color:var(--muted);margin-left:4px">(parallel)</span>
    </div>
  </div>

  <!-- CRO CHAIN -->
  <div class="team-dept">
    <div class="team-dept-name cro">CRO Chain &mdash; Sequential</div>
    <div class="team-row">
      <span class="agent-pill cro">&#128200; CRO Specialist</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill cro">&#128187; Developer</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill ops">QA Auditor</span>
      <span class="team-arrow">&#8594;</span>
      <span class="agent-pill mgr">AI Orchestrator</span>
    </div>
  </div>

</div>

<!-- ── ACTIVITY HEAT MAP ── -->
<div class="sec">Activity Heat Map &mdash; Last 7 Days</div>
{heatmap}

<!-- ── RECENT AGENT ACTIVITY ── -->
<div class="sec">Recent Agent Activity</div>
<div class="feed-wrap">
{activity_feed}
</div>

<!-- ── CADENCE ── -->
<div class="sec">Cadence Flows</div>
<div class="cgrid">
  <div class="ccard">
    <div>
      <div class="cname">Daily Master</div>
      <div class="cdesc">Full daily analysis: spend, leads, CPQL, anomaly detection, Slack summary, pause/scale candidates</div>
      <div style="margin-top:8px"><a href="{N8N_BASE}/{N8N_WORKFLOWS['orchestrator']}" target="_blank" class="n8n-link">Open Daily in n8n &rarr;</a></div>
    </div>
    <div class="csched">05:00 UTC daily</div>
  </div>
  <div class="ccard">
    <div>
      <div class="cname">Weekly Review</div>
      <div class="cdesc">7-day vs prior-7 period comparison, keyword autofix, channel flags, weekly Slack digest</div>
      <div style="margin-top:8px"><a href="{N8N_BASE}/{N8N_WORKFLOWS['weekly']}" target="_blank" class="n8n-link">Open Weekly in n8n &rarr;</a></div>
    </div>
    <div class="csched">Sun 05:00 UTC</div>
  </div>
  <div class="ccard">
    <div>
      <div class="cname">Monthly Review</div>
      <div class="cdesc">MoM review, OKR tracking, budget reconciliation, 30-day forecast</div>
      <div style="margin-top:8px"><a href="{N8N_BASE}/{N8N_WORKFLOWS['monthly']}" target="_blank" class="n8n-link">Open Monthly in n8n &rarr;</a></div>
    </div>
    <div class="csched">1st 05:00 UTC</div>
  </div>
</div>

<!-- ── ACTIONS & TASKS ── -->
<div class="sec">Actions &amp; Tasks</div>
{actions_tasks}

<!-- ═══════════════════════════════════════════════════════
     AGENT TEAM — On-Demand
     ═══════════════════════════════════════════════════════ -->

<!-- ── LAYER 1 — MANAGER ── -->
<div class="sec">Agent Team</div>

<!-- AI Orchestrator — info card only, no run buttons -->
<div class="agent-panel" style="--panel-color:#f0883e">
  <div class="agent-header" onclick="toggleSection('ab-orchestrator')">
    <span class="agent-icon">&#127775;</span>
    <span class="agent-name">AI Orchestrator</span>
    <span class="agent-desc">Routes all work &middot; gates every &#10003; &middot; daily 8-step loop at 08:00 Riyadh</span>
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['orchestrator']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">Open Daily in n8n &rarr;</a>
    <span class="dept-chip">MANAGER</span>
    <span class="toggle-arrow" id="arr-ab-orchestrator">&#9660;</span>
  </div>
  <div class="agent-body" id="ab-orchestrator">
    {_build_agent_profile("ai-orchestrator", "orchestrator")}
    <div class="orch-card">
      <div class="orch-title">The 8-Step Intelligence Loop (runs every daily cadence)</div>
      <a href="{N8N_BASE}/{N8N_WORKFLOWS['orchestrator']}" target="_blank" class="n8n-run-btn">&#9654; Run Daily Now</a>
      <ol class="orch-loop" style="margin-top:12px">
        <li>OBSERVE &mdash; pull live data from BQ, never yesterday&#39;s recollection</li>
        <li>COMPARE period-over-period &mdash; last 7d vs prior 7d via period_compare.py</li>
        <li>INVESTIGATE root cause &mdash; campaign mix, audience, launch waves, silent deaths, LP routing</li>
        <li>DECIDE with full setup &mdash; complete campaign/adset/creative/LP spec, not just &ldquo;pause this&rdquo;</li>
        <li>EXECUTE only after &#10003; approval &mdash; #approvals + &#10003;/&#10007; flow</li>
        <li>MONITOR post-action &mdash; re-evaluate every action at 7d and 14d</li>
        <li>LEARN &mdash; record outcome in memory/14_learning_patterns.md</li>
        <li>FORECAST &mdash; end-of-month projection via forecaster.py (spend, leads, SQLs, CPQL, ROAS)</li>
      </ol>
    </div>
  </div>
</div>

<!-- ── LAYER 2 — OPERATIONS ── -->
<div class="sec">Layer 2 &mdash; Operations</div>

<!-- QA Auditor -->
<div class="agent-panel" style="--panel-color:var(--red)">
  <div class="agent-header" onclick="toggleSection('ab-qa-auditor')">
    <span class="agent-icon">&#128270;</span>
    <span class="agent-name">QA Auditor</span>
    <span class="agent-desc">Validates every agent output &middot; stamps QA_PASSED or QA_FAILED &middot; nothing ships without passing</span>
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['qa']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">QA Gate &rarr;</a>
    <span class="dept-chip">GATEKEEPER</span>
    <span class="toggle-arrow" id="arr-ab-qa-auditor">&#9660;</span>
  </div>
  <div class="agent-body" id="ab-qa-auditor">
    {_build_agent_profile("qa-auditor", "qa")}
    <div class="grid-2">
      <div class="card">
        <div class="ctitle">QA Validation Run</div>
        <div class="cdesc2">Run validation checklist on recent agent outputs: data integrity, task completeness, approval gate, format, technical checks</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Project Coordinator -->
<div class="agent-panel" style="--panel-color:var(--grey)">
  <div class="agent-header" onclick="toggleSection('ab-project-coordinator')">
    <span class="agent-icon">&#128295;</span>
    <span class="agent-name">Project Coordinator</span>
    <span class="agent-desc">Seasonal &amp; product campaign coordination &middot; all-seat Asana task creation &middot; Slack monitoring &middot; monthly campaign reports &middot; connector health &middot; GTM &middot; pixel audit</span>
    <span class="dept-chip">OPS</span>
    <span class="toggle-arrow" id="arr-ab-project-coordinator">&#9660;</span>
  </div>
  <div class="agent-body" id="ab-project-coordinator">
    {_build_agent_profile("project-coordinator", None)}

    <!-- Campaign Coordination sub-section -->
    <div style="margin-bottom:10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--blue);border-bottom:1px solid color-mix(in srgb,var(--blue) 25%,var(--border));padding-bottom:6px">Campaign Coordination</div>
    <div class="grid" style="margin-bottom:22px">
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Seasonal Campaign Brief</div>
        <div class="cdesc2">Kick off a seasonal campaign (National Day &middot; Founding Day &middot; Ramadan &middot; End of Year). Timeline, budget, naming, Asana tasks for all seats.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Seasonal Campaign Monitor</div>
        <div class="cdesc2">Status check: Asana tasks on track, blockers in Slack, mid-campaign CPQL vs target, delivery dates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Product Campaign Brief</div>
        <div class="cdesc2">Launch a product/industry campaign (Bookkeeping &middot; Qflavours &middot; QHR &middot; POS). Includes HubSpot lead module check, deal pipeline, UTM structure, all-seat Asana tasks.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Product Campaign Monitor</div>
        <div class="cdesc2">Monitor active product campaigns: HubSpot attribution, deal pipeline conversion, CPQL vs target, Slack blockers</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Monthly Campaign Report</div>
        <div class="cdesc2">End-of-month report: all seasonal + product campaigns. Spend &middot; leads &middot; SQLs &middot; CPQL vs target &middot; deal value. Creates follow-up Asana tasks for misses.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
    </div>

    <!-- Technical Health sub-section -->
    <div style="margin-bottom:10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--grey);border-bottom:1px solid color-mix(in srgb,var(--grey) 25%,var(--border));padding-bottom:6px">Technical Health</div>
    <div class="grid">
      <div class="card">
        <div class="ctitle">Connector Health</div>
        <div class="cdesc2">Check BQ freshness for all source tables. Flag STALE (&gt;12h) or DEAD (&gt;24h) connectors.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #data-health</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">GTM Audit</div>
        <div class="cdesc2">Audit GTM-TFH26VC2 (web) + GTM-PK6924TJ (server): tags, triggers, UTM passthrough, duplicates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Meta Pixel Health</div>
        <div class="cdesc2">Verify both Meta pixels fire on every LP form submit. Flag gaps in Events Manager.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #data-health</span>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- ── LAYER 3 — PERFORMANCE ── -->
<div class="sec">Layer 3 &mdash; Performance</div>

<!-- Performance Lead -->
<div class="agent-panel" style="--panel-color:var(--blue)">
  <div class="agent-header" onclick="toggleSection('ab-performance-lead')">
    <span class="agent-icon">&#127919;</span>
    <span class="agent-name">Performance Lead</span>
    <span class="agent-desc">Budget reallocation &middot; channel launch &amp; sunset &middot; KPI threshold changes &middot; weekly channel mix review</span>
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['perf_lead']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">CPL sub-flow &rarr;</a>
    <span class="dept-chip">PERFORMANCE</span>
    <span class="toggle-arrow" id="arr-ab-performance-lead">&#9660;</span>
  </div>
  <div class="agent-body" id="ab-performance-lead">
    {_build_agent_profile("performance-lead", "perf_lead")}
    <div class="grid" style="margin-bottom:18px">
      <div class="card">
        <div class="ctitle">Campaign Brief</div>
        <div class="cdesc2">Full brief for a new campaign: audience, creative direction, budget, naming, KPI gates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Monthly Plan</div>
        <div class="cdesc2">Monthly performance plan with targets, channel allocation, and action priorities</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Quarterly Plan</div>
        <div class="cdesc2">Quarterly strategy: OKRs, budget roadmap by month, risk &amp; upside analysis</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">KPI Threshold Review</div>
        <div class="cdesc2">Review live CPQL/CPL/ROAS against config.py thresholds &mdash; flag if calibration needed</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
    </div>

    <!-- &#8618; Campaign Manager sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--lblue)">
      <div class="sub-header" onclick="toggleSection('sb-campaign-manager')">
        <span class="sub-arrow">&#8618;</span>
        <span class="sub-name">Campaign Manager</span>
        <span class="sub-desc">Campaign optimization &middot; keyword policy &middot; ad audit &middot; scale &amp; pause proposals &middot; naming convention</span>
        <a href="{N8N_BASE}/{N8N_WORKFLOWS['campaign_mgr']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">IS sub-flow &rarr;</a>
        <span class="sub-chip">PERFORMANCE</span>
        <span class="toggle-arrow" id="arr-sb-campaign-manager">&#9660;</span>
      </div>
      <div class="sub-body" id="sb-campaign-manager">
        {_build_agent_profile("campaign-manager", "campaign_mgr")}
        <div class="grid">
          <div class="card">
            <div class="ctitle">Keyword Audit</div>
            <div class="cdesc2">Scan enabled keywords for policy violations: always-negative patterns, wrong language, QS&lt;5+IS&gt;80%</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Ad Audit</div>
            <div class="cdesc2">Scan live ads: zero-conv ($70/7d), junk leads (60%+ disqualified), high CPL (&gt;$50/10d)</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Campaign Health</div>
            <div class="cdesc2">ROAS &rarr; CPQL &rarr; CPL waterfall per channel. Flag campaigns outside KPI zones.</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Scale Proposal</div>
            <div class="cdesc2">Identify campaigns with CPQL &le;$60 over 14d and generate full scale proposals for #approvals</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Campaign Naming Audit</div>
            <div class="cdesc2">Validate all live campaign names against &#123;Channel&#125;_&#123;Type&#125;_&#123;Language&#125;_&#123;Product&#125;_&#123;Audience&#125;. Flag &ldquo;Prospecting&rdquo; audience, wrong product names, LinkedIn UTM mismatches.</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- &#8618; Creative Strategist sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--purple)">
      <div class="sub-header" onclick="toggleSection('sb-creative-strategist')">
        <span class="sub-arrow">&#8618;</span>
        <span class="sub-name">Creative Strategist</span>
        <span class="sub-desc">OCEAN persona mapping &middot; creative variants &middot; MSA Arabic copy &middot; LP asset alignment</span>
        <a href="{N8N_BASE}/{N8N_WORKFLOWS['creative']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">Creative sub-flow &rarr;</a>
        <span class="sub-chip">PERFORMANCE</span>
        <span class="toggle-arrow" id="arr-sb-creative-strategist">&#9660;</span>
      </div>
      <div class="sub-body" id="sb-creative-strategist">
        {_build_agent_profile("creative-strategist", "creative")}
        <div class="grid">
          <div class="card">
            <div class="ctitle">Creative Analysis</div>
            <div class="cdesc2">Rank creatives by qualified leads, CPQL, CTR, and video VTR (video-aware analysis)</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Creative Brief</div>
            <div class="cdesc2">Generate brief for next creative batch: winning patterns, variants, OCEAN mapping, copy hooks</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Creative Audit</div>
            <div class="cdesc2">Audit live creatives for fatigue (&gt;30d), duplicate variants, CTR &lt;0.5%, VTR &lt;15%</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">OCEAN Persona Map</div>
            <div class="cdesc2">Map target audiences to OCEAN dimensions (O/C/E/A/N) for a product or campaign</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- ── LAYER 3 — CRO CHAIN ── -->
<div class="sec">Layer 3 &mdash; CRO Chain</div>

<!-- CRO Specialist -->
<div class="agent-panel" style="--panel-color:var(--orange)">
  <div class="agent-header" onclick="toggleSection('ab-cro-specialist')">
    <span class="agent-icon">&#128200;</span>
    <span class="agent-name">CRO Specialist</span>
    <span class="agent-desc">LP briefs &middot; OCEAN-aligned design spec &middot; qual ratio decisions (&lt;30% redirect) &middot; A/B test hypotheses &middot; weekly pixel audit</span>
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['cro']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">CPQL sub-flow &rarr;</a>
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['qual']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">Qual sub-flow &rarr;</a>
    <span class="dept-chip">CRO CHAIN</span>
    <span class="toggle-arrow" id="arr-ab-cro-specialist">&#9660;</span>
  </div>
  <div class="agent-body" id="ab-cro-specialist">
    {_build_agent_profile("cro-specialist", "cro")}
    <div class="grid-2" style="margin-bottom:18px">
      <div class="card">
        <div class="ctitle">LP Brief</div>
        <div class="cdesc2">8-section LP brief: objective, OCEAN audience, hypothesis, success criteria, ZATCA badge, timeline</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">LP Performance Analysis</div>
        <div class="cdesc2">Analyse qual rate by destination_url. Flag LPs &lt;30% qual rate for immediate redirect.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Design Spec</div>
        <div class="cdesc2">OCEAN-aligned LP design spec: visual tone, ZATCA badge above fold, RTL layout, form field annotations, interaction notes, Developer handoff checklist</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
    </div>

    <!-- &#8618; Developer sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--lgreen)">
      <div class="sub-header" onclick="toggleSection('sb-developer')">
        <span class="sub-arrow">&#8618;</span>
        <span class="sub-name">Developer</span>
        <span class="sub-desc">LP build &middot; UTM hidden fields on every form &middot; Meta pixel wiring &middot; mobile QA &middot; deploy to production</span>
        <span class="sub-chip">CRO CHAIN</span>
        <span class="toggle-arrow" id="arr-sb-developer">&#9660;</span>
      </div>
      <div class="sub-body" id="sb-developer">
        {_build_agent_profile("developer", None)}
        <div class="grid-2">
          <div class="card">
            <div class="ctitle">UTM Form Check</div>
            <div class="cdesc2">Audit all active LPs: hidden UTM fields on every form, HubSpot capturing all UTMs, mobile 375px renders correctly, &lt;3s load time</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #data-health</span>
            </div>
          </div>
          <div class="card">
            <div class="ctitle">Pixel Verification</div>
            <div class="cdesc2">Verify both Meta pixels firing (base + Lead event) on all active LPs via Events Manager</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #data-health</span>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- ── LAYER 3 — DATA ── -->
<div class="sec">Layer 3 &mdash; Data</div>

<!-- Growth Analyst -->
<div class="agent-panel" style="--panel-color:var(--green)">
  <div class="agent-header" onclick="toggleSection('ab-growth-analyst')">
    <span class="agent-icon">&#128202;</span>
    <span class="agent-name">Growth Analyst</span>
    <span class="agent-desc">BQ analysis &middot; period comparisons &middot; flag investigations &middot; forecasts &middot; owns memory/08_pitfalls.md</span>
    <a href="{N8N_BASE}/{N8N_WORKFLOWS['growth_analyst']}" target="_blank" class="n8n-link" onclick="event.stopPropagation()">ROAS sub-flow &rarr;</a>
    <span class="dept-chip">DATA</span>
    <span class="toggle-arrow" id="arr-ab-growth-analyst">&#9660;</span>
  </div>
  <div class="agent-body" id="ab-growth-analyst">
    {_build_agent_profile("growth-analyst", "growth_analyst")}
    <div class="grid">
      <div class="card">
        <div class="ctitle">Period Comparison</div>
        <div class="cdesc2">7d vs prior-7d for all channels: spend, leads, SQLs, CPQL, CPL, ROAS, qual rate, IS, CTR</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Campaign Deep Dive</div>
        <div class="cdesc2">Root cause analysis on a specific CPQL/ROAS/qual flag: contributing factors, attribution</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Forecast</div>
        <div class="cdesc2">End-of-month projection: spend, leads, SQLs, CPQL, ROAS &mdash; status-quo vs post-action paths</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
        </div>
      </div>
    </div>
  </div>
</div>

</main>

<script>
function toggleSection(id) {{
  const body = document.getElementById(id);
  const arr  = document.getElementById('arr-' + id);
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (arr) arr.textContent = open ? '▶' : '▼';
}}

async function showDayDetail(date) {{
  const panel = document.getElementById('day-detail-panel');
  panel.style.display = 'block';
  panel.innerHTML = '<p style="color:#888">Loading…</p>';
  try {{
    const r = await fetch('/api/day-detail/' + date);
    const d = await r.json();
    if (!d.rows || d.rows.length === 0) {{
      panel.innerHTML = '<p style="color:#666">No activity logged for ' + date + '</p>';
      return;
    }}
    const rows = d.rows.map(function(r) {{
      return '<tr><td>' + (r.role||'') + '</td><td>' + (r.action||'') + '</td><td>' + (r.channel||'') + '</td><td style="color:' + (r.status==='ok'?'#4caf50':'#ff6b6b') + '">' + (r.status||'') + '</td><td style="color:#aaa;font-size:11px">' + ((r.details||'').slice(0,80)) + '</td></tr>';
    }}).join('');
    panel.innerHTML = '<h4 style="margin:0 0 10px;color:#ccc">Activity on ' + date + '</h4>'
      + '<table style="width:100%;border-collapse:collapse;font-size:12px">'
      + '<thead><tr style="color:#888"><th>Role</th><th>Action</th><th>Channel</th><th>Status</th><th>Details</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table>'
      + '<button onclick="document.getElementById(\'day-detail-panel\').style.display=\'none\'" style="margin-top:10px;background:#333;color:#aaa;border:none;padding:4px 12px;cursor:pointer;border-radius:4px">Close</button>';
  }} catch(e) {{
    panel.innerHTML = '<p style="color:#f66">Failed to load: ' + e + '</p>';
  }}
}}
</script>
</body>
</html>"""
