"""Update master sheet:
  - Tab 07 — rebalance June budget to $100k cap (was $158.4k)
  - NEW Tab 15 — Bidding Strategy Playbook (decision framework + per-campaign recs)

# KPI-RULE-BYPASS — sheet update only, no SQL leads analysis.
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
        key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )


# ── Tab 07 — June Budget rebalanced to $100k cap ─────────────────────────
# Priority: keep compliance window (ZATCA + Qawaem) fully funded.
# Cut from generic/non-converting buckets.
TAB_07 = [
    ["JUNE 2026 BUDGET ALLOCATION (rebalanced 2026-05-20 to $100k cap)"],
    [""],
    ["Channel", "May actual", "May effective", "June target", "Δ vs May actual", "Rationale"],
    # Compliance — keep fully funded
    ["Google Ads (ZATCA Phase 2)", "$0",      "$0",      "$7,200",  "NEW",
     "C1 $100 + C2 $80 + C3 $60/d × 30d — Wave 24 closes Jun 30. Priority retain."],
    ["Google Ads (Qawaem 236)",    "$0",      "$0",      "$3,600",  "NEW",
     "Personal director liability deadline Jun 30. Priority retain."],
    ["Microsoft Ads (Qawaem 236)", "$0",      "$0",      "$3,600",  "NEW",
     "MS clone of Qawaem campaign — same window. Priority retain."],
    ["TikTok (WebForm Qawaem)",    "$0",      "$0",      "$1,500",  "NEW",
     "WebForm to /qawaem/ LP. Priority retain."],
    # Core Google — trimmed to fit
    ["Google Ads (Brand)",         "n/a",     "$3,500",  "$3,500",  "flat",
     "ImpressionShare + Search_AR_Brand_v2. Brand defense at top of page."],
    ["Google Ads (E-Invoice generic)", "n/a", "$10,000", "$10,000", "flat",
     "Search_E-invoice_AR + ImpressionShare_Search_AR_Invoice + Search_E-invoice_AR_Test"],
    ["Google Ads (PMax existing)", "n/a",     "$3,500",  "$3,500",  "flat",
     "PMax_AR_Invoice + PMax_AR_Invoice_Technology"],
    ["Google Ads (other / legacy)", "$93,000","$48,000", "$8,000",  "-91%",
     "CUT HARD — pause bleeders, keep only top 3 by SQL conversion"],
    # Social
    ["Meta",                       "$24,000", "$24,000", "$22,000", "-8%",
     "Hold Bookkeeping_Lookalike + WebsiteForm. Trim 2 underperforming variants."],
    ["Snapchat",                   "$19,000", "$19,000", "$17,000", "-11%",
     "iPhone Instantform held; trim BrandingEquity Lookalike. Restore product mix."],
    ["TikTok (Instantform existing)", "$10,000","$10,000","$10,000","flat",
     "$60.75 CPQL — productive, hold."],
    # Microsoft
    ["Microsoft Ads (Brand only)", "$13,000", "$8,000",  "$3,000",  "-77%",
     "Pause WebsiteTraffic ($190 CPQL) + Qflavours_Feature (0 SQL). Bid +50% on Brand ($21 CPQL — best in portfolio)."],
    # Bing
    ["TikTok (Bookkeeping/other)", "$0",      "$0",      "$2,500",  "NEW",
     "Bookkeeping_Lookalike duplication test, $50/d × ~50d ramped"],
    ["LinkedIn",                   "$0",      "$0",      "$0",      "0%",
     "Token expired since Mar; revisit Q3"],
    ["TOTAL",                      "$159,000","$112,000","$95,400", "-40%",
     "Within \$100k cap. Compliance window fully funded; legacy generic cut hard."],
    [""],
    ["Buffer:                                                                                                          $4,600"],
    [""],
    ["Compliance-deadline portfolio (Jun 30 window):"],
    ["  Google Qawaem $3.6k + ZATCA $7.2k + MS Qawaem $3.6k + TikTok WebForm $1.5k = $15.9k = 16% of total budget"],
    ["  Projection: ~530 signups × ~30% qual rate = ~160 SQLs at ~$100 CPQL incremental"],
    [""],
    ["What changed vs prior plan ($158k → $100k):"],
    ["  ✅ Compliance window unchanged — priority retained"],
    ["  ❌ Google Ads (other/legacy): -91% from \$48k → \$8k (only top 3 by SQL conversion kept)"],
    ["  ❌ Microsoft Ads (existing non-Qawaem): -77% from \$8k → \$3k (Brand only)"],
    ["  ❌ Meta -8% / Snap -11% — trim least-performing variants"],
    ["  ⚠ ~\$48k of monthly spend was going to underperforming generic campaigns. Reallocating to higher-CPQL plays."],
]


# ── NEW Tab 15 — Bidding Strategy Playbook ──────────────────────────────
TAB_15 = [
    ["BIDDING STRATEGY PLAYBOOK — when to use which, and the kickstart pattern"],
    [""],
    ["Section A: When to USE the kickstart pattern (Maximize Clicks → Maximize Conversions)"],
    [""],
    ["Use the kickstart when ALL true:", ""],
    ["  - Brand-new campaign in untested market segment", ""],
    ["  - Niche / regulatory keywords (low natural search volume)", ""],
    ["  - Zero conversion history on this campaign", ""],
    ["  - Conversion tracking IS properly set up (otherwise junk in/out)", ""],
    ["  - Budget allows for ~5-10 days of bootstrap clicks", ""],
    [""],
    ["Section B: When NOT to use it"],
    [""],
    ["Situation", "Use instead", "Why"],
    ["Existing campaign with conversion history", "Stay on Maximize Conversions",
     "Smart Bidding already has signal; switching to Clicks resets learning"],
    ["Brand campaign (Search_AR_Brand etc.)", "Target Impression Share (top of page)",
     "You want share of voice, not random click volume"],
    ["High-volume product with proven conv flow", "Maximize Conversions directly",
     "Auction pool big enough that Smart Bidding self-bootstraps in 3-5d"],
    ["Conversion tracking is broken", "Fix tracking FIRST",
     "Max Clicks burns money on untrackable traffic"],
    ["PMax / Performance Max", "Maximize Conversion Value",
     "PMax does not support Maximize Clicks at all"],
    [""],
    ["Section C: When to switch (data-based triggers, NOT calendar-based)"],
    [""],
    ["Signal observed", "Meaning", "Action"],
    ["≥ 15 clicks/day for 3+ consecutive days", "Click volume reliable",
     "Ready to layer optimization"],
    ["≥ 5 conversions in last 14 days", "Smart Bidding has signal",
     "Switch to Maximize Conversions"],
    ["≥ 30 conversions in last 30 days", "Strong signal",
     "Add tCPA at observed median CPL × 1.0"],
    ["CPC trending stable", "Auction dynamics settled",
     "Safe to layer constraint"],
    [""],
    ["⚠ Don't switch on a calendar (5 days, 7 days) — switch on the signal."],
    ["⚠ If <5 conversions at day 7-10, EXTEND Max Clicks another week. Don't starve Smart Bidding."],
    [""],
    ["Section D: Common mistakes to avoid"],
    [""],
    ["Mistake", "Result"],
    ["Leave Max Clicks running 30+ days", "Junk traffic poisons CTR/CR baseline; future Smart Bidding starts from a bad place"],
    ["Switch to Max Conv too early (<5 conv)", "Smart Bidding re-enters learning AND has bad-calibration history. Worst of both."],
    ["Use Max Clicks on a brand campaign", "Bid up on people typing brand name — buying clicks you'd get anyway"],
    ["Skip the switch entirely", "Stays on cheap traffic optimization forever; never optimizes for actual customers"],
    ["Combine Max Clicks with tight Max CPC bid limit", "Suffocates the strategy — defeats the purpose"],
    [""],
    ["Section E: Per-campaign recommendation as of 2026-05-20"],
    [""],
    ["Campaign", "Recommended starting bid strategy", "Notes"],
    ["Google_Search_AREN_ZATCAPhase2_Broad", "Maximize Clicks 5-10d → Maximize Conversions",
     "Niche legal terms; cold start expected"],
    ["Google_Search_AREN_ZATCAVendorShop_Broad", "Maximize Clicks 5-10d → Maximize Conversions",
     "Comparison terms; medium volume"],
    ["Google_Search_AREN_ZATCACompetitor_Broad", "Maximize Clicks 5-10d → Maximize Conversions",
     "Competitor terms; volume validated by Semrush"],
    ["Google_Search_AREN_FinancialStatement", "Maximize Clicks 5-10d → Maximize Conversions",
     "Just bootstrapped today; URGENT — apply immediately"],
    ["Bing_Search_AR_FinancialStatemnt (Acc 1)", "Maximize Clicks 5-10d → Maximize Conversions",
     "MS Smart Bidding bootstraps slightly faster than Google but still needs help"],
    ["Bing_Search_AR_FinancialStatemnt (Acc 2)", "Maximize Clicks 5-10d → Maximize Conversions",
     "Same as Acc 1"],
    ["Tiktok_Conversion_..._FinancialStatemnt_Websiteform", "Lowest Cost (auto-bid)",
     "TikTok doesn't have Max Clicks. Lowest Cost is the bootstrap equivalent."],
    ["Search_AR_Brand / _v2 / ImpressionShare", "Target Impression Share = 90% top",
     "Brand campaigns — never use Max Clicks"],
    ["Bing_Search_AR_Brand", "Target Impression Share = 90% top",
     "Same brand-defense logic"],
    ["Search_E-invoice_AR + ImpressionShare_Search_AR_Invoice", "Maximize Conversions (current)",
     "Existing history — leave alone"],
    ["All Meta / Snapchat existing campaigns", "Existing bidding strategy",
     "Most have history — leave alone unless flagged by health check"],
    ["PMax_AR_Invoice + PMax_AR_Invoice_Technology", "Maximize Conversions (current)",
     "PMax can't use Max Clicks"],
    [""],
    ["Section F: Practical rule of thumb"],
    [""],
    ["IF you're launching into a market segment never run before → KICKSTART (Max Clicks → Max Conv)"],
    ["IF tweaking a campaign with history → LEAVE Smart Bidding alone"],
    [""],
    ["Section G: Why this matters (the cold-start trap)"],
    [""],
    ["Smart Bidding needs ~30 conversions in 30 days to bid intelligently."],
    ["But it can't get clicks without bidding, and won't bid without conversion data."],
    ["Result: zero-history campaigns get stuck in a self-reinforcing low-spend loop."],
    ["Maximize Clicks bypasses this by ignoring conversion data entirely → forces volume → builds history."],
    ["After 5-10 days of click data + early conversions, Smart Bidding has signal to work with."],
]


def main():
    creds  = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Get current tabs
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    titles = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    # Clear tab 07
    sheets.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range="'07 · June Budget'!A1:Z200"
    ).execute()

    # Add tab 15 if not exists
    if "15 Bidding Strategy Playbook" not in titles:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": "15 Bidding Strategy Playbook"}}}]},
        ).execute()
        print("[1] added tab '15 Bidding Strategy Playbook'")

    data = [
        {"range": "'07 · June Budget'!A1",                   "majorDimension": "ROWS", "values": TAB_07},
        {"range": "'15 Bidding Strategy Playbook'!A1",       "majorDimension": "ROWS", "values": TAB_15},
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print("[2] wrote tabs 07 + 15")

    # Append action log entry
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range="'14 ZATCA Action Log'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [[
            "2026-05-20", "june_budget+playbook", "rebalanced + new bidding playbook tab",
            "June budget recapped to $95.4k (within $100k cap, was $158k). Compliance window kept fully funded; "
            "Google Ads legacy/other cut -91% from $48k → $8k. New tab 15 documents bidding strategy "
            "framework (kickstart pattern, per-campaign recommendations, cold-start trap explanation)."
        ]]},
    ).execute()
    print("[3] appended action log row")

    print(f"\n  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
