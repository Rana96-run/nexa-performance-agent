"""
scripts/miro_use_cases_v2.py
=============================
Use cases — 3-sticky layout (Trigger · Action · Result) below the main flow.
Run AFTER miro_agent_workflow.py, or standalone (only deletes below y=900).
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


def _post(path, payload):
    r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=15)
    if not r.ok:
        print(f"  FAIL {path}: {r.status_code} — {r.text[:160]}")
        return None
    return r.json()


def _get_all(kind):
    out, cursor = [], None
    while True:
        url = f"{BASE}/{kind}?limit=50"
        if cursor:
            url += f"&cursor={cursor}"
        r = requests.get(url, headers=H, timeout=15)
        if not r.ok:
            return out
        d = r.json()
        out.extend(d.get("data", []))
        cursor = d.get("cursor")
        if not cursor:
            break
    return out


def _delete_below(y_threshold):
    deleted = 0
    for kind in ("connectors", "shapes", "sticky_notes", "cards", "texts", "images"):
        for it in _get_all(kind):
            pos = it.get("position") or {}
            if pos.get("y", 0) >= y_threshold:
                requests.delete(f"{BASE}/{kind}/{it['id']}", headers=H, timeout=10)
                deleted += 1
    print(f"[miro] deleted {deleted} item(s) below y={y_threshold}")
    time.sleep(1)


def txt(content, x, y, w=900, font=14, color="#0f172a", align="center"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def sticky(content, x, y, color="light_yellow", w=230):
    return _post("/sticky_notes", {
        "data": {"content": content, "shape": "square"},
        "style": {"fillColor": color},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


USE_CASES = [
    {
        "n": 1,
        "title": "Nightly Campaign Health — CPQL / CPL Audit",
        "trigger": "⏱ TRIGGER\nNightly 03:00 Riyadh\nAutomatic · every day\nNo manual trigger needed",
        "action":  "⚙️ ACTION\naudit_campaign_health()\n• 14-day window minimum\n• CPQL first, then CPL\n• Scale / Pause / Optimize / Junk\n• Drill-down if CPQL > $130 + CPL > $32",
        "result":  "✅ RESULT\nAsana: PENDING APPROVAL tasks\n#approvals: 1 batch digest\nNothing executes until ✅",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 2,
        "title": "✅ Reaction → Execute Scale / Pause",
        "trigger": "⏱ TRIGGER\nUser reacts ✅ on\n#approvals digest\n(❌ skips everything)",
        "action":  "⚙️ ACTION\n_execute_approved_action()\n• Scale: budget +25% via API\n• Pause: pause_campaign()\n• Via Adspirer MCP or direct API\n• Asana task comment added",
        "result":  "✅ RESULT\nBudget raised / campaign paused\nThread reply with outcome\nAsana task → EXECUTED",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 3,
        "title": "Ad Audit — Zero Conv · Junk Leads · High CPL",
        "trigger": "⏱ TRIGGER\nNightly audit\nAds running 7–10+ days\nAll channels",
        "action":  "⚙️ ACTION\nZero-conv: spend > $70, 7d, 0 conv\nJunk: 60%+ disqualification rate, 10d\nHigh CPL: CPL > $50, 10d\n→ Flag → PENDING APPROVAL",
        "result":  "✅ RESULT\nAsana: PENDING APPROVAL\nIncluded in #approvals digest\nPaused only after ✅",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 4,
        "title": "Google Ads Keyword Audit — IS / QS / Expansion",
        "trigger": "⏱ TRIGGER\nSunday Riyadh (weekly)\nKeyword additions + pauses\nDaily: IS / QS audit only",
        "action":  "⚙️ ACTION\n• IS < 25%: budget recommendation\n• QS < 5 + >80% lost-IS → pause\n• Search terms → candidates\n• 30-keyword cap per ad group\n• Never delete keyword with spend",
        "result":  "✅ RESULT\nAsana tasks per campaign\nNegatives: auto-executed daily\nCandidates: Asana (Sunday only)",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 5,
        "title": "Slack — Max 2 Messages Per Night",
        "trigger": "⏱ TRIGGER\nEnd of nightly cycle\nAfter all analysis + tasks\ncreated",
        "action":  "⚙️ ACTION\n#notify: 1 summary message\n  Performance · Alerts · Counts\n#approvals: 1 batch digest\n  Scale + Pause (executable)\n  Optimize/Junk → count only",
        "result":  "✅ RESULT\nMax 2 Slack messages/night\n✅ = execute scale/pause\n❌ = skip everything",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 6,
        "title": "Data Refresh — Every 6 Hours",
        "trigger": "⏱ TRIGGER\nEvery 6h automatic\nreporting_scheduler.py\nAlso: manual via Railway",
        "action":  "⚙️ ACTION\n1. 22 collectors → BQ upsert\n2. 15 views refreshed\n3. t_* tables rebuilt (~10x faster)\n4. HubSpot 30-day resync\n5. Hex notebook re-run",
        "result":  "✅ RESULT\nAll dashboards current\nHubSpot retroactive updates caught\nHex loads in seconds",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 7,
        "title": "Health Checks — Hourly 09–17 Riyadh",
        "trigger": "⏱ TRIGGER\nHourly 09:00–17:00 Riyadh\n(UTC 06:00–14:00)\nOR on-demand via /activity",
        "action":  "⚙️ ACTION\nscripts/health_check.py\n• BigQuery · Google Ads · Meta\n• TikTok · LinkedIn · Snapchat\n• Microsoft · HubSpot · Asana\nResults → agent_activity_log (BQ)",
        "result":  "✅ RESULT\nActivity dashboard: pass/fail\nErrors visible with full detail\nNo Slack noise (dashboard only)",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 8,
        "title": "Meta Campaign Creation",
        "trigger": "⏱ TRIGGER\nUser asks agent to create\nScale plan in Asana approved\nCreative brief ready",
        "action":  "⚙️ ACTION\nPOST /act_<id>/campaigns\n• Status: PAUSED always\n• OUTCOME_LEADS objective\n• Qoyod_CRM_PIXEL (1782671302631317)\n• Qoyod_Web_PIXEL (3036579196577051)\n• Instagram profile: qoyod",
        "result":  "✅ RESULT\nPaused Meta campaign created\nBoth pixels enforced\nHuman enables after review",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 9,
        "title": "LinkedIn Campaign Setup",
        "trigger": "⏱ TRIGGER\nUser requests new LinkedIn\ncampaign: product, audience,\nbudget specified",
        "action":  "⚙️ ACTION\ncreate_full_campaign()\n• adCampaignGroups + adCampaigns\n• UTM: Group=utm_campaign\n  Campaign=utm_audience\n  Ad=utm_content\n• HubSpot Lead Event Sync",
        "result":  "✅ RESULT\nCampaign: LinkedIn_Invoice\nAd Set: LinkedIn_LeadGen_AR_Interests\nStatus: DRAFT — human enables",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 10,
        "title": "Negative Keyword Auto-Execution",
        "trigger": "⏱ TRIGGER\nDaily scan of search terms\nALWAYS_NEGATIVE policy check\n(keyword_policy.py)",
        "action":  "⚙️ ACTION\nALWAYS_NEGATIVE patterns:\n• login / تسجيل الدخول\n• free / مجاني · course / دورة\n• download / تحميل\n• job / وظيفة · loan / قرض\nAdded as negatives — no approval",
        "result":  "✅ RESULT\nJunk traffic blocked immediately\nSilent — no Slack noise\nLogged to BQ for audit",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 11,
        "title": "Asana Task Router",
        "trigger": "⏱ TRIGGER\nClaude analysis emits JSON\nwith channel + asset_level\n+ project_key",
        "action":  "⚙️ ACTION\nRoutes to correct project + section\n• channel → optimization project\n• asset_level → section name\n• Dedup: title × project × day\n6 projects · 7 channels",
        "result":  "✅ RESULT\nTask in correct project + section\nNo duplicates\nDate range always explicit (YYYY-MM-DD)",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
    {
        "n": 12,
        "title": "Activity Dashboard — Agent Transparency",
        "trigger": "⏱ TRIGGER\nAlways live at /activity\nAuto-refreshes on load\nData from agent_activity_log",
        "action":  "⚙️ ACTION\nFlask route reads BQ:\n• Asana tasks done (%)\n• Ads paused · Keywords added\n• Approval rate\n• Weekly autofix count\n• Data Hygiene status",
        "result":  "✅ RESULT\nFull accountability view\nEvery agent action logged\nApproval rate shows trust level",
        "colors":  ("light_yellow", "light_blue", "light_green"),
    },
]


def build():
    _delete_below(600)

    # Section header
    txt("<b>USE CASES</b>", x=0, y=640, w=1200, font=28, color="#0f172a")
    txt("Trigger · Action · Result  —  every major agent behaviour documented here",
        x=0, y=682, w=1400, font=13, color="#64748b")

    ROW_TOP    = 800
    ROW_HEIGHT = 400
    SW         = 230    # sticky width
    COLS       = [-260, 0, 260]
    COLORS     = ["light_yellow", "light_blue", "light_green"]

    for idx, uc in enumerate(USE_CASES):
        y_top = ROW_TOP + idx * ROW_HEIGHT

        # divider
        if idx > 0:
            txt("─" * 90, x=0, y=y_top - 22, w=1100, font=9, color="#e2e8f0")

        # title
        txt(f"<b>{uc['n']}. {uc['title']}</b>",
            x=0, y=y_top, w=1000, font=17, color="#0f172a")

        # 3 stickies
        for i, (key, col) in enumerate(zip(["trigger", "action", "result"], COLORS)):
            sticky(uc[key], x=COLS[i], y=y_top + 160, color=col, w=SW)

    print(f"\n[miro] {len(USE_CASES)} use cases built")
    print(f"       https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
