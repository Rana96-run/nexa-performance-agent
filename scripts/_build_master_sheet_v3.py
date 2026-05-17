"""V3 master sheet — channel-grouped stacked tables.

Each tab is now a vertical stack of mini-tables, one per channel:

    [GOOGLE ADS banner]
    | Metric  | April | May | Δ |
    | Spend   |  ...  | ... |...|
    | CPQL    |  ...  | ... |...|
    (blank row)
    [META banner]
    | Metric  | April | May | Δ |
    ...

Channels: google_ads, meta, snapchat, microsoft_ads, tiktok, linkedin.
Each channel has a distinct banner color matching its brand identity.
"""
from __future__ import annotations
import os, csv, json
from pathlib import Path
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SHARED_FOLDER_ID = "1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74"
SHEET_NAME = f"Qoyod Paid Media Dashboard v3 — {date.today().strftime('%Y-%m-%d')}"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]


# ── Colour palette ──────────────────────────────────────────────────────────

WHITE   = {"red": 1, "green": 1, "blue": 1}
NAVY    = {"red": 0.13, "green": 0.20, "blue": 0.36}
PALE    = {"red": 0.96, "green": 0.97, "blue": 0.99}
GREY    = {"red": 0.93, "green": 0.93, "blue": 0.93}
NEG     = {"red": 0.97, "green": 0.79, "blue": 0.78}
POS     = {"red": 0.82, "green": 0.94, "blue": 0.81}

# Channel banner colours (brand-aligned)
CH_COLOR = {
    "google_ads":    {"red": 0.92, "green": 0.39, "blue": 0.25},  # Google red-orange
    "meta":          {"red": 0.10, "green": 0.46, "blue": 0.82},  # Meta blue
    "snapchat":      {"red": 1.00, "green": 0.83, "blue": 0.00},  # Snap yellow
    "microsoft_ads": {"red": 0.00, "green": 0.62, "blue": 0.58},  # Bing teal
    "tiktok":        {"red": 0.20, "green": 0.20, "blue": 0.20},  # TikTok black
    "linkedin":      {"red": 0.00, "green": 0.46, "blue": 0.71},  # LinkedIn blue
}
CH_TEXT = {
    "google_ads":    WHITE,
    "meta":          WHITE,
    "snapchat":      {"red": 0.15, "green": 0.15, "blue": 0.15},   # dark text on yellow
    "microsoft_ads": WHITE,
    "tiktok":        WHITE,
    "linkedin":      WHITE,
}
CH_LABEL = {
    "google_ads":    "GOOGLE ADS",
    "meta":          "META",
    "snapchat":      "SNAPCHAT",
    "microsoft_ads": "MICROSOFT ADS (BING)",
    "tiktok":        "TIKTOK",
    "linkedin":      "LINKEDIN",
}

# Tab category colours
TAB_ANALYSIS = {"red": 0.20, "green": 0.45, "blue": 0.80}
TAB_ACTION   = {"red": 0.90, "green": 0.49, "blue": 0.13}
TAB_SETUP    = {"red": 0.22, "green": 0.66, "blue": 0.36}

# Number formats
CURR  = {"type": "CURRENCY", "pattern": "$#,##0"}
CURR2 = {"type": "CURRENCY", "pattern": "$#,##0.00"}
PCT   = {"type": "PERCENT",  "pattern": "0.0%"}
NUM   = {"type": "NUMBER",   "pattern": "#,##0"}
NUM1  = {"type": "NUMBER",   "pattern": "#,##0.0"}
DATE  = {"type": "DATE",     "pattern": "yyyy-mm-dd"}


def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "bigquery-key.json"
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


# ── Data — one section per channel for each tab ─────────────────────────────

# By Channel Apr vs May
CHANNEL_DATA = {
    "google_ads":    {"apr_spend": 19459, "may_spend": 46265, "apr_leads": 690, "may_leads": 1346, "apr_sqls": 325, "may_sqls": 333,
                      "apr_cpl": 28.2, "may_cpl": 34.4, "apr_cpql": 59.9,  "may_cpql": 138.9, "apr_qual": 0.471, "may_qual": 0.247,
                      "apr_deals": 697, "may_deals": 297, "apr_roas": 8.37, "may_roas": 1.71},
    "meta":          {"apr_spend": 8718,  "may_spend": 12740, "apr_leads": 352, "may_leads": 338,  "apr_sqls": 124, "may_sqls": 146,
                      "apr_cpl": 24.8, "may_cpl": 37.7, "apr_cpql": 70.3, "may_cpql": 87.3, "apr_qual": 0.352, "may_qual": 0.432,
                      "apr_deals": 18,  "may_deals": 10,  "apr_roas": 0.78, "may_roas": 0.39},
    "snapchat":      {"apr_spend": 7951,  "may_spend": 9672,  "apr_leads": 331, "may_leads": 404,  "apr_sqls": 153, "may_sqls": 178,
                      "apr_cpl": 24.0, "may_cpl": 23.9, "apr_cpql": 52.0, "may_cpql": 54.3, "apr_qual": 0.462, "may_qual": 0.441,
                      "apr_deals": 12,  "may_deals": 5,   "apr_roas": 0.53, "may_roas": 0.27},
    "microsoft_ads": {"apr_spend": 1405,  "may_spend": 6768,  "apr_leads": 75,  "may_leads": 74,   "apr_sqls": 36,  "may_sqls": 26,
                      "apr_cpl": 18.7, "may_cpl": 91.5, "apr_cpql": 39.0, "may_cpql": 260.3,"apr_qual": 0.480, "may_qual": 0.351,
                      "apr_deals": 22,  "may_deals": 10,  "apr_roas": 3.08, "may_roas": 0.34},
    "tiktok":        {"apr_spend": 4340,  "may_spend": 5101,  "apr_leads": 121, "may_leads": 160,  "apr_sqls": 67,  "may_sqls": 74,
                      "apr_cpl": 35.9, "may_cpl": 31.9, "apr_cpql": 64.8, "may_cpql": 68.9, "apr_qual": 0.554, "may_qual": 0.463,
                      "apr_deals": 6,   "may_deals": 7,   "apr_roas": 0.65, "may_roas": 0.30},
}

