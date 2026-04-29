"""
scripts/miro_agent_workflow.py
===============================
Renders the Nexa Performance Agent flow as 4 VERTICAL COLUMNS.

    INPUTS              BRAIN              ACTIONS             OUTPUTS
   (left -> right flow; arrows show data movement between columns)

Run with:
    python scripts/miro_agent_workflow.py
"""
from __future__ import annotations

import os
import time
import requests
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
    for kind in ("connectors", "shapes", "sticky_notes", "cards", "texts", "frames"):
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
          font_color="#0f172a", font_size=15):
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


def text(content, x, y, w=400, font=24, color="#0f172a", align="center"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def connect(from_id, to_id, label="", color="#475569"):
    if not from_id or not to_id:
        return None
    return _post("/connectors", {
        "startItem": {"id": from_id},
        "endItem":   {"id": to_id},
        "captions":  [{"content": label}] if label else [],
        "style": {"strokeColor": color, "strokeWidth": "3"},
    })


# ─── Build ────────────────────────────────────────────────────────────────────

def build():
    _delete_all_existing()

    # ── Layout constants ────────────────────────────────────────────────────
    # 4 columns × ~400px apart
    COL_X = {
        "inputs":  -1100,
        "brain":   -350,
        "actions":  400,
        "outputs": 1150,
    }
    BOX_W = 320     # all boxes same width for tidy column edges
    BOX_H = 120     # all boxes same height; long content can wrap

    # Title above the columns
    text("**Nexa — Performance Agent**", x=25, y=-1500, w=900, font=40)
    text("Runs autonomously every night at 03:00 Riyadh",
         x=25, y=-1430, w=900, font=18, color="#64748b")

    # Column headers
    text("INPUTS",   x=COL_X["inputs"],  y=-1280, w=320, font=24, color="#1e40af")
    text("Data the agent reads",
         x=COL_X["inputs"],  y=-1240, w=320, font=13, color="#64748b")

    text("BRAIN",    x=COL_X["brain"],   y=-1280, w=320, font=24, color="#7c3aed")
    text("3 Claude roles + 1 code assistant",
         x=COL_X["brain"],   y=-1240, w=320, font=13, color="#64748b")

    text("ACTIONS",  x=COL_X["actions"], y=-1280, w=320, font=24, color="#15803d")
    text("What the agent does",
         x=COL_X["actions"], y=-1240, w=320, font=13, color="#64748b")

    text("OUTPUTS",  x=COL_X["outputs"], y=-1280, w=320, font=24, color="#0f172a")
    text("Where things land",
         x=COL_X["outputs"], y=-1240, w=320, font=13, color="#64748b")

    # ── Column 1: INPUTS (5 boxes stacked vertically) ───────────────────────
    inputs_data = [
        ("Ad Platforms\nGoogle · Meta · Snap · TikTok\nLinkedIn · Microsoft", "#dbeafe", "#1e40af"),
        ("HubSpot CRM\nLeads · Deals · Webhooks",                              "#fecaca", "#991b1b"),
        ("BigQuery\nReporting layer",                                          "#fde68a", "#a16207"),
        ("Google Drive\nMedia Planning · Social Analysis",                     "#a7f3d0", "#047857"),
        ("Anthropic Claude API\n(reasoning)",                                  "#f9a8d4", "#9d174d"),
    ]
    in_ids = []
    y = -1100
    for txt, fill, border in inputs_data:
        in_ids.append(shape(txt, COL_X["inputs"], y, w=BOX_W, h=BOX_H,
                            fill=fill, border=border, font_size=14))
        y += BOX_H + 30   # gap between rows

    # ── Column 2: BRAIN (4 boxes — 3 roles + assistant) ─────────────────────
    role_buyer = shape(
        "🎯 MEDIA BUYER\nDaily pauses · scaling\nBudget · creative QA",
        x=COL_X["brain"], y=-1100, w=BOX_W, h=BOX_H,
        fill="#3b82f6", border="#1e3a8a", font_color="#ffffff", font_size=14)
    role_analyst = shape(
        "📊 ANALYST\nTrend & anomaly\nLead-quality drift",
        x=COL_X["brain"], y=-950, w=BOX_W, h=BOX_H,
        fill="#8b5cf6", border="#5b21b6", font_color="#ffffff", font_size=14)
    role_strat = shape(
        "🧭 STRATEGIST\nWeekly+ scale plans\nCreative briefs",
        x=COL_X["brain"], y=-800, w=BOX_W, h=BOX_H,
        fill="#ec4899", border="#9d174d", font_color="#ffffff", font_size=14)
    assistant = shape(
        "🤖 TASK-FLOW (code)\nRoutes JSON ->\nright Asana project + section",
        x=COL_X["brain"], y=-650, w=BOX_W, h=BOX_H,
        fill="#10b981", border="#047857", font_color="#ffffff", font_size=14)

    # ── Column 3: ACTIONS (4 boxes) ─────────────────────────────────────────
    direct = shape(
        "DIRECT\n(auto-execute)\nPause ad · keyword\nExclude placement",
        x=COL_X["actions"], y=-1100, w=BOX_W, h=BOX_H,
        fill="#fee2e2", border="#991b1b", font_size=14)
    approval = shape(
        "APPROVAL ✅\nScale budget · adjust bids\nPause campaign\nLaunch new audience",
        x=COL_X["actions"], y=-950, w=BOX_W, h=BOX_H,
        fill="#fef3c7", border="#92400e", font_size=14)
    notify = shape(
        "NOTIFY\nDaily report URL\nSpike alerts\nAsana task links",
        x=COL_X["actions"], y=-800, w=BOX_W, h=BOX_H,
        fill="#dcfce7", border="#15803d", font_size=14)
    autofix = shape(
        "AUTO-FIX (Zapier)\nReplay errors\nResume held tasks\nDisable broken Zaps",
        x=COL_X["actions"], y=-650, w=BOX_W, h=BOX_H,
        fill="#ede9fe", border="#5b21b6", font_size=14)

    # ── Column 4: OUTPUTS (4 boxes) ─────────────────────────────────────────
    out_asana = shape(
        "ASANA\nDaily Activity (6 projects)\nOptimization (7 channels)\nSeasonal (5 campaigns)",
        x=COL_X["outputs"], y=-1100, w=BOX_W, h=BOX_H,
        fill="#fbcfe8", border="#9f1239", font_size=14)
    out_slack = shape(
        "SLACK\n#notify · 03:30 daily report\n#approval · ✅/❌ reactions",
        x=COL_X["outputs"], y=-950, w=BOX_W, h=BOX_H,
        fill="#bfdbfe", border="#1e40af", font_size=14)
    out_dashboard = shape(
        "HTML DASHBOARD\nreports/latest\n(persisted to Drive)",
        x=COL_X["outputs"], y=-800, w=BOX_W, h=BOX_H,
        fill="#bbf7d0", border="#15803d", font_size=14)
    out_bq = shape(
        "BIGQUERY\ncampaigns_daily · leads · deals\nrefreshed nightly",
        x=COL_X["outputs"], y=-650, w=BOX_W, h=BOX_H,
        fill="#fde68a", border="#a16207", font_size=14)

    # ── Connections (left -> right flow) ─────────────────────────────────────
    # Each input feeds the brain (drawn as one arrow per input -> analyst as
    # the visual anchor; clutter would result if every input touched all 3 roles)
    for src in in_ids:
        connect(src["id"], role_analyst["id"], "")

    # 3 roles -> assistant
    connect(role_buyer["id"],   assistant["id"], "JSON", "#0f172a")
    connect(role_analyst["id"], assistant["id"], "JSON", "#0f172a")
    connect(role_strat["id"],   assistant["id"], "JSON", "#0f172a")

    # assistant -> actions (3 fan-out arrows)
    connect(assistant["id"], direct["id"],   "execution_type=Direct", "#dc2626")
    connect(assistant["id"], approval["id"], "high-confidence",       "#d97706")
    connect(assistant["id"], notify["id"],   "summary",               "#16a34a")
    # autofix is webhook-driven, not via assistant — left without an arrow
    # to keep the diagram clean

    # actions -> outputs
    connect(direct["id"],   out_asana["id"],     "logged",  "#475569")
    connect(approval["id"], out_slack["id"],     "request", "#475569")
    connect(notify["id"],   out_slack["id"],     "ping",    "#475569")
    connect(notify["id"],   out_dashboard["id"], "URL",     "#475569")
    connect(notify["id"],   out_asana["id"],     "tasks",   "#475569")
    connect(autofix["id"],  out_slack["id"],     "diag",    "#475569")

    print("[miro] Done.")
    print(f"        https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
