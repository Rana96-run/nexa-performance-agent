"""
reports/activity_dashboard.py
==============================
Agent Activity Dashboard — reads logs/activity_log.csv and serves
a live HTML dashboard at GET /activity (Railway).

Separate from the Hex performance dashboard. This shows what the AGENT
did: messages sent, tasks created, API calls, approvals, role runs, etc.

Routes added to app.py:
  GET /activity         → full activity dashboard
  GET /activity/data    → raw JSON (for Hex or external tools)
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

_CSV_PATH = Path(__file__).parent.parent / "logs" / "activity_log.csv"

# ── Workflow descriptions per role ─────────────────────────────────────────────
WORKFLOWS = {
    "bq_refresh": {
        "label":  "BQ Data Refresh",
        "steps": [
            "1. Run all channel collectors (Google Ads, Meta, Snapchat, TikTok, LinkedIn, Bing, HubSpot)",
            "2. Run sub-campaign collectors (adgroups, keywords, adsets, ads)",
            "3. Refresh all BigQuery views (paid_channel_daily, hubspot_leads_module_daily, …)",
            "4. Sync activity_log.csv → BQ agent_activity_log",
            "5. Send heartbeat to #notify",
        ],
        "schedule": "Every 6h (03:00, 09:00, 15:00, 21:00 Riyadh)",
    },
    "daily_agent": {
        "label":  "Daily Agent Cycle",
        "steps": [
            "1. Guard: skip if already ran today",
            "2. Collect data from BQ cache (campaign grain, all channels)",
            "3. Run deterministic analysers: campaign_health_tasks, spike_detector, google_ads_audit_tasks",
            "4. Batch create Asana tasks from findings",
            "5. Post daily summary to Slack #notify",
            "6. Send approval requests to #approvals for scale/pause/optimize actions",
        ],
        "schedule": "Daily at 03:00 Riyadh (nightly cycle)",
    },
    "paid_media_strategist": {
        "label":  "Paid Media Strategist (Claude)",
        "steps": [
            "1. Load system prompt (shared context + strategist role prompt)",
            "2. Append Drive asset index (creative briefs, brand guidelines)",
            "3. Send 7-day performance data via Claude API",
            "4. Parse JSON decisions from response",
            "5. Extract Asana tasks + approval requests",
            "6. Create tasks, send approvals to #approvals",
        ],
        "schedule": "Weekly / Monthly / Quarterly / On-demand",
    },
    "keyword_approval": {
        "label":  "Keyword Approval",
        "steps": [
            "1. Audit Google Ads search terms (last 7 days)",
            "2. Classify: negative / converting / watch",
            "3. Auto-execute negatives immediately (no approval)",
            "4. Converting terms → Asana task (no Slack)",
            "5. Watch terms → logged, no action",
        ],
        "schedule": "Weekly (part of weekly cadence)",
    },
    "campaign_health": {
        "label":  "Campaign Health Tasks",
        "steps": [
            "1. Query BQ for all campaigns (last 14 days minimum)",
            "2. Check CPQL vs thresholds (scale zone / pause zone)",
            "3. Scale: if CPQL ≤ scale threshold → send to #approvals",
            "4. Pause: if CPQL ≥ pause threshold AND 14d window met → send to #approvals",
            "5. Junk leads: high CPL but low qual rate → flag to #approvals",
            "6. Create Asana tasks for each finding",
        ],
        "schedule": "Daily (part of nightly cycle)",
    },
    "slack_approval": {
        "label":  "Slack Approval Flow",
        "steps": [
            "1. Approval message posted to #approvals with ✅/❌",
            "2. Team reacts with ✅ (approve) or ❌ (reject)",
            "3. Slack Events API webhook fires to /slack/events",
            "4. _handle_reaction() executes or skips the action",
            "5. Result posted as thread reply in #approvals",
            "6. Asana task updated with decision and result",
        ],
        "schedule": "Real-time (within 3s of reaction)",
    },
}

ACTION_TYPE_ICON = {
    "collect":  "🔄",
    "analyse":  "🔍",
    "notify":   "📢",
    "task":     "✅",
    "approve":  "👍",
    "execute":  "⚡",
    "refresh":  "🔁",
    "health":   "💚",
}

STATUS_COLOR = {
    "ok":       "#2ecc71",
    "failed":   "#e74c3c",
    "skipped":  "#95a5a6",
    "approved": "#2ecc71",
    "rejected": "#e67e22",
}


def _read_csv(days: int = 30) -> list[dict]:
    """Read activity_log.csv, return last N days of rows newest-first."""
    if not _CSV_PATH.exists():
        return []
    cutoff = str(date.today() - timedelta(days=days))
    rows = []
    try:
        with open(_CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("date", "") >= cutoff:
                    rows.append(row)
    except Exception:
        return []
    return list(reversed(rows))  # newest first


def get_summary(days: int = 30) -> dict:
    """Aggregate counts for the dashboard header."""
    rows = _read_csv(days)
    counts = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)

    for r in rows:
        atype = r.get("action_type", "")
        status = r.get("status", "")
        counts["total_actions"] += 1
        counts[f"type_{atype}"] += 1
        if atype == "notify":
            counts["slack_messages"] += int(r.get("count") or 1)
        elif atype == "task":
            counts["asana_tasks"] += int(r.get("count") or 0)
        elif atype == "collect":
            counts["api_calls"] += 1
            counts["rows_collected"] += int(r.get("count") or 0)
        elif atype == "approve":
            if status == "approved":
                counts["approvals_approved"] += 1
            elif status == "rejected":
                counts["approvals_rejected"] += 1
        elif atype == "execute":
            counts["executions"] += 1
        if status == "failed":
            counts["errors"] += 1
        by_day[r.get("date", "")] += 1

    counts["channels_active"] = len({
        r.get("channel", "") for r in rows
        if r.get("channel") and r.get("channel") not in ("all", "")
    })
    counts["roles_run"] = len({r.get("role") for r in rows if r.get("role")})
    counts["by_day"] = dict(by_day)
    return dict(counts)


def get_data_json(days: int = 30) -> dict:
    """Return full structured data for /activity/data endpoint."""
    rows = _read_csv(days)
    summary = get_summary(days)
    return {
        "summary": summary,
        "recent":  rows[:100],
        "workflows": WORKFLOWS,
    }


def render_dashboard_html(days: int = 30) -> str:
    """Render the full activity dashboard as HTML."""
    data    = get_data_json(days)
    s       = data["summary"]
    rows    = data["recent"]
    wf      = data["workflows"]
    today   = str(date.today())

    # ── Heatmap: contributions by day (last 30 days) ─────────────────────────
    by_day = s.get("by_day", {})
    heatmap_cells = ""
    for i in range(29, -1, -1):
        d = str(date.today() - timedelta(days=i))
        n = by_day.get(d, 0)
        intensity = min(n / 20, 1.0)
        color = f"rgba(39,174,96,{max(0.1, intensity)})" if n else "#1a1a2e"
        heatmap_cells += (
            f'<div class="hm-cell" title="{d}: {n} actions" '
            f'style="background:{color}"></div>'
        )

    # ── Stats cards ───────────────────────────────────────────────────────────
    def card(label, value, icon=""):
        return (f'<div class="stat-card"><div class="stat-icon">{icon}</div>'
                f'<div class="stat-val">{value:,}</div>'
                f'<div class="stat-label">{label}</div></div>')

    stats = "".join([
        card("Slack Messages Sent",  s.get("slack_messages", 0),      "📢"),
        card("Asana Tasks Created",  s.get("asana_tasks", 0),         "✅"),
        card("API Calls Made",       s.get("api_calls", 0),           "🔄"),
        card("Channels Active",      s.get("channels_active", 0),     "📡"),
        card("Approved Actions",     s.get("approvals_approved", 0),  "👍"),
        card("Rejected Actions",     s.get("approvals_rejected", 0),  "❌"),
        card("Executions",           s.get("executions", 0),          "⚡"),
        card("Errors",               s.get("errors", 0),              "🔴"),
    ])

    # ── Recent activity table ─────────────────────────────────────────────────
    table_rows = ""
    for r in rows[:50]:
        status   = r.get("status", "ok")
        sc       = STATUS_COLOR.get(status, "#aaa")
        icon     = ACTION_TYPE_ICON.get(r.get("action_type", ""), "•")
        ts_short = r.get("timestamp", "")[:16].replace("T", " ")
        details  = r.get("details", "")
        det_str  = ""
        if details:
            try:
                det_str = json.dumps(json.loads(details), indent=None)[:120]
            except Exception:
                det_str = details[:120]
        table_rows += f"""
        <tr>
          <td class="ts">{ts_short}</td>
          <td>{r.get("date","")}</td>
          <td><span class="tag">{r.get("role","")}</span></td>
          <td>{icon} {r.get("action_type","")}</td>
          <td class="action-text">{r.get("action","")}</td>
          <td>{r.get("channel","") or "—"}</td>
          <td><span class="status-dot" style="background:{sc}"></span>{status}</td>
          <td class="count">{r.get("count","") or "—"}</td>
          <td class="det">{det_str}</td>
        </tr>"""

    # ── Workflows section ────────────────────────────────────────────────────
    wf_cards = ""
    for wf_id, wf_data in wf.items():
        steps_html = "".join(f"<li>{step}</li>" for step in wf_data["steps"])
        wf_cards += f"""
        <div class="wf-card" id="wf-{wf_id}">
          <div class="wf-header" onclick="toggleWf('{wf_id}')">
            <span class="wf-title">{wf_data['label']}</span>
            <span class="wf-schedule">{wf_data['schedule']}</span>
            <span class="wf-toggle">▼</span>
          </div>
          <div class="wf-body" id="wfb-{wf_id}" style="display:none">
            <ol>{steps_html}</ol>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Nexa Agent Activity</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            background: #0f0f1a; color: #e0e0e0; font-size: 13px; }}
    .header {{ padding: 20px 32px; border-bottom: 1px solid #222;
               display: flex; align-items: center; gap: 16px; }}
    .header h1 {{ font-size: 18px; font-weight: 600; color: #fff; }}
    .header .sub {{ color: #888; font-size: 12px; }}
    .perf-link {{ margin-left: auto; color: #27ae60; text-decoration: none;
                  font-size: 12px; }}
    .perf-link:hover {{ text-decoration: underline; }}
    .section {{ padding: 20px 32px; }}
    .section-title {{ font-size: 12px; font-weight: 600; color: #888;
                      text-transform: uppercase; letter-spacing: 1px;
                      margin-bottom: 12px; }}
    /* heatmap */
    .heatmap {{ display: grid; grid-template-columns: repeat(30,1fr);
                gap: 3px; max-width: 600px; }}
    .hm-cell {{ width: 16px; height: 16px; border-radius: 2px; cursor: default; }}
    /* stat cards */
    .stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 4px; }}
    .stat-card {{ background: #1a1a2e; border: 1px solid #2a2a4a;
                  border-radius: 8px; padding: 14px 18px;
                  min-width: 130px; flex: 1 1 130px; }}
    .stat-icon {{ font-size: 18px; margin-bottom: 6px; }}
    .stat-val {{ font-size: 22px; font-weight: 700; color: #fff; }}
    .stat-label {{ font-size: 11px; color: #888; margin-top: 2px; }}
    /* table */
    .tbl-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th {{ background: #1a1a2e; color: #888; font-weight: 500; padding: 8px 10px;
          text-align: left; border-bottom: 1px solid #2a2a4a; white-space:nowrap; }}
    td {{ padding: 7px 10px; border-bottom: 1px solid #1a1a2e;
          vertical-align: top; }}
    tr:hover td {{ background: #1a1a2e; }}
    .ts {{ color: #666; white-space: nowrap; }}
    .tag {{ background: #2a2a4a; padding: 2px 6px; border-radius: 4px;
            font-size: 11px; white-space: nowrap; }}
    .status-dot {{ display: inline-block; width: 7px; height: 7px;
                   border-radius: 50%; margin-right: 5px; vertical-align: middle;}}
    .count {{ text-align: right; color: #27ae60; }}
    .det {{ color: #555; font-size: 11px; max-width: 220px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .action-text {{ max-width: 280px; }}
    /* workflows */
    .wf-card {{ background: #1a1a2e; border: 1px solid #2a2a4a;
                border-radius: 8px; margin-bottom: 8px; overflow: hidden; }}
    .wf-header {{ display: flex; align-items: center; gap: 12px;
                  padding: 12px 16px; cursor: pointer; user-select: none; }}
    .wf-header:hover {{ background: #20203a; }}
    .wf-title {{ font-weight: 600; color: #fff; flex: 1; }}
    .wf-schedule {{ color: #888; font-size: 11px; }}
    .wf-toggle {{ color: #555; font-size: 11px; }}
    .wf-body {{ padding: 0 16px 14px 16px; }}
    .wf-body ol {{ padding-left: 20px; color: #aaa; line-height: 1.8; }}
    .divider {{ border: none; border-top: 1px solid #1a1a2e; }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🤖 Nexa Agent Activity</h1>
      <div class="sub">Last 30 days · Updated {today}</div>
    </div>
    <a class="perf-link" href="{os.getenv('DASHBOARD_URL','https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest')}"
       target="_blank">qoyod-marketing-performance →</a>
  </div>

  <div class="section">
    <div class="section-title">Activity — last 30 days</div>
    <div class="heatmap">{heatmap_cells}</div>
  </div>

  <hr class="divider">

  <div class="section">
    <div class="section-title">Counters</div>
    <div class="stats">{stats}</div>
  </div>

  <hr class="divider">

  <div class="section">
    <div class="section-title">Recent Actions</div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Time (UTC)</th><th>Date</th><th>Role</th>
            <th>Type</th><th>Action</th><th>Channel</th>
            <th>Status</th><th>#</th><th>Details</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
  </div>

  <hr class="divider">

  <div class="section">
    <div class="section-title">Workflows — click to expand</div>
    {wf_cards}
  </div>

  <script>
    function toggleWf(id) {{
      const body = document.getElementById('wfb-' + id);
      body.style.display = body.style.display === 'none' ? 'block' : 'none';
    }}
    // Auto-refresh every 5 minutes
    setTimeout(() => location.reload(), 300000);
  </script>
</body>
</html>"""
