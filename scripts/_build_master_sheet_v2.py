"""V2 master sheet — properly designed, formatted, structured.

Improvements over v1:
- Every tab is ONE clean table with consistent column count (no mixed rows)
- Frozen header row + bold/coloured header band
- Tab colours group sections (Analysis=blue, Actions=orange, Setups=green)
- Currency / percent / date number formats per column
- Banded rows for readability
- Conditional formatting on delta columns (red for bad, green for good)
- Auto-resized columns to fit content
- Cover page with headline KPIs at the top
"""
from __future__ import annotations
import os, csv, json
from pathlib import Path
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SHARED_FOLDER_ID = "1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74"
SHEET_NAME = f"Qoyod Paid Media Dashboard — {date.today().strftime('%b %Y')}"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Colour palette (RGB 0-1)
COLOR_HEADER_BG     = {"red": 0.13, "green": 0.20, "blue": 0.36}   # navy
COLOR_HEADER_TEXT   = {"red": 1, "green": 1, "blue": 1}
COLOR_BAND_ALT      = {"red": 0.96, "green": 0.97, "blue": 0.99}   # very pale
COLOR_TAB_ANALYSIS  = {"red": 0.20, "green": 0.45, "blue": 0.80}   # blue
COLOR_TAB_ACTION    = {"red": 0.90, "green": 0.49, "blue": 0.13}   # orange
COLOR_TAB_SETUP     = {"red": 0.22, "green": 0.66, "blue": 0.36}   # green
COLOR_NEGATIVE      = {"red": 0.96, "green": 0.80, "blue": 0.80}   # pale red
COLOR_POSITIVE      = {"red": 0.85, "green": 0.95, "blue": 0.85}   # pale green
COLOR_SECTION_BG    = {"red": 0.93, "green": 0.93, "blue": 0.93}   # light grey


def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "bigquery-key.json"
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


# ── Tab definitions ─────────────────────────────────────────────────────────
# Each tab returns: (header_row, data_rows, column_formats, tab_color)
#   column_formats: list of dicts per column, e.g.
#                   [{"numberFormat":{"type":"CURRENCY","pattern":"$#,##0"}}, ...]


CURR = {"type": "CURRENCY", "pattern": "$#,##0"}
CURR2 = {"type": "CURRENCY", "pattern": "$#,##0.00"}
PCT = {"type": "PERCENT", "pattern": "0.0%"}
NUM = {"type": "NUMBER", "pattern": "#,##0"}
NUM1 = {"type": "NUMBER", "pattern": "#,##0.0"}
DATE = {"type": "DATE", "pattern": "yyyy-mm-dd"}


def tab_cover():
    header = ["Metric", "April 2026 (1-16)", "May 2026 (1-16)", "Change", "Status"]
    data = [
        ["Spend",      41874, 80547, 0.924,   "OVERSPEND"],
        ["Leads",      2234,  2323,  0.040,   "OK"],
        ["SQLs",       1331,  758,   -0.430,  "MAJOR DROP"],
        ["CPQL",       59.0,  85.0,  0.440,   "REGRESSED"],
        ["Qual rate",  0.449, 0.326, -0.274,  "DROPPED"],
        ["ROAS",       4.32,  1.12,  -0.741,  "REGRESSED"],
    ]
    formats = [
        {},
        CURR,  # April spend — we'll override per row but col formatting catches most
        CURR,
        PCT,
        {},
    ]
    return {
        "title": "01 · Cover & Headline",
        "header": header,
        "rows": data,
        "col_formats": formats,
        "tab_color": COLOR_TAB_ANALYSIS,
        "header_height": 32,
        "intro": [
            ["QOYOD PAID MEDIA — PERFORMANCE DASHBOARD"],
            [f"Generated {date.today().isoformat()}  ·  Nexa Performance Agent"],
            [""],
            ["Headline: Apr 2026 (1-16) vs May 2026 (1-16)"],
            ["Auto-flags fired: CPQL_REGRESSED · ROAS_REGRESSED · QUAL_DROPPED · LAUNCH_WAVE"],
            [""],
        ],
    }


