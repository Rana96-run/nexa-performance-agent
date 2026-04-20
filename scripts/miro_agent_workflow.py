"""
Creates a clean Miro workflow for the Qoyod Performance Agent.
Wipes previous shapes/connectors/texts on the board, then rebuilds with
edge-snapped connectors so lines never cross node text.

Run:
    python scripts/miro_agent_workflow.py
"""
import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD_ID = os.getenv("MIRO_BOARD_ID")
if not TOKEN or not BOARD_ID:
    sys.exit("Missing MIRO_ACCESS_TOKEN or MIRO_BOARD_ID")

BASE = f"https://api.miro.com/v2/boards/{BOARD_ID}"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

W, H = 240, 120
COL = 340   # horizontal spacing (> W so arrows travel in empty space)
ROW = 220   # vertical spacing

# id -> (title, subtitle, col, row, shape, fill)
NODES = {
    "sched":    ("1. Scheduler",       "08:00 Riyadh daily",                    0,  0, "round_rectangle", "#1a73e8"),
    "collect":  ("2. Collect Data",    "Google Ads | Meta | HubSpot",           1,  0, "round_rectangle", "#34a853"),
    "claude":   ("3. Claude Analyst",  "4 MD prompts -> Decision JSON",         2,  0, "round_rectangle", "#ab47bc"),
    "asana":    ("4. Asana Task",      "Always create (no approval)",           3, -1, "round_rectangle", "#fbbc04"),
    "decide":   ("5. Channel Action?", "pause / exclude / adjust / scale",      3,  1, "rhombus",         "#fb8c00"),
    "summary":  ("6a. Slack Summary",  "Recommendation posted, no exec",        4, -1, "round_rectangle", "#9e9e9e"),
    "approval": ("6b. Slack Approval", "React check or X (60 min)",             4,  1, "round_rectangle", "#ef5350"),
    "execute":  ("7. Execute",         "Google Ads / Meta pause",               5,  1, "round_rectangle", "#d32f2f"),
    "done":     ("8. Done",            "Log + next day",                        6,  0, "circle",          "#4caf50"),
}

# (from, from_side, to, to_side, caption)
#   sides: "right","left","top","bottom"
EDGES = [
    ("sched",    "right",  "collect",  "left",   None),
    ("collect",  "right",  "claude",   "left",   None),
    ("claude",   "right",  "asana",    "left",   None),
    ("claude",   "right",  "decide",   "left",   None),
    ("asana",    "right",  "summary",  "left",   None),
    ("decide",   "top",    "summary",  "bottom", "No"),
    ("decide",   "right",  "approval", "left",   "Yes"),
    ("approval", "right",  "execute",  "left",   "Approved"),
    ("summary",  "right",  "done",     "left",   None),
    ("execute",  "right",  "done",     "left",   None),
]

SIDE = {
    "right":  {"x": 1.0, "y": 0.5},
    "left":   {"x": 0.0, "y": 0.5},
    "top":    {"x": 0.5, "y": 0.0},
    "bottom": {"x": 0.5, "y": 1.0},
}


def wipe_board():
    """Delete all shapes, connectors, and texts we previously created."""
    for kind in ("connectors", "shapes", "texts"):
        cursor = None
        while True:
            url = f"{BASE}/{kind}?limit=50" + (f"&cursor={cursor}" if cursor else "")
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                break
            r.raise_for_status()
            payload = r.json()
            for item in payload.get("data", []):
                item_id = item["id"]
                requests.delete(f"{BASE}/{kind}/{item_id}", headers=HEADERS, timeout=30)
                time.sleep(0.1)
            cursor = payload.get("cursor")
            if not cursor:
                break
        print(f"  cleared {kind}")


def place(col, row):
    return {"x": col * COL, "y": row * ROW}


def create_shape(node):
    title, subtitle, col, row, shape, fill = node
    body = {
        "data": {
            "shape": shape,
            "content": f"<p><strong>{title}</strong></p><p>{subtitle}</p>",
        },
        "style": {
            "fillColor": fill,
            "color": "#ffffff",
            "textAlign": "center",
            "textAlignVertical": "middle",
            "fontSize": "14",
        },
        "position": place(col, row),
        "geometry": {"width": W, "height": H},
    }
    r = requests.post(f"{BASE}/shapes", headers=HEADERS, json=body, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def create_connector(start_id, start_side, end_id, end_side, caption=None):
    body = {
        "startItem": {"id": start_id, "position": _pct(SIDE[start_side])},
        "endItem":   {"id": end_id,   "position": _pct(SIDE[end_side])},
        "style": {"strokeColor": "#333333", "strokeWidth": "2", "endStrokeCap": "arrow"},
        "shape": "elbowed",
    }
    if caption:
        body["captions"] = [{"content": caption, "position": "50%"}]
    r = requests.post(f"{BASE}/connectors", headers=HEADERS, json=body, timeout=30)
    r.raise_for_status()


def _pct(pt):
    return {"x": f"{pt['x']*100:.0f}%", "y": f"{pt['y']*100:.0f}%"}


def create_title():
    body = {
        "data": {"content": "<p><strong>Qoyod Performance Agent — Daily Workflow</strong></p>"},
        "style": {"fontSize": "36", "textAlign": "center", "color": "#1f2937"},
        "position": {"x": 3 * COL, "y": -2 * ROW},
        "geometry": {"width": 900},
    }
    requests.post(f"{BASE}/texts", headers=HEADERS, json=body, timeout=30).raise_for_status()


def main():
    print(f"Wiping board {BOARD_ID}...")
    wipe_board()

    print("Rebuilding workflow...")
    create_title()
    ids = {}
    for key, node in NODES.items():
        ids[key] = create_shape(node)
        print(f"  + {node[0]}")
        time.sleep(0.15)

    for src, src_side, dst, dst_side, caption in EDGES:
        create_connector(ids[src], src_side, ids[dst], dst_side, caption)
        time.sleep(0.15)

    print(f"\nDone. Open: https://miro.com/app/board/{BOARD_ID}/")


if __name__ == "__main__":
    main()
