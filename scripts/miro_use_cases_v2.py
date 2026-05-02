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
    # ── Original 9 ────────────────────────────────────────────────────────────
    {
        "n":        1,
        "title":    "Daily Performance Dashboard",
        "subtitle": "Auto-generated HTML report — runs nightly + on-demand",
        "trigger":  "Nightly 03:00 Riyadh\nOR\nPOST /api/regenerate",
        "action":   "1. BQ refresh (10 collectors)\n2. Render HTML (20 sections)\n3. Upload to Drive\n4. Serve via /paid-performance/latest",
        "result":   "Live dashboard\n4 channels, KPIs, charts\nUTM tabs, dated archives",
        "image":    "07_dashboard.png",
        "link":     "https://nexa-performance-agent.up.railway.app/paid-performance/latest",
        "link_label": "open dashboard",
    },
    {
        "n":        2,
        "title":    "HubSpot Segment List Creator",
        "subtitle": "Build dynamic audiences for paid retargeting + lookalike seeding",
        "trigger":  "Strategist approves segment\nOR Asana task created\nin daily_activity/audience",
        "action":   "POST /crm/v3/lists\n• filterBranch: lifecyclestage\n• processingType: DYNAMIC\n• object: contacts (0-1)",
        "result":   "List 5674 + 5675 live\nReady for LinkedIn Matched\nAudience + Meta CAPI",
        "image":    "04_hubspot_list.png",
        "link":     "https://app.hubspot.com/contacts/144952270/objectLists/5674",
        "link_label": "open in HubSpot",
    },
    {
        "n":        3,
        "title":    "Asana Task — Auto Routed",
        "subtitle": "Claude findings JSON → right project × section × asset_level",
        "trigger":  "Claude role emits JSON\nwith asana_project_key,\nchannel, asset_level",
        "action":   "Task router resolves:\n• project_key → project ID\n• channel → optimization proj\n• asset_level → section",
        "result":   "Task in correct project\n+ section, deduped\n(title × project × day)",
        "image":    "03_asana_task.png",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        4,
        "title":    "LinkedIn Campaign (auto-paused)",
        "subtitle": "Approval-gated creation — never auto-launches",
        "trigger":  "User approves launch plan\nin Slack #approvals\nwith ✅ reaction",
        "action":   "POST /adCampaigns\n• status: PAUSED\n• audience: LIST 5674\n• Lead Gen Form attached\n• Manual CPL bid cap",
        "result":   "Paused campaign in LI\nCampaign Manager.\nHuman enables manually.",
        "image":    "05_linkedin_campaign.png",
        "link":     "https://www.linkedin.com/campaignmanager/accounts",
        "link_label": "open LinkedIn",
    },
    {
        "n":        5,
        "title":    "Meta Campaign (auto-paused)",
        "subtitle": "Naming enforced · both Qoyod pixels · Instagram = qoyod",
        "trigger":  "Scale plan in Asana\napproved + creative brief\nready",
        "action":   "POST /act_<id>/campaigns\n• status: PAUSED\n• OUTCOME_LEADS\n• Qoyod_CRM_PIXEL (1782671302631317)\n• Qoyod_Web_PIXEL (3036579196577051)\n• Instagram: qoyod",
        "result":   "Paused Meta campaign.\nDonia delivers creative,\nthen human enables.",
        "image":    "06_meta_campaign.png",
        "link":     "https://business.facebook.com/adsmanager",
        "link_label": "open Meta Ads Manager",
    },
    {
        "n":        6,
        "title":    "Slack Daily Summary",
        "subtitle": "ONE message per night — max 1 in #notify, max 2 in #approvals",
        "trigger":  "End of nightly cadence\n(after BQ + analysis +\nspike detector + audit)",
        "action":   "build_daily_summary_text()\n• Performance (7d totals)\n• Alerts vs 7d average\n• Sent to #approvals summary\n• Asana: new / pending / overdue",
        "result":   "1 post in #notify\nClean sections, no noise\nNo separate rec message",
        "image":    "01_slack_daily.png",
        "link":     "https://qoyod.slack.com/archives/C0ARMQKK8GK",
        "link_label": "open #claude-ai-performance",
    },
    {
        "n":        7,
        "title":    "Slack — 2 Messages Per Night Total",
        "subtitle": "1 in #notify (summary) + 1 in #approvals (all actions) — nothing else",
        "trigger":  "End of nightly cadence\nafter all health + audit\ntasks are created",
        "action":   "post_nightly_approvals_digest()\n• Scale + Pause (executable)\n• Optimize/Junk/Drill → count only\nPre-loads ✅ ❌ reactions",
        "result":   "#notify: date · 7d totals · alerts\n#approvals: 1 msg all actions\n✅ = execute scale/pause\n❌ = skip all",
        "image":    "02_slack_approval.png",
        "link":     "https://qoyod.slack.com/archives/C0AT1AP8TJ4",
        "link_label": "open #claude-ai-approval",
    },
    {
        "n":        8,
        "title":    "Email Digest (fallback)",
        "subtitle": "Used when Slack is unavailable OR weekly executive recap",
        "trigger":  "NOTIFY_VIA=email or both\nOR Slack post fails\nOR weekly cadence",
        "action":   "notify.send_email()\n• Gmail SMTP\n• HTML body\n• Same data as Slack",
        "result":   "Email to inbox\nrana.khalid@qoyod.com",
        "image":    "08_email.png",
        "link":     "mailto:rana.khalid@qoyod.com",
        "link_label": "rana.khalid@qoyod.com",
    },
    {
        "n":        9,
        "title":    "LinkedIn Campaign Setup via API",
        "subtitle": "Full Campaign / Ad Set created — naming enforced, HubSpot Lead Event Sync",
        "trigger":  "User requests new LinkedIn\ncampaign with product,\naudience & budget",
        "action":   "create_full_campaign()\n• adCampaignGroups + adCampaigns\n• CPC bidding + SA targeting\n• HubSpot Lead Event Sync\n• Name: LinkedIn_{Product} / LinkedIn_{Type}_{Lang}_{Audience}",
        "result":   "Campaign: LinkedIn_Invoice\nAd Set: LinkedIn_LeadGen_AR_Interests\nStatus: DRAFT\nHuman reviews before enabling",
        "image":    "09_linkedin_campaign.png",
        "link":     "https://www.linkedin.com/campaignmanager/accounts/506171805/campaigns",
        "link_label": "open LinkedIn Campaign Manager",
    },

    # ── New use cases from this session ───────────────────────────────────────
    {
        "n":        10,
        "title":    "Campaign Health Check — CPQL/CPL Audit",
        "subtitle": "Cross-channel health check runs nightly — every finding goes to #approvals",
        "trigger":  "Nightly cadence\nOR /campaign-health\nslash command",
        "action":   "audit_campaign_health()\n• 14-day window (minimum)\n• CPQL first, then CPL\n• Scale / Pause / Optimize / Junk\n• BQ: case-insensitive UTM join",
        "result":   "Asana tasks: PENDING APPROVAL\n#approvals: max 2 batch msgs\nNothing executes until ✅",
        "image":    None,
        "screenshot_text": "Asana task created:\n──────────────────\nPENDING APPROVAL: Pause —\nMeta_LeadGen_AR_Invoice_Interests\n— CPQL critical (14d)\n──────────────────\nCPQL $84.94 | CPL $23.02\nQual rate 27.1%\nAction: awaiting ✅ in #approvals",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        11,
        "title":    "✅ Reaction → Execute Scale / Pause",
        "subtitle": "User reacts on #approvals message — executor runs the platform action",
        "trigger":  "User adds ✅ reaction\nto approval message\nin #approvals",
        "action":   "_handle_reaction()\n→ _execute_approved_action()\n• scale: set_campaign_budget +25%\n• pause: pause_campaign()\n• Via Adspirer MCP or direct API\nAsana task comment added",
        "result":   "Budget raised / campaign paused\nThread reply: '✅ Approved by @user'\nAsana: [Nexa] Approved + result\nRemoved from pending_approvals.json",
        "image":    None,
        "screenshot_text": "Slack thread reply:\n──────────────────\n✅ Approved by @Amar\n\nMeta_LeadGen_AR_Invoice_Interests\n→ Budget $80→$100/day (+25%)\n\n[Nexa] Asana updated:\n✅ EXECUTED — budget raised",
        "link":     "https://qoyod.slack.com/archives/C0AT1AP8TJ4",
        "link_label": "open #claude-ai-approval",
    },
    {
        "n":        12,
        "title":    "Google Ads Audit — IS / QS / Search Terms",
        "subtitle": "Daily audit of impression share, quality score, and search term opportunities",
        "trigger":  "Nightly cadence\nOR /audit slash command",
        "action":   "create_audit_tasks()\n• Impression share by campaign\n• Quality score by keyword\n• Search terms ready to promote\n• Keywords to pause (0 conv.)",
        "result":   "Asana tasks per channel\nIS low → budget recommendation\nQS low → ad copy task\nNew keywords → add to ad group",
        "image":    None,
        "screenshot_text": "Asana task:\n──────────────────\nGoogle Ads — IS audit\n(3 campaigns flagged)\n──────────────────\nSearch_AR_Invoice_Broad\nIS: 12% | Lost-Budget: 38%\n→ Raise daily budget +25%\nQS keyword: قيود محاسبة\nQS=3 | Ad relevance: Below avg",
        "link":     "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":        13,
        "title":    "Slash Commands — Quick Actions",
        "subtitle": "Run any agent function instantly from Claude Code without waiting for the nightly cycle",
        "trigger":  "User types in Claude Code:\n/health · /audit · /report\n/campaign-health · /deploy-status",
        "action":   "/health  → scripts/health_check.py\n/audit   → google_ads_audit_tasks\n/report  → run_cadence on_demand\n/campaign-health → audit_campaign_health()\n/deploy-status  → railway logs + /health",
        "result":   "Instant output in Claude\nNo Asana tasks created\nNo Slack posts\nAnalysis only (except /report)",
        "image":    None,
        "screenshot_text": "Claude Code terminal:\n──────────────────\n$ /health\n✅ Railway  ✅ Slack\n✅ Google Ads  ✅ Meta\n✅ BigQuery  ✅ Asana\n✅ HubSpot  ✅ Flask\nALL 12/12 PASS ✅\n──────────────────\n(no Slack post — analysis only)",
        "link":     "https://nexa-performance-agent.up.railway.app/health",
        "link_label": "health endpoint",
    },
    {
        "n":        14,
        "title":    "Scheduled Routines",
        "subtitle": "Recurring automated checks beyond the nightly cycle",
        "trigger":  "9:00 AM daily (Riyadh)\n→ health check\nMonday 8:00 AM (Riyadh)\n→ weekly reminder",
        "action":   "Morning: scripts/health_check.py\n• All integrations: Railway, Slack,\n  Google Ads, Meta, BQ, Asana\nMonday: Slack reminder\n• Review last week's Asana tasks\n• Check overdue items",
        "result":   "Daily: 12/12 checks or alert\nMonday: Slack reminder in #notify\nProactive — not reactive",
        "image":    None,
        "screenshot_text": "Slack #notify (9:00 AM):\n──────────────────\n⚠️ Nexa Health — 02 May 09:00\n1 issue detected (11/12 passing)\n✖ Meta API → token expired\n  (refresh via Meta Business)\n──────────────────\nAll other checks: ✅",
        "link":     "https://nexa-performance-agent.up.railway.app/health",
        "link_label": "health endpoint",
    },
    {
        "n":        15,
        "title":    "Meta Campaign — Pixels + Instagram Setup",
        "subtitle": "Enforced checklist for every Meta campaign creation",
        "trigger":  "Any Meta campaign being\ncreated or configured\n(executor or manual)",
        "action":   "Ad Setup → Tracking:\n• ✅ CRM events: Qoyod_CRM_PIXEL\n  ID: 1782671302631317\n• ✅ Website events: Qoyod_Web_PIXEL\n  ID: 3036579196577051\nAd Setup → Instagram profile:\n• Select: qoyod",
        "result":   "Both conversion sources active\nCRM tracks SQLs\nWeb tracks site behaviour\nInstagram placements enabled",
        "image":    None,
        "screenshot_text": "Meta Ads Manager:\nAd Setup → Tracking\n──────────────────\n☑ Qoyod_CRM_PIXEL\n  (1782671302631317)\n  Event: Lead\n☑ Qoyod_Web_PIXEL\n  (3036579196577051)\n  Event: Lead\nInstagram account: qoyod ✅",
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