def tab_by_channel():
    header = ["Channel", "Period", "Spend", "Leads", "SQLs", "CPL", "CPQL", "Qual %", "Deals won", "ROAS"]
    data = [
        ["google_ads",     "Apr",  19459, 690,  325, 28.2, 59.9,  0.471, 697, 8.37],
        ["google_ads",     "May",  46265, 1346, 333, 34.4, 138.9, 0.247, 297, 1.71],
        ["meta",           "Apr",  8718,  352,  124, 24.8, 70.3,  0.352, 18,  0.78],
        ["meta",           "May",  12740, 338,  146, 37.7, 87.3,  0.432, 10,  0.39],
        ["microsoft_ads",  "Apr",  1405,  75,   36,  18.7, 39.0,  0.480, 22,  3.08],
        ["microsoft_ads",  "May",  6768,  74,   26,  91.5, 260.3, 0.351, 10,  0.34],
        ["snapchat",       "Apr",  7951,  331,  153, 24.0, 52.0,  0.462, 12,  0.53],
        ["snapchat",       "May",  9672,  404,  178, 23.9, 54.3,  0.441, 5,   0.27],
        ["tiktok",         "Apr",  4340,  121,  67,  35.9, 64.8,  0.554, 6,   0.65],
        ["tiktok",         "May",  5101,  160,  74,  31.9, 68.9,  0.463, 7,   0.30],
    ]
    formats = [{}, {}, CURR, NUM, NUM, CURR2, CURR2, PCT, NUM, NUM1]
    return {
        "title":       "02 · By Channel — Apr vs May",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ANALYSIS,
    }


def tab_movers():
    header = ["Channel", "Campaign", "Apr spend", "Apr SQLs", "Apr CPQL", "May spend", "May SQLs", "May CPQL", "CPQL Δ"]
    data = [
        ["google_ads",    "PMax_AR_Generic",                                              1129, 14, 80.7,  5025, 13, 386.5, 305.8],
        ["google_ads",    "Search_AR_Generic_PricingOffers (new)",                          0,  0, 0,     6223, 17, 366.2, 366.2],
        ["microsoft_ads", "Bing_Search_AR_Generic_AccountingSoftware",                    531,  4, 132.8, 1535, 2,  767.4, 634.6],
        ["google_ads",    "Search_E-invoice_AR",                                          2715, 39, 69.6,  5732, 43, 133.3, 63.7],
        ["google_ads",    "Search_AR_Brand_v2",                                           1249, 15, 83.2,  2426, 17, 142.7, 59.5],
        ["google_ads",    "PMax_AR_Generic_Retargeting",                                  1240, 10, 124.0, 4550, 26, 175.0, 51.0],
        ["google_ads",    "PMax_AR_Invoice",                                              1806, 26, 69.5,  5082, 46, 110.5, 41.0],
        ["meta",          "Meta_LeadGen_Prospecting_Lookalike_BrandingEquity_Instantform",1581, 27, 58.5,  3991, 22, 181.4, 122.9],
        ["meta",          "Meta_LeadGen_Prospecting_Retargeting_BrandingEquity",          1056, 19, 55.6,  807,  6,  134.4, 78.9],
        ["google_ads",    "PMax_AR_E-Invoice (silent death)",                             2994, 29, 103.2, 3,    0,  None,  9999],
        # Winners
        ["meta",          "Meta_Conversion_Lookalike_Invoice_Websiteform",                1055, 10, 105.5, 825,  21, 39.3,  -66.2],
        ["google_ads",    "Search_AR_Brand",                                              816,  17, 48.0,  2862, 66, 43.4,  -4.6],
        ["meta",          "Meta_LeadGen_Bookkeeping_Lookalike_MaxmizeLeads",              1685, 29, 58.1,  1594, 32, 49.8,  -8.3],
        ["tiktok",        "Tiktok_LeadGen_Smart+_Instantform_v2",                         2110, 28, 75.3,  2341, 34, 68.9,  -6.4],
    ]
    formats = [{}, {}, CURR, NUM, CURR2, CURR, NUM, CURR2, CURR2]
    return {
        "title":       "03 · Campaign Movers — Top Losers & Winners",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ANALYSIS,
        "conditional": [
            # CPQL Δ column (index 8): >0 red (worse), <0 green (better)
            {"col_index": 8, "operator": "NUMBER_GREATER", "value": 0, "color": COLOR_NEGATIVE},
            {"col_index": 8, "operator": "NUMBER_LESS",    "value": 0, "color": COLOR_POSITIVE},
        ],
    }


