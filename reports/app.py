"""
reports/app.py
==============
Thin Flask app for the Nexa Performance Agent activity dashboard.

Routes:
  GET  /health                      → {"status": "ok"}
  GET  /                            → redirect to /activity
  GET  /activity                    → self-contained HTML dashboard
  POST /api/ondemand/<task>         → proxy POST to n8n webhook URL

On-demand tasks proxy to n8n webhook URLs. Results arrive in Slack #approvals
or #data-health depending on the task.
No secrets, no subprocesses, no background threads.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests
from flask import Flask, jsonify, redirect, request


# ─── n8n webhook map ──────────────────────────────────────────────────────────

N8N_BASE = "https://qoyod.app.n8n.cloud/webhook"

ONDEMAND_ROUTES: dict[str, str] = {
    # QA Auditor
    "qa-check":           f"{N8N_BASE}/od-qa-check",

    # Project Coordinator — Campaign Coordination
    "seasonal-brief":         f"{N8N_BASE}/od-seasonal-brief",
    "seasonal-monitor":       f"{N8N_BASE}/od-seasonal-monitor",
    "product-campaign-brief": f"{N8N_BASE}/od-product-campaign-brief",
    "product-monitor":        f"{N8N_BASE}/od-product-monitor",
    "campaign-report":        f"{N8N_BASE}/od-campaign-report",

    # Project Coordinator — Technical Health
    "connector-health":   f"{N8N_BASE}/od-connector-health",
    "gtm-audit":          f"{N8N_BASE}/od-gtm-audit",
    "pixel-health":       f"{N8N_BASE}/od-pixel-health",

    # Performance Lead
    "campaign-brief":     f"{N8N_BASE}/od-campaign-brief",
    "monthly-plan":       f"{N8N_BASE}/od-monthly-plan",
    "quarterly-plan":     f"{N8N_BASE}/od-quarterly-plan",
    "kpi-review":         f"{N8N_BASE}/od-kpi-review",

    # Campaign Manager (under Performance Lead)
    "keyword-audit":      f"{N8N_BASE}/od-keyword-audit",
    "ad-audit":           f"{N8N_BASE}/od-ad-audit",
    "campaign-health":    f"{N8N_BASE}/od-campaign-health",
    "scale-proposal":     f"{N8N_BASE}/od-scale-proposal",
    "utm-validate":       f"{N8N_BASE}/od-utm-validate",

    # Creative Strategist (under Performance Lead)
    "creative-analysis":  f"{N8N_BASE}/od-creative-analysis",
    "creative-brief":     f"{N8N_BASE}/od-creative-brief",
    "creative-audit":     f"{N8N_BASE}/od-creative-audit",
    "ocean-persona":      f"{N8N_BASE}/od-ocean-persona",

    # CRO Specialist
    "lp-brief":           f"{N8N_BASE}/od-lp-brief",
    "lp-analysis":        f"{N8N_BASE}/od-lp-analysis",

    # UI/UX Designer (under CRO Specialist)
    "design-brief":       f"{N8N_BASE}/od-design-brief",

    # Developer (under UI/UX Designer)
    "utm-form-check":     f"{N8N_BASE}/od-utm-form-check",
    "pixel-verify":       f"{N8N_BASE}/od-pixel-verify",

    # Growth Analyst
    "period-compare":     f"{N8N_BASE}/od-period-compare",
    "campaign-drilldown": f"{N8N_BASE}/od-campaign-drilldown",
    "forecast":           f"{N8N_BASE}/od-forecast",
}

# Tasks that post to #data-health instead of #approvals
DATA_HEALTH_TASKS = {
    "connector-health", "utm-form-check", "pixel-verify", "pixel-health"
}

# BQ coordinates (fallback to known defaults)
BQ_PROJECT = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
BQ_DATASET = os.getenv("BQ_DATASET", "qoyod_marketing")

# Connectors tracked in the health cards
CONNECTORS = [
    ("Google Ads",      "google_ads"),
    ("Meta",            "meta"),
    ("Snapchat",        "snapchat"),
    ("TikTok",          "tiktok"),
    ("LinkedIn",        "linkedin"),
    ("Microsoft Ads",   "microsoft_ads"),
    ("HubSpot Leads",   "hubspot_leads"),
    ("HubSpot Deals",   "hubspot_deals"),
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
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
            )
            client = bigquery.Client(project=BQ_PROJECT, credentials=creds)
        elif creds_path:
            client = bigquery.Client(project=BQ_PROJECT)
        else:
            return []

        rows = client.query(sql).result()
        return [dict(row) for row in rows]
    except Exception:
        return []


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


def _get_connector_health() -> dict[str, Any]:
    """Return last-seen timestamp per channel from agent_activity_log."""
    rows = _bq_query(f"""
        SELECT
            channel,
            MAX(ts) AS last_ts
        FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
        WHERE channel IS NOT NULL
          AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        GROUP BY channel
    """)
    return {r["channel"]: r["last_ts"] for r in rows if r.get("channel")}


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
        system_health   = _get_system_health()
        connector_map   = _get_connector_health()
        heatmap_rows    = _get_heatmap_data()
        activity_rows   = _get_recent_activity()
        return _render_dashboard(system_health, connector_map, heatmap_rows, activity_rows)

    @app.post("/api/ondemand/<task>")
    def ondemand(task: str):
        if task not in ONDEMAND_ROUTES:
            return jsonify({"error": f"Unknown task: {task}"}), 404

        webhook_url = ONDEMAND_ROUTES[task]
        payload = request.get_json(silent=True) or {}
        payload.setdefault("triggered_by", "dashboard")
        channel = "#data-health" if task in DATA_HEALTH_TASKS else "#approvals"

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 404:
                return jsonify({
                    "status": "not_configured",
                    "task": task,
                    "message": f"Webhook not configured yet — create n8n workflow `od-{task}`",
                }), 200
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return jsonify({
                "status": "not_configured",
                "task": task,
                "message": f"Webhook not configured yet — create n8n workflow `od-{task}`",
            }), 200
        except requests.exceptions.Timeout:
            pass
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return jsonify({
                    "status": "not_configured",
                    "task": task,
                    "message": f"Webhook not configured yet — create n8n workflow `od-{task}`",
                }), 200
            return jsonify({"status": "error", "task": task, "message": str(exc)}), 502

        return jsonify({
            "status": "triggered",
            "task": task,
            "message": f"Running… results will arrive in Slack {channel}",
        })

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
</div>"""


