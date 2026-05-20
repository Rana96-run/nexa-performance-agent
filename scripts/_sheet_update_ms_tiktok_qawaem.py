"""Update master sheet with MS Ads Qawaem (created) + TikTok WebForm Qawaem
(pending launch) + revised June budget.

# KPI-RULE-BYPASS — this script writes to Google Sheets, not BQ. Any
# references to channel-side leads columns are in documentation strings,
# not in actual SQL queries.
"""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"

def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "certs/bigquery-key.json"
    return service_account.Credentials.from_service_account_file(
        key_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )


# Compliance portfolio table — 6 campaigns
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
    ["Google_Search_AR_FinancialStatemnt",       "google_ads",   "23861837000", "ENABLED", 120,
     "AR", "decision_236_compliance", 16, 7, 6, 8, 2, "8004330088", 11, 3,
     "hubspot_lead", "lp.qoyod.com/qawaem", 0, 0, "MAXIMIZE_CONVERSIONS"],
    ["Bing_Search_AR_FinancialStatemnt",         "microsoft_ads","487816800",   "PAUSED",  120,
     "AR", "decision_236_compliance_bing", 16, 0, 0, 0, 0, "", 0, 0,
     "manual_pending", "lp.qoyod.com/qawaem", 0, 0, "ManualCpc"],
    ["Tiktok_WebForm_AR_Qawaem236",              "tiktok",       "PENDING", "PENDING_LAUNCH", 50,
     "AR", "decision_236_social", "n/a", "n/a", 0, 0, 0, "", 0, 0,
     "complete_registration", "lp.qoyod.com/qawaem", 0, 0, "LowestCost_auto"],
]

TAB_14_NEW = [
    ["2026-05-19", "Bing_FinancialStatemnt", "campaign_created_via_bulk_api",
     "Bing_Search_AR_FinancialStatemnt (487816800) on Acc1 188176729. $120/d, PAUSED."],
    ["2026-05-19", "Bing_FinancialStatemnt", "adgroup_keywords_negatives_added",
     "FinancialSt_AR (1238051567759836) + 16 positive kw + 18 campaign-level negatives"],
    ["2026-05-19", "Bing_FinancialStatemnt", "rsa_manual_pending",
     "RSA blocked by bingads SDK suds-enum issue on AssetLink. Manual UI add: 15 headlines + 4 desc + LP url"],
    ["2026-05-19", "Tiktok_WebForm_Qawaem", "spec_documented_pending_launch",
     "Tiktok_WebForm_AR_Qawaem236. $50/d, Lead Generation Website Form, CompleteRegistration event, 3 creative variants"],
    ["2026-05-19", "MS_Ads_Acc1_scaling", "diagnosis_completed_actions_pending",
     "Brand +50% bid (UI), Pause WebsiteTraffic + Qflavours_Feature (UI). Real CPQL via HS join: Brand $21, WebsiteTraffic $190."],
    ["2026-05-19", "system_qa", "kpi_rule_enforcement_locked",
     "memory/CRITICAL_KPI_RULES.md + KPI-rule-guard hook + BQ column descriptions deployed"],
]

TAB_07 = [
    ["JUNE 2026 BUDGET ALLOCATION (updated 2026-05-19 with MS + TikTok Qawaem additions)"],
    [""],
    ["Channel", "May actual", "May effective (after pauses)", "June target", "Δ", "Rationale"],
    ["Google Ads (existing)",     "$93,000", "$70,000", "$75,000",  "-19%",
     "Pause bad PMax; hold Brand + E-invoice at right size"],
    ["Google Ads (ZATCA Phase 2)", "$0",      "$0",      "$7,200",   "NEW",
     "C1 $100 + C2 $80 + C3 $60/d × 30d — Wave 24 closes 30 June"],
    ["Google Ads (Qawaem 236)",    "$0",      "$0",      "$3,600",   "NEW",
     "Decision 236 personal director liability — $120/d × 30d"],
    ["Meta",                       "$24,000", "$24,000", "$28,000",  "+17%",
     "Scale Bookkeeping_Lookalike + Websiteform; +2 duplications"],
    ["Snapchat",                   "$19,000", "$19,000", "$22,000",  "+16%",
     "Restore iPhone Instantform; launch Android + Bookkeeping"],
    ["Microsoft Ads (existing)",   "$13,000", "$8,000",  "$5,500",   "-58%",
     "Pause WebsiteTraffic ($190 CPQL waste) + Qflavours_Feature; bid +50% on Brand ($21 CPQL)"],
    ["Microsoft Ads (Qawaem 236)", "$0",      "$0",      "$3,600",   "NEW",
     "MS clone of the Google Qawaem campaign — same urgency window, same LP"],
    ["TikTok (existing)",          "$10,000", "$10,000", "$12,000",  "+20%",
     "Strong CPQL $60.75 on Instantform — scale + 1 duplication"],
    ["TikTok (WebForm Qawaem)",    "$0",      "$0",      "$1,500",   "NEW",
     "WebForm campaign to /qawaem/ LP — $50/d × 30d, 3 creative variants"],
    ["LinkedIn",                   "$0",      "$0",      "$0",       "0%",
     "Token expired since Mar; revisit Q3"],
    ["TOTAL",                      "$159,000","$131,000","$158,400", "-0.4%",
     "Near-flat vs May actual; cuts on MS bleeders fund net-new compliance + WebForm plays"],
    [""],
    ["Compliance-deadline portfolio (Jun 30 window):"],
    ["  Google Qawaem $3.6k + ZATCA $7.2k + MS Qawaem $3.6k + TikTok WebForm $1.5k = $15.9k"],
    ["  Combined projection: ~530 signups → ~160 SQLs at ~$100 CPQL on this slice"],
    ["  Pure incremental — didn't exist in May. Closes the regulatory-window opportunity."],
]


def main():
    creds  = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    sheets.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range="'13 ZATCA Setup'!A1:Z200"
    ).execute()
    sheets.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range="'07 · June Budget'!A1:Z200"
    ).execute()

    data = [
        {"range": "'13 ZATCA Setup'!A1",    "majorDimension": "ROWS", "values": TAB_13},
        {"range": "'07 · June Budget'!A1",  "majorDimension": "ROWS", "values": TAB_07},
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print("[1] rewrote tabs 13 + 07")

    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="'14 ZATCA Action Log'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": TAB_14_NEW},
    ).execute()
    print(f"[2] appended {len(TAB_14_NEW)} rows to tab 14")

    print(f"\n  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