def tab_landing_pages():
    header = ["Landing page", "Type", "Spend", "Sessions", "Engagement %", "HS leads", "HS SQLs", "Qual %", "CPL", "CPQL"]
    data = [
        ["lp.qoyod.com/qf",                                              "WordPress", 3542,   None,   None,    32,  7,   0.219, 110.7, 506.0],
        ["lp.qoyod.com/accounting",                                      "WordPress", 15013,  2684,  0.516,    323, 61,  0.189, 46.5,  246.1],
        ["lp.qoyod.com/einvoice-integration",                            "WordPress", 8272,   894,   0.543,    214, 36,  0.168, 38.7,  229.8],
        ["campaigns.qoyod.com/ar/new-form-free-trial",                   "HubSpot",   7754,   118,   0.568,    137, 64,  0.467, 56.6,  121.2],
        ["campaigns.qoyod.com/ar/electronic-invoicing",                  "HubSpot",   10548,  833,   0.647,    259, 108, 0.417, 40.7,  97.7],
        ["www.qoyod.com",                                                "Main Site", 1533,   4078,  0.543,    98,  41,  0.418, 15.6,  37.4],
    ]
    formats = [{}, {}, CURR, NUM, PCT, NUM, NUM, PCT, CURR2, CURR2]
    return {
        "title":       "04 · Landing Pages — 6-Week Performance",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ANALYSIS,
        "conditional": [
            # CPQL > $200 = red, < $100 = green
            {"col_index": 9, "operator": "NUMBER_GREATER", "value": 200, "color": COLOR_NEGATIVE},
            {"col_index": 9, "operator": "NUMBER_LESS",    "value": 100, "color": COLOR_POSITIVE},
        ],
    }


def tab_daily_curve():
    header = ["Date", "Spend", "Leads", "SQLs", "Disq", "CPL", "CPQL"]
    # Read existing daily curve TSV if present
    p = Path(__file__).parent / "_apr_vs_may_2026_sheet" / "05_daily_curve.tsv"
    data = []
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for i, r in enumerate(csv.reader(f, delimiter="\t")):
                if i == 0: continue  # skip header
                if len(r) < 6: continue
                try:
                    data.append([
                        r[0],
                        float(r[1] or 0),
                        int(r[2] or 0),
                        int(r[3] or 0),
                        int(r[4] or 0),
                        float(r[5] or 0),
                        float(r[6]) if len(r) > 6 and r[6] else None,
                    ])
                except Exception:
                    pass
    formats = [DATE, CURR, NUM, NUM, NUM, CURR2, CURR2]
    return {
        "title":       "05 · Daily Curve",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ANALYSIS,
    }


