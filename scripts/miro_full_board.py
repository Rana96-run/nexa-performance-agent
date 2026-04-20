"""
Rebuilds the Qoyod Performance Agent board with two clean views:

  VIEW 1  — System Map (centralized orchestrator)
  VIEW 2  — Role Frames (one frame per specialist, lavender)

Wipes the board first so layout is predictable.
"""
import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv(Path(__file__).parent.parent / ".env")
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD = os.getenv("MIRO_BOARD_ID")
if not TOKEN or not BOARD:
    sys.exit("Missing MIRO_ACCESS_TOKEN or MIRO_BOARD_ID")

HEADERS = {"Authorization": f"Bearer {TOKEN}",
           "Accept": "application/json",
           "Content-Type": "application/json"}
BASE = f"https://api.miro.com/v2/boards/{BOARD}"

# Palette (matches reference board)
FRAME_FILL  = "#f8f7ff"
ORANGE      = "#fe9f4d"
PEACH       = "#f8d3af"
TOOL_BLUE   = "#c6dcff"
ROLE_GREEN  = "#067429"
PURPLE      = "#8f7fee"
LAVENDER    = "#dedaff"
RED         = "#ff6464"
YELLOW      = "#ffdc4a"
GRAY        = "#e7e7e7"
CREAM       = "#fff3c4"
ORCH_BLUE   = "#659df2"
INK         = "#1a1a1a"


def sh_style(fill, color=INK, size="32", align="center", opacity="0.85"):
    return {"borderColor": INK, "borderOpacity": "1.0",
            "borderStyle": "normal", "borderWidth": "2.0",
            "fontFamily": "noto_sans", "fillColor": fill,
            "fillOpacity": opacity, "color": color,
            "fontSize": size, "textAlign": align, "textAlignVertical": "middle"}


def tx_style(size="36", align="center"):
    return {"fillColor": "#ffffff", "fillOpacity": "0.0",
            "fontFamily": "noto_sans", "fontSize": size,
            "textAlign": align, "color": INK}


