"""
BI Tool Comparison — two versions on one Miro board.
Copies the most recent user-created board (to avoid "Developer team" watermark),
then draws two side-by-side comparison tables:
  1. Qoyod-specific (HubSpot Lead Module, CPQL, writeback, etc.)
  2. Generic SaaS (any B2B software business)

Run:
    railway run --service nexa-web python scripts/_bi_comparison_miro.py
"""
from __future__ import annotations
import os, time, requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
H     = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE  = ""   # set after board is found

# ── colours ───────────────────────────────────────────────────────────────────
C_NAVY   = "#1E3A5F"
C_NAVYTX = "#FFFFFF"
C_CAT    = "#EEF2FF"
C_CATTX  = "#1E3A5F"
C_GREEN  = "#D1FAE5"
C_GREENTX= "#065F46"
C_RED    = "#FEE2E2"
C_REDTX  = "#991B1B"
C_AMBER  = "#FEF3C7"
C_AMBERTX= "#92400E"
C_WHITE  = "#FFFFFF"
C_ROW    = "#F8FAFC"
C_BORDER = "#CBD5E1"
C_TXT    = "#1E293B"
C_SUBTXT = "#64748B"

YES  = "✓"
NO   = "✗"
PART = "⚠ partial"
VER  = "⚠ verify"

# ── TABLE 1 — Qoyod-specific ──────────────────────────────────────────────────
ROWS_QOYOD = [
    ("DATA & CONNECTORS", "", "", "", ""),
    ("", "Ad platform connectors\n(Meta / Google / Snap / TikTok / LinkedIn)", YES, NO, YES),
    ("", "HubSpot Lead Module (object 0-136)", VER, YES, VER),
    ("", "HubSpot Deals connector", YES, YES, YES),
    ("", "BigQuery — raw SQL", YES, YES, YES),
    ("", "Zero connector maintenance", YES, NO, YES),
    ("", "USD normalization across channels", PART, YES, YES),
    ("", "UTC → Asia/Riyadh timezone", PART, YES, PART),
    ("", "Data refresh frequency", "15 min–24 h", "On-demand+6 h", "6 h"),

    ("ANALYSIS — QOYOD KPIs", "", "", "", ""),
    ("", "CPQL from Lead Module (true qualified)", VER, YES, VER),
    ("", "Cross-channel blended CPL / CPQL", PART, YES, YES),
    ("", "Disqualification reason breakdown", NO, YES, NO),
    ("", "Ad / adset-level drill-down", YES, YES, YES),
    ("", "Raw SQL + Python in same workspace", NO, YES, NO),
    ("", "Version control on metric definitions", NO, YES, NO),

    ("VISUALIZATION", "", "", "", ""),
    ("", "Drag-and-drop dashboard builder", YES, NO, YES),
    ("", "Mobile-friendly / native app", YES, NO, PART),
    ("", "Real-time auto-refresh", YES, PART, NO),
    ("", "Branded (Qoyod navy + logo)", YES, YES, PART),
    ("", "Period-over-period delta tiles", YES, YES, YES),

    ("OPS & AUTOMATION", "", "", "", ""),
    ("", "Metric alerts (email / Slack)", YES, PART, YES),
    ("", "Writeback — pause / scale / keywords", NO, YES, NO),
    ("", "Scheduled report delivery", YES, YES, YES),
    ("", "API access for agent reads", NO, YES, PART),
    ("", "Connector maintenance ownership", "Databox", "We own it", "Funnel"),

    ("PRICING (current)", "", "", "", ""),
    ("", "Approximate monthly cost", "~$59–$199", "~$24/user", "$1k–$3k+"),
    ("", "Free tier available", NO, YES, PART),

    ("DECISION", "", "", "", ""),
    ("", "Verdict", "PRIMARY ✓", "INTERNAL\nOPTIMIZATION ✓", "DROPPED ✗"),
]