def tab_actions():
    header = ["#", "Type", "Priority", "Channel", "Action", "Status", "Asana"]
    data = [
        [1,  "Pause",   "High",   "google_ads",    "Pause PMax_AR_Generic — CPQL $386",                        "OPEN",     "https://app.asana.com/0/0/1214865244763906"],
        [2,  "Pause",   "High",   "google_ads",    "Pause PMax_AR_Generic_Retargeting — $175 CPQL",            "OPEN",     "https://app.asana.com/0/0/1214864840858564"],
        [3,  "Scale",   "Medium", "google_ads",    "Scale-back Search_E-invoice_AR to $170/d",                 "OPEN",     "https://app.asana.com/0/0/1214865012809819"],
        [4,  "Fix",     "Low",    "google_ads",    "PMax_AR_E-Invoice — confirmed deliberate pause",           "RESOLVED", "https://app.asana.com/0/0/1214864840866643"],
        [5,  "Scale",   "Medium", "meta",          "Cut Meta BrandingEquity Lookalike 75%",                    "OPEN",     "https://app.asana.com/0/0/1214864951334535"],
        [6,  "Launch",  "Medium", "meta",          "Test Websiteform variant on 1 more Invoice Lookalike",     "OPEN",     "https://app.asana.com/0/0/1214865244764431"],
        [7,  "Pause",   "High",   "microsoft_ads", "Pause 5 Bing campaigns launched May 6",                    "OPEN",     "https://app.asana.com/0/0/1214865244698718"],
        [8,  "Scale",   "Medium", "microsoft_ads", "Cut Bing_WebsiteTraffic to $40/d (IS goal)",               "OPEN",     "https://app.asana.com/0/0/1214864840869182"],
        [9,  "Pause",   "High",   "google_ads",    "Pause 3 Generic campaigns (audience issue, not LP)",       "REVISED",  "https://app.asana.com/0/0/1214865012784592"],
        [10, "Verify",  "Medium", "google_ads",    "Confirm LP form parity; await LP A/B test",                "REVISED",  "https://app.asana.com/0/0/1214864840803036"],
        [11, "Launch",  "Medium", "google_ads",    "Build HubSpot LP equivalent for /accounting",              "BLOCKED",  "https://app.asana.com/0/0/1214865244777757"],
        [12, "Fix",     "High",   "tracking",      "Fix GA4 generate_lead event coverage across all LPs",      "OPEN",     "https://app.asana.com/0/0/1214865012889339"],
        [13, "Scale",   "High",   "snapchat",      "Restore Snap iPhone Instantform to $185/d",                "OPEN",     "https://app.asana.com/0/0/1214864840869199"],
        [14, "Fix",     "High",   "tracking",      "ENG: Add impression_share fields to Google + Bing",        "SHIPPED",  "https://app.asana.com/0/0/1214864840871361"],
        [15, "Fix",     "High",   "tracking",      "ENG: Lag-aware CPQL — suppress when open > 30%",           "SHIPPED",  "https://app.asana.com/0/0/1214865244764259"],
        [16, "Fix",     "High",   "tracking",      "ENG: spend_drift.py — 3 detection rules",                  "SHIPPED",  "https://app.asana.com/0/0/1214865244779563"],
        [17, "Fix",     "High",   "tracking",      "ENG: launch_policy.py — 1 launch/channel/7d",              "SHIPPED",  "https://app.asana.com/0/0/1214864951424904"],
        [18, "Fix",     "High",   "tracking",      "ENG: Switch primary KPI CPL → CPQL",                       "SHIPPED",  "https://app.asana.com/0/0/1214864951403496"],
        [19, "Test",    "High",   "meta",          "Run controlled LP A/B (HubSpot vs WP), 14d",               "OPEN",     "https://app.asana.com/0/0/1214865737696001"],
    ]
    formats = [NUM, {}, {}, {}, {}, {}, {}]
    return {
        "title":       "06 · Action Points — 19 Asana Tasks",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ACTION,
        "conditional": [
            # Status column (index 5)
            {"col_index": 5, "operator": "TEXT_EQ", "value": "SHIPPED",  "color": COLOR_POSITIVE},
            {"col_index": 5, "operator": "TEXT_EQ", "value": "OPEN",     "color": COLOR_NEGATIVE},
            {"col_index": 5, "operator": "TEXT_EQ", "value": "BLOCKED",  "color": {"red":1, "green":0.9, "blue":0.7}},
        ],
    }