# Top movers per channel
MOVERS_BY_CHANNEL = {
    "google_ads": [
        # name, apr_spend, apr_sqls, apr_cpql, may_spend, may_sqls, may_cpql
        ("PMax_AR_Generic",                              1129, 14, 80.7,  5025, 13, 386.5, "Loser"),
        ("Search_AR_Generic_PricingOffers (new)",        0,    0, None,   6223, 17, 366.2, "Loser"),
        ("Search_E-invoice_AR",                          2715, 39, 69.6,  5732, 43, 133.3, "Loser"),
        ("Search_AR_Brand_v2",                           1249, 15, 83.2,  2426, 17, 142.7, "Loser"),
        ("PMax_AR_Generic_Retargeting",                  1240, 10, 124.0, 4550, 26, 175.0, "Loser"),
        ("PMax_AR_Invoice",                              1806, 26, 69.5,  5082, 46, 110.5, "Loser"),
        ("PMax_AR_E-Invoice (silent death)",             2994, 29, 103.2, 3,    0, None,   "Dead"),
        ("Search_AR_Brand",                              816,  17, 48.0,  2862, 66, 43.4,  "Winner"),
        ("PMax_AR_Invoice_FiveSectors",                  5385, 93, 57.9,  3146, 42, 74.9,  "Holding"),
    ],
    "meta": [
        ("Meta_LeadGen_Prospecting_Lookalike_BrandingEquity_Instantform",1581, 27, 58.5,  3991, 22, 181.4, "Loser"),
        ("Meta_LeadGen_Prospecting_Retargeting_BrandingEquity",          1056, 19, 55.6,  807,  6,  134.4, "Loser"),
        ("Meta_LeadGen_Bookkeeping_Lookalike_MaxmizeLeads",              1685, 29, 58.1,  1594, 32, 49.8,  "Winner"),
        ("Meta_Conversion_Lookalike_Invoice_Websiteform",                1055, 10, 105.5, 825,  21, 39.3,  "Winner"),
    ],
    "snapchat": [
        ("Snapchat_Leadgen_Prospecting_iPhone_Instantform (deal-closer)",2950, 65, 45.4,  1654, 31, 53.4,  "Starved"),
        ("Snapchat_LeadGen_Prospecting_iOS_Instantform_v3",              3285, 90, 36.5,  3035, 74, 41.0,  "Holding"),
        ("Snapchat_Leadgen_Retargeting_Instantform",                     2567, 38, 67.6,  3318, 49, 67.7,  "Holding"),
    ],
    "microsoft_ads": [
        ("Bing_Search_AR_Generic_AccountingSoftware",                    531, 4,  132.8, 1535, 2,   767.4, "Loser"),
        ("Bing_WebsiteTraffic_Search_AR_Generic (IS-strategy)",          0,   0,  None,   1711, 0,  149.0, "Watch"),
    ],
    "tiktok": [
        ("Tiktok_LeadGen_Smart+_Instantform_v2",                          2110, 28, 75.3,  2341, 34, 68.9,  "Winner"),
    ],
}

# Action points per channel
ACTIONS_BY_CHANNEL = {
    "google_ads": [
        ("Pause PMax_AR_Generic — CPQL $386",                              "High",   "Pause",   "OPEN",     "1214865244763906"),
        ("Pause PMax_AR_Generic_Retargeting — $175 CPQL",                  "High",   "Pause",   "OPEN",     "1214864840858564"),
        ("Scale-back Search_E-invoice_AR to $170/d",                       "Medium", "Scale",   "OPEN",     "1214865012809819"),
        ("PMax_AR_E-Invoice — confirmed deliberate pause Apr 20",          "Low",    "Fix",     "RESOLVED", "1214864840866643"),
        ("Pause 3 Generic Search campaigns (audience issue, not LP)",      "High",   "Pause",   "REVISED",  "1214865012784592"),
        ("Confirm LP form parity HubSpot vs WP; await A/B test",           "Medium", "Verify",  "REVISED",  "1214864840803036"),
        ("Build HubSpot LP equivalent for /accounting",                    "Medium", "Launch",  "BLOCKED",  "1214865244777757"),
    ],
    "meta": [
        ("Cut Meta BrandingEquity Lookalike 75%",                          "Medium", "Scale",   "OPEN",     "1214864951334535"),
        ("Test Websiteform variant on 1 more Invoice Lookalike",           "Medium", "Launch",  "OPEN",     "1214865244764431"),
        ("Run controlled LP A/B (HubSpot vs WP), 14d, identical traffic",  "High",   "Test",    "OPEN",     "1214865737696001"),
    ],
    "snapchat": [
        ("RESTORE Snap iPhone Instantform to $185/d + investigate close-rate", "High", "Scale", "OPEN",     "1214864840869199"),
    ],
    "microsoft_ads": [
        ("Pause 5 Bing campaigns launched May 6 with 0 SQLs",              "High",   "Pause",   "OPEN",     "1214865244698718"),
        ("Cut Bing_WebsiteTraffic to $40/d (IS goal)",                     "Medium", "Scale",   "OPEN",     "1214864840869182"),
    ],
}

