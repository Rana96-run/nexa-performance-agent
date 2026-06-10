"""
Create the BI Tool Comparison table on the existing Miro board.

Adds a new frame at the right of the board — does NOT delete existing content.

Run:
    railway run python scripts/_bi_comparison_miro.py
"""
from __future__ import annotations
import os, time, requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD = os.getenv("MIRO_BOARD_ID")
H     = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE  = f"https://api.miro.com/v2/boards/{BOARD}"

# ── colours ──────────────────────────────────────────────────────────────────
C_NAVY    = "#1E5FA4"
C_CAT     = "#E8ECF2"
C_GREEN   = "#D9F2E0"
C_RED     = "#FCE0E0"
C_AMBER   = "#FEF3CC"
C_WHITE   = "#FFFFFF"
C_GREY    = "#F8F9FA"
C_TXT     = "#0F172A"
C_SUBTXT  = "#64748B"

YES  = "✓"
NO   = "✗"
PART = "⚠ partial"
VER  = "⚠ verify"

ROWS = [
    # (category, feature, databox, hex, funnel)
    ("DATA & CONNECTORS", "", "", "", ""),
    ("", "Native ad platform connectors (Meta / Google / Snap / TikTok / LinkedIn / Microsoft)", YES, NO, YES),
    ("", "HubSpot Contact connector", YES, YES, YES),
    ("", "HubSpot Deals connector", YES, YES, YES),
    ("", "HubSpot Lead Module (object 0-136)", VER, YES, VER),
    ("", "BigQuery — raw SQL support", YES, YES, YES),
    ("", "Zero connector maintenance effort", YES, NO, YES),
    ("", "Cross-channel blended CPL / CPQL", PART, YES, YES),
    ("", "Data refresh frequency", "15 min–24 h", "On-demand + 6 h", "6 h"),
    ("", "Historical backfill", PART, YES, YES),
    ("", "Custom dimension definitions via code", NO, YES, NO),
    ("", "USD normalization across all channels", PART, YES, YES),
    ("", "UTC → Asia/Riyadh timezone handling", PART, YES, PART),

    ("VISUALIZATION", "", "", "", ""),
    ("", "Drag-and-drop dashboard builder", YES, NO, YES),
    ("", "Chart types (line / bar / donut / table / funnel)", YES, YES, YES),
    ("", "Mobile-friendly view / native app", YES, NO, PART),
    ("", "Real-time auto-refresh while viewing", YES, PART, NO),
    ("", "Branded dashboard (logo / custom colors)", YES, YES, PART),
    ("", "Period-over-period delta tiles", YES, YES, YES),

    ("ANALYSIS & SQL", "", "", "", ""),
    ("", "Raw SQL query support", YES, YES, PART),
    ("", "Python / Pandas cells", NO, YES, NO),
    ("", "Formula / calculated metrics", YES, YES, PART),
    ("", "Ad-level / adset-level drill-down", YES, YES, YES),
    ("", "Disqualification reason breakdown", NO, YES, NO),
    ("", "CPQL from Lead Module (true qualified count)", VER, YES, VER),
    ("", "Version control on metric definitions", NO, YES, NO),

    ("OPS & AUTOMATION", "", "", "", ""),
    ("", "Metric-based alerts (email / Slack)", YES, PART, YES),
    ("", "Writeback to ad platforms (pause / scale / keywords)", NO, YES, NO),
    ("", "Scheduled report delivery", YES, YES, YES),
    ("", "Programmatic / API access for agent reads", NO, YES, PART),
    ("", "Connector maintenance (API version updates)", YES, NO, YES),

    ("SHARING & ACCESS", "", "", "", ""),
    ("", "Public shareable link (no login required)", YES, YES, YES),
    ("", "Embed in other tools (iframe)", YES, PART, YES),
    ("", "Mobile native app", YES, NO, NO),

    ("PRICING", "", "", "", ""),
    ("", "Free tier available", NO, YES, PART),
    ("", "Approximate monthly cost", "~$59–$199", "~$24/user", "Funnel $1k–$3k+"),
    ("", "Cost scales with data volume", NO, PART, YES),

    ("DECISION", "", "", "", ""),
    ("", "Verdict — what we keep", "PRIMARY ✓", "INTERNAL OPTIMIZATION ✓", "DROPPED ✗"),
]

# ── geometry ─────────────────────────────────────────────────────────────────
COL_WIDTHS   = [420, 140, 140, 200]   # Feature | Databox | Hex | Funnel
ROW_H        = 52
FRAME_X      = 3400   # placed to the right of existing diagrams
FRAME_Y      = 0
FRAME_PAD    = 60
TABLE_W      = sum(COL_WIDTHS)
TABLE_H      = len(ROWS) * ROW_H
FRAME_W      = TABLE_W + FRAME_PAD * 2
FRAME_H      = TABLE_H + FRAME_PAD * 2 + 100  # +100 for title


# ── helpers ───────────────────────────────────────────────────────────────────

def _post(path, payload, retries=3):
    for attempt in range(retries):
        r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=20)
        if r.status_code == 429:
            time.sleep(2 + attempt)
            continue
        if not r.ok:
            print(f"  WARN {path}: {r.status_code} — {r.text[:120]}")
            return None
        return r.json()
    return None


def _frame(title, x, y, w, h):
    return _post("/frames", {
        "data":     {"title": title, "format": "custom"},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
        "style":    {"fillColor": "#F0F4F8"},
    })