def tab_june_calendar():
    header = ["Week of", "Date", "Channel", "Action Type", "Description"]
    data = [
        ["May 18", "2026-05-18", "google_ads",   "Pause",   "Pause PMax_AR_Generic + PMax_AR_Generic_Retargeting"],
        ["May 18", "2026-05-18", "google_ads",   "Cut",     "Cut Search_E-invoice_AR to $170/d"],
        ["May 18", "2026-05-18", "meta",         "Cut",     "Cut BrandingEquity Lookalike 75%; restore Bookkeeping_Lookalike"],
        ["May 18", "2026-05-18", "microsoft",    "Pause",   "Pause Bing 5-pack"],
        ["May 18", "2026-05-18", "snapchat",     "Restore", "RESTORE Snap iPhone Instantform to $185/d (highest leverage)"],
        ["May 18", "2026-05-17", "meta+snap",    "Launch",  "Meta Invoice Interests $30/d + Snap Invoice iOS $100/d"],
        ["May 25", "2026-05-25", "google_ads",   "Re-point","Re-point Generic LP to HubSpot /ar/electronic-invoicing"],
        ["May 25", "2026-05-24", "meta+snap",    "Launch",  "Meta Invoice Lookalike v2 + Snap Invoice Broad iPhone"],
        ["Jun 1",  "2026-06-01", "meta+snap",    "Launch",  "Meta Bookkeeping Websiteform + Snap Bookkeeping iOS"],
        ["Jun 1",  "2026-06-01", "landing_page","Test",    "LP A/B test starts: HubSpot vs WP, $20/d each, 14d"],
        ["Jun 1",  "2026-06-01", "google_ads",   "Scale",   "PMax_AR_Invoice_FiveSectors +25% budget at same tCPA"],
        ["Jun 8",  "2026-06-08", "meta+snap",    "Launch",  "Meta Qflavours + Snap Bookkeeping Android (gated on Tier-1 < $60 CPQL)"],
        ["Jun 8",  "2026-06-08", "snapchat",     "Add",     "Snap Android variant of iPhone winner"],
        ["Jun 15", "2026-06-15", "meta+snap",    "Launch",  "Customer Lookalike 3% v2 + Snap iOS Instantform v4 (creative refresh)"],
        ["Jun 22", "2026-06-22", "all",          "Scale",   "Top-3 winners +30% every 4 days; losers pause"],
    ]
    formats = [{}, DATE, {}, {}, {}]
    return {
        "title":       "07 · June Calendar",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ACTION,
    }


def tab_june_budget():
    header = ["Channel", "May actual", "May effective (post-pause)", "June target", "Δ", "Rationale"]
    data = [
        ["Google Ads",    93000, 70000, 75000, -0.194, "Pause bad PMax; hold Brand + E-invoice at right size"],
        ["Meta",          24000, 24000, 28000,  0.167, "Scale Bookkeeping_Lookalike + Websiteform; +2 duplications"],
        ["Snapchat",      19000, 19000, 22000,  0.158, "Restore iPhone Instantform; launch Android + Bookkeeping"],
        ["Microsoft Ads", 13000, 8000,  8000,  -0.385, "Pause 5-pack; hold Brand + WebsiteTraffic at cap"],
        ["TikTok",        10000, 10000, 10000,  0,     "Hold; no Tier-1 actions queued"],
        ["LinkedIn",      0,     0,     0,      0,     "Token expired since Mar; revisit Q3"],
        ["TOTAL",         159000, 131000, 143000, -0.101, "Net -10% vs current trend; reallocated to higher-CPQL spend"],
    ]
    formats = [{}, CURR, CURR, CURR, PCT, {}]
    return {
        "title":       "08 · June Budget",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ACTION,
        "conditional": [
            {"col_index": 4, "operator": "NUMBER_GREATER", "value": 0, "color": COLOR_POSITIVE},
            {"col_index": 4, "operator": "NUMBER_LESS",    "value": 0, "color": COLOR_NEGATIVE},
        ],
    }


