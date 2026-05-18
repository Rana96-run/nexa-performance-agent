"""Rebuild tabs 13 + 14 in proper table structure to match the rest of the
master sheet. Also apply formatting: bold header rows, frozen first row,
sensible column widths."""
from __future__ import annotations
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


# ── Tab 13 — ZATCA Setup ────────────────────────────────────────────────────
def tab_13_rows() -> list[list]:
    rows = []
    # Title row (single cell, will merge)
    rows.append(["ZATCA PHASE 2 — PORTFOLIO SETUP"])
    rows.append([""])

    # Section A: Portfolio Overview
    rows.append(["A. PORTFOLIO OVERVIEW"])
    rows.append(["Campaign", "ID", "Status", "Daily Budget", "Channel", "Intent", "Primary Keywords"])
    rows.append([
        "Google_Search_AREN_ZATCAPhase2_Broad", "23851270716", "ENABLED", "$100",
        "Search", "Direct Phase 2 buyer", "ربط المرحلة الثانية, ZATCA Phase 2, fatoora portal",
    ])
    rows.append([
        "Google_Search_AREN_ZATCAVendorShop_Broad", "23861101390", "PAUSED", "$80",
        "Search", "Comparison shopper", "أفضل برنامج فاتورة, best e-invoice software",
    ])
    rows.append([
        "Google_Search_AREN_ZATCACompetitor_Broad", "23861965426", "PAUSED", "$60",
        "Search", "Competitor conquest", "daftra, wafeq, rewaa, منصة فاتورة, رواء",
    ])
    rows.append(["TOTAL", "—", "—", "$240/d", "—", "—", "≈ $7,200/mo  (7.2% of June $100k cap)"])
    rows.append([""])

    # Section B: Ad-group structure
    rows.append(["B. AD-GROUP STRUCTURE (AR / EN split per campaign)"])
    rows.append(["Campaign", "AR ad group", "EN ad group", "AR keywords", "EN keywords", "AR RSA", "EN RSA"])
    rows.append(["ZATCAPhase2",     "_AR_AdGroup", "_EN_AdGroup", "12", "10",
                 "12 hl / 4 desc", "12 hl / 4 desc"])
    rows.append(["ZATCAVendorShop", "_AR_AdGroup", "_EN_AdGroup", "10", "4",
                 "12 hl / 4 desc", "12 hl / 4 desc"])
    rows.append(["ZATCACompetitor", "_AR_AdGroup", "_EN_AdGroup", "7 (+7 paused)", "6 (+5 paused)",
                 "12 hl / 4 desc", "12 hl / 4 desc"])
    rows.append([""])

    # Section C: Extensions
    rows.append(["C. EXTENSIONS (per campaign)"])
    rows.append(["Campaign", "Sitelinks", "Callouts", "Snippets", "Call"])
    rows.append(["ZATCAPhase2",      "5", "10", "4 (Types EN+AR, Service catalog EN+AR)", "8004330088"])
    rows.append(["ZATCAVendorShop",  "5", "10", "4", "8004330088"])
    rows.append(["ZATCACompetitor",  "6 (5 shared + 1 conquest-specific)", "10", "4", "8004330088"])
    rows.append([""])

    # Section D: Sitelinks detail
    rows.append(["D. SITELINKS — text + URL (all campaigns share these 5 + C3 extras)"])
    rows.append(["Sitelink Text", "URL", "Linked Campaigns"])
    rows.append(["أسعار الفاتورة",              "lp.qoyod.com/einvoice-integration/#pricing",      "C1, C2, C3"])
    rows.append(["اربط منشأتك بـ4 خطوات",       "lp.qoyod.com/einvoice-integration/#integration",   "C1, C2, C3"])
    rows.append(["مميزات الفاتورة",             "lp.qoyod.com/einvoice-integration/#features",      "C1, C2, C3"])
    rows.append(["قصص نجاح العملاء",            "lp.qoyod.com/einvoice-integration/#testimonials",  "C1, C2, C3"])
    rows.append(["دليل المرحلة الثانية",        "lp.qoyod.com/einvoice-integration/#faq",           "C1, C2, C3"])
    rows.append(["لماذا الشركات تنتقل إلينا",   "lp.qoyod.com/einvoice-integration/#testimonials",  "C3 only"])
    rows.append([""])

    # Section E: Callouts (1 row per callout)
    rows.append(["E. CALLOUTS (10 — all 3 campaigns)"])
    rows.append(["Callout"])
    for c in [
        "متوافق مع ZATCA", "REST API", "XML + PDF/A-3", "دعم 24/7 بالعربية",
        "بدون بطاقة ائتمان", "تجربة 14 يوم", "ربط في دقائق",
        "آلاف الشركات السعودية", "ضمان الامتثال أو استرداد", "تكامل مع منصة فاتورة",
    ]:
        rows.append([c])
    rows.append([""])

    # Section F: Audiences (observation)
    rows.append(["F. OBSERVATION AUDIENCES (Smart Bidding signal — no reach loss)"])
    rows.append(["Audience ID", "Name", "Mode"])
    for aid, name in [
        ("80133", "Financial Planning"),
        ("80137", "Tax Preparation Services & Software"),
        ("80281", "Accounting Software"),
        ("80463", "Business Services"),
        ("80530", "Enterprise Software"),
        ("80536", "ERP Solutions"),
        ("80539", "Network & Enterprise Security"),
    ]:
        rows.append([aid, name, "Observation (bid_only=True)"])
    rows.append([""])

    # Section G: Conversion + URL tracking
    rows.append(["G. CONVERSION + URL TRACKING"])
    rows.append(["Setting", "Value"])
    rows.append(["Bidding strategy", "MAXIMIZE_CONVERSIONS (no tCPA target for first 30d)"])
    rows.append(["Conversion goal", "HubSpot - Lead (SIGNUP) — UI step pending"])
    rows.append(["final_url_suffix",
                 "utm_source=Google&utm_medium=ppc&utm_campaign={_campaign}&utm_content={_adname}"
                 "&utm_audience={_adgroupname}&campaign_id={campaignid}&ad_group_id={_adgroupid}"
                 "&ad_id={creative}&utm_term={keyword}"])
    rows.append(["Custom params per campaign", "campaign, adname, adgroupname, adgroupid (resolved at click time)"])
    rows.append([""])

    # Section H: Pending
    rows.append(["H. STILL PENDING"])
    rows.append(["Item", "Owner", "Notes"])
    rows.append(["UI: lock 'HubSpot - Lead' as only conversion goal per campaign", "Team", "Settings → Conversion goals → uncheck Account default"])
    rows.append(["UI: archive OLD HubSpot - Lead conversion action",            "Team", "Tools → Conversions → Archive"])
    rows.append(["Review + enable C2 (ZATCAVendorShop)",                         "Team", "Currently PAUSED — wait 24h after C1 then enable"])
    rows.append(["Review + enable C3 (ZATCACompetitor)",                         "Team", "After C2 — most likely to attract policy review"])
    rows.append(["Top up Semrush credits",                                       "Ops",  "To pull daftra.com / wafeq.com paid keyword + ad copy reports"])
    rows.append([""])

    # Section I: Expected impact
    rows.append(["I. EXPECTED JUNE IMPACT"])
    rows.append(["Metric", "Value"])
    rows.append(["Added monthly spend",          "$7,200"])
    rows.append(["Target signup CPL",            "$25 – $35"])
    rows.append(["Projected signups (June)",     "200 – 290"])
    rows.append(["Projected SQLs (June)",        "60 – 87 (~30% qualified rate)"])
    rows.append(["Wave 24 deadline",             "30 June 2026"])

    return rows


