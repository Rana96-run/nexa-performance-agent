"""
scripts/miro_use_cases.py
==========================
Adds use-case cards BELOW the existing 4-column flow on the Miro board.
Each card shows: capability name, trigger, sample output / artifact.

Layout:
- Existing main flow stays at y < 600
- Use Cases header at y=900
- 3 rows × 5 columns of cards below that

Run with:
    python scripts/miro_use_cases.py
"""
from __future__ import annotations

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD = os.getenv("MIRO_BOARD_ID")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = f"https://api.miro.com/v2/boards/{BOARD}"


def _post(path, payload):
    r = requests.post(f"{BASE}{path}", headers=H, json=payload, timeout=15)
    if not r.ok:
        print(f"FAIL {path}: {r.status_code} — {r.text[:200]}")
        return None
    return r.json()


def shape(text_content, x, y, w=320, h=130, fill="#dbeafe", border="#2563eb",
          font_color="#0f172a", font_size=13):
    return _post("/shapes", {
        "data": {"content": text_content, "shape": "round_rectangle"},
        "style": {
            "fillColor": fill, "borderColor": border, "borderWidth": "2",
            "fontFamily": "open_sans", "fontSize": str(font_size),
            "color": font_color, "textAlign": "left",
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


def text(content, x, y, w=600, font=24, color="#0f172a", align="center"):
    return _post("/texts", {
        "data": {"content": content},
        "style": {"fontSize": str(font), "color": color, "textAlign": align},
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w},
    })


def output_box(content, x, y, w=320, h=180, fill="#1e293b",
               font_color="#e2e8f0", font_size=11):
    """A 'screenshot-style' shape — dark background, monospace-feel content."""
    return _post("/shapes", {
        "data": {"content": content, "shape": "rectangle"},
        "style": {
            "fillColor": fill, "borderColor": "#0f172a", "borderWidth": "1",
            "fontFamily": "roboto_mono", "fontSize": str(font_size),
            "color": font_color, "textAlign": "left",
        },
        "position": {"x": x, "y": y, "origin": "center"},
        "geometry": {"width": w, "height": h},
    })


# ─── Build ────────────────────────────────────────────────────────────────────

def build():
    # Section header
    text("USE CASES — what each capability looks like in action",
         x=25, y=900, w=1400, font=32)
    text("Cards show trigger · output sample · the real artifact created",
         x=25, y=945, w=1400, font=14, color="#64748b")

    # ── Layout: 3 rows × 5 cards = 15 use cases ─────────────────────────────
    # Each card: header (top, 130h) + output mock-up (bottom, 180h)
    # Vertical spacing per card: ~340 (130 + 180 + 30 gap)
    # Horizontal spacing: 360 between cards (320w + 40 gap)
    COL_X = [-1100, -740, -380, 0, 360]   # 5 columns; second-row start at 720
    # We'll use 5 cols across, 3 rows down.
    # Actually we have 15 cards — fit in 4 cols × 4 rows for cleaner layout.
    # Let me use 4 cols.
    COL_X = [-1080, -720, -360, 0, 360, 720]   # not all used per row
    ROW_HEAD_Y_BASE = 1080  # top row card-header center y
    ROW_OUT_Y_BASE  = 1240  # output box center y (below header)
    ROW_GAP = 380           # space between rows

    use_cases = [
        # ── Row 1: ANALYSIS / READ-ONLY ─────────────────────────────────────
        {
            "title":   "1. Daily HTML Dashboard",
            "trigger": "Nightly 03:00 + on-demand /api/regenerate",
            "fill":    "#dbeafe", "border": "#1e40af",
            "output": (
                "/reports/latest\n"
                "Generated: 2026-04-27 12:33 Riyadh\n"
                "Channels: google_ads · meta · snap · linkedin\n"
                "──────────────\n"
                "7d total: $22,803 · 548 leads · CPL $42\n"
                "Hosted on Railway, persisted to Drive\n"
                "  via /reports/latest → Drive fallback.\n"
                "Per-channel sections, UTM tabs,\n"
                "30-day Plotly trend charts, custom\n"
                "date-range API."
            ),
        },
        {
            "title":   "2. Spike Detection (anomalies)",
            "trigger": "Nightly · ±30% spend / ±40% leads / ±20pp qual",
            "fill":    "#fef3c7", "border": "#a16207",
            "output": (
                "[spike-detector] running\n"
                "  google_ads leads ▼ 31% (243 vs 351)\n"
                "  meta spend     ▲ 24%  (no alert)\n"
                "  snap qual_rate ▲ 22pp (audience win)\n"
                "──────────────\n"
                "→ inline in daily Slack summary\n"
                "  'Anomalies detected: 2 (see dashboard)'"
            ),
        },
        {
            "title":   "3. Keyword Waste Analysis",
            "trigger": "Live Google Ads API · 14d · zero conv / >$15",
            "fill":    "#fee2e2", "border": "#991b1b",
            "output": (
                "$2,705 wasted · 56 keywords · 14d\n"
                "Top:\n"
                "  $707 BROAD نظام فودكس (Foodics) 0 conv\n"
                "  $190 PHRASE تطبيقات التوصيل   0 conv\n"
                "  $144 PHRASE برنامج إدارة العملاء 0 conv\n"
                "──────────────\n"
                "→ Asana task + auto-pause when\n"
                "  keywords_daily collector lands."
            ),
        },
        {
            "title":   "4. Impression-Share Audit",
            "trigger": "Nightly · search_*_lost_impression_share",
            "fill":    "#e0e7ff", "border": "#4338ca",
            "output": (
                "12 IS findings\n"
                "  rank issue: 10 (low QS / weak bid)\n"
                "    PMax_Invoice_FiveSectors\n"
                "      $10,992 spend, IS 11%, lost 86% rank\n"
                "  scale-budget: 2\n"
                "    Search_AR_Brand $1,933 lost 23% bud"
            ),
        },
        # ── Row 2: ANALYSIS continued ───────────────────────────────────────
        {
            "title":   "5. Quality-Score Audit",
            "trigger": "Nightly · QS<5 & spend>$50",
            "fill":    "#ecfccb", "border": "#3f6212",
            "output": (
                "15 keywords with QS < 5\n"
                "  EXACT قيود محاسبية · QS 3 · $70\n"
                "    Ad relevance: BELOW_AVG\n"
                "    LP experience: BELOW_AVG\n"
                "  PHRASE برنامج محاسبة · QS 4 · $61\n"
                "──────────────\n"
                "Asana: ad-copy / LP rewrite tasks"
            ),
        },
        {
            "title":   "6. Search-Terms / New Keywords",
            "trigger": "Nightly · 30d · search_term_view",
            "fill":    "#fce7f3", "border": "#9f1239",
            "output": (
                "63 NEW keyword candidates (conv ≥ 1)\n"
                "  'برنامج محاسبة سحابي' 5 conv $42 CPA\n"
                "  'فاتورة الكترونية موحدة' 3 conv\n"
                "49 NEGATIVE candidates (waste)\n"
                "  $50 'فواتير الكترونية' 28 clk 0 conv\n"
                "──────────────\n"
                "Negatives = direct-execute"
            ),
        },
        {
            "title":   "7. Channel Attribution Resolver",
            "trigger": "On HubSpot lead/deal write",
            "fill":    "#cffafe", "border": "#0e7490",
            "output": (
                "Fallback chain (first hit wins):\n"
                "  1. qoyod_source label\n"
                "  2. lead_*_traffic_source enum\n"
                "     + drilldown_1 (bing→Microsoft)\n"
                "  3. 'Unknown keywords (SSL)'→organic\n"
                "  4. utm_campaign keyword pattern\n"
                "  5. utm_audience/content/medium\n"
                "Result: Other 25% → 3.3% (-86%)"
            ),
        },
        {
            "title":   "8. Health Check",
            "trigger": "07:00 daily + /scripts/health_check",
            "fill":    "#dcfce7", "border": "#15803d",
            "output": (
                "Nexa Health — 27 Apr 15:09 KSA\n"
                "  ✓ Flask                OK   0.9s\n"
                "  ✓ HubSpot API          OK   0.6s\n"
                "  ✓ BigQuery             OK   2.2s\n"
                "  ✓ Google Ads (2 acct)  OK   2.3s\n"
                "  ✓ Meta · Slack · Asana OK\n"
                "  ✓ /webhooks/zapier     OK\n"
                "Slack only on FAILURE."
            ),
        },
        # ── Row 3: WRITE / CREATE ──────────────────────────────────────────
        {
            "title":   "9. HubSpot Lists (segments)",
            "trigger": "executors.hubspot_lists.create_list",
            "fill":    "#fed7aa", "border": "#9a3412",
            "output": (
                "POST /crm/v3/lists\n"
                "✓ LIST_won_deals_lookalike_seed\n"
                "  listId 5674 · DYNAMIC\n"
                "  filter: lifecyclestage IN [customer,\n"
                "          evangelist]\n"
                "✓ LIST_existing_customers_exclude\n"
                "  listId 5675\n"
                "→ LinkedIn matched audience seed\n"
                "→ Meta CAPI exclusion list"
            ),
        },
        {
            "title":   "10. Asana Tasks (routed)",
            "trigger": "executors.asana.create_task",
            "fill":    "#fbcfe8", "border": "#be185d",
            "output": (
                "[Recommendation | Pause]\n"
                "Google Ads — Pause-zone review (12)\n"
                "──────────────\n"
                "Routed to:\n"
                "  Project: Google Ads Optimization\n"
                "  Section: Campaign\n"
                "  Channel × asset_level resolver\n"
                "Deduped by (title × project × day)\n"
                "Created today: 14"
            ),
        },
        {
            "title":   "11. LinkedIn Paused Campaign",
            "trigger": "executors.linkedin_campaign.create  (pending)",
            "fill":    "#bae6fd", "border": "#0369a1",
            "output": (
                "POST /adCampaigns  (status=PAUSED)\n"
                "  name: LI_Lookalike_Seed_Q2\n"
                "  objective: LEAD_GENERATION\n"
                "  daily_budget: $40\n"
                "  audience: matched (LIST 5674)\n"
                "  bid: max CPL $90 (manual)\n"
                "──────────────\n"
                "PAUSED — never auto-enable.\n"
                "Slack: 'Campaign created for review'"
            ),
        },
        {
            "title":   "12. Meta Paused Campaign",
            "trigger": "executors.meta_campaign.create  (pending)",
            "fill":    "#bfdbfe", "border": "#1e40af",
            "output": (
                "POST /act_<id>/campaigns  (PAUSED)\n"
                "  name: Meta_LeadGen_Q2_Lookalike\n"
                "  objective: OUTCOME_LEADS\n"
                "  daily_budget: $30\n"
                "  pixel: 1782671302631317 (CRM)\n"
                "  bid_strategy: LOWEST_COST_W_BID_CAP\n"
                "──────────────\n"
                "PAUSED. Asana brief for Donia."
            ),
        },
        # ── Row 4: NOTIFY ──────────────────────────────────────────────────
        {
            "title":   "13. Daily Slack Summary",
            "trigger": "End of nightly cycle (one message)",
            "fill":    "#d1fae5", "border": "#065f46",
            "output": (
                "*Daily Report — 26 Apr*  open dashboard\n"
                "7d total: $22,803 · 548 L · 210 Q\n"
                "  CPL $42 · CPQL $109\n"
                "  • google_ads:$16,588 · 352 · CPL $47\n"
                "  • meta:      $4,466 · 131 · CPL $34\n"
                "  • snapchat:  $1,750 ·  65 · CPL $27\n"
                "Tasks created today: 14\n"
                "  • Bing Ads Scaling: 16 pending\n"
                "  • Google Ads Optim: 9 pending"
            ),
        },
        {
            "title":   "14. Approval Request (optimized)",
            "trigger": "High-confidence channel mutation",
            "fill":    "#fef9c3", "border": "#854d0e",
            "output": (
                "*PAUSE* · google_ads · `PMax_Invoice`\n"
                "*CPQL* = `$472`  (threshold $80)\n"
                "_4-day breach · 11 leads · 2 qual_\n"
                "Confidence: High\n"
                "──────────────\n"
                "✓ approve   ✗ reject\n"
                "(no action until reaction)"
            ),
        },
        {
            "title":   "15. Auto-Fix (Zapier)",
            "trigger": "POST /webhooks/zapier (errors / held)",
            "fill":    "#ddd6fe", "border": "#5b21b6",
            "output": (
                "Zap 'Lead → HubSpot' errored\n"
                "→ replay attempt 1: success  silent\n"
                "Zap 'Subscriber → Slack' held\n"
                "→ resume attempt 1: success  silent\n"
                "Zap 'Brief → Asana' errored 3×\n"
                "→ disabled · Claude diagnosis sent\n"
                "  to Asana: 'auth expired, reconnect'"
            ),
        },
    ]

    # Place cards in a 4-col grid (4 cols × 4 rows = 16 cells, we use 15)
    n_cols = 4
    col_xs = [-1080, -720, -360, 0]
    for i, uc in enumerate(use_cases):
        col = i % n_cols
        row = i // n_cols
        x = col_xs[col]
        y_head = ROW_HEAD_Y_BASE + row * ROW_GAP
        y_out  = ROW_OUT_Y_BASE  + row * ROW_GAP

        # Header card (title + trigger)
        head_text = f"**{uc['title']}**\n\n{uc['trigger']}"
        shape(head_text, x, y_head, w=320, h=130,
              fill=uc["fill"], border=uc["border"], font_size=13)

        # Output mock-up (dark "screenshot")
        output_box(uc["output"], x, y_out, w=320, h=180)

    print("[miro] Use case board built.")
    print(f"        https://miro.com/app/board/{BOARD}")


if __name__ == "__main__":
    build()
