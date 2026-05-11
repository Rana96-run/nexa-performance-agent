"""
scripts/miro_use_cases_v2.py
=============================
All use cases — 4-sticky layout per row, placed below the main flow diagram.

Run AFTER miro_agent_workflow.py (that script owns the flow above y=900).

Run with:  python scripts/miro_use_cases_v2.py
"""
from __future__ import annotations

import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD = os.getenv("MIRO_BOARD_ID")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
H_AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = f"https://api.miro.com/v2/boards/{BOARD}"

SHOTS = Path(__file__).parent / "_screenshots"


# ─── API helpers ─────────────────────────────────────────────────────────────

def _post(path, payload):
    r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=15)
    if not r.ok:
        print(f"  FAIL {path}: {r.status_code} — {r.text[:160]}")
        return None
    return r.json()


def _get_all(kind: str):
    out, cursor = [], None
    while True:
        url = f"{BASE}/{kind}?limit=50"
        if cursor:
            url += f"&cursor={cursor}"
        r = requests.get(url, headers=H_AUTH, timeout=15)
        if not r.ok:
            return out
        d = r.json()
        out.extend(d.get("data", []))
        cursor = d.get("cursor")
        if not cursor:
            break
    return out


def _delete_below(y_threshold: int):
    """Delete everything below y_threshold — preserves the main flow."""
    deleted = 0
    for kind in ("connectors", "shapes", "sticky_notes", "cards", "texts", "images"):
        for it in _get_all(kind):
            pos = it.get("position") or {}
            y = pos.get("y", 0)
            if y >= y_threshold:
                requests.delete(f"{BASE}/{kind}/{it['id']}", headers=H_AUTH, timeout=10)
                deleted += 1
    print(f"[miro] deleted {deleted} item(s) below y={y_threshold}")
    time.sleep(2)