# Campaign setups per channel (8 staged duplications)
SETUPS_BY_CHANNEL = {
    "meta": [
        # name, daily_budget, objective, bidding, audience, lp, creative, launch_date
        ("Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform",
         30, "OUTCOME_LEADS", "Maximise Leads (no tCPA first 7d, then $50)",
         "Interests + Job titles (Invoice-specific): ZATCA, Tax compliance, E-Invoicing, B2B SaaS + Finance Mgr, Accountant, CFO, Owner SMB. ONE adset, OR-logic, Advantage+ ON.",
         "Meta Instant Form (in-app)",
         "3× video 9:16 + 2× static carousel, Arabic VO",
         "2026-05-17"),
        ("Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2",
         25, "OUTCOME_LEADS (Conversion)", "Cost cap $40",
         "LAL seed [Nexa] Customers Invoice (5891), 3% Customer Lookalike — v1 used 2% SQL LAL",
         "campaigns.qoyod.com/ar/electronic-invoicing (HubSpot LP)",
         "Same as v1 (audience-only change)",
         "2026-05-24"),
        ("Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform",
         25, "OUTCOME_LEADS (Conversion)", "Cost cap $50",
         "LAL seed [Nexa] Customers Bookkeeping (5893), 2% Lookalike",
         "Interim: campaigns.qoyod.com/ar/new-form-free-trial; switch when task #11 ships",
         "Stop chasing invoices / reconciling spreadsheets theme",
         "2026-05-31"),
        ("Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform",
         20, "OUTCOME_LEADS", "Maximise Leads (no tCPA — algo finds pockets)",
         "Interests: F&B, Restaurants, Cafés, Cloud Kitchens, Restaurant Mgmt",
         "Meta Instant Form (Qflavours has no good LP)",
         "F&B imagery: kitchen, POS, dishes",
         "2026-06-07"),
    ],
    "snapchat": [
        ("Snapchat_LeadGen_Invoice_Prospecting_Interest_iOS_Instantform",
         100, "LEAD_GENERATION", "Auto-bid; goal CPA $45 after learning",
         "Snap Interests: Business & Finance, SMB Owners, Tech Early Adopters. iOS only.",
         "Snap Instant Form",
         "Vertical 9:16 6-10s Arabic captions; ZATCA-compliance hook",
         "2026-05-17"),
        ("Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform",
         25, "LEAD_GENERATION", "Auto-bid; goal CPA $40",
         "Broad (no interest layer); iPhone only. Creative carries targeting signal.",
         "Snap Instant Form",
         "Product-anchored: ZATCA Phase 2 deadline",
         "2026-05-24"),
        ("Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_iOS_Instantform",
         75, "LEAD_GENERATION", "Auto-bid; goal CPA $45",
         "Snap Interests: SMB Owners, F&B, Retail, Professional Services, Accounting. iOS 28-50.",
         "Snap Instant Form",
         "Demo-style 9:16 screen recording: Replace your spreadsheets",
         "2026-05-31"),
        ("Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_Android_Instantform",
         50, "LEAD_GENERATION", "Auto-bid; goal CPA $50",
         "Same as iOS Bookkeeping but Android. Launch only after iOS hits CPQL < $60 in 7d.",
         "Snap Instant Form",
         "Same creative as iOS",
         "2026-06-07"),
    ],
}

# Calendar entries per channel
CALENDAR_BY_CHANNEL = {
    "google_ads":    [
        ("2026-05-18", "Pause",    "Pause PMax_AR_Generic + PMax_AR_Generic_Retargeting"),
        ("2026-05-18", "Cut",      "Cut Search_E-invoice_AR to $170/d"),
        ("2026-05-25", "Re-point", "Re-point Generic LP traffic to HubSpot /ar/electronic-invoicing"),
        ("2026-06-01", "Scale",    "PMax_AR_Invoice_FiveSectors +25% budget at same tCPA"),
    ],
    "meta": [
        ("2026-05-17", "Launch", "Meta Invoice Interests $30/d"),
        ("2026-05-18", "Cut",    "Cut BrandingEquity Lookalike 75%; restore Bookkeeping_Lookalike"),
        ("2026-05-24", "Launch", "Meta Invoice Lookalike v2 (Customer LAL 3%)"),
        ("2026-05-31", "Launch", "Meta Bookkeeping Websiteform"),
        ("2026-06-07", "Launch", "Meta Qflavours Interests (gated on Tier-1 < $60 CPQL)"),
        ("2026-06-15", "Launch", "Customer LAL 3% v2 (different seed)"),
    ],
    "snapchat": [
        ("2026-05-17", "Launch",  "Snap Invoice iOS Instantform $100/d"),
        ("2026-05-18", "Restore", "RESTORE Snap iPhone Instantform to $185/d (highest leverage)"),
        ("2026-05-24", "Launch",  "Snap Invoice Broad iPhone $25/d"),
        ("2026-05-31", "Launch",  "Snap Bookkeeping iOS"),
        ("2026-06-07", "Launch",  "Snap Bookkeeping Android (gated)"),
        ("2026-06-15", "Launch",  "Snap iOS Instantform v4 (creative refresh)"),
    ],
    "microsoft_ads": [
        ("2026-05-18", "Pause", "Pause Bing 5-pack launched May 6 (0 SQLs)"),
        ("2026-05-18", "Cut",   "Cut Bing_WebsiteTraffic to $40/d"),
    ],
    "tiktok": [
        ("2026-06-22", "Scale", "Scale Tiktok_LeadGen_Smart+_Instantform_v2 if CPQL holds"),
    ],
}