def tab_june_kpis():
    header = ["Week ending", "CPQL target", "Cumulative target", "Notes"]
    data = [
        ["2026-05-24", 75, "Reset", "Post-pause cleanup; SDRs catch up on May 15-16 open queue"],
        ["2026-05-31", 70, "<$72",  "First Tier-1 duplications stabilizing"],
        ["2026-06-07", 65, "<$69",  "Tier-2 duplications staged; LP A/B running"],
        ["2026-06-14", 62, "<$66",  "LP question resolved; full duplication portfolio active"],
        ["2026-06-21", 60, "<$64",  "Scaling phase begins on confirmed winners"],
        ["2026-06-30", 58, "<$62",  "June final — if hit, sustainable trajectory established"],
    ]
    formats = [DATE, CURR, {}, {}]
    return {
        "title":       "09 · June KPI Targets",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_ACTION,
    }


def tab_campaign_setups():
    header = ["#", "Channel", "Campaign Name", "Daily Budget", "Objective", "Bidding", "Audience", "LP / Form", "Creative", "Launch Date"]
    data = [
        [1, "meta",     "Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform",
                       30, "OUTCOME_LEADS", "Maximise Leads (no tCPA first 7d, then $50)",
                       "Interests + Job titles (Invoice-specific): ZATCA, Tax compliance, E-Invoicing, B2B SaaS + Finance Manager, Accountant, CFO, Owner SMB. ONE adset, OR-logic, Advantage+ Audience ON.",
                       "Meta Instant Form (in-app)",
                       "3× video 9:16 + 2× static carousel, Arabic VO",
                       "2026-05-17"],
        [2, "meta",     "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2",
                       25, "OUTCOME_LEADS (Conversion)", "Cost cap $40",
                       "LAL seed [Nexa Agent] LAL Seed - Customers Invoice (5891), 3% Customer Lookalike — v1 used 2% SQL Lookalike",
                       "campaigns.qoyod.com/ar/electronic-invoicing (HubSpot LP)",
                       "Same as v1 (audience-only change)",
                       "2026-05-24"],
        [3, "snapchat", "Snapchat_LeadGen_Invoice_Prospecting_Interest_iOS_Instantform",
                       100, "LEAD_GENERATION", "Auto-bid; goal CPA $45 after learning",
                       "Snap Interests: Business & Finance, SMB Owners, Technology Early Adopters. iOS only.",
                       "Snap Instant Form",
                       "Vertical 9:16 6-10s Arabic captions; ZATCA-compliance hook",
                       "2026-05-17"],
        [4, "snapchat", "Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform",
                       25, "LEAD_GENERATION", "Auto-bid; goal CPA $40",
                       "Broad (no interest layer); iPhone only. Creative carries targeting signal.",
                       "Snap Instant Form",
                       "Product-anchored: ZATCA Phase 2 deadline messaging",
                       "2026-05-24"],
        [5, "meta",     "Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform",
                       25, "OUTCOME_LEADS (Conversion)", "Cost cap $50",
                       "LAL seed [Nexa Agent] LAL Seed - Customers Bookkeeping (5893), 2% Lookalike",
                       "Interim: campaigns.qoyod.com/ar/new-form-free-trial; switch when task #11 HubSpot LP ships",
                       "Stop chasing invoices / reconciling spreadsheets theme",
                       "2026-05-31"],
        [6, "snapchat", "Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_iOS_Instantform",
                       75, "LEAD_GENERATION", "Auto-bid; goal CPA $45",
                       "Snap Interests: SMB Owners, F&B, Retail, Professional Services, Accounting. NOT Tax/ZATCA. iOS 28-50.",
                       "Snap Instant Form",
                       "Demo-style 9:16 screen recording: Replace your spreadsheets",
                       "2026-05-31"],
        [7, "meta",     "Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform",
                       20, "OUTCOME_LEADS", "Maximise Leads (no tCPA — let algo find pockets)",
                       "Interests: F&B, Restaurants, Cafés, Cloud Kitchens, Restaurant Management.",
                       "Meta Instant Form (Qflavours has no good LP — /qf killed)",
                       "F&B imagery: kitchen, POS, dishes",
                       "2026-06-07"],
        [8, "snapchat", "Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_Android_Instantform",
                       50, "LEAD_GENERATION", "Auto-bid; goal CPA $50",
                       "Same Interests as #6 but Android device. Launch only after #6 hits CPQL < $60 in 7d.",
                       "Snap Instant Form",
                       "Same creative as #6",
                       "2026-06-07"],
    ]
    formats = [NUM, {}, {}, CURR, {}, {}, {}, {}, {}, DATE]
    return {
        "title":       "10 · Campaign Setups",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_SETUP,
    }