def post(path, body):
    r = requests.post(f"{BASE}/{path}", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("ERR", path, r.status_code, r.text[:300])
        r.raise_for_status()
    return r.json()


def mk_shape(shape, content, x, y, w, h, st):
    return post("shapes", {"data": {"shape": shape, "content": content},
                           "style": st, "position": {"x": x, "y": y},
                           "geometry": {"width": w, "height": h}})["id"]


def mk_text(content, x, y, w, st):
    return post("texts", {"data": {"content": content}, "style": st,
                          "position": {"x": x, "y": y}, "geometry": {"width": w}})["id"]


def mk_frame(title, x, y, w, h):
    return post("frames", {"data": {"format": "custom", "title": title,
                                    "type": "freeform", "showContent": True},
                           "style": {"fillColor": FRAME_FILL},
                           "position": {"x": x, "y": y},
                           "geometry": {"width": w, "height": h}})["id"]


def mk_line(a, b, a_side=("100%","50%"), b_side=("0%","50%"), caption=None, shape="elbowed"):
    body = {"startItem": {"id": a, "position": {"x": a_side[0], "y": a_side[1]}},
            "endItem":   {"id": b, "position": {"x": b_side[0], "y": b_side[1]}},
            "style": {"strokeColor": INK, "strokeWidth": "2", "endStrokeCap": "arrow"},
            "shape": shape}
    if caption:
        body["captions"] = [{"content": caption, "position": "50%"}]
    post("connectors", body)


def wipe():
    for kind in ("connectors", "shapes", "texts", "frames"):
        while True:
            r = requests.get(f"{BASE}/{kind}?limit=50", headers=HEADERS, timeout=30)
            if not r.ok:
                break
            items = r.json().get("data", [])
            if not items:
                break
            for it in items:
                requests.delete(f"{BASE}/{kind}/{it['id']}", headers=HEADERS, timeout=15)
        print(f"  wiped {kind}")


# =============================================================
# VIEW 1 — SYSTEM MAP (centralized orchestrator)
# =============================================================
TOOLS_SYS = [
    "🔌 Google Ads", "🔌 Meta", "🔌 Snapchat", "🔌 TikTok",
    "🔌 LinkedIn", "🔌 Bing", "🔌 YouTube", "🔌 HubSpot",
    "🔌 BigQuery", "🔌 Asana", "🔌 Slack", "🔌 Canva",
    "🔌 SEMrush", "🔌 Looker",
]
TRIGGERS_SYS = [
    ("⚡ On-Demand",          YELLOW),
    ("⚡ Daily Automation",   ORANGE),
    ("⚡ Weekly Automation",  ORANGE),
    ("⚡ Monthly Automation", ORANGE),
    ("⚡ Quarterly Automation", ORANGE),
]
ROLES_SYS = [
    ("🤖 Paid Media Specialist", ORANGE),
    ("🤖 HubSpot CRO",           RED),
    ("🤖 Creative Specialist",   LAVENDER),
    ("🤖 Reporter",              PEACH),
    ("🤖 Task Flow",             LAVENDER),
    ("🤖 Marketing Ops",         PURPLE),
]


def build_system_view(y0):
    # title
    mk_text("<p><strong>System Map — Qoyod Performance Agent</strong></p>",
            x=0, y=y0 - 400, w=4200, st=tx_style("88"))

    COL_T, COL_E, COL_R = -2400, 0, 2400
    # column headers
    mk_text("<p><strong>Tools (via MCP)</strong></p>", COL_T, y0 - 140, 1800, tx_style("46"))
    mk_text("<p><strong>Execution</strong></p>",       COL_E, y0 - 140, 1800, tx_style("46"))
    mk_text("<p><strong>Roles</strong></p>",           COL_R, y0 - 140, 1800, tx_style("46"))

    # Orchestrator at center
    orch_y = y0 + 900
    orch = mk_shape("round_rectangle",
                    "<p><strong>Orchestrator</strong></p><p>CLAUDE.manager.md</p>",
                    COL_E, orch_y, 900, 260, sh_style(ORCH_BLUE, size="40"))

    # Tools column (green)
    tool_ids = []
    for i, t in enumerate(TOOLS_SYS):
        ty = y0 + 40 + i * 130
        tid = mk_shape("round_rectangle", f"<p>{t}</p>", COL_T, ty, 1800, 110,
                       sh_style(ROLE_GREEN, color="#ffffff", size="34"))
        tool_ids.append(tid)
        time.sleep(0.06)

    # Execution triggers
    for i, (label, fill) in enumerate(TRIGGERS_SYS):
        ey = y0 + 40 + i * 170
        eid = mk_shape("round_rectangle", f"<p>{label}</p>", COL_E, ey, 1600, 140,
                       sh_style(fill, size="34"))
        mk_line(eid, orch, ("50%","100%"), ("50%","0%"), shape="straight")
        time.sleep(0.06)

    # Roles
    for i, (label, fill) in enumerate(ROLES_SYS):
        ry = y0 + 40 + i * 230
        rid = mk_shape("round_rectangle", f"<p>{label}</p>", COL_R, ry, 1800, 180,
                       sh_style(fill, size="34"))
        mk_line(orch, rid, ("100%","50%"), ("0%","50%"))
        time.sleep(0.06)

    if tool_ids:
        mk_line(tool_ids[len(tool_ids) // 2], orch)

    agent_y = y0 + 40 + max(len(TOOLS_SYS), len(ROLES_SYS) * 2) * 115 + 650
    mk_shape("round_rectangle",
             "<p><strong>== The Qoyod Performance Agent ==</strong></p><p>v.1</p>",
             COL_E, agent_y, 2400, 220, sh_style(ORCH_BLUE, size="42"))
    mk_shape("round_rectangle", "<p><strong>Skills</strong></p>",
             COL_E, agent_y + 340, 2400, 220, sh_style(GRAY, size="40"))
    return agent_y + 460  # bottom y of this view


# =============================================================
# VIEW 2 — ROLE FRAMES
# =============================================================
# (frame_title, tools[], execution[], role_name, md_file)
ROLE_FRAMES = [
    ("🤖 Paid Media Specialist",
     ["🔌 Google Ads","🔌 Meta","🔌 Snapchat","🔌 TikTok","🔌 LinkedIn","🔌 Bing","🔌 YouTube"],
     ["⚡ Daily KPI pull (4d)","Check CPL / CPQL thresholds","Propose pause / scale / adjust","Flag creative fatigue"],
     "Paid Media", "qoyod-paid-media-agent.md"),
    ("🤖 HubSpot CRO",
     ["🔌 HubSpot","🔌 BigQuery","🔌 SEMrush"],
     ["Pull Contact-module SQLs","Compute CPQL per channel","Detect funnel drop-offs","Recommend CRO experiments"],
     "HubSpot CRO", "qoyod-hubspot-cro-agent.md"),
    ("🤖 Creative Specialist",
     ["🔌 Canva","🔌 Meta","🔌 Google Ads"],
     ["Detect CTR decay / fatigue","Draft creative brief","Generate Canva variants","Hand-off to approval"],
     "Creative", "qoyod-creative-agent.md"),
    ("🤖 Reporter",
     ["🔌 Looker","🔌 BigQuery","🔌 Slack","🔌 Email"],
     ["⚡ Weekly digest (Mon)","⚡ Monthly executive report","⚡ Quarterly QoQ analysis","Distribute to stakeholders"],
     "Reporter", "qoyod-reporter-agent.md"),
    ("🤖 Task Flow",
     ["🔌 Asana","🔌 Slack","🔌 Email"],
     ["Always create Asana task","Route to notify vs approval channel","Wait 60min for ✅ / ❌","Execute approved action"],
     "Task Flow", "qoyod-task-flow.md"),
    ("🤖 Marketing Ops",
     ["🔌 BigQuery","🔌 Asana","🔌 Email"],
     ["⚡ On-demand data pulls","Portfolio / project hygiene","Env + secrets audit","Weekly ops digest"],
     "Marketing Ops", "qoyod-manager-os.md"),
]


def build_role_frame(x0, y0, frame_data):
    title, tools, execs, role_name, md = frame_data
    FW, FH = 5400, 4600
    mk_frame(title, x=x0 + FW/2, y=y0 + FH/2, w=FW, h=FH)

    COL_T = x0 + 950
    COL_E = x0 + 2700
    COL_R = x0 + 4450

    mk_text("<p><strong>Tools (via MCP)</strong></p>", COL_T, y0 + 220, 1500, tx_style("38"))
    mk_text("<p><strong>Execution</strong></p>",       COL_E, y0 + 220, 1500, tx_style("38"))
    mk_text("<p><strong>Role</strong></p>",            COL_R, y0 + 220, 1500, tx_style("38"))

    tool_ids = []
    for i, t in enumerate(tools):
        ty = y0 + 500 + i * 150
        tid = mk_shape("round_rectangle", f"<p>{t}</p>", COL_T, ty, 1500, 120,
                       sh_style(TOOL_BLUE, size="30"))
        tool_ids.append(tid)
        time.sleep(0.05)

    exec_ids = []
    for i, s in enumerate(execs):
        ey = y0 + 500 + i * 190
        fill = ORANGE if s.startswith("⚡") else GRAY
        eid = mk_shape("round_rectangle", f"<p>{s}</p>", COL_E, ey, 1600, 150,
                       sh_style(fill, size="30"))
        exec_ids.append(eid)
        if i > 0:
            mk_line(exec_ids[i-1], eid, ("50%","100%"), ("50%","0%"), shape="straight")
        time.sleep(0.05)

    role_id = mk_shape("round_rectangle",
                       f"<p><strong>{role_name}</strong></p><p>{md}</p>",
                       COL_R, y0 + FH/2, 1600, 280,
                       sh_style(ROLE_GREEN, color="#ffffff", size="34"))

    # cross-column arrows
    if tool_ids and exec_ids:
        mk_line(tool_ids[-1], exec_ids[0])
    if exec_ids and role_id:
        mk_line(exec_ids[-1], role_id)


def build_roles_view(y0):
    mk_text("<p><strong>Role Frames — Specialist Agents</strong></p>",
            x=0, y=y0 - 300, w=4600, st=tx_style("88"))
    FW, FH = 5400, 4600
    GAP_X, GAP_Y = 400, 400
    origin_x = -(FW + GAP_X) / 2
    origin_y = y0

    for idx, rf in enumerate(ROLE_FRAMES):
        col = idx % 2
        row = idx // 2
        x = origin_x + col * (FW + GAP_X)
        y = origin_y + row * (FH + GAP_Y)
        print(f"  frame: {rf[0]}")
        build_role_frame(x, y, rf)


def main():
    print(f"Wiping board {BOARD}...")
    wipe()

    print("\nBuilding VIEW 1 — System Map...")
    view1_bottom = build_system_view(y0=0)

    print("\nBuilding VIEW 2 — Role Frames...")
    # Start Role Frames just below the System Map (close, not 5000px away)
    build_roles_view(y0=view1_bottom + 600)

    print(f"\nDone. Open: https://miro.com/app/board/{BOARD}/")


if __name__ == "__main__":
    main()
