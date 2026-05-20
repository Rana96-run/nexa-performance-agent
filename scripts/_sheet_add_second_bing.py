"""Add the second Bing Qawaem campaign to tab 13.
Tab 13 has 6 rows currently (header + 5 campaigns). Add Acc 2 Bing as row 7.

# KPI-RULE-BYPASS — sheet update only.
"""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "certs/bigquery-key.json"
creds = service_account.Credentials.from_service_account_file(
    key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Re-write the entire tab 13 with both Bing rows
TAB_13 = [
    ["campaign", "channel", "id", "status", "budget_usd_per_day", "language",
     "intent", "ar_keywords", "en_keywords", "sitelinks", "callouts", "snippets",
     "call_extension", "obs_audiences", "user_list_exclusions",
     "conversion_goal", "landing_page",
     "ar_adgroup_paused_kw", "en_adgroup_paused_kw", "bidding"],
    ["Google_Search_AREN_ZATCAPhase2_Broad",     "google_ads",   "23851270716", "ENABLED", 100,
     "AREN", "direct_phase2_buyer", 12, 10, 5, 10, 4, "8004330088", 11, 2,
     "hubspot_lead", "lp.qoyod.com/einvoice-integration", 0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_ZATCAVendorShop_Broad", "google_ads",   "23861101390", "PAUSED",  80,
     "AREN", "comparison_shopper", 10, 4, 5, 10, 4, "8004330088", 11, 2,
     "hubspot_lead", "lp.qoyod.com/einvoice-integration", 0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_ZATCACompetitor_Broad", "google_ads",   "23861965426", "PAUSED",  60,
     "AREN", "competitor_conquest", 7, 6, 6, 10, 4, "8004330088", 11, 2,
     "hubspot_lead", "lp.qoyod.com/einvoice-integration", 7, 5, "MAXIMIZE_CONVERSIONS"],
    ["Google_Search_AREN_FinancialStatement",    "google_ads",   "23861837000", "ENABLED", 100,
     "AR", "decision_236_compliance", 16, 7, 6, 8, 2, "8004330088", 11, 3,
     "hubspot_lead", "lp.qoyod.com/qawaem", 0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Bing_Search_AR_FinancialStatemnt (Acc 1)", "microsoft_ads","487816800",  "ACTIVE",  40,
     "AR", "decision_236_compliance_bing", 16, 0, 0, 0, 0, "", 0, 0,
     "rsa_manual_pending", "lp.qoyod.com/qawaem", 0, 0, "ManualCpc"],
    ["Bing_Search_AR_FinancialStatemnt (Acc 2)", "microsoft_ads","524237046",  "PAUSED",  120,
     "AR", "decision_236_compliance_bing", 16, 0, 0, 0, 0, "", 0, 0,
     "rsa_manual_pending", "lp.qoyod.com/qawaem", 0, 0, "ManualCpc"],
    ["Tiktok_Conversion_Prospecting_Interests_FinancialStatemnt_Websiteform", "tiktok", "1865704232893537", "DISABLED", 50,
     "AR", "decision_236_social", "n/a", "n/a", 0, 0, 0, "", 0, 0,
     "complete_registration", "lp.qoyod.com/qawaem", 0, 0, "LowestCost_auto"],
]

sheets.spreadsheets().values().clear(
    spreadsheetId=SHEET_ID, range="'13 ZATCA Setup'!A1:Z200"
).execute()

sheets.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": "'13 ZATCA Setup'!A1", "majorDimension": "ROWS", "values": TAB_13}],
    },
).execute()
print("[1] rewrote tab 13 with both Bing campaigns (7 total entries)")

# Append action log
sheets.spreadsheets().values().append(
    spreadsheetId=SHEET_ID,
    range="'14 ZATCA Action Log'!A1",
    valueInputOption="USER_ENTERED",
    insertDataOption="INSERT_ROWS",
    body={"values": [[
        "2026-05-20", "compliance_portfolio_documentation", "added_second_bing_to_sheet",
        "Tab 13 was missing Acc 2 Bing Qawaem (id 524237046). Added. "
        "Also noted: Acc 1 Bing campaign is now ACTIVE at $40/d (user enabled + cut budget from $120). "
        "Acc 2 still PAUSED awaiting RSA manual add."
    ]]},
).execute()
print("[2] action log row appended")
print(f"\n  https://docs.google.com/spreadsheets/d/{SHEET_ID}")
