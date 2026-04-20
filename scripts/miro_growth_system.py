"""
Creates a new Miro board for the Qoyod Performance Agent styled like the
'Growth Marketing System' reference board (uXjVGk7YbXE=):
  - Columns: Tools (via MCP) | Execution | Roles
  - One lavender frame per sub-agent
  - Orange automation chips, blue tool chips, green role boxes
"""
import os
import sys
import time
import requests
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("Missing MIRO_ACCESS_TOKEN")

HEADERS = {"Authorization": f"Bearer {TOKEN}",
           "Accept": "application/json",
           "Content-Type": "application/json"}

# ---- Palette copied from reference board ----
FRAME_FILL   = "#f8f7ff"
AUTOMATION   = "#fe9f4d"      # orange
TOOL_BLUE    = "#c6dcff"
ROLE_GREEN   = "#067429"
PURPLE       = "#8f7fee"
RED          = "#ff6464"
YELLOW       = "#ffdc4a"
GRAY         = "#e7e7e7"
BG_TEXT      = "#1a1a1a"

BORDER = {
    "borderColor": BG_TEXT, "borderOpacity": "1.0",
    "borderStyle": "normal", "borderWidth": "2.0",
    "fontFamily": "noto_sans",
}


def style(fill, color=BG_TEXT, size="24", align="center", dashed=False, opacity="0.7"):
    s = dict(BORDER, fillColor=fill, fillOpacity=opacity, color=color,
             fontSize=size, textAlign=align, textAlignVertical="middle")
    if dashed:
        s["borderStyle"] = "dashed"
    return s


def text_style(size="24", align="left"):
    return {"fillColor": "#ffffff", "fillOpacity": "0.0",
            "fontFamily": "noto_sans", "fontSize": size,
            "textAlign": align, "color": BG_TEXT}


# ---- API helpers ----
API_BOARDS = "https://api.miro.com/v2/boards"