def tab_hubspot():
    header = ["List Name", "List ID", "Members", "Type", "Used For"]
    data = [
        ["[Nexa Agent] LAL Seed - Customers Invoice",     5891, 44315,  "LAL seed",    "Meta/Snap Invoice Lookalike base"],
        ["[Nexa Agent] LAL Seed - Customers Bookkeeping", 5893, 683,    "LAL seed",    "Meta/Snap Bookkeeping Lookalike base"],
        ["[Nexa Agent] LAL Seed - Customers Qflavours",   5895, 52,     "LAL seed",    "Meta/Snap Qflavours Lookalike base"],
        ["[Nexa Agent] LAL Seed - SQLs Invoice",          5897, 53377,  "LAL seed",    "Alt seed using qualified leads"],
        ["[Nexa Agent] LAL Seed - SQLs Bookkeeping",      5899, 636,    "LAL seed",    "Alt seed using qualified leads"],
        ["[Nexa Agent] LAL Seed - SQLs Qflavours",        5901, 376,    "LAL seed",    "Alt seed using qualified leads"],
        ["[Nexa Agent] Exclude - All Customers",          5903, 92776,  "Exclusion",   "Apply to every prospecting campaign"],
        ["[Nexa Agent] Exclude - Open Leads",             5904, 295121, "Exclusion",   "Stop double-marketing active funnel"],
        ["[Nexa Agent] Exclude - Qoyod Employees",        5905, 756,    "Exclusion",   "Internal team filter"],
    ]
    formats = [{}, NUM, NUM, {}, {}]
    return {
        "title":       "11 · HubSpot Lists",
        "header":      header,
        "rows":        data,
        "col_formats": formats,
        "tab_color":   COLOR_TAB_SETUP,
    }


# ── Main builder ────────────────────────────────────────────────────────────

def _column_letter(idx: int) -> str:
    """0 -> A, 1 -> B, ..."""
    s = ""
    while True:
        s = chr(65 + idx % 26) + s
        idx = idx // 26 - 1
        if idx < 0: break
    return s


