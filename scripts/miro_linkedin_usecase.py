"""
scripts/miro_linkedin_usecase.py
=================================
Appends Use Case 9 — LinkedIn Campaign Setup via API — to the existing
use case board, using the exact same layout as miro_use_cases_v2.py.

Does NOT delete or touch existing items.

Before running:
  Save the LinkedIn Campaign Manager screenshots as:
  scripts/_screenshots/09_linkedin_campaign.png

Run with:
    python scripts/miro_linkedin_usecase.py
"""
from __future__ import annotations
import os, sys, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN  = os.getenv("MIRO_ACCESS_TOKEN")
BOARD  = os.getenv("MIRO_BOARD_ID")
H      = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
H_AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE   = f"https://api.miro.com/v2/boards/{BOARD}"
SHOTS  = Path(__file__).parent / "_screenshots"


# ── Same helpers as miro_use_cases_v2.py ─────────────────────────────────────

def _post(path, payload):
    r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=15)
    if not r.ok:
        print(f"  FAIL {path}: {r.status_code} — {r.text[:160]}")
        return None
    return r.json()


def text(content, x, y, w=600, font=18, color="#0f172a", align="left"):
    return _post("/texts", {
        "data":     {"content": content},
        "style":    {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def sticky(content, x, y, color="light_yellow", w=200):
    return _post("/sticky_notes", {
        "data":     {"content": content, "shape": "square"},
        "style":    {"fillColor": color},
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


# ── Layout constants — identical to miro_use_cases_v2.py ─────────────────────
ROW_TOP     = 1100
ROW_HEIGHT  = 480
STICKY_W    = 200
sx          = [-330, -110, 110, 330]
IMG_W       = 480
IMG_Y_OFF   = 180
LINK_Y_OFF  = 320
STICKY_COLORS = ["light_yellow", "light_blue", "light_pink", "light_green"]


def build():
    # Use Case 9 is index 8 (0-based) — placed right after the existing 8
    idx   = 8
    n     = 9
    y_top = ROW_TOP + idx * ROW_HEIGHT   # = 4940

    # ── Divider line (same as in v2.py) ──────────────────────────────────────
    _post("/shapes", {
        "data":     {"shape": "rectangle", "content": ""},
        "style":    {"fillColor": "#e2e8f0", "borderColor": "#e2e8f0", "borderWidth": "1"},
        "position": {"x": 0, "y": y_top - 30, "origin": "center"},
        "geometry": {"width": 900, "height": 2},
    })

    # ── Title + subtitle ──────────────────────────────────────────────────────
    text(f"<strong>Use Case {n} — LinkedIn Campaign Setup via API</strong>",
         x=0, y=y_top, w=1000, font=20, align="center")
    text("Full Campaign / Ad Set created via Marketing API — naming enforced, HubSpot Lead Event Sync",
         x=0, y=y_top + 32, w=1000, font=12, color="#64748b", align="center")

    # ── 4 stickies ───────────────────────────────────────────────────────────
    sticky_y = y_top + 110
    labels   = ["1 · TRIGGER", "2 · ACTION", "3 · SCREENSHOT", "4 · RESULT"]
    contents = [
        # TRIGGER
        "User requests new\nLinkedIn campaign\nwith product, audience\n& budget",
        # ACTION
        "create_full_campaign()\n- Campaign (adCampaignGroups)\n- Ad Set (adCampaigns)\n- CPC bidding + SA targeting\n- HubSpot Lead Event Sync",
        # SCREENSHOT
        "see image below",
        # RESULT
        "Campaign: LinkedIn_Invoice\nID: 1047600914\nAd Set: LinkedIn_LeadGen_AR_Interests\nID: 694901284 | DRAFT",
    ]
    for i in range(4):
        sticky(f"<strong>{labels[i]}</strong>\n\n{contents[i]}",
               x=sx[i], y=sticky_y, color=STICKY_COLORS[i], w=STICKY_W)

    # ── Screenshot ────────────────────────────────────────────────────────────
    img_path = SHOTS / "09_linkedin_campaign.png"
    if img_path.exists():
        upload_image(img_path, x=0, y=sticky_y + IMG_Y_OFF, w=IMG_W)
        print(f"  image uploaded: {img_path.name}")
    else:
        print(f"  [warn] missing screenshot — save it as: {img_path}")
        text("[ screenshot: LinkedIn_Invoice campaign + LinkedIn_LeadGen_AR_Interests ad set ]",
             x=0, y=sticky_y + IMG_Y_OFF, w=700, font=12, color="#94a3b8", align="center")

    # ── Link ──────────────────────────────────────────────────────────────────
    link = "https://www.linkedin.com/campaignmanager/accounts/506171805/campaigns"
    text(f'<a href="{link}">open LinkedIn Campaign Manager</a>',
         x=0, y=sticky_y + LINK_Y_OFF, w=600, font=13, color="#2563eb", align="center")

    print(f"\n[miro] Use Case 9 added at y={y_top}")
    print(f"       https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