# ── TABLE 2 — Generic SaaS ────────────────────────────────────────────────────
ROWS_SAAS = [
    ("DATA & CONNECTORS", "", "", "", ""),
    ("", "Ad platform connectors (major channels)", YES, NO, YES),
    ("", "CRM connector (any — HubSpot/SF/Pipedrive)", YES, YES, YES),
    ("", "E-commerce / product analytics", YES, PART, YES),
    ("", "Data warehouse (BQ / Snowflake / Redshift)", YES, YES, YES),
    ("", "Zero connector maintenance", YES, NO, YES),
    ("", "Currency normalization", PART, YES, YES),
    ("", "Timezone control", PART, YES, PART),
    ("", "Data refresh frequency", "15 min–24 h", "On-demand+6 h", "6 h"),

    ("SAAS KPIs", "", "", "", ""),
    ("", "MRR / ARR tracking", YES, YES, YES),
    ("", "Churn rate & cohort retention", PART, YES, PART),
    ("", "CAC / LTV / Payback period", PART, YES, YES),
    ("", "Pipeline velocity & win rate", YES, YES, YES),
    ("", "Product funnel (trial → paid)", PART, YES, PART),
    ("", "Custom formula metrics", YES, YES, PART),

    ("VISUALIZATION", "", "", "", ""),
    ("", "No-code dashboard builder", YES, NO, YES),
    ("", "Mobile app / responsive view", YES, NO, PART),
    ("", "Real-time refresh", YES, PART, NO),
    ("", "White-label / branded dashboards", YES, YES, PART),
    ("", "Exec-ready shareable link", YES, YES, YES),

    ("OPS & AUTOMATION", "", "", "", ""),
    ("", "KPI alerts (email / Slack / Teams)", YES, PART, YES),
    ("", "Automated report delivery", YES, YES, YES),
    ("", "API / programmatic access", NO, YES, PART),
    ("", "Writeback to ad platforms", NO, YES, NO),
    ("", "Connector maintenance ownership", "Vendor", "You own it", "Vendor"),

    ("PRICING", "", "", "", ""),
    ("", "Approx monthly cost (small team)", "~$59–$199", "~$24/user", "$500–$3k+"),
    ("", "Scales with data volume", NO, PART, YES),
    ("", "Free tier", NO, YES, PART),

    ("DECISION", "", "", "", ""),
    ("", "Best for", "Fast team\ndashboards", "Analyst +\nautomation", "Multi-source\nblending"),
]

# ── geometry ──────────────────────────────────────────────────────────────────
COL_W   = [360, 150, 150, 190]   # Feature | Databox | Hex | Funnel
ROW_H   = 52
HDR_H   = 60
CAT_H   = 38
TITLE_H = 80
TABLE_W = sum(COL_W)
GAP     = 120   # horizontal gap between the two tables

# second table starts at TABLE_W + GAP
OFFSET2 = TABLE_W + GAP


# ── helpers ───────────────────────────────────────────────────────────────────

def _post(path, payload, retries=3):
    for attempt in range(retries):
        r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=20)
        if r.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if not r.ok:
            print(f"  WARN {path}: {r.status_code} — {r.text[:100]}")
            return None
        return r.json()
    return None


def _create_frame(title, x, y, w, h):
    """Create a Miro frame (slide) and return its id."""
    r = _post("/frames", {
        "data":     {"title": title, "format": "custom", "type": "freeform"},
        "style":    {"fillColor": "#FFFFFF"},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })
    return r["id"] if r else None