# ── Helper to build a "stacked channel sections" tab ────────────────────────

def build_stacked_tab(title: str, tab_color: dict, intro_rows: list[list],
                      sections: list[dict], header_label: str = "") -> dict:
    """sections: list of {channel, header, rows, col_formats, conditional}"""
    return {
        "title":     title,
        "tab_color": tab_color,
        "intro":     intro_rows,
        "sections":  sections,
    }


# ── Tab builders (each returns the stacked-tab structure) ───────────────────

def tab_cover():
    return {
        "title": "01 · Cover",
        "tab_color": TAB_ANALYSIS,
        "intro": [
            ["QOYOD PAID MEDIA — PERFORMANCE DASHBOARD"],
            [f"Generated {date.today().isoformat()}  ·  Nexa Performance Agent"],
            [""],
            ["Comparison window: April 1-16 vs May 1-16 (matched apples-to-apples, 16d each)"],
            ["Auto-flags fired: CPQL_REGRESSED  ·  ROAS_REGRESSED  ·  QUAL_DROPPED  ·  LAUNCH_WAVE"],
            [""],
        ],
        "sections": [
            {
                "header": "BLENDED HEADLINE — ALL CHANNELS COMBINED",
                "banner_color": NAVY,
                "banner_text":  WHITE,
                "columns": ["Metric", "April (16d)", "May (16d)", "Δ", "Status"],
                "rows": [
                    ["Spend",     41874, 80547, 0.924,  "OVERSPEND"],
                    ["Leads",     2234,  2323,  0.040,  "OK"],
                    ["SQLs",      1331,  758,   -0.430, "MAJOR DROP"],
                    ["CPQL",      59,    85,    0.440,  "REGRESSED"],
                    ["Qual rate", 0.449, 0.326, -0.274, "DROPPED"],
                    ["ROAS",      4.32,  1.12,  -0.741, "REGRESSED"],
                ],
                "col_formats": [{}, CURR, CURR, PCT, {}],
                "conditional": [
                    {"col_index": 3, "operator": "NUMBER_GREATER", "value": 0,     "color": NEG},
                    {"col_index": 3, "operator": "NUMBER_LESS",    "value": -0.05, "color": NEG},
                ],
            }
        ],
    }


def tab_by_channel():
    sections = []
    for ch in ["google_ads", "meta", "snapchat", "microsoft_ads", "tiktok"]:
        d = CHANNEL_DATA[ch]
        rows = [
            ["Spend",     d["apr_spend"],  d["may_spend"],  (d["may_spend"]  / d["apr_spend"]  - 1) if d["apr_spend"]  else 0],
            ["Leads",     d["apr_leads"],  d["may_leads"],  (d["may_leads"]  / d["apr_leads"]  - 1) if d["apr_leads"]  else 0],
            ["SQLs",      d["apr_sqls"],   d["may_sqls"],   (d["may_sqls"]   / d["apr_sqls"]   - 1) if d["apr_sqls"]   else 0],
            ["CPL",       d["apr_cpl"],    d["may_cpl"],    (d["may_cpl"]    / d["apr_cpl"]    - 1) if d["apr_cpl"]    else 0],
            ["CPQL",      d["apr_cpql"],   d["may_cpql"],   (d["may_cpql"]   / d["apr_cpql"]   - 1) if d["apr_cpql"]   else 0],
            ["Qual rate", d["apr_qual"],   d["may_qual"],   (d["may_qual"]   - d["apr_qual"])],          # absolute pp delta
            ["Deals won", d["apr_deals"],  d["may_deals"],  (d["may_deals"]  / d["apr_deals"]  - 1) if d["apr_deals"]  else 0],
            ["ROAS",      d["apr_roas"],   d["may_roas"],   (d["may_roas"]   / d["apr_roas"]   - 1) if d["apr_roas"]   else 0],
        ]
        sections.append({
            "header":       CH_LABEL[ch],
            "banner_color": CH_COLOR[ch],
            "banner_text":  CH_TEXT[ch],
            "columns":      ["Metric", "April", "May", "Δ"],
            "rows":         rows,
            "col_formats":  [{}, CURR2, CURR2, PCT],
            "conditional": [
                {"col_index": 3, "operator": "NUMBER_GREATER", "value": 0.10,  "color": NEG, "rows": [3, 4]},  # CPL, CPQL bad if up
                {"col_index": 3, "operator": "NUMBER_LESS",    "value": -0.10, "color": POS, "rows": [3, 4]},
            ],
        })
    return {
        "title": "02 · By Channel — Apr vs May",
        "tab_color": TAB_ANALYSIS,
        "intro": [["Each channel as its own table. Δ column = % change Apr → May (qual rate Δ is in percentage points)."]],
        "sections": sections,
    }


