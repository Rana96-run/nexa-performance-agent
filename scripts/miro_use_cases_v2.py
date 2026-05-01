"""
Miro use cases — sticky-note flow style.

Per use case (~400px tall row):
  ┌──────────────────────────────────────────────────────────────┐
  │  Use Case N — Title                                          │
  │  Subtitle / context                                          │
  ├──────────┬──────────┬──────────┬──────────┐                  │
  │ TRIGGER  │ ACTION   │ SCREENSHT│ RESULT   │                  │
  │ (yellow) │ (blue)   │ (pink)   │ (green)  │                  │
  ├──────────┴──────────┴──────────┴──────────┤                  │
  │ [image embedded below]                    │                  │
  │ open ↗  https://...                       │                  │
  └──────────────────────────────────────────────────────────────┘

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
    """Delete every connector / shape / sticky / image / text below y_threshold."""
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


# ─── Drawing primitives ─────────────────────────────────────────────────────

def text(content, x, y, w=600, font=18, color="#0f172a", align="left"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def sticky(content, x, y, color="light_yellow", w=220):
    """A single sticky note. Color: light_yellow / light_blue / light_pink / light_green."""
    return _post("/sticky_notes", {
        "data": {"content": content, "shape": "square"},
        "style": {"fillColor": color},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def upload_image(path: Path, x: int, y: int, w: int):
    """POST multipart upload to /images."""
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


# ─── Use case definitions ───────────────────────────────────────────────────

USE_CASES = [
    {
        "n":         1,
        "title":     "Daily Performance Dashboard",
        "subtitle":  "Auto-generated HTML report — runs nightly + on-demand",
        "trigger":   "Nightly 03:00 Riyadh\nOR\nPOST /api/regenerate",
        "action":    "1. BQ refresh (10 collectors)\n2. Render HTML (20 sections)\n3. Upload to Drive\n4. Serve via /reports/latest",
        "image":     "07_dashboard.png",
        "result":    "Live dashboard\n4 channels, KPIs, charts,\nUTM tabs, dated archives",
        "link":      "https://nexa-performance-agent.up.railway.app/reports/latest",
        "link_label": "open dashboard",
    },
    {
        "n":         2,
        "title":     "HubSpot Segment List Creator",
        "subtitle":  "Build dynamic audiences for paid retargeting + lookalike seeding",
        "trigger":   "Strategist approves segment\nOR Asana task created\nin daily_activity/audience",
        "action":    "POST /crm/v3/lists\n• filterBranch: lifecyclestage\n• processingType: DYNAMIC\n• object: contacts (0-1)",
        "image":     "04_hubspot_list.png",
        "result":    "List 5674 + 5675 live\nReady for LinkedIn Matched\nAudience + Meta CAPI",
        "link":      "https://app.hubspot.com/contacts/144952270/objectLists/5674",
        "link_label": "open in HubSpot",
    },
    {
        "n":         3,
        "title":     "Asana Task — Auto Routed",
        "subtitle":  "Claude decisions JSON -> right project × section × asset_level",
        "trigger":   "Claude role emits JSON\nwith asana_project_key,\nchannel, asset_level",
        "action":    "Task router resolves:\n• project_key -> project ID\n• channel -> optimization proj\n• asset_level -> section",
        "image":     "03_asana_task.png",
        "result":    "Task created in correct\nproject + section, deduped\n(title × project × day)",
        "link":      "https://app.asana.com/0/1213239419217795/list",
        "link_label": "open Optimization board",
    },
    {
        "n":         4,
        "title":     "LinkedIn Campaign (auto-paused)",
        "subtitle":  "Approval-gated execution — never auto-launches",
        "trigger":   "User approves launch plan\nin Slack #approval\nwith ✓ reaction",
        "action":    "POST /adCampaigns\n• status: PAUSED\n• audience: LIST 5674\n• Lead Gen Form attached\n• Manual CPL bid cap",
        "image":     "05_linkedin_campaign.png",
        "result":    "Paused campaign in LI\nCampaign Manager.\nHuman enables manually.",
        "link":      "https://www.linkedin.com/campaignmanager/accounts",
        "link_label": "open LinkedIn",
    },
    {
        "n":         5,
        "title":     "Meta Campaign (auto-paused)",
        "subtitle":  "Same approval gate — Donia briefed for creative",
        "trigger":   "Scale plan in Asana\napproved + creative brief\nready",
        "action":    "POST /act_<id>/campaigns\n• status: PAUSED\n• OUTCOME_LEADS\n• CRM pixel\n• cost cap bidding",
        "image":     "06_meta_campaign.png",
        "result":    "Paused Meta campaign.\nDonia delivers creative,\nthen human enables.",
        "link":      "https://business.facebook.com/adsmanager",
        "link_label": "open Meta Ads Manager",
    },
    {
        "n":         6,
        "title":     "Slack Daily Summary",
        "subtitle":  "ONE concise message at end of nightly cycle (no spam)",
        "trigger":   "End of nightly cadence\n(after BQ + roles +\nspike detector + audit)",
        "action":    "build_daily_summary_text()\n• 7d total + per channel\n• Asana counts (today + pend)\n• spike count inline",
        "image":     "01_slack_daily.png",
        "result":    "One post in #notify\nUnder 12 lines, no emoji.\nReplaces 3 prior messages.",
        "link":      "https://qoyod.slack.com/archives/C0ARMQKK8GK",
        "link_label": "open #claude-ai-performance",
    },
    {
        "n":         7,
        "title":     "Slack Approval Request",
        "subtitle":  "High-confidence channel mutations — ✓/✗ reaction = action",
        "trigger":   "Claude emits decision\nwith confidence=High AND\naction in {pause,scale,...}",
        "action":    "post_approval_request()\n• 3-block layout\n• Action / KPI / proof\n• Posts to #approval",
        "image":     "02_slack_approval.png",
        "result":    "✓ -> executor runs\n✗ -> drop\nNo reaction -> wait",
        "link":      "https://qoyod.slack.com/archives/C0AT1AP8TJ4",
        "link_label": "open #claude-ai-approval",
    },
    {
        "n":         8,
        "title":     "Email Digest (fallback)",
        "subtitle":  "Used when Slack is unavailable OR weekly executive recap",
        "trigger":   "NOTIFY_VIA=email or both\nOR Slack post fails\nOR weekly cadence",
        "action":    "notify.send_email()\n• Gmail SMTP\n• HTML body\n• Same data as Slack",
        "image":     "08_email.png",
        "result":    "Email to your inbox\nat rana.khalid@qoyod.com",
        "link":      "mailto:rana.khalid@qoyod.com",
        "link_label": "rana.khalid@qoyod.com",
    },
]


# ─── Build ──────────────────────────────────────────────────────────────────

def build():
    # Clear everything below y=900 (keeps the main 4-column flow intact)
    _delete_below(900)

    # Section header
    text("USE CASES — sticky-note flow style",
         x=0, y=950, w=1200, font=32, align="center")
    text("4 stickies per use case · screenshot below · click 'open' to see the live artifact",
         x=0, y=1000, w=1400, font=14, color="#64748b", align="center")

    # ── Layout constants — compact + organized ─────────────────────────────
    ROW_TOP    = 1100   # first use case top
    ROW_HEIGHT = 480    # space per use case (was 600 — tightened)
    STICKY_W   = 200    # was 220
    sx         = [-330, -110, 110, 330]   # 4-sticky row, total span ~660
    IMG_W      = 480    # was 800 — much smaller, sized to readable
    IMG_Y_OFF  = 180    # below the stickies
    LINK_Y_OFF = 320    # below the image

    sticky_colors = ["light_yellow", "light_blue", "light_pink", "light_green"]

    for idx, uc in enumerate(USE_CASES):
        y_top = ROW_TOP + idx * ROW_HEIGHT

        # ── Subtle divider line between use cases (thin grey rule) ───────
        if idx > 0:
            _post("/shapes", {
                "data":  {"shape": "rectangle", "content": ""},
                "style": {"fillColor": "#e2e8f0", "borderColor": "#e2e8f0",
                           "borderWidth": "1"},
                "position": {"x": 0, "y": y_top - 30, "origin": "center"},
                "geometry": {"width": 900, "height": 2},
            })

        # 1. Title + subtitle
        text(f"<strong>Use Case {uc['n']} — {uc['title']}</strong>",
             x=0, y=y_top, w=1000, font=20, align="center")
        text(uc["subtitle"], x=0, y=y_top + 32, w=1000,
             font=12, color="#64748b", align="center")

        # 2. The 4 stickies row
        sticky_y = y_top + 110
        labels = ["1 · TRIGGER", "2 · ACTION", "3 · SCREENSHOT", "4 · RESULT"]
        contents = [uc["trigger"], uc["action"],
                    "see image below", uc["result"]]
        for i in range(4):
            sticky(f"<strong>{labels[i]}</strong>\n\n{contents[i]}",
                   x=sx[i], y=sticky_y, color=sticky_colors[i], w=STICKY_W)

        # 3. Screenshot image (centered below stickies, smaller width)
        img_path = SHOTS / uc["image"]
        if img_path.exists():
            upload_image(img_path,
                          x=0, y=sticky_y + IMG_Y_OFF, w=IMG_W)
        else:
            print(f"  [warn] missing image: {img_path}")

        # 4. Link below the image
        text(f'<a href="{uc["link"]}">↗ {uc["link_label"]}</a>',
             x=0, y=sticky_y + LINK_Y_OFF, w=600,
             font=13, color="#2563eb", align="center")

    print(f"\n[miro] {len(USE_CASES)} use case rows built")
    print(f"      https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