# ── Tab 14 — Action Log ─────────────────────────────────────────────────────
def tab_14_rows() -> list[list]:
    rows = []
    rows.append(["ZATCA PHASE 2 — ACTION LOG"])
    rows.append([""])
    rows.append(["Date", "Action", "Detail"])
    rows.append(["2026-05-17", "Account selection",
                 "Compared Acc1 (1513020554) vs Acc2: chose Acc1 (48.4% IS, 1.48x ROAS vs 27.2%, 1.24x)"])
    rows.append(["2026-05-17", "Created C1 ZATCAPhase2",
                 "14 keywords (6 EXACT + 8 PHRASE), 18 negatives, $50/d, tCPA $90"])
    rows.append(["2026-05-17", "Created C2 ZATCAVendorShop",
                 "15 keywords, 18 negatives, $35/d, tCPA $100"])
    rows.append(["2026-05-17", "Disabled Display Network",
                 "All campaigns: target_content_network=False, target_partner_search_network=False"])
    rows.append(["2026-05-17", "Geo + language locked",
                 "Saudi Arabia only + Arabic + English"])
    rows.append(["2026-05-17", "Fixed truncated RSA headlines on C1",
                 "Replaced 2 headlines that exceeded 30 chars"])
    rows.append(["2026-05-17", "Added 19 extension assets to C1 + C2",
                 "5 sitelinks, 9 callouts, 2 snippets, 1 call extension (8004330088)"])
    rows.append(["2026-05-17", "Removed placeholder call extension",
                 "Wrong-number +966112345678 removed — kept real Qoyod 800: 8004330088"])
    rows.append(["2026-05-18", "Created C3 ZATCACompetitor",
                 "16 keywords (6 EXACT + 10 PHRASE), 18 negatives, $25/d, tCPA $110"])
    rows.append(["2026-05-18", "Linked existing assets to C3 + 2 new comparison sitelinks",
                 "قارن قيود بالمنافسين + لماذا الشركات تنتقل إلينا"])
    rows.append(["2026-05-18", "Applied canonical UTM final_url_suffix",
                 "Set final_url_suffix at campaign level; stripped hardcoded UTMs from RSA final_urls"])
    rows.append(["2026-05-18", "Stripped tCPA on C2 + C3",
                 "Moved to pure MAXIMIZE_CONVERSIONS — let algorithm find volume first 30d"])
    rows.append(["2026-05-18", "Bumped budgets",
                 "C1 $50→$100, C2 $35→$80, C3 $25→$60 — supports ≥3× tCPA rule when added later"])
    rows.append(["2026-05-18", "Renamed _AR_ → _AREN_",
                 "Per CLAUDE.md naming for mixed Arabic+English keyword campaigns"])
    rows.append(["2026-05-18", "Split each campaign into AR + EN ad groups",
                 "Existing AR group renamed; new EN group created with language-matched RSA"])
    rows.append(["2026-05-18", "Added high-volume keywords (Keyword Planner)",
                 "5 AR additions: 3 to C1, 1 to C2, 1 to C3"])
    rows.append(["2026-05-18", "Added LP-anchored sitelinks",
                 "أسعار الفاتورة (#pricing), كيف تربط نظامك (#integration), مميزات الفاتورة (#features)"])
    rows.append(["2026-05-18", "Deduped overlapping sitelinks",
                 "Kept higher-converting wording per anchor"])
    rows.append(["2026-05-18", "Added Arabic-value structured snippets",
                 "Types AR + Service catalog AR alongside the existing EN versions"])
    rows.append(["2026-05-18", "C3 competitor brand keywords (Semrush + Planner)",
                 "رواء (49,500/mo), منصة رواء (12,100), رواء المحاسبي (1,000), برنامج رواء (880), رواء منصة (590)"])
    rows.append(["2026-05-18", "Added 3 login negatives at C3 campaign level",
                 "تسجيل الدخول, تسجيل دخول, login (BROAD) — block existing-user search intent"])
    rows.append(["2026-05-18", "Paused 12 RARELY_SERVED keywords on C3",
                 "7 AR + 5 EN long-tails Google flagged too niche to serve"])
    rows.append(["2026-05-18", "Added 7 in-market audiences as observation",
                 "21 associations × 3 campaigns — bid signal layer for Smart Bidding"])
    return rows