def tab_movers():
    sections = []
    for ch in ["google_ads", "meta", "snapchat", "microsoft_ads", "tiktok"]:
        items = MOVERS_BY_CHANNEL.get(ch, [])
        if not items: continue
        rows = []
        for it in items:
            name, a_sp, a_sq, a_cq, m_sp, m_sq, m_cq, tag = it
            cpql_delta = ((m_cq or 0) - (a_cq or 0)) if a_cq and m_cq else (m_cq if m_cq else (-(a_cq or 0)))
            rows.append([name, a_sp, a_sq, a_cq, m_sp, m_sq, m_cq, cpql_delta, tag])
        sections.append({
            "header":       CH_LABEL[ch],
            "banner_color": CH_COLOR[ch],
            "banner_text":  CH_TEXT[ch],
            "columns":      ["Campaign", "Apr spend", "Apr SQLs", "Apr CPQL", "May spend", "May SQLs", "May CPQL", "CPQL Δ", "Verdict"],
            "rows":         rows,
            "col_formats":  [{}, CURR, NUM, CURR2, CURR, NUM, CURR2, CURR2, {}],
            "conditional": [
                {"col_index": 7, "operator": "NUMBER_GREATER", "value": 0, "color": NEG},
                {"col_index": 7, "operator": "NUMBER_LESS",    "value": 0, "color": POS},
                {"col_index": 8, "operator": "TEXT_EQ",        "value": "Loser",  "color": NEG},
                {"col_index": 8, "operator": "TEXT_EQ",        "value": "Winner", "color": POS},
                {"col_index": 8, "operator": "TEXT_EQ",        "value": "Dead",   "color": {"red": 0.5, "green": 0.5, "blue": 0.5}},
            ],
        })
    return {
        "title": "03 · Movers — by Channel",
        "tab_color": TAB_ANALYSIS,
        "intro": [["Top campaigns ranked by CPQL change Apr → May, grouped by channel. Verdict column tags each row."]],
        "sections": sections,
    }


def tab_actions():
    sections = []
    for ch in ["google_ads", "meta", "snapchat", "microsoft_ads"]:
        items = ACTIONS_BY_CHANNEL.get(ch, [])
        if not items: continue
        rows = []
        for desc, prio, type_, status, gid in items:
            rows.append([desc, prio, type_, status, f"https://app.asana.com/0/0/{gid}"])
        sections.append({
            "header":       CH_LABEL[ch],
            "banner_color": CH_COLOR[ch],
            "banner_text":  CH_TEXT[ch],
            "columns":      ["Action", "Priority", "Type", "Status", "Asana URL"],
            "rows":         rows,
            "col_formats":  [{}, {}, {}, {}, {}],
            "conditional": [
                {"col_index": 3, "operator": "TEXT_EQ", "value": "SHIPPED",  "color": POS},
                {"col_index": 3, "operator": "TEXT_EQ", "value": "RESOLVED", "color": POS},
                {"col_index": 3, "operator": "TEXT_EQ", "value": "OPEN",     "color": NEG},
                {"col_index": 3, "operator": "TEXT_EQ", "value": "BLOCKED",  "color": {"red":1, "green":0.9, "blue":0.7}},
                {"col_index": 1, "operator": "TEXT_EQ", "value": "High",     "color": {"red":0.99, "green":0.86, "blue":0.86}},
            ],
        })

    # Add engineering section (channel-less)
    sections.append({
        "header":       "ENGINEERING (CROSS-CHANNEL)",
        "banner_color": {"red": 0.40, "green": 0.40, "blue": 0.40},
        "banner_text":  WHITE,
        "columns":      ["Action", "Priority", "Type", "Status", "Asana URL"],
        "rows": [
            ["ENG: Add impression_share fields to Google + Bing collectors", "High", "Fix", "SHIPPED", "https://app.asana.com/0/0/1214864840871361"],
            ["ENG: Lag-aware CPQL — suppress when open > 30%",               "High", "Fix", "SHIPPED", "https://app.asana.com/0/0/1214865244764259"],
            ["ENG: spend_drift.py — 3 detection rules",                      "High", "Fix", "SHIPPED", "https://app.asana.com/0/0/1214865244779563"],
            ["ENG: launch_policy.py — 1 launch/channel/7d",                  "High", "Fix", "SHIPPED", "https://app.asana.com/0/0/1214864951424904"],
            ["ENG: Switch primary KPI CPL → CPQL",                           "High", "Fix", "SHIPPED", "https://app.asana.com/0/0/1214864951403496"],
            ["Fix GA4 generate_lead event coverage across all LPs",          "High", "Fix", "OPEN",    "https://app.asana.com/0/0/1214865012889339"],
        ],
        "col_formats": [{}, {}, {}, {}, {}],
        "conditional": [
            {"col_index": 3, "operator": "TEXT_EQ", "value": "SHIPPED", "color": POS},
            {"col_index": 3, "operator": "TEXT_EQ", "value": "OPEN",    "color": NEG},
        ],
    })

    return {
        "title": "04 · Action Points — by Channel",
        "tab_color": TAB_ACTION,
        "intro": [["19 Asana tasks grouped by channel. Cross-channel engineering work at the bottom."]],
        "sections": sections,
    }


