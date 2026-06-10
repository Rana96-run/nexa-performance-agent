"""
BI Tool Comparison table on Miro — Databox vs Hex vs Funnel + Data Studio.
Creates a fresh board in the Qoyod team and draws a clean, sharp table.

Run:
    railway run --service nexa-web python scripts/_bi_comparison_miro.py
"""
from __future__ import annotations
import os, time, requests
from dotenv import load_dotenv

load_dotenv()
TOKEN   = os.getenv("MIRO_ACCESS_TOKEN")
TEAM_ID = "3074457345976989160"   # Qoyod team
H       = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE    = ""   # set after board is created

# ── colours ───────────────────────────────────────────────────────────────────
C_NAVY   = "#1E3A5F"   # header bg
C_NAVYTX = "#FFFFFF"   # header text
C_CAT    = "#EEF2FF"   # section header bg
C_CATTX  = "#1E3A5F"   # section header text
C_GREEN  = "#D1FAE5"   # yes fill
C_GREENTX= "#065F46"   # yes text
C_RED    = "#FEE2E2"   # no fill
C_REDTX  = "#991B1B"   # no text
C_AMBER  = "#FEF3C7"   # partial fill
C_AMBERTX= "#92400E"   # partial text
C_WHITE  = "#FFFFFF"
C_ROW    = "#F8FAFC"   # alternating row
C_BORDER = "#CBD5E1"   # cell border
C_TXT    = "#1E293B"   # body text
C_SUBTXT = "#64748B"

YES  = "✓"
NO   = "✗"
PART = "⚠ partial"
VER  = "⚠ verify"

ROWS = [
    # (category, feature, databox, hex, funnel)
    ("DATA & CONNECTORS", "", "", "", ""),
    ("", "Native ad platform connectors\n(Meta / Google / Snap / TikTok / LinkedIn / Microsoft)", YES, NO, YES),
    ("", "HubSpot Contact connector", YES, YES, YES),
    ("", "HubSpot Deals connector", YES, YES, YES),
    ("", "HubSpot Lead Module (object 0-136)", VER, YES, VER),
    ("", "BigQuery — raw SQL support", YES, YES, YES),
    ("", "Zero connector maintenance effort", YES, NO, YES),
    ("", "Cross-channel blended CPL / CPQL", PART, YES, YES),
    ("", "Data refresh frequency", "15 min – 24 h", "On-demand + 6 h", "6 h"),
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
    ("", "Approximate monthly cost", "~$59 – $199", "~$24/user", "$1k – $3k+"),
    ("", "Cost scales with data volume", NO, PART, YES),

    ("DECISION", "", "", "", ""),
    ("", "Verdict — what we keep", "PRIMARY ✓", "INTERNAL\nOPTIMIZATION ✓", "DROPPED ✗"),
]

# ── geometry ──────────────────────────────────────────────────────────────────
COL_W  = [440, 160, 160, 200]   # Feature | Databox | Hex | Funnel
ROW_H  = 56
HDR_H  = 64    # column header row height
CAT_H  = 40    # section header row height
TABLE_W = sum(COL_W)

TITLE_H  = 90   # space above table for title
PADDING  = 40   # frame padding on all sides

# table top-left on the board
TL_X = 0
TL_Y = TITLE_H

# total frame dimensions
FRAME_W = TABLE_W + PADDING * 2
FRAME_H = TITLE_H + HDR_H + sum(
    CAT_H if r[0] else ROW_H for r in ROWS
) + PADDING


# ── helpers ───────────────────────────────────────────────────────────────────

def _post(path, payload, retries=3):
    for attempt in range(retries):
        r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=20)
        if r.status_code == 429:
            time.sleep(2 + attempt * 2)
            continue
        if not r.ok:
            print(f"  WARN {path}: {r.status_code} — {r.text[:120]}")
            return None
        return r.json()
    return None