def _build_connector_cards(connector_map: dict[str, Any]) -> str:
    cards = []
    for name, key in CONNECTORS:
        ts = connector_map.get(key)
        color, label = _freshness_status(ts)
        ts_str = _ts_fmt(ts)
        cards.append(f"""
    <div class="conn-card">
      <div class="conn-top">
        <span class="conn-name">{name}</span>
        <span class="conn-dot" style="background:{color};box-shadow:0 0 4px {color}"></span>
      </div>
      <div class="conn-ts">{ts_str}</div>
      <div class="conn-status" style="color:{color}">{label}</div>
    </div>""")
    return "\n".join(cards)


def _build_heatmap(heatmap_rows: list[dict[str, Any]]) -> str:
    # dow: 1=Sun … 7=Sat in BQ DAYOFWEEK. We show Mon–Sun (2–7, 1).
    DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    DOW_ORDER  = [2, 3, 4, 5, 6, 7, 1]  # Mon=2 … Sat=7, Sun=1

    lookup: dict[tuple[int, int], int] = {}
    for r in heatmap_rows:
        lookup[(int(r["dow"]), int(r["hr"]))] = int(r["cnt"])

    max_cnt = max(lookup.values(), default=1)

    hour_headers = "".join(
        f'<th class="hm-h">{h:02d}</th>' for h in range(24)
    )

    rows_html = []
    for i, dow in enumerate(DOW_ORDER):
        cells = []
        for hr in range(24):
            cnt = lookup.get((dow, hr), 0)
            intensity = int((cnt / max_cnt) * 255) if max_cnt else 0
            bg = f"rgba(0,255,136,{intensity/255:.2f})" if cnt else "var(--border)"
            title = f"{cnt} events" if cnt else "no activity"
            cells.append(
                f'<td class="hm-cell" style="background:{bg}" title="{title}"></td>'
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
    <span style="color:var(--muted);font-size:11px;margin-left:16px">Asia/Riyadh &middot; last 7 days</span>
  </div>
</div>"""


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


# ─── Dashboard HTML ───────────────────────────────────────────────────────────

def _render_dashboard(
    system_health: dict[str, Any],
    connector_map: dict[str, Any],
    heatmap_rows: list[dict[str, Any]],
    activity_rows: list[dict[str, Any]],
) -> str:
    health_bar       = _build_health_bar(system_health)
    connector_cards  = _build_connector_cards(connector_map)
    heatmap          = _build_heatmap(heatmap_rows)
    activity_feed    = _build_activity_feed(activity_rows)

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
@media(max-width:900px){{.conn-grid{{grid-template-columns:repeat(2,1fr)}}}}
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
.btn{{font-size:11px;font-weight:600;padding:5px 12px;border-radius:5px;
  border:none;background:var(--btn-color,var(--accent));
  color:#0d0d0d;cursor:pointer;flex-shrink:0;transition:opacity .15s}}
.btn:hover{{opacity:.8}}
.btn:disabled{{background:#333;color:var(--muted);cursor:not-allowed}}
.cst{{font-size:11px;min-height:15px;transition:color .2s}}
.cst.ok{{color:var(--accent)}}.cst.err{{color:var(--orange)}}.cst.spin{{color:var(--dim)}}
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

<!-- ── CONNECTOR HEALTH CARDS ── -->
<div class="sec">Connector Health</div>
<div class="conn-grid">
{connector_cards}
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
    </div>
    <div class="csched">05:00 UTC daily</div>
  </div>
  <div class="ccard">
    <div>
      <div class="cname">Weekly Review</div>
      <div class="cdesc">7-day vs prior-7 period comparison, keyword autofix, channel flags, weekly Slack digest</div>
    </div>
    <div class="csched">Sun 05:00 UTC</div>
  </div>
  <div class="ccard">
    <div>
      <div class="cname">Monthly Review</div>
      <div class="cdesc">MoM review, OKR tracking, budget reconciliation, 30-day forecast</div>
    </div>
    <div class="csched">1st 05:00 UTC</div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════
     AGENT TEAM — On-Demand
     ═══════════════════════════════════════════════════════ -->

<!-- ── LAYER 1 — MANAGER ── -->
<div class="sec">Agent Team</div>

<!-- AI Orchestrator — info card only, no run buttons -->
<div class="agent-panel" style="--panel-color:#f0883e">
  <div class="agent-header">
    <span class="agent-icon">&#127775;</span>
    <span class="agent-name">AI Orchestrator</span>
    <span class="agent-desc">Routes all work &middot; gates every &#10003; &middot; daily 8-step loop at 08:00 Riyadh</span>
    <span class="dept-chip">MANAGER</span>
  </div>
  <div class="agent-body">
    <div class="orch-card">
      <div class="orch-title">The 8-Step Intelligence Loop (runs every daily cadence)</div>
      <ol class="orch-loop">
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
  <div class="agent-header">
    <span class="agent-icon">&#128270;</span>
    <span class="agent-name">QA Auditor</span>
    <span class="agent-desc">Validates every agent output &middot; stamps QA_PASSED or QA_FAILED &middot; nothing ships without passing</span>
    <span class="dept-chip">GATEKEEPER</span>
  </div>
  <div class="agent-body">
    <div class="grid-2">
      <div class="card">
        <div class="ctitle">QA Validation Run</div>
        <div class="cdesc2">Run validation checklist on recent agent outputs: data integrity, task completeness, approval gate, format, technical checks</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--red)" onclick="run(this,'qa-check')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-qa-check"></div>
      </div>
    </div>
  </div>
</div>

<!-- Project Coordinator -->
<div class="agent-panel" style="--panel-color:var(--grey)">
  <div class="agent-header">
    <span class="agent-icon">&#128295;</span>
    <span class="agent-name">Project Coordinator</span>
    <span class="agent-desc">Seasonal &amp; product campaign coordination &middot; all-seat Asana task creation &middot; Slack monitoring &middot; monthly campaign reports &middot; connector health &middot; GTM &middot; pixel audit</span>
    <span class="dept-chip">OPS</span>
  </div>
  <div class="agent-body">

    <!-- Campaign Coordination sub-section -->
    <div style="margin-bottom:10px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--blue);border-bottom:1px solid color-mix(in srgb,var(--blue) 25%,var(--border));padding-bottom:6px">Campaign Coordination</div>
    <div class="grid" style="margin-bottom:22px">
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Seasonal Campaign Brief</div>
        <div class="cdesc2">Kick off a seasonal campaign (National Day &middot; Founding Day &middot; Ramadan &middot; End of Year). Timeline, budget, naming, Asana tasks for all seats.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'seasonal-brief')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-seasonal-brief"></div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Seasonal Campaign Monitor</div>
        <div class="cdesc2">Status check: Asana tasks on track, blockers in Slack, mid-campaign CPQL vs target, delivery dates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'seasonal-monitor')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-seasonal-monitor"></div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Product Campaign Brief</div>
        <div class="cdesc2">Launch a product/industry campaign (Bookkeeping &middot; Qflavours &middot; QHR &middot; POS). Includes HubSpot lead module check, deal pipeline, UTM structure, all-seat Asana tasks.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'product-campaign-brief')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-product-campaign-brief"></div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Product Campaign Monitor</div>
        <div class="cdesc2">Monitor active product campaigns: HubSpot attribution, deal pipeline conversion, CPQL vs target, Slack blockers</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'product-monitor')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-product-monitor"></div>
      </div>
      <div class="card" style="border-color:color-mix(in srgb,var(--blue) 18%,var(--border))">
        <div class="ctitle" style="color:var(--blue)">Monthly Campaign Report</div>
        <div class="cdesc2">End-of-month report: all seasonal + product campaigns. Spend &middot; leads &middot; SQLs &middot; CPQL vs target &middot; deal value. Creates follow-up Asana tasks for misses.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'campaign-report')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-campaign-report"></div>
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
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'connector-health')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-connector-health"></div>
      </div>
      <div class="card">
        <div class="ctitle">GTM Audit</div>
        <div class="cdesc2">Audit GTM-TFH26VC2 (web) + GTM-PK6924TJ (server): tags, triggers, UTM passthrough, duplicates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'gtm-audit')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-gtm-audit"></div>
      </div>
      <div class="card">
        <div class="ctitle">Meta Pixel Health</div>
        <div class="cdesc2">Verify both Meta pixels fire on every LP form submit. Flag gaps in Events Manager.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #data-health</span>
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'pixel-health')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-pixel-health"></div>
      </div>
    </div>

  </div>
</div>

<!-- ── LAYER 3 — PERFORMANCE ── -->
<div class="sec">Layer 3 &mdash; Performance</div>

<!-- Performance Lead -->
<div class="agent-panel" style="--panel-color:var(--blue)">
  <div class="agent-header">
    <span class="agent-icon">&#127919;</span>
    <span class="agent-name">Performance Lead</span>
    <span class="agent-desc">KPI thresholds &middot; budget allocation &middot; channel mix &middot; triage to Campaign Manager or Creative Strategist</span>
    <span class="dept-chip">PERFORMANCE</span>
  </div>
  <div class="agent-body">
    <div class="grid" style="margin-bottom:18px">
      <div class="card">
        <div class="ctitle">Campaign Brief</div>
        <div class="cdesc2">Full brief for a new campaign: audience, creative direction, budget, naming, KPI gates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'campaign-brief')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-campaign-brief"></div>
      </div>
      <div class="card">
        <div class="ctitle">Monthly Plan</div>
        <div class="cdesc2">Monthly performance plan with targets, channel allocation, and action priorities</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'monthly-plan')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-monthly-plan"></div>
      </div>
      <div class="card">
        <div class="ctitle">Quarterly Plan</div>
        <div class="cdesc2">Quarterly strategy: OKRs, budget roadmap by month, risk &amp; upside analysis</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'quarterly-plan')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-quarterly-plan"></div>
      </div>
      <div class="card">
        <div class="ctitle">KPI Threshold Review</div>
        <div class="cdesc2">Review live CPQL/CPL/ROAS against config.py thresholds &mdash; flag if calibration needed</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'kpi-review')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-kpi-review"></div>
      </div>
    </div>

    <!-- &#8618; Campaign Manager sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--lblue)">
      <div class="sub-header">
        <span class="sub-arrow">&#8618;</span>
        <span class="sub-name">Campaign Manager</span>
        <span class="sub-desc">Campaign optimization &middot; keyword policy &middot; ad audit &middot; scale &amp; pause proposals &middot; naming convention</span>
        <span class="sub-chip">PERFORMANCE</span>
      </div>
      <div class="sub-body">
        <div class="grid">
          <div class="card">
            <div class="ctitle">Keyword Audit</div>
            <div class="cdesc2">Scan enabled keywords for policy violations: always-negative patterns, wrong language, QS&lt;5+IS&gt;80%</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'keyword-audit')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-keyword-audit"></div>
          </div>
          <div class="card">
            <div class="ctitle">Ad Audit</div>
            <div class="cdesc2">Scan live ads: zero-conv ($70/7d), junk leads (60%+ disqualified), high CPL (&gt;$50/10d)</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'ad-audit')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-ad-audit"></div>
          </div>
          <div class="card">
            <div class="ctitle">Campaign Health</div>
            <div class="cdesc2">ROAS &rarr; CPQL &rarr; CPL waterfall per channel. Flag campaigns outside KPI zones.</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'campaign-health')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-campaign-health"></div>
          </div>
          <div class="card">
            <div class="ctitle">Scale Proposal</div>
            <div class="cdesc2">Identify campaigns with CPQL &le;$60 over 14d and generate full scale proposals for #approvals</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'scale-proposal')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-scale-proposal"></div>
          </div>
          <div class="card">
            <div class="ctitle">Campaign Naming Audit</div>
            <div class="cdesc2">Validate all live campaign names against &#123;Channel&#125;_&#123;Type&#125;_&#123;Language&#125;_&#123;Product&#125;_&#123;Audience&#125;. Flag &ldquo;Prospecting&rdquo; audience, wrong product names, LinkedIn UTM mismatches.</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'utm-validate')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-utm-validate"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- &#8618; Creative Strategist sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--purple)">
      <div class="sub-header">
        <span class="sub-arrow">&#8618;</span>
        <span class="sub-name">Creative Strategist</span>
        <span class="sub-desc">OCEAN persona mapping &middot; creative variants &middot; MSA Arabic copy &middot; LP asset alignment</span>
        <span class="sub-chip">PERFORMANCE</span>
      </div>
      <div class="sub-body">
        <div class="grid">
          <div class="card">
            <div class="ctitle">Creative Analysis</div>
            <div class="cdesc2">Rank creatives by qualified leads, CPQL, CTR, and video VTR (video-aware analysis)</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'creative-analysis')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-creative-analysis"></div>
          </div>
          <div class="card">
            <div class="ctitle">Creative Brief</div>
            <div class="cdesc2">Generate brief for next creative batch: winning patterns, variants, OCEAN mapping, copy hooks</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'creative-brief')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-creative-brief"></div>
          </div>
          <div class="card">
            <div class="ctitle">Creative Audit</div>
            <div class="cdesc2">Audit live creatives for fatigue (&gt;30d), duplicate variants, CTR &lt;0.5%, VTR &lt;15%</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'creative-audit')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-creative-audit"></div>
          </div>
          <div class="card">
            <div class="ctitle">OCEAN Persona Map</div>
            <div class="cdesc2">Map target audiences to OCEAN dimensions (O/C/E/A/N) for a product or campaign</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'ocean-persona')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-ocean-persona"></div>
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
  <div class="agent-header">
    <span class="agent-icon">&#128200;</span>
    <span class="agent-name">CRO Specialist</span>
    <span class="agent-desc">LP briefs &middot; qual ratio decisions (redirect at &lt;30%) &middot; A/B test hypotheses &middot; test result calls</span>
    <span class="dept-chip">CRO CHAIN</span>
  </div>
  <div class="agent-body">
    <div class="grid-2" style="margin-bottom:18px">
      <div class="card">
        <div class="ctitle">LP Brief</div>
        <div class="cdesc2">8-section LP brief: objective, OCEAN audience, hypothesis, success criteria, ZATCA badge, timeline</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--orange)" onclick="run(this,'lp-brief')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-lp-brief"></div>
      </div>
      <div class="card">
        <div class="ctitle">LP Performance Analysis</div>
        <div class="cdesc2">Analyse qual rate by destination_url. Flag LPs &lt;30% qual rate for immediate redirect.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--orange)" onclick="run(this,'lp-analysis')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-lp-analysis"></div>
      </div>
    </div>

    <!-- &#8618; UI/UX Designer sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--warm-orange)">
      <div class="sub-header">
        <span class="sub-arrow">&#8618;</span>
        <span class="sub-name">UI/UX Designer</span>
        <span class="sub-desc">LP design from CRO brief &middot; OCEAN-aligned visual tone &middot; ZATCA badge above fold &middot; mobile-first 375px</span>
        <span class="sub-chip">CRO CHAIN</span>
      </div>
      <div class="sub-body">
        <div class="grid-2" style="margin-bottom:14px">
          <div class="card">
            <div class="ctitle">Design Brief</div>
            <div class="cdesc2">Generate LP design brief: OCEAN visual mapping, ZATCA placement, RTL layout, form field names, interaction notes, handoff checklist for Developer</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--warm-orange)" onclick="run(this,'design-brief')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-design-brief"></div>
          </div>
        </div>

        <!-- &#8618; Developer sub-panel (nested inside UI/UX) -->
        <div class="sub-panel" style="--sub-color:var(--lgreen);margin-left:0">
          <div class="sub-header">
            <span class="sub-arrow">&#8618;</span>
            <span class="sub-name">Developer</span>
            <span class="sub-desc">LP build &middot; UTM hidden fields on every form &middot; Meta pixel wiring &middot; mobile QA &middot; deploy to production</span>
            <span class="sub-chip">CRO CHAIN</span>
          </div>
          <div class="sub-body">
            <div class="grid-2">
              <div class="card">
                <div class="ctitle">UTM Form Check</div>
                <div class="cdesc2">Audit all active LPs: hidden UTM fields on every form, HubSpot capturing all UTMs, mobile 375px renders correctly, &lt;3s load time</div>
                <div class="cfoot">
                  <span class="cnote">Results &rarr; #data-health</span>
                  <button class="btn" style="--btn-color:var(--lgreen)" onclick="run(this,'utm-form-check')">Run &rarr;</button>
                </div>
                <div class="cst spin" id="st-utm-form-check"></div>
              </div>
              <div class="card">
                <div class="ctitle">Pixel Verification</div>
                <div class="cdesc2">Verify both Meta pixels firing (base + Lead event) on all active LPs via Events Manager</div>
                <div class="cfoot">
                  <span class="cnote">Results &rarr; #data-health</span>
                  <button class="btn" style="--btn-color:var(--lgreen)" onclick="run(this,'pixel-verify')">Run &rarr;</button>
                </div>
                <div class="cst spin" id="st-pixel-verify"></div>
              </div>
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
  <div class="agent-header">
    <span class="agent-icon">&#128202;</span>
    <span class="agent-name">Growth Analyst</span>
    <span class="agent-desc">BQ analysis &middot; period comparisons &middot; flag investigations &middot; forecasts &middot; owns memory/08_pitfalls.md</span>
    <span class="dept-chip">DATA</span>
  </div>
  <div class="agent-body">
    <div class="grid">
      <div class="card">
        <div class="ctitle">Period Comparison</div>
        <div class="cdesc2">7d vs prior-7d for all channels: spend, leads, SQLs, CPQL, CPL, ROAS, qual rate, IS, CTR</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--green)" onclick="run(this,'period-compare')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-period-compare"></div>
      </div>
      <div class="card">
        <div class="ctitle">Campaign Deep Dive</div>
        <div class="cdesc2">Root cause analysis on a specific CPQL/ROAS/qual flag: contributing factors, attribution</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--green)" onclick="run(this,'campaign-drilldown')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-campaign-drilldown"></div>
      </div>
      <div class="card">
        <div class="ctitle">Forecast</div>
        <div class="cdesc2">End-of-month projection: spend, leads, SQLs, CPQL, ROAS &mdash; status-quo vs post-action paths</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--green)" onclick="run(this,'forecast')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-forecast"></div>
      </div>
    </div>
  </div>
</div>

</main>
<script>
async function run(btn, task) {{
  const el = document.getElementById('st-' + task);
  btn.disabled = true; btn.textContent = '...';
  el.className = 'cst spin'; el.textContent = 'Triggering…';
  try {{
    const r = await fetch('/api/ondemand/' + task, {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{triggered_by:'dashboard'}})
    }});
    const d = await r.json();
    if (d.status === 'triggered') {{
      el.className = 'cst ok';
      el.textContent = 'Triggered ✓ — ' + (d.message || 'check Slack');
    }} else if (d.status === 'not_configured') {{
      el.className = 'cst err';
      el.textContent = d.message || 'Webhook not configured';
    }} else {{
      el.className = 'cst err';
      el.textContent = d.message || 'Unknown error';
    }}
  }} catch(e) {{
    el.className = 'cst err';
    el.textContent = 'Network error — is Railway reachable?';
  }}
  btn.textContent = 'Run →'; btn.disabled = false;
}}
</script>
</body>
</html>"""