def _shape(text, x, y, w, h, fill, border_color, font_size, font_color,
           h_align="center", bold=False, border_w=1):
    content = f"<b>{text}</b>" if bold else str(text)
    style = {
        "fillColor":   fill,
        "borderColor": border_color,
        "fontFamily":  "open_sans",
        "fontSize":    str(font_size),
        "color":       font_color,
        "textAlign":   h_align,
    }
    if border_w > 0:
        style["borderWidth"] = str(border_w)
    _post("/shapes", {
        "data":     {"content": content, "shape": "rectangle"},
        "style":    style,
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def _text(content, x, y, w, font_size, color, align="center"):
    _post("/texts", {
        "data":     {"content": content},
        "style":    {"fontSize": str(font_size), "color": color,
                     "textAlign": align, "fontFamily": "open_sans"},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def status_style(val):
    s = str(val)
    if s in (YES, "PRIMARY ✓") or s.startswith("INTERNAL"):
        return C_GREEN, C_GREENTX
    if s in (NO, "DROPPED ✗"):
        return C_RED, C_REDTX
    if s.startswith("⚠"):
        return C_AMBER, C_AMBERTX
    return None, None


def _table_height(rows):
    """Calculate total pixel height of a table."""
    h = TITLE_H + HDR_H
    for rec in rows:
        h += CAT_H if rec[0] else ROW_H
    return h


def _draw_table(rows, x_offset, y_offset, title, subtitle):
    """Draw one full comparison table starting at (x_offset, y_offset)."""
    cx = x_offset + TABLE_W / 2
    TL_Y = y_offset + TITLE_H

    # title bar
    _shape("", cx, y_offset + TITLE_H / 2, TABLE_W, TITLE_H,
           fill=C_NAVY, border_color=C_NAVY,
           font_size=14, font_color=C_NAVYTX, border_w=0)
    _text(f"<b>{title}</b>", cx, y_offset + 22, TABLE_W, 22, "#FFFFFF")
    _text(subtitle, cx, y_offset + 58, TABLE_W, 13, "#93C5FD")
    time.sleep(0.2)

    # column headers
    col_labels = ["Feature / Capability", "Databox", "Hex", "Funnel + Data Studio"]
    cx_off = x_offset
    for label, cw in zip(col_labels, COL_W):
        _shape(label, cx_off + cw / 2, TL_Y + HDR_H / 2, cw, HDR_H,
               fill="#162D4A", border_color="#0F1E30",
               font_size=14, font_color="#FFFFFF", bold=True)
        cx_off += cw
    time.sleep(0.2)

    # data rows
    cur_y = TL_Y + HDR_H
    row_num = 0
    data_row = 0

    for rec in rows:
        cat, feature, db, hx, fn = rec

        if cat:
            _shape(f"  {cat}", x_offset + TABLE_W / 2, cur_y + CAT_H / 2,
                   TABLE_W, CAT_H,
                   fill=C_CAT, border_color="#C7D2E8",
                   font_size=12, font_color=C_CATTX, h_align="left", bold=True)
            cur_y += CAT_H
        else:
            data_row += 1
            row_bg = C_WHITE if data_row % 2 else C_ROW

            _shape(f"  {feature}", x_offset + COL_W[0] / 2, cur_y + ROW_H / 2,
                   COL_W[0], ROW_H,
                   fill=row_bg, border_color=C_BORDER,
                   font_size=12, font_color=C_TXT, h_align="left")

            x_off = x_offset + COL_W[0]
            for val, cw in zip([db, hx, fn], COL_W[1:]):
                sf, stx = status_style(val)
                _shape(val, x_off + cw / 2, cur_y + ROW_H / 2, cw, ROW_H,
                       fill=sf or row_bg, border_color=C_BORDER,
                       font_size=12, font_color=stx or C_TXT,
                       bold=bool(sf))
                x_off += cw

            cur_y += ROW_H

        row_num += 1
        if row_num % 10 == 0:
            time.sleep(0.3)

    return row_num, data_row


def _get_existing_board():
    """Return the ID of the most recent user-created board (not this script's boards)."""
    r = requests.get(
        "https://api.miro.com/v2/boards?team_id=3074457345976989160"
        "&sort=last_modified&limit=20",
        headers=H, timeout=15
    )
    script_names = {
        "BI Tool Comparison — Databox vs Hex vs Funnel",
        "agent-write-test-DELETE-ME",
    }
    for b in r.json().get("data", []):
        if b["name"] not in script_names and "BI Tool Comparison" not in b["name"]:
            return b["id"], b["name"]
    return None, None


BOARD_ID = "uXjVHHXnHHM="   # existing board in Qoyod team


def build():
    if not TOKEN:
        print("[miro] MIRO_ACCESS_TOKEN not set — aborting")
        return

    global BASE
    BASE = f"https://api.miro.com/v2/boards/{BOARD_ID}"
    view_link = f"https://miro.com/app/board/{BOARD_ID}"
    print(f"[miro] using existing board: {view_link}")

    # Clear any existing content from the copied board
    deleted = 0
    for kind in ("shapes", "sticky_notes", "texts", "frames", "images", "cards"):
        cursor = None
        while True:
            url = f"{BASE}/{kind}?limit=50"
            if cursor:
                url += f"&cursor={cursor}"
            gr = requests.get(url, headers=H, timeout=15)
            if not gr.ok:
                break
            d = gr.json()
            for item in d.get("data", []):
                requests.delete(f"{BASE}/{kind}/{item['id']}", headers=H, timeout=10)
                deleted += 1
            cursor = d.get("cursor")
            if not cursor:
                break
    if deleted:
        print(f"[miro] cleared {deleted} existing items")
        time.sleep(1)

    FRAME_PAD = 40   # padding inside each frame
    h1 = _table_height(ROWS_QOYOD)
    h2 = _table_height(ROWS_SAAS)
    frame_h = max(h1, h2) + FRAME_PAD * 2
    frame_w = TABLE_W + FRAME_PAD * 2

    # Slide 1 — Qoyod
    f1_x = frame_w / 2
    f1_y = frame_h / 2
    _create_frame("BI Tool Comparison — Qoyod Performance", f1_x, f1_y, frame_w, frame_h)
    print("[miro] Frame 1 created")
    time.sleep(0.3)

    r1, d1 = _draw_table(
        ROWS_QOYOD, FRAME_PAD, FRAME_PAD,
        "BI Tool Comparison — Qoyod Performance",
        "Qoyod-specific  ·  CPQL / Lead Module / Writeback / Attribution  ·  2026-06-10",
    )
    print(f"[miro] Table 1 done: {r1} rows")
    time.sleep(0.5)

    # Slide 2 — Generic SaaS (offset to the right)
    f2_x = frame_w + GAP + frame_w / 2
    f2_y = frame_h / 2
    _create_frame("BI Tool Comparison — Generic SaaS", f2_x, f2_y, frame_w, frame_h)
    print("[miro] Frame 2 created")
    time.sleep(0.3)

    r2, d2 = _draw_table(
        ROWS_SAAS, frame_w + GAP + FRAME_PAD, FRAME_PAD,
        "BI Tool Comparison — Generic SaaS Business",
        "Applies to any B2B SaaS  ·  MRR / CAC / LTV / Churn / Pipeline  ·  2026-06-10",
    )
    print(f"[miro] Table 2 done: {r2} rows")

    print(f"\n[miro] Done! Board: {view_link}")


if __name__ == "__main__":
    build()