def create_board():
    # Reuse existing or create new
    existing = os.getenv("MIRO_SYSTEM_BOARD_ID")
    if existing:
        return existing
    body = {"name": "Qoyod Performance Agent - System",
            "description": "Daily performance marketing agent: data -> Claude -> Slack approval -> execute"}
    r = requests.post(API_BOARDS, headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("ERR", r.status_code, r.text[:400])
        r.raise_for_status()
    return r.json()["id"]


def mk_shape(board, shape, content, x, y, w, h, st, parent=None):
    body = {
        "data": {"shape": shape, "content": content},
        "style": st,
        "position": {"x": x, "y": y},
        "geometry": {"width": w, "height": h},
    }
    # parent deliberately omitted - use absolute positions
    r = requests.post(f"{API_BOARDS}/{board}/shapes", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("ERR", r.status_code, r.text[:400])
        r.raise_for_status()
    return r.json()["id"]


def mk_text(board, content, x, y, w, st, parent=None):
    body = {
        "data": {"content": content},
        "style": st,
        "position": {"x": x, "y": y},
        "geometry": {"width": w},
    }
    # parent deliberately omitted - use absolute positions
    r = requests.post(f"{API_BOARDS}/{board}/texts", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("ERR", r.status_code, r.text[:400])
        r.raise_for_status()
    return r.json()["id"]


def mk_frame(board, title, x, y, w, h):
    body = {
        "data": {"format": "custom", "title": title, "type": "freeform", "showContent": True},
        "style": {"fillColor": FRAME_FILL},
        "position": {"x": x, "y": y},
        "geometry": {"width": w, "height": h},
    }
    r = requests.post(f"{API_BOARDS}/{board}/frames", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("ERR", r.status_code, r.text[:400])
        r.raise_for_status()
    return r.json()["id"]


def mk_connector(board, a, b, caption=None):
    body = {
        "startItem": {"id": a, "position": {"x": "100%", "y": "50%"}},
        "endItem":   {"id": b, "position": {"x": "0%",   "y": "50%"}},
        "style": {"strokeColor": BG_TEXT, "strokeWidth": "2", "endStrokeCap": "arrow"},
        "shape": "elbowed",
    }
    if caption:
        body["captions"] = [{"content": caption, "position": "50%"}]
    requests.post(f"{API_BOARDS}/{board}/connectors", headers=HEADERS, json=body, timeout=30).raise_for_status()


# ---- Layout ----
FRAME_W = 6000
ROW_H   = 2200
COL_GAP = 400

# x positions of columns inside each frame
COL_TOOLS = -2200
COL_EXEC  = 0
COL_ROLE  = 2200

# Roles (rows). Each has its tools, execution steps, role green box.
ROLES = [
    {
        "title": "🤖 Orchestrator",
        "tools": ["🔌 Asana", "🔌 Slack", "🔌 BigQuery"],
        "exec":  ["⚡ Daily 08:00 Riyadh trigger",
                  "Route data to sub-agents",
                  "Aggregate decisions",
                  "Post summary to Slack"],
        "role":  ("Orchestrator", "qoyod-manager-os.md"),
    },
    {
        "title": "🤖 Paid Media Analyst",
        "tools": ["🔌 Google Ads", "🔌 Meta Ads", "🔌 Snapchat",
                  "🔌 TikTok", "🔌 LinkedIn", "🔌 Bing Ads", "🔌 YouTube"],
        "exec":  ["Pull 4-day KPIs per channel",
                  "Compare vs CPL/CPQL thresholds",
                  "Propose pause / scale / adjust",
                  "Flag creative fatigue"],
        "role":  ("Paid Media Analyst", "qoyod-paid-media-agent.md"),
    },
    {
        "title": "🤖 HubSpot CRO Analyst",
        "tools": ["🔌 HubSpot", "🔌 BigQuery", "🔌 SEMrush"],
        "exec":  ["Pull Contact-module SQLs",
                  "Compute CPQL per channel",
                  "Detect funnel drop-offs",
                  "Recommend CRO experiments"],
        "role":  ("HubSpot CRO", "qoyod-hubspot-cro-agent.md"),
    },
    {
        "title": "🤖 Task Flow",
        "tools": ["🔌 Asana", "🔌 Slack", "🔌 Email"],
        "exec":  ["Create Asana task (always)",
                  "Post Slack (summary or approval)",
                  "Wait 60min for ✅ / ❌",
                  "Execute approved channel action"],
        "role":  ("Task Flow", "qoyod-task-flow.md"),
    },
    {
        "title": "🤖 Creative Specialist",
        "tools": ["🔌 Canva", "🔌 Meta Ads", "🔌 Google Ads"],
        "exec":  ["Detect ad fatigue (CTR drop)",
                  "Draft new creative brief",
                  "Generate variants via Canva",
                  "Hand-off to approval"],
        "role":  ("Creative Specialist", "qoyod-brand-identity.md"),
    },
    {
        "title": "🤖 Reporter",
        "tools": ["🔌 Looker", "🔌 BigQuery", "🔌 Slack", "🔌 Email"],
        "exec":  ["⚡ Weekly digest (Mon 08:00)",
                  "⚡ Monthly executive report",
                  "Render Looker screenshots",
                  "Distribute to stakeholders"],
        "role":  ("Reporter", "qoyod-manager-os.md"),
    },
]


def build_row(board, row_idx, role):
    cy = row_idx * (ROW_H + 300)
    frame_id = mk_frame(board, role["title"],
                        x=0, y=cy, w=FRAME_W, h=ROW_H)
    # column headers
    mk_text(board, "<p><strong>Tools (via MCP)</strong></p>", COL_TOOLS, cy - ROW_H/2 + 120, 1500,
            text_style("28", "center"), parent=frame_id)
    mk_text(board, "<p><strong>Execution</strong></p>",       COL_EXEC,  cy - ROW_H/2 + 120, 1500,
            text_style("28", "center"), parent=frame_id)
    mk_text(board, "<p><strong>Role</strong></p>",            COL_ROLE,  cy - ROW_H/2 + 120, 1500,
            text_style("28", "center"), parent=frame_id)

    # tools (blue chips stacked)
    first_tool = None
    last_tool = None
    for i, t in enumerate(role["tools"]):
        ty = cy - ROW_H/2 + 320 + i * 140
        tid = mk_shape(board, "round_rectangle", f"<p>{t}</p>",
                       COL_TOOLS, ty, 1400, 110, style(TOOL_BLUE, size="22"), parent=frame_id)
        if first_tool is None:
            first_tool = tid
        last_tool = tid
        time.sleep(0.1)

    # execution (orange=automation if starts with lightning, else gray chain)
    prev = None
    first_exec = None
    last_exec = None
    for i, step in enumerate(role["exec"]):
        ey = cy - ROW_H/2 + 320 + i * 180
        is_auto = step.startswith("⚡")
        fill = AUTOMATION if is_auto else GRAY
        eid = mk_shape(board, "round_rectangle", f"<p>{step}</p>",
                       COL_EXEC, ey, 1700, 140, style(fill, size="22"), parent=frame_id)
        if first_exec is None:
            first_exec = eid
        last_exec = eid
        if prev is not None:
            body = {
                "startItem": {"id": prev, "position": {"x": "50%", "y": "100%"}},
                "endItem":   {"id": eid,  "position": {"x": "50%", "y": "0%"}},
                "style": {"strokeColor": BG_TEXT, "strokeWidth": "2", "endStrokeCap": "arrow"},
                "shape": "straight",
            }
            requests.post(f"{API_BOARDS}/{board}/connectors", headers=HEADERS, json=body, timeout=30).raise_for_status()
        prev = eid
        time.sleep(0.1)

    # role (green box)
    name, md = role["role"]
    role_id = mk_shape(board, "round_rectangle",
                      f"<p><strong>{name}</strong></p><p>{md}</p>",
                      COL_ROLE, cy, 1700, 260,
                      style(ROLE_GREEN, color="#ffffff", size="26"), parent=frame_id)

    # Cross-column arrows (tools -> first exec, last exec -> role)
    if last_tool and first_exec:
        body = {
            "startItem": {"id": last_tool, "position": {"x": "100%", "y": "50%"}},
            "endItem":   {"id": first_exec, "position": {"x": "0%",  "y": "50%"}},
            "style": {"strokeColor": BG_TEXT, "strokeWidth": "2", "endStrokeCap": "arrow"},
            "shape": "elbowed",
        }
        requests.post(f"{API_BOARDS}/{board}/connectors", headers=HEADERS, json=body, timeout=30).raise_for_status()
    if last_exec and role_id:
        body = {
            "startItem": {"id": last_exec, "position": {"x": "100%", "y": "50%"}},
            "endItem":   {"id": role_id,   "position": {"x": "0%",  "y": "50%"}},
            "style": {"strokeColor": BG_TEXT, "strokeWidth": "2", "endStrokeCap": "arrow"},
            "shape": "elbowed",
        }
        requests.post(f"{API_BOARDS}/{board}/connectors", headers=HEADERS, json=body, timeout=30).raise_for_status()


def main():
    print("Creating new Miro board...")
    board = create_board()
    print(f"  board id: {board}")

    # Main title above all frames
    mk_text(board, "<p><strong>Qoyod Performance Agent — System Map</strong></p>",
            x=0, y=-(ROW_H + 600), w=5000, st=text_style("64", "center"))

    for i, role in enumerate(ROLES):
        print(f"  building row {i+1}/{len(ROLES)}: {role['title']}")
        build_row(board, i, role)

    print(f"\nDone. Open: https://miro.com/app/board/{board}/")


if __name__ == "__main__":
    main()
