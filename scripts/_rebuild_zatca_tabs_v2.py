"""Rebuild tabs 13 + 14 as PURE flat tables to match the format of tabs
02-07 (which are TSV-driven: row 1 = column headers, rows 2-N = data;
no title row, no blank rows, no sections).
"""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "certs/bigquery-key.json"
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


# ── Tab 13 — flat campaign table ───────────────────────────────────────────
TAB_13 = [
    ["campaign", "id", "status", "budget_usd_per_day", "channel", "language",
     "intent", "ar_keywords", "en_keywords", "sitelinks", "callouts", "snippets",
     "call_extension", "obs_audiences", "conversion_goal", "landing_page",
     "ar_adgroup_paused_kw", "en_adgroup_paused_kw", "bidding"],
    ["Google_Search_AREN_ZATCAPhase2_Broad",     "23851270716", "ENABLED", 100, "search", "AREN",
     "direct_phase2_buyer", 12, 10, 5, 10, 4, "8004330088", 7, "hubspot_lead",
     "lp.qoyod.com/einvoice-integration", 0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_ZATCAVendorShop_Broad", "23861101390", "PAUSED", 80, "search", "AREN",
     "comparison_shopper", 10, 4, 5, 10, 4, "8004330088", 7, "hubspot_lead",
     "lp.qoyod.com/einvoice-integration", 0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_ZATCACompetitor_Broad", "23861965426", "PAUSED", 60, "search", "AREN",
     "competitor_conquest", 7, 6, 6, 10, 4, "8004330088", 7, "hubspot_lead",
     "lp.qoyod.com/einvoice-integration", 7, 5, "MAXIMIZE_CONVERSIONS"],
]

# ── Tab 14 — flat action log ───────────────────────────────────────────────
TAB_14 = [
    ["date", "campaign_scope", "action", "detail"],
    ["2026-05-17", "all",              "account_selection",
     "Acc1 (1513020554) selected over Acc2: 48.4% IS, 1.48x ROAS vs 27.2%, 1.24x"],
    ["2026-05-17", "ZATCAPhase2",      "campaign_created",
     "14 kw (6 EXACT + 8 PHRASE), 18 negatives, $50/d, tCPA $90"],
    ["2026-05-17", "ZATCAVendorShop",  "campaign_created",
     "15 kw, 18 negatives, $35/d, tCPA $100"],
    ["2026-05-17", "all_zatca",        "display_network_off",
     "target_content_network=False, target_partner_search_network=False"],
    ["2026-05-17", "all_zatca",        "geo_language_locked",
     "Saudi only, Arabic + English"],
    ["2026-05-17", "ZATCAPhase2",      "rsa_headlines_fixed",
     "Replaced 2 headlines exceeding 30 chars"],
    ["2026-05-17", "ZATCAPhase2,ZATCAVendorShop", "extensions_added_v1",
     "5 sitelinks, 9 callouts, 2 snippets, 1 call (8004330088)"],
    ["2026-05-17", "all_zatca",        "wrong_phone_removed",
     "Placeholder +966112345678 unlinked; kept real Qoyod 800: 8004330088"],
    ["2026-05-18", "ZATCACompetitor",  "campaign_created",
     "16 kw (6 EXACT + 10 PHRASE), 18 negatives, $25/d, tCPA $110"],
    ["2026-05-18", "ZATCACompetitor",  "assets_reused_plus_2_new",
     "Reused C1 19 assets; added قارن قيود بالمنافسين + لماذا الشركات تنتقل إلينا"],
    ["2026-05-18", "all_zatca",        "utm_suffix_canonical_applied",
     "final_url_suffix set at campaign level; RSAs stripped of hardcoded UTMs"],
    ["2026-05-18", "ZATCAVendorShop,ZATCACompetitor", "tcpa_stripped",
     "Moved to pure MAXIMIZE_CONVERSIONS — no target for first 30d learning"],
    ["2026-05-18", "all_zatca",        "budgets_bumped",
     "C1 $50->$100, C2 $35->$80, C3 $25->$60 — supports >=3x tCPA when added later"],
    ["2026-05-18", "all_zatca",        "renamed_AR_to_AREN",
     "Per CLAUDE.md naming convention for mixed Arabic+English campaigns"],
    ["2026-05-18", "all_zatca",        "split_ar_en_adgroups",
     "Each campaign now has _AR_AdGroup + _EN_AdGroup with language-matched RSA"],
    ["2026-05-18", "all_zatca",        "high_volume_kw_added",
     "5 AR additions: 3 to C1, 1 to C2, 1 to C3 (from Keyword Planner)"],
    ["2026-05-18", "all_zatca",        "lp_anchored_sitelinks_added",
     "أسعار الفاتورة (#pricing), اربط منشأتك بـ4 خطوات (#integration), مميزات الفاتورة (#features)"],
    ["2026-05-18", "all_zatca",        "sitelink_dedupe",
     "Kept higher-converting wording per anchor"],
    ["2026-05-18", "all_zatca",        "arabic_snippets_added",
     "Types AR + Service catalog AR alongside the EN versions"],
    ["2026-05-18", "ZATCACompetitor",  "rewaa_brand_kw_added",
     "رواء (49,500/mo), منصة رواء (12,100), رواء المحاسبي (1,000), برنامج رواء (880), رواء منصة (590)"],
    ["2026-05-18", "ZATCACompetitor",  "login_negatives_added",
     "تسجيل الدخول, تسجيل دخول, login (BROAD) — block existing-user search intent"],
    ["2026-05-18", "ZATCACompetitor",  "rarely_served_paused",
     "7 AR + 5 EN long-tails paused — Google flagged too niche to serve"],
    ["2026-05-18", "all_zatca",        "in_market_audiences_attached",
     "7 audiences as observation (bid_only=True): Financial Planning, Tax Prep, Accounting Software, Business Services, Enterprise Software, ERP Solutions, Network & Enterprise Security"],
]


def main():
    creds  = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    tab_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    target_ids = {t: tab_ids[t] for t in ("13 ZATCA Setup", "14 ZATCA Action Log") if t in tab_ids}
    print(f"target tabs: {list(target_ids.keys())}")

    # Clear
    for title in target_ids:
        sheets.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range=f"'{title}'!A1:Z500",
        ).execute()

    # Write flat tables
    data = [
        {"range": "'13 ZATCA Setup'!A1",      "majorDimension": "ROWS", "values": TAB_13},
        {"range": "'14 ZATCA Action Log'!A1", "majorDimension": "ROWS", "values": TAB_14},
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print("[step 2] wrote flat-table content")

    # Format header row only (row 1): bold + light-blue background. Freeze row 1.
    fmt = []
    for title, sid in target_ids.items():
        fmt.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        })
        fmt.append({
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.91, "green": 0.93, "blue": 0.96},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
        # Auto-resize all columns
        fmt.append({
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sid, "dimension": "COLUMNS",
                               "startIndex": 0, "endIndex": 20}
            }
        })

    sheets.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": fmt}).execute()
    print("[step 3] formatting applied")
    print(f"\n  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