def main():
    creds  = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Find tab IDs for 13 and 14
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    tab_ids = {}
    for s in meta["sheets"]:
        t = s["properties"]["title"]
        if t in ("13 ZATCA Setup", "14 ZATCA Action Log"):
            tab_ids[t] = s["properties"]["sheetId"]
    print(f"tab IDs: {tab_ids}")

    # 1. Clear existing content
    for title in tab_ids:
        sheets.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range=f"'{title}'!A1:Z200",
        ).execute()
    print("[step 1] cleared existing tab content")

    # 2. Write new table-structured rows
    data = [
        {"range": "'13 ZATCA Setup'!A1",      "majorDimension": "ROWS", "values": tab_13_rows()},
        {"range": "'14 ZATCA Action Log'!A1", "majorDimension": "ROWS", "values": tab_14_rows()},
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print("[step 2] wrote new table-structured content")

    # 3. Format: bold title rows + freeze + column widths
    fmt_requests = []
    for title, sid in tab_ids.items():
        # Freeze row 1
        fmt_requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        })
        # Bold row 1 (title)
        fmt_requests.append({
            "repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 12},
                    "backgroundColor": {"red": 0.91, "green": 0.93, "blue": 0.96},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
        # Auto-resize columns A-G
        fmt_requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId":   sid,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex":   7,
                }
            }
        })

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": fmt_requests},
    ).execute()
    print("[step 3] applied formatting (freeze + bold + auto-width)")

    print()
    print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
