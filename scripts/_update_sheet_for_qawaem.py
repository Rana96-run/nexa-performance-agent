"""Update master sheet to include the new Qawaem (Decision 236) campaign:
  - Tab 13: add a row for Google_Search_AR_FinancialStatemnt
  - Tab 14: append action log entries for May 19 (Qawaem campaign + bundle)
  - Tab 07: add Qawaem line to Google Ads spend ($120/d → $3,600/mo)
"""
import os, sys
from datetime import date
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "certs/bigquery-key.json"
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


# ── Renamed tab 13 (was 'ZATCA Setup' — now covers Compliance Portfolio) ───
TAB_13_ROWS = [
    ["campaign", "id", "status", "budget_usd_per_day", "channel", "language",
     "intent", "ar_keywords", "en_keywords", "sitelinks", "callouts", "snippets",
     "call_extension", "obs_audiences", "user_list_exclusions",
     "conversion_goal", "landing_page",
     "ar_adgroup_paused_kw", "en_adgroup_paused_kw", "bidding"],
    # ZATCA campaigns
    ["Google_Search_AREN_ZATCAPhase2_Broad",     "23851270716", "ENABLED", 100, "search", "AREN",
     "direct_phase2_buyer", 12, 10, 5, 10, 4, "8004330088", 11, 2,
     "hubspot_lead", "lp.qoyod.com/einvoice-integration",
     0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_ZATCAVendorShop_Broad", "23861101390", "PAUSED",  80,  "search", "AREN",
     "comparison_shopper", 10, 4, 5, 10, 4, "8004330088", 11, 2,
     "hubspot_lead", "lp.qoyod.com/einvoice-integration",
     0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_ZATCACompetitor_Broad", "23861965426", "PAUSED",  60,  "search", "AREN",
     "competitor_conquest", 7, 6, 6, 10, 4, "8004330088", 11, 2,
     "hubspot_lead", "lp.qoyod.com/einvoice-integration",
     7, 5, "MAXIMIZE_CONVERSIONS"],
    # NEW — Qawaem / Decision 236 campaign
    ["Google_Search_AR_FinancialStatemnt",       "23861837000", "ENABLED", 120, "search", "AR",
     "decision_236_compliance", 16, 7, 6, 8, 2, "8004330088", 11, 3,
     "hubspot_lead", "lp.qoyod.com/qawaem",
     0, 0, "MAXIMIZE_CONVERSIONS"],
]

# ── Tab 14 — append new action log rows ────────────────────────────────────
TAB_14_NEW = [
    ["2026-05-19", "FinancialStatemnt", "campaign_created",
     "Google_Search_AR_FinancialStatemnt (23861837000) — $120/d, MAX_CONVERSIONS, ENABLED"],
    ["2026-05-19", "FinancialStatemnt", "adgroups_added",
     "FinancialSt_AR (198301170444) 16 kw + FinancialSt_EN (199721186547) 7 kw"],
    ["2026-05-19", "FinancialStatemnt", "extensions_bundle",
     "6 sitelinks (/qawaem/ anchors) + 8 callouts + 2 snippets + 1 call ext (8004330088)"],
    ["2026-05-19", "FinancialStatemnt", "audience_layer_applied",
     "11 in-market + 3 customer exclusions + 5 warm observe + 1 domain visitor list"],
    ["2026-05-19", "FinancialStatemnt", "rsa_url_corrected_via_ui",
     "RSA was pointing to /accounting/; user fixed to /qawaem/ via UI (API rejected with DESTINATION_NOT_WORKING — fresh LP)"],
    ["2026-05-19", "FinancialStatemnt", "adgroup_custom_params_set",
     "Per-adgroup overrides for adgroupname/adgroupid/adname so UTM attribution resolves correctly"],
    ["2026-05-19", "FinancialStatemnt", "audience_parity_with_zatca",
     "Same 4-layer audience stack as ZATCA campaigns — comparable signal infrastructure"],
]

# ── Tab 07 — updated June budget table including Qawaem line ──────────────
TAB_07_ROWS = [
    ["JUNE 2026 BUDGET ALLOCATION (updated 2026-05-19 with Qawaem Phase 2 addition)"],
    [""],
    ["Channel", "May actual", "May effective (after pauses)", "June target", "Δ", "Rationale"],
    ["Google Ads (existing)",     "$93,000", "$70,000", "$75,000",  "-19%",
     "Pause bad PMax; hold Brand + E-invoice at right size"],
    ["Google Ads (ZATCA Phase 2)", "$0",      "$0",      "$7,200",   "NEW",
     "C1 $100/d + C2 $80/d + C3 $60/d × 30d — Wave 24 closes 30 June"],
    ["Google Ads (Qawaem 236)",    "$0",      "$0",      "$3,600",   "NEW",
     "Decision 236 — $120/d × 30d. Director liability triggers Jun 30, 2026"],
    ["Meta",                       "$24,000", "$24,000", "$28,000",  "+17%",
     "Scale Bookkeeping_Lookalike + Websiteform; +2 duplications"],
    ["Snapchat",                   "$19,000", "$19,000", "$22,000",  "+16%",
     "Restore iPhone Instantform; launch Android + Bookkeeping"],
    ["Microsoft Ads",              "$13,000", "$8,000",  "$8,000",   "-38%",
     "Pause 5-pack; hold Brand + WebsiteTraffic at cap"],
    ["TikTok",                     "$10,000", "$10,000", "$12,000",  "+20%",
     "Strong CPQL $60.75 — scale + 1 duplication + ZATCA test angle"],
    ["LinkedIn",                   "$0",      "$0",      "$0",       "0%",
     "Token expired since Mar; revisit Q3"],
    ["TOTAL",                      "$159,000","$131,000","$155,800", "-2.0%",
     "Net -2% vs May actual; ZATCA + Qawaem capture window justifies +$10.8k"],
    [""],
    ["Compliance-deadline portfolio (ZATCA $7.2k + Qawaem $3.6k = $10.8k) projected:"],
    ["~360 signups × ~30% qual rate = ~108 SQLs at ~$100 CPQL — pure incremental, didn't exist in May."],
    ["Combined June outcome: ~2,800 SQLs at $56 blended CPQL (vs status-quo 1,478 at $82)"],
]


def main():
    creds = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    titles = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    # Clear tab 13 + write new
    sheets.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range="'13 ZATCA Setup'!A1:Z200",
    ).execute()
    # Clear tab 07 + write new
    sheets.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range="'07 · June Budget'!A1:Z200",
    ).execute()

    data = [
        {"range": "'13 ZATCA Setup'!A1",      "majorDimension": "ROWS", "values": TAB_13_ROWS},
        {"range": "'07 · June Budget'!A1",    "majorDimension": "ROWS", "values": TAB_07_ROWS},
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print(f"[step 1] tabs 13 + 07 rewritten with Qawaem additions")

    # Append to tab 14 (don't clear — append below existing rows)
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="'14 ZATCA Action Log'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": TAB_14_NEW},
    ).execute()
    print(f"[step 2] {len(TAB_14_NEW)} action log rows appended to tab 14")

    print(f"\n  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
