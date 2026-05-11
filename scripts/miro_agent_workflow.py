"""
scripts/miro_agent_workflow.py
===============================
Qoyod Performance Agent — 4-column architecture with two brain tracks.

    INPUTS  →  BRAIN (2 tracks)  →  ACTIONS  →  OUTPUTS

Run:
    python scripts/miro_agent_workflow.py
"""
from __future__ import annotations

import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD = os.getenv("MIRO_BOARD_ID")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = f"https://api.miro.com/v2/boards/{BOARD}"


def _post(path, payload):
    r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=15)
    if not r.ok:
        print(f"FAIL {path}: {r.status_code} — {r.text[:200]}")
        return None
    return r.json()


def _delete_all_existing():
    deleted = 0
    for kind in ("connectors", "shapes", "sticky_notes", "cards", "texts", "frames", "images"):
        cursor = None
        while True:
            url = f"{BASE}/{kind}?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            r = requests.get(url, headers=H, timeout=15)
            if not r.ok:
                break
            d = r.json()
            for item in d.get("data", []):
                requests.delete(f"{BASE}/{kind}/{item['id']}", headers=H, timeout=10)
                deleted += 1
            cursor = d.get("cursor")
            if not cursor:
                break
    print(f"[miro] cleared {deleted} existing items")
    time.sleep(2)