def tab_calendar():
    sections = []
    for ch in ["google_ads", "meta", "snapchat", "microsoft_ads", "tiktok"]:
        items = CALENDAR_BY_CHANNEL.get(ch, [])
        if not items: continue
        rows = [list(it) for it in items]
        sections.append({
            "header":       CH_LABEL[ch],
            "banner_color": CH_COLOR[ch],
            "banner_text":  CH_TEXT[ch],
            "columns":      ["Date", "Action Type", "Description"],
            "rows":         rows,
            "col_formats":  [DATE, {}, {}],
            "conditional": [
                {"col_index": 1, "operator": "TEXT_EQ", "value": "Pause",   "color": NEG},
                {"col_index": 1, "operator": "TEXT_EQ", "value": "Launch",  "color": POS},
                {"col_index": 1, "operator": "TEXT_EQ", "value": "Scale",   "color": {"red": 0.85, "green": 0.92, "blue": 0.98}},
                {"col_index": 1, "operator": "TEXT_EQ", "value": "Restore", "color": {"red": 1.0,  "green": 0.95, "blue": 0.70}},
            ],
        })
    return {
        "title": "05 · Calendar — by Channel",
        "tab_color": TAB_ACTION,
        "intro": [["Week-by-week through Jun 30 grouped by channel. Each channel respects the 7d launch_policy cooldown."]],
        "sections": sections,
    }


def tab_setups():
    sections = []
    for ch in ["meta", "snapchat"]:
        items = SETUPS_BY_CHANNEL.get(ch, [])
        if not items: continue
        rows = [list(it) for it in items]
        sections.append({
            "header":       CH_LABEL[ch],
            "banner_color": CH_COLOR[ch],
            "banner_text":  CH_TEXT[ch],
            "columns":      ["Campaign Name", "Daily Budget", "Objective", "Bidding", "Audience", "LP / Form", "Creative", "Launch Date"],
            "rows":         rows,
            "col_formats":  [{}, CURR, {}, {}, {}, {}, {}, DATE],
        })
    return {
        "title": "06 · Campaign Setups — by Channel",
        "tab_color": TAB_SETUP,
        "intro": [
            ["8 staged duplications grouped by channel. Staggered 7d per channel (launch_policy enforces)."],
            ["Universal: start PAUSED · one product per campaign · use [Nexa Agent] HubSpot lists · UTM = source/medium/campaign/content."],
            [""],
        ],
        "sections": sections,
    }


def tab_budget():
    # Per-channel budget — already a 1-row-per-channel table, no grouping needed
    return {
        "title": "07 · June Budget",
        "tab_color": TAB_ACTION,
        "intro": [["Per-channel budget allocation — May actual vs June target. Δ% column highlights the reallocation."]],
        "sections": [{
            "header":       "JUNE 2026 ALLOCATION",
            "banner_color": NAVY,
            "banner_text":  WHITE,
            "columns":      ["Channel", "May actual", "May effective (post-pause)", "June target", "Δ%", "Rationale"],
            "rows": [
                ["Google Ads",    93000, 70000, 75000, -0.194, "Pause bad PMax; hold Brand + E-invoice at right size"],
                ["Meta",          24000, 24000, 28000,  0.167, "Scale Bookkeeping_Lookalike + Websiteform; +2 duplications"],
                ["Snapchat",      19000, 19000, 22000,  0.158, "Restore iPhone Instantform; launch Android + Bookkeeping"],
                ["Microsoft Ads", 13000, 8000,  8000,  -0.385, "Pause 5-pack; hold Brand + WebsiteTraffic at cap"],
                ["TikTok",        10000, 10000, 10000,  0,     "Hold; no Tier-1 actions queued"],
                ["LinkedIn",      0,     0,     0,      0,     "Token expired since Mar; revisit Q3"],
                ["TOTAL",         159000, 131000, 143000, -0.101, "Net -10% vs current trend"],
            ],
            "col_formats": [{}, CURR, CURR, CURR, PCT, {}],
            "conditional": [
                {"col_index": 4, "operator": "NUMBER_GREATER", "value": 0,    "color": POS},
                {"col_index": 4, "operator": "NUMBER_LESS",    "value": 0,    "color": NEG},
            ],
        }],
    }


def tab_kpis():
    return {
        "title": "08 · June KPI Targets",
        "tab_color": TAB_ACTION,
        "intro": [["Blended weekly CPQL targets + abort/scale triggers. Blended KPIs only — channel-specific targets in code: config.py CPQL_*."]],
        "sections": [
            {
                "header":       "WEEKLY TARGETS",
                "banner_color": NAVY,
                "banner_text":  WHITE,
                "columns":      ["Week ending", "CPQL target", "Cumulative", "Notes"],
                "rows": [
                    ["2026-05-24", 75, "Reset", "Post-pause cleanup; SDRs catch up on May 15-16 open queue"],
                    ["2026-05-31", 70, "<$72",  "First Tier-1 duplications stabilizing"],
                    ["2026-06-07", 65, "<$69",  "Tier-2 duplications staged; LP A/B running"],
                    ["2026-06-14", 62, "<$66",  "LP question resolved; full duplication portfolio active"],
                    ["2026-06-21", 60, "<$64",  "Scaling phase begins on confirmed winners"],
                    ["2026-06-30", 58, "<$62",  "June final — if hit, sustainable trajectory established"],
                ],
                "col_formats": [DATE, CURR, {}, {}],
            },
            {
                "header":       "ABORT TRIGGERS (auto-pause)",
                "banner_color": {"red": 0.85, "green": 0.18, "blue": 0.18},
                "banner_text":  WHITE,
                "columns":      ["Trigger", "Action"],
                "rows": [
                    ["Single new campaign hits CPQL > $140 by Day 10",                    "Auto-pause via launch_policy enforcement"],
                    ["Blended weekly CPQL doesn't improve > 5% WoW for 2 weeks",          "Freeze new launches; debug attribution"],
                    ["'Lead denies registration' daily spike > 30 (vs baseline 5-10)",    "Freeze new traffic on suspect LP/audience"],
                ],
                "col_formats": [{}, {}],
            },
            {
                "header":       "SCALE TRIGGERS (auto-propose to #approvals)",
                "banner_color": {"red": 0.18, "green": 0.62, "blue": 0.18},
                "banner_text":  WHITE,
                "columns":      ["Trigger", "Action"],
                "rows": [
                    ["Campaign CPQL < channel ACCEPTABLE for 14d AND > 10 SQLs AND IS < 70%", "+25% daily budget"],
                    ["Adset frequency < 1.5 AND CPL stable for 14d",                         "Duplicate to test new audience"],
                    ["Channel CPQL beats target by 20% with budget headroom",                "+20% channel allocation"],
                ],
                "col_formats": [{}, {}],
            },
        ],
    }


