"""
scripts/miro_agent_workflow.py
===============================
Renders a SIMPLIFIED Nexa Performance Agent flow diagram into Miro.

Layout (top-down, 3 horizontal bands):

    ┌─────────────────────────────────────────────────────────┐
    │  INPUTS    Ad APIs · CRM · BQ · Drive (Media Planning)  │
    └────────────────────┬────────────────────────────────────┘
                         ▼
    ┌─────────────────────────────────────────────────────────┐
    │  BRAIN     Media Buyer · Analyst · Strategist           │
    │            (3 Claude roles, run nightly 03:00 Riyadh)   │
    └────────────────────┬────────────────────────────────────┘
                         ▼
    ┌─────────────────────────────────────────────────────────┐
    │  ACTIONS   Direct · Approval · Notify                   │
    │            Asana tasks · Slack messages · Dashboard     │
    └─────────────────────────────────────────────────────────┘

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


def shape(text_content, x, y, w=260, h=110, fill="#dbeafe", border="#2563eb",
          font_color="#0f172a", font_size=16):
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

    # Title
    text("**Nexa — Performance Agent**", x=0, y=-1100, w=900, font=40)
    text("Runs autonomously every night at 03:00 Riyadh",
         x=0, y=-1030, w=900, font=18, color="#64748b")

    # ── BAND 1: INPUTS ───────────────────────────────────────────────────────
    text("INPUTS", x=-1200, y=-820, w=200, font=22, color="#1e40af")
    text("Data the agent reads", x=-1200, y=-790, w=300,
         font=14, color="#64748b")

    inputs = [
        ("Ad Platforms\nGoogle · Meta · Snap · TikTok\nLinkedIn · Microsoft", -750, -800, "#dbeafe"),
        ("HubSpot CRM\nLeads · Deals · Webhooks",                              -420, -800, "#fecaca"),
        ("BigQuery\nReporting layer\n(refreshed nightly)",                     -90,  -800, "#fde68a"),
        ("Google Drive\nMedia Planning\nSocial Media Analysis",                 240,  -800, "#a7f3d0"),
        ("Anthropic\nClaude API",                                              570, -800, "#f9a8d4"),
    ]
    in_ids = [shape(t, x, y, w=270, h=130, fill=c, border="#1e40af", font_size=14)
              for t, x, y, c in inputs]

    # ── BAND 2: BRAIN ────────────────────────────────────────────────────────
    text("BRAIN", x=-1200, y=-380, w=200, font=22, color="#7c3aed")
    text("3 Claude roles + 1 code assistant", x=-1200, y=-350, w=300,
         font=14, color="#64748b")

    role_buyer = shape(
        "🎯 MEDIA BUYER\nDaily pauses · scaling\nBudget pacing · creative QA",
        x=-650, y=-360, w=300, h=150, fill="#3b82f6", border="#1e3a8a",
        font_color="#ffffff", font_size=15)
    role_analyst = shape(
        "📊 ANALYST\nTrend & anomaly\nLead-quality drift · attribution",
        x=-300, y=-360, w=300, h=150, fill="#8b5cf6", border="#5b21b6",
        font_color="#ffffff", font_size=15)
    role_strat = shape(
        "🧭 STRATEGIST\nWeekly+ scale plans\nCreative briefs · channel mix",
        x=50, y=-360, w=300, h=150, fill="#ec4899", border="#9d174d",
        font_color="#ffffff", font_size=15)
    assistant = shape(
        "🤖 TASK-FLOW ASSISTANT (code)\nRoutes JSON decisions →\nright Asana project + section",
        x=480, y=-360, w=320, h=150, fill="#10b981", border="#047857",
        font_color="#ffffff", font_size=14)

    # ── BAND 3: ACTIONS ──────────────────────────────────────────────────────
    text("ACTIONS", x=-1200, y=110, w=200, font=22, color="#15803d")
    text("What the agent does with the decisions", x=-1200, y=140, w=300,
         font=14, color="#64748b")

    direct = shape(
        "DIRECT\n(auto-execute)\n──────\nPause ad · Pause keyword\nExclude placement\nAdd negative keyword",
        x=-650, y=130, w=320, h=210, fill="#fee2e2", border="#991b1b", font_size=14)
    approval = shape(
        "APPROVAL ✅ NEEDED\n(Slack approval channel)\n──────\nScale budget · Adjust bids\nPause campaign\nLaunch new audience",
        x=-280, y=130, w=320, h=210, fill="#fef3c7", border="#92400e", font_size=14)
    notify = shape(
        "NOTIFY\n(Slack notify channel)\n──────\nDaily report URL\nSpike alerts\nAsana tasks linked",
        x=90, y=130, w=320, h=210, fill="#dcfce7", border="#15803d", font_size=14)
    autofix = shape(
        "AUTO-FIX (Zapier)\n──────\nReplay errored Zaps\nResume held tasks\nDisable broken Zaps",
        x=460, y=130, w=320, h=210, fill="#ede9fe", border="#5b21b6", font_size=14)

    # ── BAND 4: OUTPUTS ──────────────────────────────────────────────────────
    text("OUTPUTS", x=-1200, y=460, w=200, font=22, color="#0f172a")

    out_asana = shape(
        "ASANA\nDaily Activity (6 projects)\nOptimization (7 channels)\nSeasonal (5 campaigns)",
        x=-650, y=470, w=320, h=160, fill="#fbcfe8", border="#9f1239", font_size=14)
    out_slack = shape(
        "SLACK\n#notify · 03:30 daily report\n#approval · ✅/❌ reactions",
        x=-280, y=470, w=320, h=160, fill="#bfdbfe", border="#1e40af", font_size=14)
    out_dashboard = shape(
        "HTML DASHBOARD\nreports/latest\n(persisted to Drive)",
        x=90, y=470, w=320, h=160, fill="#bbf7d0", border="#15803d", font_size=14)
    out_bq = shape(
        "BIGQUERY\ncampaigns_daily\nhubspot_leads · deals\nrefreshed nightly",
        x=460, y=470, w=320, h=160, fill="#fde68a", border="#a16207", font_size=14)

    # ── Connections (data flow) ──────────────────────────────────────────────
    # Inputs → Brain
    for src in in_ids:
        connect(src["id"], role_analyst["id"], "")  # all inputs feed the brain
    # Brain → Assistant
    connect(role_buyer["id"],   assistant["id"], "JSON", "#0f172a")
    connect(role_analyst["id"], assistant["id"], "JSON", "#0f172a")
    connect(role_strat["id"],   assistant["id"], "JSON", "#0f172a")
    # Assistant → Actions
    connect(assistant["id"], direct["id"],   "execution_type=Direct", "#dc2626")
    connect(assistant["id"], approval["id"], "high-confidence",       "#d97706")
    connect(assistant["id"], notify["id"],   "summary",               "#16a34a")
    # Webhook autofix is independent of brain
    # Actions → Outputs
    connect(direct["id"],   out_asana["id"], "logged",       "#475569")
    connect(approval["id"], out_slack["id"], "approval req", "#475569")
    connect(notify["id"],   out_slack["id"], "summary",      "#475569")
    connect(notify["id"],   out_dashboard["id"], "URL",      "#475569")
    connect(notify["id"],   out_asana["id"],  "tasks",       "#475569")

    print("[miro] Done.")
    print(f"        https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