def text(content, x, y, w=600, font=18, color="#0f172a", align="left"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def sticky(content, x, y, color="light_yellow", w=220):
    return _post("/sticky_notes", {
        "data": {"content": content, "shape": "square"},
        "style": {"fillColor": color},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def upload_image(path: Path, x: int, y: int, w: int):
    url = f"{BASE}/images"
    with open(path, "rb") as f:
        files = {
            "resource": (path.name, f, "image/png"),
            "data": (None,
                     '{"position":{"x":' + str(x) + ',"y":' + str(y) + '},'
                     '"geometry":{"width":' + str(w) + '}}',
                     "application/json"),
        }
        r = requests.post(url, headers=H_AUTH, files=files, timeout=60)
    if not r.ok:
        print(f"  upload FAIL {path.name}: {r.status_code} {r.text[:160]}")
        return None
    return r.json().get("id")


# ─── Use case definitions ─────────────────────────────────────────────────────

USE_CASES = [
    {
        "n":        1,
        "title":    "Nightly Campaign Health — CPQL/CPL Audit",
        "subtitle": "Cross-channel health check every night — every finding goes to #approvals",
        "trigger":  "Nightly 03:00 Riyadh\nautomatic — every day\n(no manual trigger needed)",
        "action":   "audit_campaign_health()\n• 14-day minimum window\n• CPQL first, then CPL\n• Scale / Pause / Optimize / Junk\n• Case-insensitive UTM join (BQ)",
        "result":   "Asana tasks: PENDING APPROVAL\n#approvals: 1 batch digest\nNothing executes until ✅",
        "image":    None,
        "screenshot_text": "Asana task:\n──────────────────\nPENDING APPROVAL: Pause —\nMeta_LeadGen_AR_Invoice_Interests\nCPQL $84.94 | CPL $23.02\nQual rate 27.1%\nAwaiting ✅ in #approvals",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        2,
        "title":    "✅ Reaction → Execute Scale / Pause",
        "subtitle": "React on #approvals → executor fires immediately",
        "trigger":  "User reacts ✅ or ❌\non the nightly digest\nin Slack #approvals",
        "action":   "_handle_reaction()\n→ _execute_approved_action()\n• scale: budget +25%\n• pause: pause_campaign()\n• Via Adspirer MCP or direct API\n• Asana task comment added",
        "result":   "Budget raised / campaign paused\nThread reply with result\nAsana task updated to EXECUTED\nRemoved from pending queue",
        "image":    None,
        "screenshot_text": "Slack thread reply:\n──────────────────\n✅ Approved by @Amar\n\nMeta_LeadGen_AR_Invoice_Interests\n→ Budget $80 → $100/day (+25%)\n\nAsana: ✅ EXECUTED",
        "link":     "https://qoyod.slack.com/archives/C0AT1AP8TJ4",
        "link_label": "open #approvals",
    },
    {
        "n":        3,
        "title":    "Asana Task Router",
        "subtitle": "Every Claude finding → right project × section × asset level, deduplicated",
        "trigger":  "Claude analysis emits JSON\nwith asana_project_key,\nchannel, asset_level",
        "action":   "Task router resolves:\n• project_key → project ID\n• channel → optimization project\n• asset_level → section\nDedup: title × project × day",
        "result":   "Task in correct project + section\nNo duplicate tasks\n6 projects · 7 channels covered",
        "image":    "03_asana_task.png",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        4,
        "title":    "Slack — 2 Messages Per Night Maximum",
        "subtitle": "1 in #notify (summary) + 1 in #approvals (all actions) — nothing else",
        "trigger":  "End of nightly cadence\nafter all analysis + audits\n+ task creation done",
        "action":   "post_nightly_approvals_digest()\n• Scale + Pause (executable on ✅)\n• Optimize/Junk/Drill → count only\n  → Asana already created\nMax 2 total messages per night",
        "result":   "#notify: date · 7d totals · alerts\n#approvals: all actions in 1 msg\n✅ = execute scale/pause\n❌ = skip everything",
        "image":    "02_slack_approval.png",
        "link":     "https://qoyod.slack.com/archives/C0AT1AP8TJ4",
        "link_label": "open #approvals",
    },
    {
        "n":        5,
        "title":    "Google Ads Audit — IS / QS / Keywords",
        "subtitle": "Impression share, quality score, and keyword expansion — weekly on Sundays",
        "trigger":  "Sunday Riyadh (weekly)\nKeyword additions + pauses\nDaily: IS/QS audit only",
        "action":   "create_audit_tasks()\n• Impression share by campaign\n• QS < 5 + >80% lost-IS → pause\n• Search terms → keyword candidates\n• 30-keyword cap per ad group\n• Never delete keyword with spend",
        "result":   "Asana tasks per campaign\nIS low → budget recommendation\nQS low → ad copy task\nKeyword candidates (Sunday only)",
        "image":    None,
        "screenshot_text": "Asana task (Sunday):\n──────────────────\nGoogle Ads — Keyword audit\nSearch_AR_Invoice_Broad\nIS: 12% | Lost-Budget: 38%\n→ Raise daily budget +25%\nKeyword: قيود محاسبة QS=3\n→ Below avg ad relevance",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        6,
        "title":    "Meta Campaign (auto-paused)",
        "subtitle": "Naming enforced · both Qoyod pixels · Instagram = qoyod",
        "trigger":  "Scale plan in Asana approved\n+ creative brief ready\n→ user asks agent to create",
        "action":   "POST /act_<id>/campaigns\n• status: PAUSED (always)\n• OUTCOME_LEADS objective\n• Qoyod_CRM_PIXEL (1782671302631317)\n• Qoyod_Web_PIXEL (3036579196577051)\n• Instagram profile: qoyod",
        "result":   "Paused Meta campaign created\nBoth pixels active\nHuman enables after review",
        "image":    "06_meta_campaign.png",
        "link":     "https://business.facebook.com/adsmanager",
        "link_label": "open Meta Ads Manager",
    },
    {
        "n":        7,
        "title":    "LinkedIn Campaign Setup via API",
        "subtitle": "Full Campaign / Ad Set created — naming enforced, HubSpot Lead Event Sync",
        "trigger":  "User requests new LinkedIn\ncampaign: product, audience,\nbudget specified",
        "action":   "create_full_campaign()\n• adCampaignGroups + adCampaigns\n• CPC bidding + SA targeting\n• HubSpot Lead Event Sync\n• LinkedIn UTM: Group=utm_campaign\n  Campaign=utm_audience  Ad=utm_content",
        "result":   "Campaign: LinkedIn_Invoice\nAd Set: LinkedIn_LeadGen_AR_Interests\nStatus: DRAFT\nHuman reviews before enabling",
        "image":    "09_linkedin_campaign.png",
        "link":     "https://www.linkedin.com/campaignmanager/accounts/506171805/campaigns",
        "link_label": "open LinkedIn Campaign Manager",
    },
    {
        "n":        8,
        "title":    "HubSpot Segment List Creator",
        "subtitle": "Dynamic audiences for paid retargeting + lookalike seeding",
        "trigger":  "Strategist approves segment\nOR Asana task created\nin daily_activity/audience",
        "action":   "POST /crm/v3/lists\n• filterBranch: lifecyclestage\n• processingType: DYNAMIC\n• object: contacts (0-1)\nLinkedIn Matched Audience sync",
        "result":   "Dynamic list live in HubSpot\nReady for LinkedIn Matched\nAudience + Meta CAPI",
        "image":    "04_hubspot_list.png",
        "link":     "https://app.hubspot.com/contacts/144952270/objectLists/5674",
        "link_label": "open in HubSpot",
    },
    {
        "n":        9,
        "title":    "Data Refresh — Every 6 Hours",
        "subtitle": "22 collectors → BigQuery → t_* materialized tables → Hex re-run",
        "trigger":  "Every 6h automatic\n(reporting_scheduler.py)\nAlso: manual via Railway",
        "action":   "1. Run all 22 collectors (upsert)\n2. refresh_all_views() — 15 views\n3. run_migration() → t_* tables\n4. Hex notebook API re-run\n5. HubSpot 30-day lead resync",
        "result":   "All dashboards current\nt_* tables refreshed (~10x faster)\nHubSpot retroactive updates caught\nHex loads in seconds",
        "image":    None,
        "screenshot_text": "reporting_scheduler.py log:\n──────────────────\n[6h] 22 collectors done\n[6h] 15 views refreshed\n[6h] t_* tables rebuilt\n[6h] HubSpot 30d resync: 847 rows\n[6h] Hex triggered ✅",
        "link":     "https://nexa-performance-agent.up.railway.app/health",
        "link_label": "health endpoint",
    },
    {
        "n":        10,
        "title":    "Data Hygiene — Hourly Health Checks",
        "subtitle": "Every connector checked 09–17 Riyadh — results visible in Activity Dashboard",
        "trigger":  "Hourly 09:00–17:00 Riyadh\n(UTC 06:00–14:00)\nOR on-demand via dashboard",
        "action":   "scripts/health_check.py\n• BigQuery connection\n• Google Ads, Meta, TikTok\n• LinkedIn, HubSpot, Asana\n• Data freshness per channel\nResults logged → agent_activity_log",
        "result":   "Activity dashboard: pass/fail cards\nClick card → full error detail\nAll results persisted in BQ\n'Run now' button for on-demand",
        "image":    None,
        "screenshot_text": "Activity Dashboard:\n── Data Hygiene ──\n9/10 passing · 1 failing\n✅ BigQuery\n✅ Google Ads\n✅ Meta\n✅ TikTok\n✅ HubSpot\n❌ LinkedIn — token expired\n  AADSTS70011: invalid scope",
        "link":     "https://nexa-performance-agent.up.railway.app/activity",
        "link_label": "open Activity Dashboard",
    },
    {
        "n":        11,
        "title":    "Activity Dashboard — Agent Transparency",
        "subtitle": "What did the agent actually do? Six metric cards + full action log",
        "trigger":  "Always live at /activity\nAuto-refreshes on load\nData from agent_activity_log",
        "action":   "Flask route reads BQ:\n• Asana tasks done (%)\n• Campaign outcomes\n• Keywords added\n• Ads paused\n• Approval rate\n• Weekly autofix count\n• Campaigns paused (grouped)",
        "result":   "Full accountability view\nNo black-box — every action logged\nApproval rate shows trust level\nData Hygiene shows connector status",
        "image":    None,
        "screenshot_text": "Activity Dashboard cards:\n──────────────────\n✅ Asana Done: 78%\n📊 Campaign Outcomes: 12\n🔑 Keywords Added: 34\n⏸ Ads Paused: 3\n✅ Approval Rate: 91%\n🔁 Weekly Autofix: 7",
        "link":     "https://nexa-performance-agent.up.railway.app/activity",
        "link_label": "open Activity Dashboard",
    },
    {
        "n":        12,
        "title":    "LP A/B Test Tracking",
        "subtitle": "HubSpot landing page vs WordPress landing page — weekly performance view",
        "trigger":  "Test started: 2026-05-04\nTracked automatically\nvia v_lp_performance_weekly",
        "action":   "v_lp_performance_weekly:\n• Joins ads_daily final_url\n• Splits: HubSpot LP vs WP LP\n• CPL + CPQL + conv rate per LP\n• Weekly grain (rolling)",
        "result":   "Side-by-side LP comparison\nWhich LP converts better?\nWhich LP has better CPQL?\nData-driven decision on winner",
        "image":    None,
        "screenshot_text": "Hex — LP Test (Week 2):\n──────────────────\nHubSpot LP\n  CPL $18.40 | CPQL $52.10\n  Conv rate: 8.2%\n\nWordPress LP\n  CPL $22.80 | CPQL $71.30\n  Conv rate: 5.9%\n→ HubSpot LP winning",
        "link":     "https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest",
        "link_label": "open Hex dashboard",
    },
    {
        "n":        13,
        "title":    "Negative Keyword Auto-Execution",
        "subtitle": "Junk traffic blocked automatically — no approval needed",
        "trigger":  "Daily scan of search terms\n+ ALWAYS_NEGATIVE policy check\n(keyword_policy.py)",
        "action":   "ALWAYS_NEGATIVE patterns:\n• login / sign in / تسجيل الدخول\n• free / مجاني\n• course / دورة / كورس\n• download / تحميل\n• job / وظيفة / توظيف\n• loan / قرض / تمويل\nAdded as negatives — no approval",
        "result":   "Junk traffic blocked immediately\nNo budget wasted on intent mismatch\nSilent — no Slack noise\nLogged to BQ for audit",
        "image":    None,
        "screenshot_text": "keyword_policy.py auto-execute:\n──────────────────\nAdded as negatives (today):\n• تحميل مجاني (exact)\n• تسجيل دخول (phrase)\n• دورة محاسبة (exact)\n• وظائف محاسبة (phrase)\nLogged to agent_activity_log ✅",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        14,
        "title":    "Junk Lead Detection — Ad Pause",
        "subtitle": "Ad with 60%+ disqualification rate gets flagged for pause",
        "trigger":  "Nightly audit\nAd running 10+ days\nLeads converting but mostly junk",
        "action":   "Check: leads_disqualified /\nleads_total >= 60%\nAND ad_age >= 10 days\nFlag → PENDING APPROVAL in Asana\n+ included in #approvals digest",
        "result":   "Ad paused after ✅\nJunk rate surfaced in task\nCreative insight: wrong audience\nAsana task with date range proof",
        "image":    None,
        "screenshot_text": "Asana task:\n──────────────────\nPENDING APPROVAL: Pause ad\nMeta_AR_UGC_Ahmed (junk leads)\n2026-04-28 to 2026-05-11\n──────────────────\nLeads: 38 | Qualified: 14\nDisqualification rate: 63.2%\nSpend: $142 | CPL: $3.74",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        15,
        "title":    "Meta Campaign — Pixel Enforcement",
        "subtitle": "Both Qoyod pixels required on every Meta campaign — enforced at creation",
        "trigger":  "Any Meta campaign creation\nor configuration\n(agent or manual)",
        "action":   "Ad Setup → Tracking:\n✅ Qoyod_CRM_PIXEL\n   ID: 1782671302631317\n   (tracks SQL conversions)\n✅ Qoyod_Web_PIXEL\n   ID: 3036579196577051\n   (tracks site behaviour)\nInstagram profile: qoyod",
        "result":   "Both conversion sources active\nCRM tracks qualified leads\nWeb tracks site funnel\nInstagram placements enabled",
        "image":    None,
        "screenshot_text": "Meta Ads Manager:\nAd Setup → Tracking\n──────────────────\n☑ Qoyod_CRM_PIXEL\n  (1782671302631317) Lead\n☑ Qoyod_Web_PIXEL\n  (3036579196577051) Lead\nInstagram account: qoyod ✅",
        "link":     "https://business.facebook.com/adsmanager",
        "link_label": "open Meta Ads Manager",
    },
]


# ─── Build ──────────────────────────────────────────────────────────────────

def build():
    _delete_below(900)

    # Section header
    text("<b>USE CASES</b>", x=0, y=960, w=1200, font=30,
         color="#0f172a", align="center")
    text("4 stickies per use case  ·  Trigger → Action → Screenshot → Result",
         x=0, y=1005, w=1400, font=13, color="#64748b", align="center")

    # ── Layout constants ─────────────────────────────────────────────────────
    ROW_TOP    = 1100
    ROW_HEIGHT = 480
    STICKY_W   = 210
    sx         = [-330, -110, 110, 330]
    IMG_W      = 480
    IMG_Y_OFF  = 180
    LINK_Y_OFF = 320
    COLORS     = ["light_yellow", "light_blue", "light_pink", "light_green"]

    for idx, uc in enumerate(USE_CASES):
        y_top = ROW_TOP + idx * ROW_HEIGHT

        # Divider — thin text rule (shapes below ~10px fail Miro validation)
        if idx > 0:
            text("─" * 80, x=0, y=y_top - 28, w=1000,
                 font=10, color="#cbd5e1", align="center")

        # Title + subtitle
        text(f"<b>Use Case {uc['n']} — {uc['title']}</b>",
             x=0, y=y_top, w=1000, font=19, align="center")
        text(uc["subtitle"], x=0, y=y_top + 30, w=1000,
             font=12, color="#64748b", align="center")

        # 4 stickies
        sticky_y  = y_top + 110
        labels    = ["1 · TRIGGER", "2 · ACTION", "3 · SCREENSHOT", "4 · RESULT"]
        img_path  = SHOTS / uc["image"] if uc.get("image") else None
        has_image = img_path and img_path.exists()
        if not has_image and uc.get("image"):
            print(f"  [warn] missing image: {img_path}")
        screenshot_content = (
            "see image below" if has_image
            else uc.get("screenshot_text", "—")
        )
        contents = [uc["trigger"], uc["action"], screenshot_content, uc["result"]]
        for i in range(4):
            sticky(f"<b>{labels[i]}</b>\n\n{contents[i]}",
                   x=sx[i], y=sticky_y, color=COLORS[i], w=STICKY_W)

        # Screenshot image (if file exists)
        if has_image:
            upload_image(img_path, x=0, y=sticky_y + IMG_Y_OFF, w=IMG_W)

        # Link
        text(f'<a href="{uc["link"]}">↗ {uc["link_label"]}</a>',
             x=0, y=sticky_y + LINK_Y_OFF, w=600,
             font=13, color="#2563eb", align="center")

    print(f"\n[miro] {len(USE_CASES)} use cases built")
    print(f"       https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