def tab_hubspot():
    return {
        "title": "09 · HubSpot Lists",
        "tab_color": TAB_SETUP,
        "intro": [
            ["9 product-segmented Smart Lists in HubSpot. Sync to Meta + Snap Custom Audiences via HubSpot UI."],
            ["Verified live 2026-05-17. Customer Bookkeeping = 683 matches manual ref of 673 (1.5%)."],
            [""],
        ],
        "sections": [
            {
                "header":       "LOOKALIKE SEEDS (CUSTOMERS)",
                "banner_color": {"red": 0.30, "green": 0.60, "blue": 0.30},
                "banner_text":  WHITE,
                "columns":      ["List Name", "List ID", "Members", "Used For"],
                "rows": [
                    ["[Nexa Agent] LAL Seed - Customers Invoice",     5891, 44315, "Meta/Snap Invoice Lookalike base"],
                    ["[Nexa Agent] LAL Seed - Customers Bookkeeping", 5893, 683,   "Meta/Snap Bookkeeping Lookalike base"],
                    ["[Nexa Agent] LAL Seed - Customers Qflavours",   5895, 52,    "Meta/Snap Qflavours Lookalike base"],
                ],
                "col_formats": [{}, NUM, NUM, {}],
            },
            {
                "header":       "LOOKALIKE SEEDS (SQLs — alt to Customers)",
                "banner_color": {"red": 0.30, "green": 0.60, "blue": 0.30},
                "banner_text":  WHITE,
                "columns":      ["List Name", "List ID", "Members", "Used For"],
                "rows": [
                    ["[Nexa Agent] LAL Seed - SQLs Invoice",     5897, 53377, "Alt LAL seed using qualified leads"],
                    ["[Nexa Agent] LAL Seed - SQLs Bookkeeping", 5899, 636,   "Alt LAL seed using qualified leads"],
                    ["[Nexa Agent] LAL Seed - SQLs Qflavours",   5901, 376,   "Alt LAL seed using qualified leads"],
                ],
                "col_formats": [{}, NUM, NUM, {}],
            },
            {
                "header":       "EXCLUSIONS (apply to every prospecting campaign)",
                "banner_color": {"red": 0.60, "green": 0.30, "blue": 0.30},
                "banner_text":  WHITE,
                "columns":      ["List Name", "List ID", "Members", "Used For"],
                "rows": [
                    ["[Nexa Agent] Exclude - All Customers",   5903, 92776,  "Prevent re-marketing to current customers"],
                    ["[Nexa Agent] Exclude - Open Leads",      5904, 295121, "Stop double-marketing active funnel"],
                    ["[Nexa Agent] Exclude - Qoyod Employees", 5905, 756,    "Internal team filter"],
                ],
                "col_formats": [{}, NUM, NUM, {}],
            },
        ],
    }


# ── Sheet builder ───────────────────────────────────────────────────────────