def _cell(text, x, y, w, h, fill=C_WHITE, border="#D0D5DD",
          font_size=12, bold=False, font_color=C_TXT, align="center"):
    _post("/shapes", {
        "data": {"content": f"<b>{text}</b>" if bold else str(text),
                 "shape": "rectangle"},
        "style": {
            "fillColor":   fill,
            "borderColor": border,
            "borderWidth": "1",
            "fontFamily":  "open_sans",
            "fontSize":    str(font_size),
            "color":       font_color,
            "textAlign":   align,
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def status_fill(val):
    s = str(val)
    if s in (YES, "PRIMARY ✓", "INTERNAL OPTIMIZATION ✓"):
        return C_GREEN
    if s in (NO, "DROPPED ✗"):
        return C_RED
    if s.startswith("⚠"):
        return C_AMBER
    return None


def _make_board():
    r = requests.post(
        "https://api.miro.com/v2/boards",
        headers=H,
        json={
            "name": "BI Tool Comparison — Databox vs Hex vs Funnel (2026-06-10)",
            "description": "Qoyod Performance Agent — auto-generated",
            "policy": {
                "permissionsPolicy": {"collaborationToolsStartAccess": "all_editors"},
                "sharingPolicy": {"access": "private", "teamAccess": "edit"},
            },
        },
        timeout=15,
    )
    if not r.ok:
        print(f"[miro] board create failed: {r.status_code} {r.text[:200]}")
        return None, None
    d = r.json()
    return d["id"], d.get("viewLink", "")


def build():
    if not TOKEN:
        print("[miro] MIRO_ACCESS_TOKEN not set — aborting")
        return

    board_id, view_link = _make_board()
    if not board_id:
        return

    global BASE
    BASE = f"https://api.miro.com/v2/boards/{board_id}"

    # ── frame ─────────────────────────────────────────────────────────────────
    print(f"[miro] drawing on board {board_id}")
    _frame(
        "BI Tool Comparison — Databox vs Hex vs Funnel (2026-06-10)",
        FRAME_X, FRAME_Y, FRAME_W, FRAME_H
    )
    time.sleep(0.5)

    # origin of the table top-left
    tl_x = FRAME_X - TABLE_W / 2
    tl_y = FRAME_Y - FRAME_H / 2 + FRAME_PAD + 70  # skip title area

    # ── column headers ────────────────────────────────────────────────────────
    headers = ["Feature / Capability", "Databox", "Hex", "Funnel + Data Studio"]
    cx = tl_x
    for i, (hdr, cw) in enumerate(zip(headers, COL_WIDTHS)):
        _cell(hdr, cx + cw / 2, tl_y + ROW_H / 2,
              cw, ROW_H, fill=C_NAVY, border=C_NAVY,
              font_size=13, bold=True, font_color="#FFFFFF",
              align="center")
        cx += cw
    time.sleep(0.3)

    # ── data rows ─────────────────────────────────────────────────────────────
    row_num = 0
    data_row = 0

    for r in ROWS:
        cat, feature, db, hx, fn = r
        row_y = tl_y + (row_num + 1) * ROW_H + ROW_H / 2

        if cat:
            # section header spanning full width
            _cell(cat, tl_x + TABLE_W / 2, row_y,
                  TABLE_W, ROW_H, fill=C_CAT, border="#B8C4D4",
                  font_size=12, bold=True, font_color="#2C3E6B", align="left")
        else:
            data_row += 1
            row_bg = C_WHITE if data_row % 2 else C_GREY

            # col A: feature name
            _cell(feature, tl_x + COL_WIDTHS[0] / 2, row_y,
                  COL_WIDTHS[0], ROW_H, fill=row_bg, border="#E2E8F0",
                  font_size=11, font_color=C_TXT, align="left")

            # cols B/C/D: status
            vals  = [db, hx, fn]
            x_off = tl_x + COL_WIDTHS[0]
            for val, cw in zip(vals, COL_WIDTHS[1:]):
                sf = status_fill(val)
                _cell(val, x_off + cw / 2, row_y,
                      cw, ROW_H,
                      fill=sf or row_bg,
                      border="#E2E8F0",
                      font_size=12,
                      bold=bool(sf),
                      font_color=C_TXT,
                      align="center")
                x_off += cw

        row_num += 1

        # small sleep every 10 rows to avoid rate-limit
        if row_num % 10 == 0:
            time.sleep(0.5)

    # ── title text above table ─────────────────────────────────────────────────
    title_y = FRAME_Y - FRAME_H / 2 + FRAME_PAD + 25
    _post("/texts", {
        "data":     {"content": "<b>BI Tool Comparison — Databox vs Hex vs Funnel + Data Studio</b>"},
        "style":    {"fontSize": "22", "color": C_TXT, "textAlign": "center"},
        "position": {"x": FRAME_X, "y": title_y, "origin": "center"},
        "geometry": {"width": TABLE_W},
    })
    _post("/texts", {
        "data":     {"content": f"Qoyod Performance Agent · {FRAME_X and '2026-06-10'}  ·  Green = ✓  ·  Red = ✗  ·  Amber = ⚠ partial / needs verification"},
        "style":    {"fontSize": "13", "color": C_SUBTXT, "textAlign": "center"},
        "position": {"x": FRAME_X, "y": title_y + 30, "origin": "center"},
        "geometry": {"width": TABLE_W},
    })

    print(f"[miro] Done! Board: {view_link}")
    print(f"[miro] {row_num} rows drawn ({data_row} data rows + section headers)")


if __name__ == "__main__":
    build()
