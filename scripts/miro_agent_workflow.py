"""
scripts/miro_agent_workflow.py
===============================
Qoyod Performance Agent — clean 3-column diagram + key rules.

    DATA SOURCES  →  AGENT (2 runtimes)  →  OUTPUTS

Run:
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
H     = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE  = f"https://api.miro.com/v2/boards/{BOARD}"


# ── API helpers ───────────────────────────────────────────────────────────────

def _post(path, payload):
    r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=15)
    if not r.ok:
        print(f"  FAIL {path}: {r.status_code} — {r.text[:200]}")
        return None
    return r.json()


def _delete_all():
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


def box(text, x, y, w=280, h=100, fill="#dbeafe", border="#2563eb",
        font_color="#0f172a", font_size=13, shape="round_rectangle"):
    return _post("/shapes", {
        "data": {"content": text, "shape": shape},
        "style": {
            "fillColor": fill, "borderColor": border, "borderWidth": "2",
            "fontFamily": "open_sans", "fontSize": str(font_size),
            "color": font_color, "textAlign": "center",
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def txt(content, x, y, w=800, font=14, color="#0f172a", align="center"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def arrow(a, b, label="", color="#94a3b8", width="2"):
    if not a or not b:
        return
    return _post("/connectors", {
        "startItem": {"id": a["id"]},
        "endItem":   {"id": b["id"]},
        "captions":  [{"content": label, "position": "50%"}] if label else [],
        "style": {"strokeColor": color, "strokeWidth": width,
                  "endStrokeCap": "stealth"},
    })


# ── Layout ────────────────────────────────────────────────────────────────────

X_SRC   = -900
X_AGENT = 0
X_OUT   = 900

BW = 270   # box width
BH = 90    # box height
GAP = 20   # vertical gap between boxes


def build():
    _delete_all()

    # ── Title ─────────────────────────────────────────────────────────────────
    txt("<b>Qoyod Performance Agent</b>", x=0, y=-600, font=38, color="#0f172a")
    txt("Two runtimes  ·  Every action approval-gated  ·  All data in BigQuery",
        x=0, y=-548, font=14, color="#64748b")

    # ── Column headers ────────────────────────────────────────────────────────
    for x, label, color in [
        (X_SRC,   "DATA SOURCES",  "#1e40af"),
        (X_AGENT, "AGENT",         "#7c3aed"),
        (X_OUT,   "OUTPUTS",       "#15803d"),
    ]:
        txt(f"<b>{label}</b>", x=x, y=-490, w=320, font=20, color=color)

    # ─────────────────────────────────────────────────────────────────────────
    # COLUMN 1 — Data Sources
    # ─────────────────────────────────────────────────────────────────────────
    src_items = [
        ("Ad Platforms\nMeta · Google Ads · TikTok\nLinkedIn · Snapchat · Microsoft",
         "#dbeafe", "#1e40af"),
        ("HubSpot CRM\nLeads (Lead Module only)\nDeals · Read-only",
         "#fee2e2", "#991b1b"),
        ("BigQuery\nqoyod_marketing\nt_* materialized tables",
         "#fef9c3", "#a16207"),
        ("Anthropic Claude API\nclaude-sonnet-4-6\nReasoning + analysis",
         "#fce7f3", "#9d174d"),
    ]

    src_nodes = []
    for i, (text, fill, border) in enumerate(src_items):
        y = -380 + i * (BH + GAP)
        n = box(text, X_SRC, y, w=BW, h=BH, fill=fill, border=border)
        src_nodes.append(n)

    # ─────────────────────────────────────────────────────────────────────────
    # COLUMN 2 — Agent (2 runtime tracks)
    # ─────────────────────────────────────────────────────────────────────────

    # Track A header
    txt("⏱ Nightly 03:00 Riyadh", x=X_AGENT, y=-445, w=340,
        font=12, color="#7c3aed", align="center")

    nightly_items = [
        ("Campaign Health\nCPQL / CPL audit · Scale / Pause / Optimize\n14-day minimum window",
         "#ede9fe", "#7c3aed"),
        ("Ad Audit\nZero-conv · Junk leads · High CPL\nFindings → PENDING APPROVAL",
         "#f5f3ff", "#6d28d9"),
        ("Keyword Audit (Sundays)\nIS / QS · Candidates · Negatives\nNegatives auto-executed",
         "#f3e8ff", "#7c3aed"),
        ("Approval Digest\n#approvals — 1 batch/night\nScale + Pause on ✅  |  ❌ skips all",
         "#fef3c7", "#d97706"),
    ]

    nightly_nodes = []
    for i, (text, fill, border) in enumerate(nightly_items):
        y = -380 + i * (BH + GAP)
        n = box(text, X_AGENT, y, w=BW, h=BH, fill=fill, border=border)
        nightly_nodes.append(n)

    # Divider
    txt("── ── ── ── ── ── ── ──", x=X_AGENT, y=-380 + 4 * (BH + GAP) - 10,
        w=320, font=11, color="#cbd5e1")

    # Track B header
    txt("⟳ Every 6 Hours", x=X_AGENT,
        y=-380 + 4 * (BH + GAP) + 15, w=340, font=12, color="#0e7490")

    reporting_items = [
        ("Data Refresh\n22 collectors → BQ upsert\nView materialisation → t_* tables",
         "#cffafe", "#0e7490"),
        ("Health Checks  09–17 Riyadh\nAll connectors + APIs + BQ\nResults → Activity Dashboard",
         "#ecfeff", "#0891b2"),
    ]

    reporting_nodes = []
    for i, (text, fill, border) in enumerate(reporting_items):
        y = -380 + (5 + i) * (BH + GAP) + 30
        n = box(text, X_AGENT, y, w=BW, h=BH, fill=fill, border=border)
        reporting_nodes.append(n)

    # ─────────────────────────────────────────────────────────────────────────
    # COLUMN 3 — Outputs
    # ─────────────────────────────────────────────────────────────────────────
    out_items = [
        ("Slack #approvals\n1 digest/night · ✅ executes\nScale + Pause actions",
         "#dbeafe", "#1e40af"),
        ("Slack #notify\n1 summary/night\nPerformance · Alerts",
         "#bfdbfe", "#1d4ed8"),
        ("Asana\n6 projects · 7 channels\nPENDING APPROVAL tasks",
         "#fce7f3", "#9f1239"),
        ("Hex Dashboard\nCampaign · Ad · Keyword\nRefreshed every 6h",
         "#d1fae5", "#15803d"),
        ("Activity Dashboard\n/activity — full audit log\nApproval rate · Data hygiene",
         "#e0e7ff", "#4338ca"),
    ]

    out_nodes = []
    for i, (text, fill, border) in enumerate(out_items):
        y = -380 + i * (BH + GAP)
        n = box(text, X_OUT, y, w=BW, h=BH, fill=fill, border=border)
        out_nodes.append(n)

    # ─────────────────────────────────────────────────────────────────────────
    # Connectors
    # ─────────────────────────────────────────────────────────────────────────

    # Sources → nightly analysis
    for src in src_nodes:
        arrow(src, nightly_nodes[0], color="#94a3b8")

    # Nightly chain
    arrow(nightly_nodes[0], nightly_nodes[1], color="#7c3aed")
    arrow(nightly_nodes[0], nightly_nodes[2], color="#7c3aed")
    arrow(nightly_nodes[1], nightly_nodes[3], color="#d97706")
    arrow(nightly_nodes[2], nightly_nodes[3], color="#d97706")

    # Nightly → outputs
    arrow(nightly_nodes[3], out_nodes[0], "posts digest",   color="#d97706", width="3")
    arrow(nightly_nodes[0], out_nodes[2], "creates tasks",  color="#9f1239")
    arrow(nightly_nodes[3], out_nodes[1], "summary",        color="#1d4ed8")

    # Reporting → outputs
    arrow(reporting_nodes[0], out_nodes[3], "triggers re-run", color="#15803d")
    arrow(reporting_nodes[1], out_nodes[4], "logs results",    color="#4338ca")

    # ─────────────────────────────────────────────────────────────────────────
    # KEY RULES — below the diagram
    # ─────────────────────────────────────────────────────────────────────────
    rules_y = -380 + 8 * (BH + GAP) + 120

    txt("<b>KEY RULES</b>", x=0, y=rules_y, w=1200, font=22, color="#0f172a")
    txt("Non-negotiable constraints the agent always follows",
        x=0, y=rules_y + 35, w=1200, font=13, color="#64748b")

    rules = [
        ("🚫 No Auto-Execute\nScale + Pause always wait\nfor ✅ in #approvals",
         "#fef3c7", "#d97706"),
        ("📊 Leads from HubSpot Only\nLead Module · Not contacts\nCPQL evaluated first",
         "#fee2e2", "#991b1b"),
        ("💵 Spend Always USD\nPlatforms in micros → ÷1M\nSAR peg: 1 USD = 3.75 SAR",
         "#d1fae5", "#15803d"),
        ("📅 14-Day Minimum Window\nNo pause/scale on < 14 days\nAwareness = impressions only",
         "#dbeafe", "#1e40af"),
        ("🔑 Keywords Weekly (Sun)\nNegatives: daily auto-exec\nAdditions: Sunday only",
         "#f3e8ff", "#7c3aed"),
        ("🔒 Secrets in Railway Only\nNever hardcode tokens\n.env = local cert path only",
         "#ecfeff", "#0e7490"),
    ]

    rule_bw = 240
    total_w = len(rules) * rule_bw + (len(rules) - 1) * 20
    start_x = -total_w // 2 + rule_bw // 2

    for i, (text, fill, border) in enumerate(rules):
        x = start_x + i * (rule_bw + 20)
        box(text, x, rules_y + 140, w=rule_bw, h=110, fill=fill, border=border,
            font_size=12)

    print(f"[miro] Board built: https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