def shape(text_content, x, y, w=300, h=120, fill="#dbeafe", border="#2563eb",
          font_color="#0f172a", font_size=14):
    return _post("/shapes", {
        "data": {"content": text_content, "shape": "round_rectangle"},
        "style": {
            "fillColor": fill, "borderColor": border, "borderWidth": "2",
            "fontFamily": "open_sans", "fontSize": str(font_size),
            "color": font_color, "textAlign": "center",
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def label(content, x, y, w=340, font=13, color="#64748b", align="center"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def connect(from_id, to_id, lbl="", color="#94a3b8"):
    if not from_id or not to_id:
        return None
    return _post("/connectors", {
        "startItem": {"id": from_id},
        "endItem":   {"id": to_id},
        "captions":  [{"content": lbl}] if lbl else [],
        "style": {"strokeColor": color, "strokeWidth": "2"},
    })


def build():
    _delete_all_existing()

    # ── Layout ─────────────────────────────────────────────────────────────────
    CX   = {"inputs": -1100, "brain": -200, "actions": 620, "outputs": 1400}
    W    = 310
    H    = 118
    G    = 30       # gap between rows
    TOP  = -900

    # ── Title ──────────────────────────────────────────────────────────────────
    _post("/texts", {
        "data": {"content": "<b>Qoyod Performance Agent</b>"},
        "style": {"fontSize": "36", "color": "#0f172a", "textAlign": "center"},
        "position": {"x": 150, "y": -1130, "origin": "center"},
        "geometry": {"width": 1000},
    })
    _post("/texts", {
        "data": {"content": "Two runtimes: Nightly 03:00 Riyadh (operational) · Every 6h (reporting)  ·  Nothing executes without human ✅"},
        "style": {"fontSize": "14", "color": "#64748b", "textAlign": "center"},
        "position": {"x": 150, "y": -1075, "origin": "center"},
        "geometry": {"width": 1300},
    })

    # ── Column headers ─────────────────────────────────────────────────────────
    headers = [
        ("inputs",  "INPUTS",   "What the agent reads",              "#1e40af"),
        ("brain",   "BRAIN",    "Two tracks: operational + reporting","#7c3aed"),
        ("actions", "ACTIONS",  "What the agent does",               "#15803d"),
        ("outputs", "OUTPUTS",  "Where things land",                 "#0f172a"),
    ]
    for col, title, sub, color in headers:
        _post("/texts", {
            "data": {"content": f"<b>{title}</b>"},
            "style": {"fontSize": "20", "color": color, "textAlign": "center"},
            "position": {"x": CX[col], "y": TOP - 100, "origin": "center"},
            "geometry": {"width": W},
        })
        label(sub, CX[col], TOP - 68, w=W, font=12)

    # ── INPUTS — 5 nodes ───────────────────────────────────────────────────────
    in_data = [
        ("Ad Platforms\nMeta · Google Ads · TikTok\nLinkedIn",
         "#dbeafe", "#1e40af"),
        ("Adspirer MCP\nExecution API\nBudget · pause · keyword mutations",
         "#e0f2fe", "#0369a1"),
        ("HubSpot CRM\nLeads (Lead Module only)\nDeals · Read-only by default",
         "#fecaca", "#991b1b"),
        ("BigQuery\nqoyod_marketing dataset\nt_* materialized tables (6h refresh)",
         "#fde68a", "#a16207"),
        ("Anthropic Claude API\nReasoning + analysis\nclaude-sonnet-4-6",
         "#f9a8d4", "#9d174d"),
    ]
    in_ids = []
    for i, (txt, fill, border) in enumerate(in_data):
        n = shape(txt, CX["inputs"], TOP + i * (H + G), w=W, h=H,
                  fill=fill, border=border, font_size=13)
        in_ids.append(n)

    # ── BRAIN — 4 nodes in 2 tracks ───────────────────────────────────────────
    # Track A: Operational (nightly 03:00) — top half
    track_a_top = TOP + 0.0 * (H + G)
    analysis = shape(
        "🧠 ANALYSIS — Nightly 03:00\nCPQL/CPL health · Anomaly detection\nKeyword audit (Sundays) · Ad audit",
        CX["brain"], track_a_top,
        w=W, h=H + 20, fill="#7c3aed", border="#4c1d95",
        font_color="#ffffff", font_size=13)

    task_flow = shape(
        "🤖 TASK-FLOW (code)\nRoutes findings → Asana + #approvals\nNever auto-executes pause/scale",
        CX["brain"], track_a_top + (H + G) + 20,
        w=W, h=H, fill="#0f172a", border="#0f172a",
        font_color="#ffffff", font_size=13)

    # Divider label between tracks
    label("── Reporting track (every 6h) ──", CX["brain"],
          track_a_top + 2 * (H + G) + 60, w=W + 40, font=11, color="#94a3b8")

    # Track B: Reporting (6h) — bottom half
    track_b_top = track_a_top + 2 * (H + G) + 90

    data_refresh = shape(
        "⟳ DATA REFRESH — Every 6h\n22 collectors → BQ upsert\nView materialisation → t_* tables\nHubSpot 30-day lead resync",
        CX["brain"], track_b_top,
        w=W, h=H + 20, fill="#0e7490", border="#155e75",
        font_color="#ffffff", font_size=13)

    health_checks = shape(
        "🩺 HEALTH CHECKS — Hourly 09–17\nAll connectors + APIs + BQ\nResults logged → Activity Dashboard\nOn-demand via dashboard button",
        CX["brain"], track_b_top + (H + G) + 20,
        w=W, h=H + 10, fill="#374151", border="#111827",
        font_color="#ffffff", font_size=13)

    # ── ACTIONS — 3 nodes ──────────────────────────────────────────────────────
    act_top = TOP + 0.3 * (H + G)

    approval_req = shape(
        "APPROVAL DIGEST\n#approvals — max 2 msgs/night\nScale + pause in one batch\nOptimize/junk → Asana only",
        CX["actions"], act_top,
        w=W, h=H + 20, fill="#fef3c7", border="#92400e", font_size=13)

    execute = shape(
        "EXECUTE ON ✅\nUser reaction → executor\nScale +25% · Pause campaign\nAsana task updated",
        CX["actions"], act_top + (H + G) + 20,
        w=W, h=H + 10, fill="#dcfce7", border="#15803d", font_size=13)

    notify_box = shape(
        "NOTIFY\n1 message → #notify\nPerformance summary · Alerts\nAsana counts",
        CX["actions"], act_top + 2 * (H + G) + 30,
        w=W, h=H, fill="#e0e7ff", border="#4338ca", font_size=13)

    # ── OUTPUTS — 5 nodes ──────────────────────────────────────────────────────
    out_top = TOP + 0.1 * (H + G)

    out_slack = shape(
        "SLACK\n#notify  max 1 msg/night\n#approvals  max 2 msgs/night\n✅/❌ reactions trigger execution",
        CX["outputs"], out_top,
        w=W, h=H + 10, fill="#bfdbfe", border="#1e40af", font_size=13)

    out_asana = shape(
        "ASANA\n6 projects · 7 channels\nPENDING APPROVAL tasks\nOverdue count tracked daily",
        CX["outputs"], out_top + (H + G) + 10,
        w=W, h=H + 10, fill="#fbcfe8", border="#9f1239", font_size=13)

    out_hex = shape(
        "HEX DASHBOARD\nCampaign · Ad set · Ad · Keyword\nCPL / CPQL / ROAS trends\nRefreshed every 6h via t_* tables",
        CX["outputs"], out_top + 2 * (H + G) + 20,
        w=W, h=H + 10, fill="#bbf7d0", border="#15803d", font_size=13)

    out_activity = shape(
        "ACTIVITY DASHBOARD\n/activity — Agent transparency\nTasks done · Ads paused · Approval rate\nData Hygiene health checks",
        CX["outputs"], out_top + 3 * (H + G) + 30,
        w=W, h=H + 10, fill="#c7d2fe", border="#4338ca", font_size=13)

    out_bq = shape(
        "BIGQUERY\nt_* tables refreshed every 6h\nUTC stored · Riyadh for UI\nAll spend in USD",
        CX["outputs"], out_top + 4 * (H + G) + 40,
        w=W, h=H, fill="#fde68a", border="#a16207", font_size=13)

    # ── Connections ────────────────────────────────────────────────────────────
    # All inputs → analysis (operational track)
    for src in in_ids:
        connect(src["id"], analysis["id"], color="#94a3b8")

    # analysis → task-flow
    connect(analysis["id"], task_flow["id"], "findings", "#7c3aed")

    # task-flow → actions
    connect(task_flow["id"], approval_req["id"], "scale/pause", "#d97706")
    connect(task_flow["id"], notify_box["id"],   "summary",     "#4338ca")

    # approval_req → slack (#approvals)
    connect(approval_req["id"], out_slack["id"], "posts to #approvals", "#d97706")

    # slack ✅ → execute
    connect(out_slack["id"], execute["id"], "✅ reaction", "#16a34a")

    # execute → adspirer (calls back)
    connect(execute["id"], in_ids[1]["id"], "calls executor", "#0369a1")

    # execute → asana
    connect(execute["id"], out_asana["id"], "updates task", "#9f1239")

    # task-flow → asana
    connect(task_flow["id"], out_asana["id"], "creates tasks", "#9f1239")

    # notify → slack + dashboard
    connect(notify_box["id"], out_slack["id"], "1 msg to #notify", "#4338ca")
    connect(notify_box["id"], out_hex["id"],   "dashboard URL",    "#15803d")

    # reporting track
    connect(in_ids[3]["id"], data_refresh["id"], "reads/writes", "#a16207")
    connect(data_refresh["id"], out_bq["id"],    "upsert + t_*", "#a16207")
    connect(data_refresh["id"], out_hex["id"],   "triggers Hex re-run", "#15803d")

    # health checks → activity dashboard
    connect(health_checks["id"], out_activity["id"], "logs results", "#4338ca")

    # BigQuery feeds analysis
    connect(in_ids[3]["id"], analysis["id"], "reads", "#a16207")

    print("[miro] Main flow done. Rebuilding use cases...")

    import subprocess, sys
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "miro_use_cases_v2.py")],
        check=True,
    )

    print(f"[miro] Board fully rebuilt: https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
