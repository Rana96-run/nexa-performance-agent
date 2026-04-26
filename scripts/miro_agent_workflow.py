"""
scripts/miro_agent_workflow.py
===============================
Renders the current Nexa Performance Agent architecture into a Miro board.

5 sections (top → bottom):

  1. Connectors / MCPs / APIs   — data + comms inputs
  2. Executions                 — Railway runtime (Flask + 2 daemon threads)
  3. Roles                      — 3 Claude personas (compact)
  4. Actions                    — what the agent actually does
  5. Roles in Detail            — each role's responsibilities + outputs

Frames are drawn as visual containers only — items are placed by absolute
board coordinates (Miro frames clip incorrectly when items use the parent
field, so we anchor everything to the board).
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


def frame(title, x, y, w, h, color="#FFFFFF"):
    return _post("/frames", {
        "data": {"title": title, "format": "custom", "type": "freeform"},
        "style": {"fillColor": color},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def shape(text_content, x, y, w=220, h=70, fill="#dbeafe", border="#2563eb",
          font_color="#0f172a", font_size=14):
    return _post("/shapes", {
        "data": {"content": text_content, "shape": "round_rectangle"},
        "style": {
            "fillColor": fill,
            "borderColor": border,
            "borderWidth": "2",
            "fontFamily": "open_sans",
            "fontSize": str(font_size),
            "color": font_color,
            "textAlign": "center",
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def text(content, x, y, w=300, font=18):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": "#1e293b", "textAlign": "left"},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def connect(from_id, to_id, label=""):
    if not from_id or not to_id:
        return None
    return _post("/connectors", {
        "startItem": {"id": from_id},
        "endItem":   {"id": to_id},
        "captions":  [{"content": label}] if label else [],
        "style": {"strokeColor": "#64748b", "strokeWidth": "2"},
    })


# ─── Build ────────────────────────────────────────────────────────────────────

def build():
    _delete_all_existing()

    # Layout band Y-axis (top to bottom):
    #   Frame 1: y = -2200 to -1700 (height 500)
    #   Frame 2: y = -1500 to -700  (height 800)
    #   Frame 3: y = -400  to 200   (height 600)
    #   Frame 4: y = -400  to 200   (height 600)  [right of Frame 3]
    #   Frame 5: y = 400   to 1200  (height 800)

    # ── FRAME 1: Connectors / APIs / MCPs ────────────────────────────────────
    frame("1 · Connectors / APIs / MCPs", x=0, y=-1950, w=2600, h=520, color="#eff6ff")

    text("CONNECTORS · APIs · MCPs", x=0, y=-2160, w=600, font=24)
    text("Ad Platforms (paid)", x=-1000, y=-2080, w=400, font=14)
    text("CRM / Comms / Storage / AI", x=600, y=-2080, w=500, font=14)

    ad_platforms = [
        ("Google Ads API\nv18 · 2 accts", -1150, -1950, "#fed7aa"),
        ("Meta Ads API\n2 accounts",      -930, -1950, "#bfdbfe"),
        ("Snapchat Ads API\n2 accounts",  -710, -1950, "#fef9c3"),
        ("TikTok Ads API\n2 accounts",    -490, -1950, "#e9d5ff"),
        ("LinkedIn Ads API",              -270, -1950, "#bae6fd"),
        ("Microsoft Ads API",             -50,  -1950, "#d1fae5"),
    ]
    ad_ids = [shape(t, x, y, w=200, h=80, fill=c, border="#1e40af")
              for t, x, y, c in ad_platforms]

    others = [
        ("HubSpot API\n+ Webhooks",      230,  -1950, "#fecaca"),
        ("BigQuery\nreporting layer",    450,  -1950, "#fde68a"),
        ("Slack API\n+ Listener",        670,  -1950, "#c7d2fe"),
        ("Asana API\ntask router",       890,  -1950, "#fbcfe8"),
        ("Google Drive\n(reports)",      1110, -1950, "#a7f3d0"),
        ("Anthropic Claude\n(reasoning)", -1150, -1830, "#f9a8d4"),
        ("Zapier Webhook\n(error monitor)", -930, -1830, "#fcd34d"),
        ("Gmail SMTP\n(fallback)",        -710, -1830, "#bbf7d0"),
    ]
    other_ids = [shape(t, x, y, w=200, h=80, fill=c, border="#475569")
                 for t, x, y, c in others]

    # ── FRAME 2: Executions (Railway runtime) ────────────────────────────────
    frame("2 · Executions (Railway runtime)", x=0, y=-1100, w=2600, h=720, color="#f0fdf4")

    text("EXECUTIONS · Railway · Always-on Flask + 2 daemon threads",
         x=0, y=-1390, w=900, font=22)

    flask = shape("Flask Web Server  (port 8080)\nserves /reports + /webhooks + /api/*",
                  x=0, y=-1280, w=620, h=80, fill="#16a34a", border="#15803d",
                  font_color="#ffffff", font_size=14)

    web_eps = [
        ("/health",                      -900, -1130, "#86efac"),
        ("/reports/latest\nDrive fallback", -650, -1130, "#86efac"),
        ("/api/refresh\n/api/regenerate",   -400, -1130, "#86efac"),
        ("/webhooks/hubspot\nreal-time",    -150, -1130, "#fca5a5"),
        ("/webhooks/zapier\nauto-fix",      100, -1130, "#fcd34d"),
    ]
    web_ids = [shape(t, x, y, w=210, h=80, fill=c, border="#16a34a")
               for t, x, y, c in web_eps]

    thread_op = shape("operational-scheduler\nNightly 03:00 Riyadh\nHealth 07:00 Riyadh",
                      x=420, y=-1130, w=290, h=120, fill="#0ea5e9", border="#0284c7",
                      font_color="#ffffff")
    thread_sl = shape("slack-listener\nSlack 60s · Asana 120s\n@Nexa mention handler",
                      x=750, y=-1130, w=290, h=120, fill="#8b5cf6", border="#7c3aed",
                      font_color="#ffffff")
    thread_w = shape("Webhook Handlers\n(in Flask request loop)\nHubSpot · Zapier",
                     x=1080, y=-1130, w=290, h=120, fill="#f97316", border="#c2410c",
                     font_color="#ffffff")

    text("NIGHTLY 03:00 RIYADH SEQUENCE (operational-scheduler)",
         x=0, y=-980, w=900, font=14)

    sched_steps = [
        ("1. BQ refresh\n10 collectors", -1080, -880),
        ("2. Run Claude roles\nbuyer + analyst", -800, -880),
        ("3. Extract decisions\n→ Asana router", -520, -880),
        ("4. Render report\n+ Drive upload", -240, -880),
        ("5. Spike detector\nsilent if OK", 40, -880),
        ("6. 'Report ready'\nSlack ping", 320, -880),
        ("7. Approval reqs\nhigh-confidence", 600, -880),
    ]
    sched_ids = [shape(t, x, y, w=240, h=80, fill="#fef3c7", border="#0284c7")
                 for t, x, y in sched_steps]

    # ── FRAME 3: Roles (3 Claude personas — compact) ─────────────────────────
    frame("3 · Roles (Claude personas)", x=-900, y=-100, w=900, h=560, color="#fef3c7")

    text("ROLES · 3 Claude personas",
         x=-900, y=-340, w=600, font=22)

    role_buyer = shape("🎯 Media Buyer\n(media_buyer)\n────\nDaily pauses\nQuick fixes\nScale candidates",
                       x=-1180, y=-100, w=240, h=240, fill="#3b82f6", border="#1e40af",
                       font_color="#ffffff", font_size=14)
    role_analyst = shape("📊 Paid Media Analyst\n(paid_media_analyst)\n────\nTrend / anomaly\nLead-quality drift\nAttribution",
                         x=-900, y=-100, w=240, h=240, fill="#8b5cf6", border="#6d28d9",
                         font_color="#ffffff", font_size=14)
    role_strat = shape("🧭 Paid Media Strategist\n(paid_media_strategist)\n────\nScale plans · briefs\nQuarterly bets\nWeekly+ only",
                       x=-620, y=-100, w=240, h=240, fill="#ec4899", border="#be185d",
                       font_color="#ffffff", font_size=14)

    # ── FRAME 4: Actions ─────────────────────────────────────────────────────
    frame("4 · Actions (what the agent does)", x=550, y=-100, w=1900, h=560, color="#fce7f3")

    text("ACTIONS · routed by execution_type field",
         x=550, y=-340, w=1000, font=22)

    text("DIRECT (auto-execute)", x=-280, y=-260, w=300, font=15)
    direct_actions = [
        ("Pause Ad\nzero conv · 7d · spend>$30",     -340, -160, "#f87171"),
        ("Pause Keyword\nzero conv · 14d · spend>$15", -340, -50, "#f87171"),
        ("Exclude Placement\nspend>$10 · bounce>80%", -340, 60, "#f87171"),
        ("Add Negative Keyword\nclearly irrelevant",  -340, 170, "#f87171"),
    ]
    for t, x, y, c in direct_actions:
        shape(t, x, y, w=260, h=80, fill=c, border="#991b1b",
              font_color="#ffffff")

    text("APPROVAL CHANNEL (✅ to execute)", x=120, y=-260, w=400, font=15)
    approval_actions = [
        ("Scale Budget\n+20% if CPL < scale zone",   60, -160, "#fbbf24"),
        ("Adjust Bid Strategy\nManual ↔ Target CPA", 60, -50, "#fbbf24"),
        ("Pause Campaign\n(not just an ad)",         60, 60, "#fbbf24"),
        ("Launch New Audience\nlookalike from CRM",  60, 170, "#fbbf24"),
    ]
    for t, x, y, c in approval_actions:
        shape(t, x, y, w=260, h=80, fill=c, border="#92400e")

    text("NOTIFICATIONS / OUTPUTS", x=520, y=-260, w=400, font=15)
    outputs = [
        ("Asana Task\nrouted by channel × asset", 460, -160, "#86efac"),
        ("Slack Daily Summary",                   460, -50, "#86efac"),
        ("Daily Report HTML\n+ Drive backup",     460, 60, "#86efac"),
        ("Spike Alert\n±30% spend / ±40% leads",  460, 170, "#86efac"),
    ]
    for t, x, y, c in outputs:
        shape(t, x, y, w=260, h=80, fill=c, border="#15803d")

    text("AUTO-FIX (Zapier)", x=920, y=-260, w=300, font=15)
    autofix = [
        ("Auto-replay errored Zaps", 860, -160, "#a78bfa"),
        ("Auto-resume held tasks",   860, -50, "#a78bfa"),
        ("Disable broken Zap\nafter 3 failed retries", 860, 60, "#a78bfa"),
        ("Diagnose w/ Claude\n+ Asana fix-task",      860, 170, "#a78bfa"),
    ]
    for t, x, y, c in autofix:
        shape(t, x, y, w=260, h=80, fill=c, border="#5b21b6",
              font_color="#ffffff")

    text("WEBHOOK-DRIVEN", x=1320, y=-260, w=300, font=15)
    webhook_actions = [
        ("HubSpot lead/deal events\nlogged silently", 1260, -160, "#fde68a"),
        ("Aggregated weekly\nin agent run",           1260, -50, "#fde68a"),
        ("/api/regenerate\non-demand HTML refresh",   1260, 60, "#fde68a"),
        ("/api/refresh?days=N\nbackfill (async)",     1260, 170, "#fde68a"),
    ]
    for t, x, y, c in webhook_actions:
        shape(t, x, y, w=260, h=80, fill=c, border="#a16207")

    # ── FRAME 5: Roles in Detail ─────────────────────────────────────────────
    frame("5 · Roles in Detail (responsibilities · outputs)",
          x=0, y=850, w=2700, h=720, color="#fffbeb")

    text("ROLES IN DETAIL · responsibilities · outputs",
         x=0, y=540, w=900, font=22)

    role_buyer_d = shape(
        "🎯 MEDIA BUYER\n────\nDAILY (03:00 Riyadh):\n"
        "• Budget pacing per campaign (±15%)\n"
        "• CPL/CPQL trend (4-day · pause >$30)\n"
        "• Quick actions — DIRECT execution\n"
        "• Negatives from search-term report\n\n"
        "WEEKLY:\n"
        "• Campaign scoring (scale/hold/test/pause)\n"
        "• Creative fatigue (CTR drop >20% w/w)\n"
        "• Audience review (CPL × qual rate)\n\n"
        "OUTPUT: JSON → Asana\n  daily_activity / optimization",
        x=-1050, y=850, w=560, h=560,
        fill="#dbeafe", border="#1e40af", font_size=14)

    role_analyst_d = shape(
        "📊 PAID MEDIA ANALYST\n────\nDAILY:\n"
        "• Spend anomaly attribution (which campaign?)\n"
        "• Lead-quality drift (qual rate ±20pp)\n"
        "• CPL/CPQL trend up >25% → flag\n\n"
        "WEEKLY+:\n"
        "• Channel-mix drift (% of SQLs)\n"
        "• Funnel stage diagnosis\n"
        "• Disqualification reason analysis\n"
        "• UTM coverage check (fail < 80%)\n\n"
        "NEVER: Pauses · briefs · raw HubSpot\n\n"
        "OUTPUT: JSON → Asana (Recommendation/Tracking)",
        x=-450, y=850, w=560, h=560,
        fill="#ede9fe", border="#6d28d9", font_size=14)

    role_strat_d = shape(
        "🧭 PAID MEDIA STRATEGIST\n────\nWEEKLY+ ONLY:\n"
        "• Channel mix re-allocation\n"
        "• Scale plans (CPL<scale zone for 7+ days)\n"
        "• Creative briefs for Donia\n"
        "• Quarterly bets / new tests\n"
        "• Competitor angle adoption\n\n"
        "INPUTS:\n"
        "• 7d aggregate KPIs · Analyst findings\n"
        "• Brand identity file\n\n"
        "OUTPUT: JSON → Asana\n"
        "  optimization (briefs)\n"
        "  campaigns_hub (scale plans)\n"
        "  seasonal (campaign launches)",
        x=150, y=850, w=560, h=560,
        fill="#fce7f3", border="#be185d", font_size=14)

    role_assistant_d = shape(
        "🤖 TASK-FLOW ASSISTANT\n  (CODE — NOT a Claude role)\n────\n"
        "Lives in: main._extract_tasks\n  + executors.asana.create_task\n\n"
        "INPUT: JSON decisions from 3 Claude roles\n\n"
        "DOES:\n"
        "• Resolves project_key + channel\n"
        "    → exact Asana project ID\n"
        "• Resolves asset_level\n"
        "    → section in project\n"
        "• Action verb prefixes title\n"
        "• Deduplicates (title × project × day)\n"
        "• Runs executor for execution_type='Direct'\n"
        "• Approval req for high-confidence\n"
        "    channel mutations\n\n"
        "ZERO TOKENS — pure deterministic routing.",
        x=750, y=850, w=560, h=560,
        fill="#f0fdf4", border="#15803d", font_size=14)

    # ── Connections ──────────────────────────────────────────────────────────
    if other_ids[0] and flask:
        connect(other_ids[0]["id"], flask["id"], "events")  # HubSpot → Flask
    if other_ids[6] and flask:
        connect(other_ids[6]["id"], flask["id"], "errors/held")  # Zapier → Flask
    if ad_ids[0] and thread_op:
        connect(ad_ids[0]["id"], thread_op["id"], "API pull")
    if other_ids[1] and thread_op:
        connect(other_ids[1]["id"], thread_op["id"], "writes")
    if other_ids[5] and thread_op:
        connect(other_ids[5]["id"], thread_op["id"], "Claude")
    if thread_op and sched_ids[0]:
        connect(thread_op["id"], sched_ids[0]["id"], "")
    if sched_ids[1] and role_buyer:
        connect(sched_ids[1]["id"], role_buyer["id"], "invokes")
    if sched_ids[1] and role_analyst:
        connect(sched_ids[1]["id"], role_analyst["id"], "invokes")
    if role_buyer and role_buyer_d:
        connect(role_buyer["id"], role_buyer_d["id"], "")
    if role_analyst and role_analyst_d:
        connect(role_analyst["id"], role_analyst_d["id"], "")
    if role_strat and role_strat_d:
        connect(role_strat["id"], role_strat_d["id"], "")
    if role_buyer and role_assistant_d:
        connect(role_buyer["id"], role_assistant_d["id"], "JSON")
    if role_analyst and role_assistant_d:
        connect(role_analyst["id"], role_assistant_d["id"], "JSON")

    print("[miro] Done. Open the board to see it.")
    print(f"        https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