def main():
    creds = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive  = build("drive",  "v3", credentials=creds, cache_discovery=False)

    print(f"[sheet] creating '{SHEET_NAME}' in shared folder ...")
    file = drive.files().create(
        body={"name": SHEET_NAME, "mimeType": "application/vnd.google-apps.spreadsheet",
              "parents": [SHARED_FOLDER_ID]},
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()
    sid = file["id"]
    print(f"[drive] created id={sid}")

    tabs = [tab_cover(), tab_by_channel(), tab_movers(), tab_actions(),
            tab_calendar(), tab_setups(), tab_budget(), tab_kpis(), tab_hubspot()]

    # Add all sheets with proper colors
    add_reqs = [
        {"addSheet": {"properties": {"title": t["title"], "tabColor": t["tab_color"]}}}
        for t in tabs
    ]
    resp = sheets.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": add_reqs}).execute()
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

    # Build the values + formatting for each tab
    data_payload = []
    fmt_requests = []
    GAP = 1  # blank rows between sections

    for tab, sheet_id in zip(tabs, sheet_ids):
        title  = tab["title"]
        intro  = tab.get("intro", [])
        n_cols = max(len(s["columns"]) for s in tab["sections"])

        all_rows = []
        # Intro
        for r in intro:
            all_rows.append(r + [""] * (n_cols - len(r)))

        # Track which rows are banners/headers/data for formatting
        section_specs = []  # [(banner_row, header_row, data_start, data_end, section_def, n_cols)]
        for sec in tab["sections"]:
            cols = sec["columns"]
            sec_n = len(cols)
            # Banner row (channel name)
            banner_row_idx = len(all_rows)
            all_rows.append([sec["header"]] + [""] * (n_cols - 1))
            # Column header row
            header_row_idx = len(all_rows)
            all_rows.append(cols + [""] * (n_cols - sec_n))
            # Data rows
            data_start = len(all_rows)
            for row in sec["rows"]:
                padded = list(row) + [""] * (n_cols - len(row))
                all_rows.append(padded)
            data_end = len(all_rows)
            # Gap
            for _ in range(GAP):
                all_rows.append([""] * n_cols)
            section_specs.append((banner_row_idx, header_row_idx, data_start, data_end, sec, sec_n))

        data_payload.append({
            "range":         f"'{title}'!A1",
            "majorDimension":"ROWS",
            "values":        all_rows,
        })

        # Formatting per tab — freeze first row of first section
        first_banner_row = section_specs[0][0]
        fmt_requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id,
                               "gridProperties": {"frozenRowCount": first_banner_row}},
                "fields": "gridProperties.frozenRowCount",
            }
        })

        # Intro rows — grey background, bold
        if intro:
            fmt_requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": len(intro),
                              "startColumnIndex": 0, "endColumnIndex": n_cols},
                    "cell": {"userEnteredFormat": {"backgroundColor": GREY,
                                                    "textFormat": {"bold": True, "fontSize": 11}}},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })

        # Per-section formatting
        for banner_row_idx, header_row_idx, data_start, data_end, sec, sec_n in section_specs:
            # 1. Banner row — channel-coloured, merged across all columns, bold, big
            fmt_requests.append({
                "mergeCells": {
                    "range": {"sheetId": sheet_id, "startRowIndex": banner_row_idx,
                              "endRowIndex": banner_row_idx + 1,
                              "startColumnIndex": 0, "endColumnIndex": n_cols},
                    "mergeType": "MERGE_ALL",
                }
            })
            fmt_requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": banner_row_idx,
                              "endRowIndex": banner_row_idx + 1,
                              "startColumnIndex": 0, "endColumnIndex": n_cols},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": sec["banner_color"],
                        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": sec["banner_text"]},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "padding": {"top": 8, "bottom": 8, "left": 12, "right": 12},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,padding)",
                }
            })
            fmt_requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "ROWS",
                              "startIndex": banner_row_idx, "endIndex": banner_row_idx + 1},
                    "properties": {"pixelSize": 36},
                    "fields": "pixelSize",
                }
            })

            # 2. Column header row — navy bg, white text, bold
            fmt_requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": header_row_idx,
                              "endRowIndex": header_row_idx + 1,
                              "startColumnIndex": 0, "endColumnIndex": sec_n},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": NAVY,
                        "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": WHITE},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            })

            # 3. Per-column number formats on data range
            for col_idx, fmt in enumerate(sec.get("col_formats", [])):
                if not fmt: continue
                fmt_requests.append({
                    "repeatCell": {
                        "range": {"sheetId": sheet_id,
                                  "startRowIndex": data_start, "endRowIndex": data_end,
                                  "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1},
                        "cell": {"userEnteredFormat": {"numberFormat": fmt}},
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })

            # 4. Banded rows
            fmt_requests.append({
                "addBanding": {
                    "bandedRange": {
                        "range": {"sheetId": sheet_id,
                                  "startRowIndex": data_start, "endRowIndex": data_end,
                                  "startColumnIndex": 0, "endColumnIndex": sec_n},
                        "rowProperties": {
                            "firstBandColor": WHITE, "secondBandColor": PALE,
                        },
                    }
                }
            })

            # 5. Conditional formatting
            for cond in sec.get("conditional", []):
                rules_rows = cond.get("rows", None)  # optional subset of data rows
                if rules_rows is not None:
                    # Apply only to specific data row indices
                    row_starts = [data_start + r for r in rules_rows if data_start + r < data_end]
                else:
                    row_starts = list(range(data_start, data_end))
                if not row_starts: continue
                # Group consecutive
                ranges = []
                cur_start = row_starts[0]
                prev = cur_start
                for r in row_starts[1:]:
                    if r == prev + 1:
                        prev = r
                    else:
                        ranges.append((cur_start, prev + 1))
                        cur_start = r
                        prev = r
                ranges.append((cur_start, prev + 1))

                col_idx = cond["col_index"]
                for s_row, e_row in ranges:
                    fmt_requests.append({
                        "addConditionalFormatRule": {
                            "rule": {
                                "ranges": [{
                                    "sheetId": sheet_id,
                                    "startRowIndex": s_row, "endRowIndex": e_row,
                                    "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
                                }],
                                "booleanRule": {
                                    "condition": {
                                        "type":   cond["operator"],
                                        "values": [{"userEnteredValue": str(cond["value"])}],
                                    },
                                    "format": {"backgroundColor": cond["color"]},
                                }
                            },
                            "index": 0,
                        }
                    })

        # Auto-resize columns
        fmt_requests.append({
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS",
                               "startIndex": 0, "endIndex": n_cols},
            }
        })

    # Write data
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={"valueInputOption": "USER_ENTERED", "data": data_payload},
    ).execute()
    print(f"[sheet] wrote {len(tabs)} tabs")

    # Apply formatting (chunked)
    chunk_size = 50
    total = 0
    for i in range(0, len(fmt_requests), chunk_size):
        chunk = fmt_requests[i:i+chunk_size]
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sid, body={"requests": chunk}
        ).execute()
        total += len(chunk)
    print(f"[sheet] applied {total} formatting requests")

    print()
    print("=" * 70)
    print(f"  ✅ Done.  URL: {file['webViewLink']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
