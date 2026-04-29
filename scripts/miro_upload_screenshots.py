"""
Upload the rendered screenshot PNGs to the Miro board, replacing the dark
text mock-ups with real visuals.

Strategy:
  1. Delete only the dark output_box shapes (fill #1e293b) below the main flow
  2. Upload each PNG via multipart and place it next to the matching header card
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD = os.getenv("MIRO_BOARD_ID")
H_AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = f"https://api.miro.com/v2/boards/{BOARD}"

SHOTS = Path(__file__).parent / "_screenshots"


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


def _delete_dark_outputs():
    """The dark mock-up shapes use fillColor #1e293b — delete only those."""
    deleted = 0
    for s in _get_all("shapes"):
        fill = (s.get("style") or {}).get("fillColor", "").lower()
        if fill == "#1e293b":
            requests.delete(f"{BASE}/shapes/{s['id']}", headers=H_AUTH, timeout=10)
            deleted += 1
    print(f"[miro] deleted {deleted} dark mock-up shape(s)")


def _upload_image(path: Path, x: int, y: int, w: int) -> str | None:
    """Upload PNG via multipart. Returns image_id."""
    url = f"{BASE}/images"
    with open(path, "rb") as f:
        files = {
            "resource": (path.name, f, "image/png"),
            # data is a JSON string — Miro multipart pattern
            "data": (None,
                     '{"position":{"x":' + str(x) + ',"y":' + str(y) + '},'
                     '"geometry":{"width":' + str(w) + '}}',
                     "application/json"),
        }
        r = requests.post(url, headers=H_AUTH, files=files, timeout=60)
    if not r.ok:
        print(f"  upload FAIL {path.name}: {r.status_code} {r.text[:160]}")
        return None
    img_id = r.json().get("id")
    print(f"  uploaded {path.name} -> {img_id}")
    return img_id


def main():
    _delete_dark_outputs()

    # Same layout as miro_use_cases.py — 4 columns, x positions: -1080, -720, -360, 0
    col_xs = [-1080, -720, -360, 0]
    ROW_OUT_Y_BASE = 1240
    ROW_GAP = 380
    IMG_W = 320

    # Map use cases -> file (in order matching miro_use_cases.py grid).
    # Use cases that have screenshots replace those slots; others keep text mocks.
    # The 15 cards in miro_use_cases.py are indexed 0..14:
    #   0: Daily HTML Dashboard      -> 07_dashboard
    #   1: Spike Detection           -> (no screenshot — keep text)
    #   2: Keyword Waste             -> (no screenshot)
    #   3: Impression-Share Audit    -> (no screenshot)
    #   4: Quality-Score Audit       -> (no screenshot)
    #   5: Search-Terms              -> (no screenshot)
    #   6: Channel Attribution       -> (no screenshot)
    #   7: Health Check              -> (no screenshot)
    #   8: HubSpot Lists             -> 04_hubspot_list
    #   9: Asana Tasks               -> 03_asana_task
    #  10: LinkedIn Paused Campaign  -> 05_linkedin_campaign
    #  11: Meta Paused Campaign      -> 06_meta_campaign
    #  12: Daily Slack Summary       -> 01_slack_daily
    #  13: Approval Request          -> 02_slack_approval
    #  14: Auto-Fix Zapier           -> (no screenshot — could add later)
    # Email screenshot (08) is NOT in use_cases — let's add it as a 16th card.
    placements = {
        0:  "07_dashboard.png",
        8:  "04_hubspot_list.png",
        9:  "03_asana_task.png",
        10: "05_linkedin_campaign.png",
        11: "06_meta_campaign.png",
        12: "01_slack_daily.png",
        13: "02_slack_approval.png",
    }

    for idx, fname in placements.items():
        p = SHOTS / fname
        if not p.exists():
            print(f"  MISSING file: {p}")
            continue
        col = idx % 4
        row = idx // 4
        x = col_xs[col]
        y = ROW_OUT_Y_BASE + row * ROW_GAP
        _upload_image(p, x, y, IMG_W)

    # Add email screenshot below the grid as a bonus card
    email = SHOTS / "08_email.png"
    if email.exists():
        # Place it just below the 4th row of the grid (16th cell area)
        _upload_image(email, x=360, y=ROW_OUT_Y_BASE + 3 * ROW_GAP, w=IMG_W)

    print("[miro] all uploads finished")
    print(f"      https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    main()