def main():
    creds = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive  = build("drive",  "v3", credentials=creds, cache_discovery=False)

    print(f"[sheet] creating '{SHEET_NAME}' in shared folder ...")

    # Build all tab specs
    tab_specs = [
        tab_cover(),
        tab_by_channel(),
        tab_movers(),
        tab_landing_pages(),
        tab_daily_curve(),
        tab_actions(),
        tab_june_calendar(),
        tab_june_budget(),
        tab_june_kpis(),
        tab_campaign_setups(),
        tab_hubspot(),
    ]

    # 1) Create the file via Drive API
    file_meta = {
        "name":     SHEET_NAME,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents":  [SHARED_FOLDER_ID],
    }
    file = drive.files().create(body=file_meta, fields="id, webViewLink",
                                 supportsAllDrives=True).execute()
    sid = file["id"]
    print(f"[drive] created file id={sid}")

    # 2) Create tabs + delete default
    add_requests = [
        {"addSheet": {"properties": {
            "title": spec["title"],
            "tabColor": spec.get("tab_color"),
            "gridProperties": {"frozenRowCount": 1 + len(spec.get("intro", []))},
        }}}
        for spec in tab_specs
    ]
    resp = sheets.spreadsheets().batchUpdate(
        spreadsheetId=sid, body={"requests": add_requests}
    ).execute()
    sheet_ids = [r["addSheet"]["properties"]["sheetId"] for r in resp["replies"]]

    # Delete default Sheet1
    meta = sheets.spreadsheets().get(spreadsheetId=sid).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == "Sheet1":
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=sid,
                body={"requests": [{"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]},
            ).execute()
            break

    # 3) Write data + apply formatting per tab
    data_payload = []
    format_requests = []

    for spec, sheet_id in zip(tab_specs, sheet_ids):
        title  = spec["title"]
        header = spec["header"]
        rows   = spec["rows"]
        intro  = spec.get("intro", [])
        col_fmts = spec.get("col_formats", [])

        # Pad intro rows to header width
        n_cols = len(header)
        padded_intro = [r + [""] * (n_cols - len(r)) for r in intro]

        all_rows = padded_intro + [header] + [list(r) for r in rows]
        data_payload.append({
            "range":         f"'{title}'!A1",
            "majorDimension":"ROWS",
            "values":        all_rows,
        })

        header_row_index = len(padded_intro)   # 0-indexed
        data_start = header_row_index + 1
        data_end   = header_row_index + 1 + len(rows)

        # Header formatting: bold + filled + white text
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row_index,
                    "endRowIndex":   header_row_index + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex":   n_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "textFormat": {"bold": True, "foregroundColor": COLOR_HEADER_TEXT, "fontSize": 11},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment":   "MIDDLE",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
            }
        })

        # Intro rows: light grey background, bold first row
        if padded_intro:
            format_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex":   len(padded_intro),
                        "startColumnIndex": 0,
                        "endColumnIndex":   n_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": COLOR_SECTION_BG,
                            "textFormat": {"bold": True, "fontSize": 11},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })

        # Per-column number formats
        for col_idx, fmt in enumerate(col_fmts):
            if not fmt: continue
            format_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": data_start,
                        "endRowIndex":   data_end,
                        "startColumnIndex": col_idx,
                        "endColumnIndex":   col_idx + 1,
                    },
                    "cell": {"userEnteredFormat": {"numberFormat": fmt}},
                    "fields": "userEnteredFormat.numberFormat",
                }
            })

        # Banded rows
        format_requests.append({
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": data_start,
                        "endRowIndex":   data_end,
                        "startColumnIndex": 0,
                        "endColumnIndex":   n_cols,
                    },
                    "rowProperties": {
                        "headerColor":  None,
                        "firstBandColor":  {"red": 1, "green": 1, "blue": 1},
                        "secondBandColor": COLOR_BAND_ALT,
                    },
                }
            }
        })

        # Conditional formatting
        for cond in spec.get("conditional", []):
            op_type = cond["operator"]
            value   = cond["value"]
            color   = cond["color"]
            col_idx = cond["col_index"]
            condition = {
                "type":   op_type,
                "values": [{"userEnteredValue": str(value)}],
            }
            format_requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": data_start,
                            "endRowIndex":   data_end,
                            "startColumnIndex": col_idx,
                            "endColumnIndex":   col_idx + 1,
                        }],
                        "booleanRule": {
                            "condition": condition,
                            "format":    {"backgroundColor": color},
                        }
                    },
                    "index": 0,
                }
            })

        # Auto-resize columns
        format_requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId":   sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex":   n_cols,
                }
            }
        })

    # 4) Write data
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={"valueInputOption": "USER_ENTERED", "data": data_payload},
    ).execute()
    print(f"[sheet] wrote {len(tab_specs)} tabs of data")

    # 5) Apply formatting (chunked — Sheets API limits batch size)
    chunk_size = 50
    for i in range(0, len(format_requests), chunk_size):
        chunk = format_requests[i:i+chunk_size]
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sid, body={"requests": chunk}
        ).execute()
    print(f"[sheet] applied {len(format_requests)} formatting requests")

    print()
    print("=" * 70)
    print(f"  ✅ Done.")
    print(f"     URL: {file['webViewLink']}")
    print("=" * 70)
    return file["webViewLink"]


if __name__ == "__main__":
    main()
