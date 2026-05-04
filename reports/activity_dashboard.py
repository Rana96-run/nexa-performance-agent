"""
reports/activity_dashboard.py
==============================
Agent Activity Dashboard — reads logs/activity_log.csv and serves
a live HTML dashboard at GET /activity on Railway.

Separate from the Hex performance dashboard (qoyod-marketing-performance).
This shows what the AGENT did: Slack messages, Asana tasks, API collects,
approval decisions, role runs, and clickable workflow diagrams.
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

_CSV_PATH = Path(__file__).parent.parent / "logs" / "activity_log.csv"

WORKFLOWS = {
    "bq_refresh": {
        "label":    "BQ Data Refresh",
        "schedule": "Every 6h (03:00 09:00 15:00 21:00 Riyadh)",
        "steps": [
            "Run all channel collectors (Google Ads, Meta, Snapchat, TikTok, LinkedIn, Bing, HubSpot)",
            "Run sub-campaign collectors (adgroups, keywords, adsets, ads)",
            "Refresh all BigQuery views (paid_channel_daily, hubspot_leads_module_daily, …)",
            "Sync activity_log.csv → BQ agent_activity_log",
            "Send heartbeat to #notify",
        ],
    },
    "daily_agent": {
        "label":    "Daily Agent Cycle",
        "schedule": "Daily at 03:00 Riyadh",
        "steps": [
            "Guard: skip if already ran today",
            "Collect data from BQ cache (campaign grain, all channels)",
            "Run deterministic analysers: campaign_health_tasks, spike_detector, google_ads_audit_tasks",
            "Batch create Asana tasks from all findings",
            "Post daily summary to Slack #notify",
            "Send scale/pause/optimize approvals to #approvals",
        ],
    },
    "paid_media_strategist": {
        "label":    "Paid Media Strategist (Claude AI)",
        "schedule": "Weekly / Monthly / Quarterly / On-demand",
        "steps": [
            "Load system prompt (shared context + strategist role)",
            "Append Drive asset index (creative briefs, brand guidelines)",
            "Send 7-day performance data to Claude API",
            "Parse JSON decisions from response",
            "Create Asana tasks + send approvals to #approvals",
        ],
    },
    "keyword_approval": {
        "label":    "Keyword Approval",
        "schedule": "Weekly (part of weekly cadence)",
        "steps": [
            "Audit Google Ads search terms (last 7 days)",
            "Classify: negative / converting / watch",
            "Auto-execute negatives immediately (no approval needed)",
            "Converting terms → Asana task only (no Slack)",
            "Watch terms → logged, no action",
        ],
    },
    "campaign_health": {
        "label":    "Campaign Health Tasks",
        "schedule": "Daily (part of nightly cycle)",
        "steps": [
            "Query BQ for all campaigns (last 14 days minimum)",
            "Check CPQL vs thresholds (scale zone / pause zone)",
            "Scale: CPQL ≤ scale threshold → send to #approvals",
            "Pause: CPQL ≥ pause threshold AND 14d window met → send to #approvals",
            "Junk leads: cheap CPL but low qual rate → flag to #approvals",
            "Create Asana task for each finding",
        ],
    },
    "slack_approval": {
        "label":    "Slack Approval Flow",
        "schedule": "Real-time (within 3s of reaction)",
        "steps": [
            "Approval message posted to #approvals with ✅/❌",
            "Team reacts with ✅ (approve) or ❌ (reject)",
            "Slack Events API webhook fires → /slack/events on Railway",
            "_handle_reaction() executes or skips the action via channel API",
            "Result posted as thread reply in #approvals",
            "Asana task updated with decision and outcome",
        ],
    },
}

ACTION_ICON = {
    "collect": "🔄", "analyse": "🔍", "notify": "📢",
    "task": "✅", "approve": "👍", "execute": "⚡",
    "refresh": "🔁", "health": "💚",
}

STATUS_COLOR = {
    "ok": "#2ecc71", "failed": "#e74c3c", "skipped": "#95a5a6",
    "approved": "#2ecc71", "rejected": "#e67e22",
}


def _read_csv(days: int = 30) -> list[dict]:
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
    return list(reversed(rows))


def _summary(rows: list[dict]) -> dict:
    s: dict = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for r in rows:
        atype  = r.get("action_type", "")
        status = r.get("status", "")
        s["total"] += 1
        if atype == "notify":
            s["slack_messages"] += int(r.get("count") or 1)
        elif atype == "task":
            s["asana_tasks"] += int(r.get("count") or 0)
        elif atype == "collect":
            s["api_calls"] += 1
            s["rows_collected"] += int(r.get("count") or 0)
        elif atype == "approve":
            if status == "approved":   s["approved"] += 1
            elif status == "rejected": s["rejected"] += 1
        elif atype == "execute":
            s["executions"] += 1
        if status == "failed":
            s["errors"] += 1
        by_day[r.get("date", "")] += 1
    s["channels"] = len({r.get("channel") for r in rows
                          if r.get("channel") not in ("", "all", None)})
    s["roles"]    = len({r.get("role") for r in rows if r.get("role")})
    s["by_day"]   = dict(by_day)
    return dict(s)


def render_dashboard_html(days: int = 30) -> str:
    rows = _read_csv(days)
    s    = _summary(rows)
    today = str(date.today())
    hex_url = os.getenv(
        "DASHBOARD_URL",
        "https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/"
        "Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest",
    )

    # ── Heatmap ───────────────────────────────────────────────────────────────
    by_day = s.get("by_day", {})
    cells = ""
    for i in range(29, -1, -1):
        d = str(date.today() - timedelta(days=i))
        n = by_day.get(d, 0)
        alpha = min(n / 20, 1.0)
        bg = f"rgba(39,174,96,{max(0.12, alpha)})" if n else "#1a1a2e"
        cells += f'<div class="hm" title="{d}: {n}" style="background:{bg}"></div>'

    # ── Stat cards ────────────────────────────────────────────────────────────
    def card(icon, val, label):
        return (f'<div class="card"><div class="ci">{icon}</div>'
                f'<div class="cv">{val:,}</div>'
                f'<div class="cl">{label}</div></div>')

    cards = "".join([
        card("📢", s.get("slack_messages", 0), "Slack Messages"),
        card("✅", s.get("asana_tasks",    0), "Asana Tasks"),
        card("🔄", s.get("api_calls",      0), "API Calls"),
        card("📡", s.get("channels",       0), "Channels Active"),
        card("👍", s.get("approved",       0), "Approved"),
        card("❌", s.get("rejected",       0), "Rejected"),
        card("⚡", s.get("executions",     0), "Executions"),
        card("🔴", s.get("errors",         0), "Errors"),
    ])

    # ── Table rows ────────────────────────────────────────────────────────────
    trows = ""
    for r in rows[:100]:
        st  = r.get("status", "ok")
        sc  = STATUS_COLOR.get(st, "#aaa")
        ico = ACTION_ICON.get(r.get("action_type", ""), "•")
        ts  = r.get("timestamp", "")[:16].replace("T", " ")
        det = r.get("details", "")
        try:
            det = json.dumps(json.loads(det))[:120] if det else ""
        except Exception:
            det = det[:120]
        trows += f"""<tr>
          <td class="ts">{ts}</td>
          <td>{r.get("date","")}</td>
          <td><span class="tag">{r.get("role","")}</span></td>
          <td>{ico} {r.get("action_type","")}</td>
          <td class="act">{r.get("action","")}</td>
          <td>{r.get("channel","") or "—"}</td>
          <td><span class="dot" style="background:{sc}"></span>{st}</td>
          <td class="num">{r.get("count","") or "—"}</td>
          <td class="det">{det}</td>
        </tr>"""

    # ── Workflow cards ────────────────────────────────────────────────────────
    wf_html = ""
    for wid, wf in WORKFLOWS.items():
        steps = "".join(f"<li>{s}</li>" for s in wf["steps"])
        wf_html += f"""<div class="wfc">
          <div class="wfh" onclick="t('{wid}')">
            <span class="wft">{wf['label']}</span>
            <span class="wfs">{wf['schedule']}</span>
            <span class="wfa">▼</span>
          </div>
          <div class="wfb" id="w{wid}" style="display:none">
            <ol>{steps}</ol>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Nexa Agent Activity</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#0f0f1a;color:#e0e0e0;font-size:13px}}
    .hdr{{padding:18px 28px;border-bottom:1px solid #1e1e30;
          display:flex;align-items:center;gap:14px}}
    .hdr h1{{font-size:17px;font-weight:600;color:#fff}}
    .hdr .sub{{color:#666;font-size:11px;margin-top:2px}}
    .perf{{margin-left:auto;color:#27ae60;text-decoration:none;font-size:12px}}
    .perf:hover{{text-decoration:underline}}
    .sec{{padding:18px 28px}}
    .stl{{font-size:11px;font-weight:600;color:#666;text-transform:uppercase;
          letter-spacing:1px;margin-bottom:10px}}
    .heatmap{{display:grid;grid-template-columns:repeat(30,1fr);gap:3px;max-width:540px}}
    .hm{{height:14px;border-radius:2px;cursor:default}}
    .cards{{display:flex;flex-wrap:wrap;gap:10px}}
    .card{{background:#1a1a2e;border:1px solid #242440;border-radius:8px;
           padding:12px 16px;min-width:120px;flex:1 1 120px}}
    .ci{{font-size:16px;margin-bottom:4px}}
    .cv{{font-size:20px;font-weight:700;color:#fff}}
    .cl{{font-size:11px;color:#666;margin-top:2px}}
    .tbl{{overflow-x:auto}}
    table{{width:100%;border-collapse:collapse;font-size:12px}}
    th{{background:#1a1a2e;color:#666;font-weight:500;padding:7px 9px;
        text-align:left;border-bottom:1px solid #1e1e30;white-space:nowrap}}
    td{{padding:6px 9px;border-bottom:1px solid #141420;vertical-align:top}}
    tr:hover td{{background:#1a1a2e}}
    .ts{{color:#555;white-space:nowrap}}
    .tag{{background:#1e1e30;padding:2px 6px;border-radius:3px;font-size:11px}}
    .dot{{display:inline-block;width:6px;height:6px;border-radius:50%;
          margin-right:4px;vertical-align:middle}}
    .num{{text-align:right;color:#27ae60}}
    .det{{color:#444;font-size:11px;max-width:200px;
          overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .act{{max-width:260px}}
    .wfc{{background:#1a1a2e;border:1px solid #242440;border-radius:7px;
          margin-bottom:7px;overflow:hidden}}
    .wfh{{display:flex;align-items:center;gap:10px;padding:11px 14px;
          cursor:pointer;user-select:none}}
    .wfh:hover{{background:#20203a}}
    .wft{{font-weight:600;color:#fff;flex:1}}
    .wfs{{color:#666;font-size:11px}}
    .wfa{{color:#444;font-size:11px}}
    .wfb{{padding:0 14px 12px 14px}}
    .wfb ol{{padding-left:18px;color:#999;line-height:1.9}}
    hr{{border:none;border-top:1px solid #141420}}
  </style>
</head>
<body>
  <div class="hdr">
    <div>
      <h1>🤖 Nexa Agent Activity</h1>
      <div class="sub">Last {days} days · {today}</div>
    </div>
    <a class="perf" href="{hex_url}" target="_blank">qoyod-marketing-performance ↗</a>
  </div>

  <div class="sec">
    <div class="stl">Activity — last 30 days</div>
    <div class="heatmap">{cells}</div>
  </div><hr>

  <div class="sec">
    <div class="stl">Counters</div>
    <div class="cards">{cards}</div>
  </div><hr>

  <div class="sec">
    <div class="stl">Recent Actions</div>
    <div class="tbl"><table>
      <thead><tr>
        <th>Time UTC</th><th>Date</th><th>Role</th><th>Type</th>
        <th>Action</th><th>Channel</th><th>Status</th><th>#</th><th>Details</th>
      </tr></thead>
      <tbody>{trows}</tbody>
    </table></div>
  </div><hr>

  <div class="sec">
    <div class="stl">Workflows — click to expand</div>
    {wf_html}
  </div>

  <script>
    function t(id){{
      var b=document.getElementById('w'+id);
      b.style.display=b.style.display==='none'?'block':'none';
    }}
    setTimeout(()=>location.reload(), 300000);
  </script>
</body>
</html>"""


def get_data_json(days: int = 30) -> dict:
    rows = _read_csv(days)
    return {"summary": _summary(rows), "recent": rows[:200], "workflows": WORKFLOWS}
