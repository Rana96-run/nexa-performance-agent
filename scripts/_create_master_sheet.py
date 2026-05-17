"""Create the master Google Sheet inside the shared Drive folder. Writes
12 tabs covering Apr/May analysis + June plan + campaign setups + HubSpot
lists + Asana actions. This is the living dashboard for paid-media perf."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SHARED_FOLDER_ID = "1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74"
SHEET_NAME       = "Qoyod Paid Media — Performance, Plan & Setups"
SHARE_WITH       = "rana.khalid@qoyod.com"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "bigquery-key.json"
    if not os.path.exists(key_path):
        raise SystemExit(f"Credentials file not found: {key_path}")
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


# ── Tab content builders ────────────────────────────────────────────────────

def _read_tsv(name: str) -> list[list]:
    p = Path(__file__).parent / "_apr_vs_may_2026_sheet" / name
    if not p.exists():
        return [["(file not found)"]]
    with open(p, encoding="utf-8") as f:
        return [r for r in csv.reader(f, delimiter="\t")]


def tab_index() -> list[list]:
    return [
        ["Qoyod Paid Media — Performance, Plan & Setups"],
        [f"Generated {date.today().isoformat()} by Nexa Performance Agent"],
        [""],
        ["Tab", "Purpose"],
        ["01 Index",                "this page"],
        ["02 Headline Apr-vs-May",  "May 2026 first-16d vs April first-16d"],
        ["03 By Channel",           "Same comparison, split by channel"],
        ["04 Campaign Movers",      "Top 20 CPQL regressions Apr → May"],
        ["05 Landing Pages",        "LP performance (HubSpot vs WP)"],
        ["06 Daily Curve",          "Daily spend / leads / SQLs / CPQL"],
        ["07 Action Points",        "19 Asana tasks + status"],
        ["08 June Plan",            "Week-by-week calendar + scenarios"],
        ["09 June Budget",          "Per-channel budget allocation"],
        ["10 June KPI Targets",     "Weekly CPQL targets through June 30"],
        ["11 Campaign Setups",      "Full 8-duplication spec (Meta + Snap)"],
        ["12 HubSpot Lists",        "9 Smart Lists for Meta/Snap LAL + exclusion"],
    ]


def tab_june_plan() -> list[list]:
    return [
        ["JUNE 2026 PLAN"],
        [""],
        ["1. Current state"],
        ["May 1-16 vs April 1-16:  Spend +92%  Leads +4%  SQLs -43%  CPQL +44%  ROAS -74%"],
        ["Auto-flags fired: CPQL_REGRESSED, ROAS_REGRESSED, QUAL_DROPPED, LAUNCH_WAVE"],
        [""],
        ["2. Root cause"],
        ["• Launch wave May 4-10 (8 new Generic/IS campaigns in 6 days, no observation gap)"],
        ["• Bing 5-pack May 6 (zero SQLs after 10+ days)"],
        ["• PMax_AR_Generic scaled while already above pause threshold"],
        ["• WP /accounting LP ramped without validation (camp-mix confounded)"],
        ["• Snap iPhone Instantform budget halved (deal-closer starved)"],
        [""],
        ["3. Status-quo forecast (do nothing)"],
        ["End May",      "$158,698", "1,497 SQLs", "$82 CPQL", "1.16x ROAS"],
        ["End June",     "$156,302", "1,478 SQLs", "$82 CPQL", "1.16x ROAS"],
        [""],
        ["4. With-actions forecast (if 19 Asana tasks execute)"],
        ["Daily spend reallocated", "$1,935/day"],
        ["Monthly reallocated",     "$58,050"],
        ["Net SQL gain from reallocation", "+20.4/day"],
        ["Plus 8 duplication launches",    "+6.9/day"],
        ["Projected June CPQL", "~$53 (-35.7% vs status quo)"],
        ["Realistic range (execution friction)", "$60–$70"],
        [""],
        ["5. Week-by-week calendar"],
        ["Week of", "Channel", "Action"],
        ["May 18", "google_ads",  "Pause PMax_AR_Generic + PMax_AR_Generic_Retargeting"],
        ["May 18", "google_ads",  "Cut Search_E-invoice_AR to $170/d"],
        ["May 18", "meta",        "Cut BrandingEquity Lookalike 75%; restore Bookkeeping_Lookalike"],
        ["May 18", "microsoft",   "Pause Bing 5-pack"],
        ["May 18", "snapchat",    "**RESTORE Snap iPhone Instantform to $185/d** (highest leverage)"],
        ["May 17", "meta+snap",   "LAUNCH: Meta Invoice Interests + Snap Invoice iOS"],
        ["May 25", "google_ads",  "Re-point Generic LP to HubSpot /ar/electronic-invoicing"],
        ["May 24", "meta+snap",   "LAUNCH: Meta Invoice Lookalike v2 + Snap Invoice Broad iPhone"],
        ["Jun 1",  "meta+snap",   "LAUNCH: Meta Bookkeeping Websiteform + Snap Bookkeeping iOS"],
        ["Jun 1",  "landing_page","LP A/B test (task #19) starts: HubSpot vs WP on identical traffic"],
        ["Jun 1",  "google_ads",  "Scale: PMax_AR_Invoice_FiveSectors +25% budget @ same tCPA"],
        ["Jun 8",  "meta+snap",   "LAUNCH: Meta Qflavours + Snap Bookkeeping Android (gated on Tier-1 < $60 CPQL)"],
        ["Jun 8",  "snapchat",    "Add Snap Android variant of iPhone winner"],
        ["Jun 15", "meta+snap",   "LAUNCH: Customer Lookalike 3% v2 + Snap iOS Instantform v4 (creative refresh)"],
        ["Jun 22+", "all",        "Scaling phase: top-3 winners +30% budget every 4 days; losers pause"],
    ]


def tab_june_budget() -> list[list]:
    return [
        ["JUNE 2026 BUDGET ALLOCATION"],
        [""],
        ["Channel", "May actual", "May effective (after pauses)", "June target", "Δ", "Rationale"],
        ["Google Ads",     "$93,000", "$70,000",  "$75,000",  "-19%", "Pause bad PMax; hold Brand + E-invoice at right size"],
        ["Meta",           "$24,000", "$24,000",  "$28,000",  "+17%", "Scale Bookkeeping_Lookalike + Websiteform; +2 duplications"],
        ["Snapchat",       "$19,000", "$19,000",  "$22,000",  "+16%", "Restore iPhone Instantform; launch Android + Bookkeeping"],
        ["Microsoft Ads",  "$13,000", "$8,000",   "$8,000",   "-38%", "Pause 5-pack; hold Brand + WebsiteTraffic at cap"],
        ["TikTok",         "$10,000", "$10,000",  "$10,000",  "0%",   "Hold; no Tier-1 actions queued"],
        ["LinkedIn",       "$0",      "$0",       "$0",       "0%",   "Token expired since Mar; revisit Q3"],
        ["TOTAL",          "$159,000","$131,000", "$143,000", "-10%", "Net -10% vs current trend; reallocated to higher-CPQL spend"],
        [""],
        ["Expected outcome on $143k spend at $58 CPQL target: ~2,466 SQLs (vs status-quo 1,478 = +67% volume at lower cost)"],
    ]


def tab_june_kpi() -> list[list]:
    return [
        ["WEEKLY KPI TARGETS — JUNE 2026"],
        [""],
        ["Week ending", "Blended CPQL target", "Notes"],
        ["May 24",  "< $75", "Post-pause cleanup; SDRs catch up on May 15-16 open queue"],
        ["May 31",  "< $70", "First Tier-1 duplications stabilizing"],
        ["Jun 7",   "< $65", "Tier-2 duplications staged; LP A/B running"],
        ["Jun 14",  "< $62", "LP question resolved; full duplication portfolio active"],
        ["Jun 21",  "< $60", "Scaling phase begins on confirmed winners"],
        ["Jun 30",  "< $58", "June final — if hit, sustainable trajectory"],
        [""],
        ["ABORT TRIGGERS (auto-pause)"],
        ["• Any single new campaign hits CPQL > $140 by Day 10 → pause (launch_policy enforces 7d gap)"],
        ["• Blended weekly CPQL doesn't improve > 5% WoW for 2 weeks → freeze new launches, debug"],
        ["• 'Lead denies registration' daily spike > 30 → freeze new traffic on suspect LP/audience"],
        [""],
        ["SCALE TRIGGERS (auto-propose to #approvals)"],
        ["• Campaign CPQL < channel ACCEPTABLE for 14d AND > 10 SQLs AND IS < 70% → +25% daily budget"],
        ["• Adset frequency < 1.5 AND CPL stable for 14d → duplicate to test new audience variation"],
        ["• Whole channel CPQL beats target by 20% with budget headroom → +20% channel allocation"],
    ]


CAMPAIGN_SETUPS = [
    # name, channel, budget/day, objective, bidding, audience, LP, creative, notes
    ("Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform", "meta", "$30/d",
     "OUTCOME_LEADS", "Maximise Leads (no tCPA first 7d)",
     "Interests (Invoice-specific): ZATCA, Tax compliance, E-Invoicing, B2B SaaS, Saudi VAT, Fatoora + Job titles: Finance Manager, Accountant, CFO, Owner SMB. ONE adset, OR-logic, Advantage+ Audience ON.",
     "Meta Instant Form (in-app, no LP)",
     "3× video 9:16 + 2× static carousel. Arabic VO. CTA 'Free trial'.",
     "Exclude: [Nexa Agent] Exclude - All Customers + Exclude - Open Leads. LAL not used here (Interests-based)."),

    ("Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2", "meta", "$25/d",
     "OUTCOME_LEADS (Conversion)", "Cost cap $40",
     "LAL seed: [Nexa Agent] LAL Seed - Customers Invoice (listId 5891). 3% Lookalike (v1 used 2% SQL Lookalike — v2 tests Customer 3%).",
     "campaigns.qoyod.com/ar/electronic-invoicing (HubSpot LP, $98 CPQL proven)",
     "Same creative bucket as v1 — only the audience is changed.",
     "PIXEL VERIFY before launch: Qoyod_CRM_PIXEL 1782671302631317 + Qoyod_Web_PIXEL 3036579196577051 fire Lead event."),

    ("Snapchat_LeadGen_Invoice_Prospecting_Interest_iOS_Instantform", "snapchat", "$100/d",
     "LEAD_GENERATION", "Auto-bid; set goal CPA $45 after learning",
     "Snap Interest categories: Business & Finance, SMB Owners, Technology Early Adopters. iOS only. NOT Bookkeeping lifestyle bundle.",
     "Snap Instant Form (in-app)",
     "Vertical 9:16, 6-10s, Arabic captions burned-in. ZATCA-compliance hook.",
     "Exclude: Snap Audience Match from CRM customer list."),

    ("Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform", "snapchat", "$25/d",
     "LEAD_GENERATION", "Auto-bid; goal CPA $40",
     "Broad (no interest layer); iPhone only. Creative carries the targeting signal.",
     "Snap Instant Form",
     "Product-anchored: 'ZATCA Phase 2 deadline — are you ready?'",
     "Algorithm finds Invoice buyers via creative; do not narrow audience."),

    ("Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform", "meta", "$25/d",
     "OUTCOME_LEADS (Conversion)", "Cost cap $50",
     "LAL seed: [Nexa Agent] LAL Seed - Customers Bookkeeping (listId 5893). 2% Lookalike. Saudi Arabia, age 25-55.",
     "GATING — campaigns.qoyod.com/ar/new-form-free-trial as interim; switch when Bookkeeping HubSpot LP ships (task #11)",
     "Bookkeeping-specific creative: 'Stop chasing invoices and reconciling spreadsheets'",
     "Different theme from Invoice — bookkeeping pain points (cash flow, multi-currency, ZATCA reporting)."),

    ("Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_iOS_Instantform", "snapchat", "$75/d",
     "LEAD_GENERATION", "Auto-bid; goal CPA $45",
     "Snap Interests: SMB Owners, Restaurants & F&B, Retail, Professional Services, Accounting. NOT Tax/ZATCA. Age 28-50, iOS.",
     "Snap Instant Form",
     "Demo-style 9:16, screen recording of dashboard. 'Replace your spreadsheets.'",
     "Exclude: Snap CRM customer match."),

    ("Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform", "meta", "$20/d",
     "OUTCOME_LEADS", "Maximise Leads (no tCPA — let algo find pockets)",
     "Interests: F&B, Restaurants, Cafés, Cloud Kitchens, Restaurant Management, F&B Owners. NOT general accounting interests.",
     "Meta Instant Form (Qflavours has no good LP — /qf is killed)",
     "F&B-specific imagery (kitchen, POS, dishes); NOT accounting/spreadsheets.",
     "Smallest budget — Qflavours is the experiment, not the bet."),

    ("Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_Android_Instantform", "snapchat", "$50/d",
     "LEAD_GENERATION", "Auto-bid; goal CPA $50",
     "Same as iOS Bookkeeping but Android device. Launch only after iOS version hits CPQL < $60 in 7d.",
     "Snap Instant Form",
     "Same creative as iOS",
     "Smaller starting budget since Android cohort untested."),
]


def tab_campaign_setups() -> list[list]:
    rows = [
        ["CAMPAIGN FULL SETUPS — 8 staged duplications"],
        [""],
        ["Name", "Channel", "Daily Budget", "Objective", "Bidding", "Audience", "LP / Form", "Creative", "Notes"],
    ]
    rows.extend(CAMPAIGN_SETUPS)
    rows.append([""])
    rows.append(["UNIVERSAL RULES (apply to every campaign above):"])
    rows.append(["• Start PAUSED. Enable manually after creative + audience loaded."])
    rows.append(["• One product per campaign. No audience overlap between products."])
    rows.append(["• Lookalike seeds use product-segmented HubSpot lists (see Tab 12)."])
    rows.append(["• Exclude All Customers + Open Leads + Qoyod Employees on every prospecting campaign."])
    rows.append(["• UTM format: source={channel} medium=cpc campaign={CampaignName} content={AdName}"])
    rows.append(["• Stagger 7 days per channel (executors/launch_policy.py enforces this)."])
    return rows


def tab_hubspot_lists() -> list[list]:
    return [
        ["HUBSPOT SMART LISTS — for Meta/Snap Custom Audience sync"],
        [""],
        ["List name", "listId", "Members (2026-05-17)", "Type", "Used as"],
        ["[Nexa Agent] LAL Seed - Customers Invoice",     "5891", "44,315", "LAL seed", "Meta/Snap Invoice Lookalike base"],
        ["[Nexa Agent] LAL Seed - Customers Bookkeeping", "5893",    "683", "LAL seed", "Meta/Snap Bookkeeping Lookalike base"],
        ["[Nexa Agent] LAL Seed - Customers Qflavours",   "5895",     "52", "LAL seed", "Meta/Snap Qflavours Lookalike base"],
        ["[Nexa Agent] LAL Seed - SQLs Invoice",          "5897", "53,377", "LAL seed (SQL)", "Alt seed using qualified leads"],
        ["[Nexa Agent] LAL Seed - SQLs Bookkeeping",      "5899",    "636", "LAL seed (SQL)", "Alt seed using qualified leads"],
        ["[Nexa Agent] LAL Seed - SQLs Qflavours",        "5901",    "376", "LAL seed (SQL)", "Alt seed using qualified leads"],
        ["[Nexa Agent] Exclude - All Customers",          "5903", "92,776", "Exclusion",      "Apply to every prospecting campaign"],
        ["[Nexa Agent] Exclude - Open Leads",             "5904","295,121", "Exclusion",      "Stop double-marketing active funnel"],
        ["[Nexa Agent] Exclude - Qoyod Employees",        "5905",    "756", "Exclusion",      "Internal team filter"],
        [""],
        ["MANUAL NEXT STEP — sync these to Meta + Snap Custom Audiences"],
        ["Meta: HubSpot UI → Marketing → Ads → for each list → Sync to Meta. Creates a corresponding Custom Audience."],
        ["Snap: HubSpot UI → Export each list as CSV (hashed email) → Snap Business Manager → Audiences → Customer Match → Upload."],
    ]


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    creds = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive  = build("drive",  "v3", credentials=creds, cache_discovery=False)

    print(f"[sheet] creating '{SHEET_NAME}' in shared folder {SHARED_FOLDER_ID} ...")

    # 1) Create the spreadsheet via Drive API (bypasses SA "no My Drive" quota
    # issue — files.create with explicit parents=[shared folder] works when
    # the SA has Editor permission on the folder)
    file_meta = {
        "name":     SHEET_NAME,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents":  [SHARED_FOLDER_ID],
    }
    try:
        file = drive.files().create(
            body=file_meta,
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        print(f"[drive] CREATE failed: {e}")
        print("       Check: is the service account email an Editor on the shared folder?")
        print(f"       Folder: https://drive.google.com/drive/folders/{SHARED_FOLDER_ID}")
        return None

    sid = file["id"]
    web_url = file["webViewLink"]
    print(f"[drive] created via Drive API id={sid}")

    # Now add the tabs via Sheets API (this works once the file exists)
    tabs = [
        ("01 Index",                tab_index()),
        ("02 Headline Apr-vs-May",  _read_tsv("01_headline.tsv")),
        ("03 By Channel",           _read_tsv("02_by_channel_16d.tsv")),
        ("04 Campaign Movers",      _read_tsv("03_campaign_movers.tsv")),
        ("05 Landing Pages",        _read_tsv("04_landing_pages.tsv")),
        ("06 Daily Curve",          _read_tsv("05_daily_curve.tsv")),
        ("07 Action Points",        _read_tsv("07_action_points.tsv")),
        ("08 June Plan",            tab_june_plan()),
        ("09 June Budget",          tab_june_budget()),
        ("10 June KPI Targets",     tab_june_kpi()),
        ("11 Campaign Setups",      tab_campaign_setups()),
        ("12 HubSpot Lists",        tab_hubspot_lists()),
    ]

    # Create all the tabs (one batchUpdate after the file exists)
    add_sheet_requests = [
        {"addSheet": {"properties": {"title": t}}}
        for t, _ in tabs
    ]
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": add_sheet_requests},
    ).execute()
    # Then delete the default "Sheet1" that was created with the file
    try:
        meta = sheets.spreadsheets().get(spreadsheetId=sid).execute()
        for s in meta.get("sheets", []):
            if s["properties"]["title"] == "Sheet1":
                sheets.spreadsheets().batchUpdate(
                    spreadsheetId=sid,
                    body={"requests": [{"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]},
                ).execute()
                print("[sheet] removed default Sheet1")
                break
    except HttpError as e:
        print(f"[sheet] Sheet1 cleanup skipped: {e}")

    # 3) Write each tab
    data = []
    for tab_name, rows in tabs:
        if not rows: continue
        data.append({
            "range":         f"'{tab_name}'!A1",
            "majorDimension":"ROWS",
            "values":        rows,
        })
        print(f"[sheet]   queued '{tab_name}': {len(rows)} rows")
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print(f"[sheet] all tabs written")

    # 4) Share with team
    try:
        drive.permissions().create(
            fileId=sid,
            body={"type": "user", "role": "writer", "emailAddress": SHARE_WITH},
            sendNotificationEmail=False,
            fields="id",
        ).execute()
        print(f"[share] granted writer access to {SHARE_WITH}")
    except HttpError as e:
        print(f"[share] failed: {e}")

    print()
    print("=" * 70)
    print(f"  ✅ Done.  URL: {web_url}")
    print("=" * 70)
    return web_url


if __name__ == "__main__":
    main()