def _shape(text, x, y, w, h, fill, border_color, border_w,
           font_size, font_color, h_align, v_align, bold=False):
    """Post a rectangle cell using only fields the Miro API accepts."""
    content = f"<b>{text}</b>" if bold else str(text)
    _post("/shapes", {
        "data": {"content": content, "shape": "rectangle"},
        "style": {
            "fillColor":   fill,
            "borderColor": border_color,
            **({ "borderWidth": str(border_w) } if border_w > 0 else {}),
            "fontFamily":  "open_sans",
            "fontSize":    str(font_size),
            "color":       font_color,
            "textAlign":   h_align,
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def status_style(val):
    """Return (fill, text_color) for a status value, or None if neutral."""
    s = str(val)
    if s in (YES, "PRIMARY ✓") or s.startswith("INTERNAL"):
        return C_GREEN, C_GREENTX
    if s in (NO, "DROPPED ✗"):
        return C_RED, C_REDTX
    if s.startswith("⚠"):
        return C_AMBER, C_AMBERTX
    return None, None


def _make_board():
    r = requests.post(
        "https://api.miro.com/v2/boards",
        headers=H,
        json={
            "name": "BI Tool Comparison — Databox vs Hex vs Funnel",
            "description": "Qoyod Performance Agent · 2026-06-10",
            "policy": {
                "permissionsPolicy": {"collaborationToolsStartAccess": "all_editors"},
                "sharingPolicy": {"access": "private", "teamAccess": "edit"},
            },
        },
        timeout=15,
    )
    if not r.ok:
        print(f"[miro] board create failed: {r.status_code} {r.text[:300]}")
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
    print(f"[miro] board created: {view_link}")

    # ── title block ───────────────────────────────────────────────────────────
    cx = TL_X + TABLE_W / 2

    # Title background bar
    _shape("", cx, TITLE_H / 2,
           TABLE_W, TITLE_H,
           fill=C_NAVY, border_color=C_NAVY, border_w=0,
           font_size=14, font_color=C_NAVYTX, h_align="center", v_align="middle")

    # Title text (posted as a text widget for cleaner rendering)
    _post("/texts", {
        "data": {"content": "<b>BI Tool Comparison — Databox vs Hex vs Funnel + Data Studio</b>"},
        "style": {
            "fontSize": "24",
            "color": "#FFFFFF",
            "textAlign": "center",
            "fontFamily": "open_sans",
        },
        "position": {"x": cx, "y": 28, "origin": "center"},
        "geometry": {"width": TABLE_W},
    })
    _post("/texts", {
        "data": {"content": "Qoyod Performance Agent  ·  2026-06-10  ·  Green = ✓  Red = ✗  Amber = ⚠ partial"},
        "style": {
            "fontSize": "14",
            "color": "#93C5FD",
            "textAlign": "center",
            "fontFamily": "open_sans",
        },
        "position": {"x": cx, "y": 66, "origin": "center"},
        "geometry": {"width": TABLE_W},
    })
    time.sleep(0.3)

    # ── column header row ─────────────────────────────────────────────────────
    col_labels = ["Feature / Capability", "Databox", "Hex", "Funnel + Data Studio"]
    cx_off = TL_X
    for label, cw in zip(col_labels, COL_W):
        _shape(label,
               cx_off + cw / 2, TL_Y + HDR_H / 2,
               cw, HDR_H,
               fill="#162D4A", border_color="#0F1E30", border_w=1,
               font_size=15, font_color="#FFFFFF",
               h_align="center", v_align="middle", bold=True)
        cx_off += cw
    time.sleep(0.3)

    # ── data rows ─────────────────────────────────────────────────────────────
    cur_y = TL_Y + HDR_H
    row_num = 0
    data_row = 0

    for rec in ROWS:
        cat, feature, db, hx, fn = rec

        if cat:
            # section header — full width, shorter height
            _shape(f"  {cat}",
                   TL_X + TABLE_W / 2, cur_y + CAT_H / 2,
                   TABLE_W, CAT_H,
                   fill=C_CAT, border_color="#C7D2E8", border_w=1,
                   font_size=13, font_color=C_CATTX,
                   h_align="left", v_align="middle", bold=True)
            cur_y += CAT_H
        else:
            data_row += 1
            row_bg = C_WHITE if data_row % 2 else C_ROW

            # Feature cell
            _shape(f"  {feature}",
                   TL_X + COL_W[0] / 2, cur_y + ROW_H / 2,
                   COL_W[0], ROW_H,
                   fill=row_bg, border_color=C_BORDER, border_w=1,
                   font_size=13, font_color=C_TXT,
                   h_align="left", v_align="middle")

            # Status cells
            x_off = TL_X + COL_W[0]
            for val, cw in zip([db, hx, fn], COL_W[1:]):
                sf, stx = status_style(val)
                _shape(val,
                       x_off + cw / 2, cur_y + ROW_H / 2,
                       cw, ROW_H,
                       fill=sf or row_bg,
                       border_color=C_BORDER, border_w=1,
                       font_size=13,
                       font_color=stx or C_TXT,
                       h_align="center", v_align="middle",
                       bold=bool(sf))
                x_off += cw

            cur_y += ROW_H

        row_num += 1
        if row_num % 10 == 0:
            time.sleep(0.4)

    print(f"[miro] Done — {row_num} rows ({data_row} data + section headers)")
    print(f"[miro] Board: {view_link}")


if __name__ == "__main__":
    build()
