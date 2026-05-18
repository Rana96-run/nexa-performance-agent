"""Update the existing master sheet with:
  - New tab '13 ZATCA Phase 2' — full record of the 3 campaigns + structure
  - Update tab '07 · June Budget' — add ZATCA line to Google Ads channel

Existing sheet ID is the v3 master sheet (Apr/May analysis + June plan).
"""
from __future__ import annotations
import os
from datetime import date
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _creds():
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "bigquery-key.json"
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


def tab_zatca_setup() -> list[list]:
    return [
        ["ZATCA PHASE 2 — 3-CAMPAIGN ACQUISITION PORTFOLIO"],
        [f"Snapshot {date.today().isoformat()}"],
        [""],
        ["1. PORTFOLIO OVERVIEW"],
        ["Goal: capture Phase 2 buyers before Wave 24 deadline (30 June 2026)"],
        ["Account: 1513020554  |  All campaigns SEARCH  |  Bidding: MAXIMIZE_CONVERSIONS"],
        ["Total daily budget: $240/d  →  ~$7,200/mo = 7.2% of June $100k cap"],
        [""],
        ["Campaign", "ID", "Status", "Daily Budget", "Intent", "Keyword Theme"],
        ["Google_Search_AREN_ZATCAPhase2_Broad",     "23851270716", "ENABLED",
         "$100/d", "Direct buyer", "ربط المرحلة الثانية, ZATCA Phase 2, fatoora portal"],
        ["Google_Search_AREN_ZATCAVendorShop_Broad", "23861101390", "PAUSED",
         "$80/d",  "Comparison shopper", "أفضل برنامج فاتورة, best e-invoice software"],
        ["Google_Search_AREN_ZATCACompetitor_Broad", "23861965426", "PAUSED",
         "$60/d",  "Competitor conquest", "daftra, wafeq, rewaa, منصة فاتورة, رواء"],
        [""],

        ["2. AR / EN AD-GROUP SPLIT (per campaign)"],
        ["Campaign", "AR ad group (enabled kw)", "EN ad group (enabled kw)", "RSA AR", "RSA EN"],
        ["ZATCAPhase2",      "12 keywords",  "10 keywords",  "12 hl / 4 desc", "12 hl / 4 desc"],
        ["ZATCAVendorShop",  "10 keywords",  "4 keywords",   "12 hl / 4 desc", "12 hl / 4 desc"],
        ["ZATCACompetitor",  "7 keywords + 7 paused (RARELY_SERVED)",
                             "6 keywords + 5 paused (RARELY_SERVED)",
                             "12 hl / 4 desc", "12 hl / 4 desc"],
        [""],

        ["3. KEYWORD STRATEGY"],
        ["Match types: PHRASE-heavy (broader reach), EXACT for proven buyer terms"],
        ["High-volume additions (from Keyword Planner + Semrush research):"],
        ["• C1 EN: zatca phase 2, fatoora portal (880/mo), zatca integration"],
        ["• C2 AR: أفضل برنامج محاسبة (140/mo), افضل برامج المحاسبه (140/mo)"],
        ["• C3 AR: منصة فاتورة (1,900/mo), رواء (49,500/mo), منصة رواء (12,100/mo)"],
        ["• C3 EN: daftra (1,900/mo), wafeq (1,900/mo), rewaa (3,600/mo) — all PHRASE"],
        [""],
        ["NEGATIVES applied:"],
        ["• C1/C2: informational ('كيف', 'ما هي', 'what is', 'tutorial', 'guide')"],
        ["• C3: login-intent ('تسجيل الدخول', 'تسجيل دخول', 'login') — block existing-user searches"],
        ["• All: free-download / course / job / loan via keyword_policy.py defaults"],
        [""],

        ["4. ASSETS (extensions) — linked to all 3 campaigns"],
        ["Sitelinks (5 shared + 2 C3-only):"],
        ["• أسعار الفاتورة → /einvoice-integration/#pricing"],
        ["• اربط منشأتك بـ4 خطوات → /einvoice-integration/#integration"],
        ["• مميزات الفاتورة → /einvoice-integration/#features"],
        ["• قصص نجاح العملاء → /einvoice-integration/#testimonials"],
        ["• دليل المرحلة الثانية → /einvoice-integration/#faq"],
        ["• (C3 only) لماذا الشركات تنتقل إلينا → /einvoice-integration/#testimonials"],
        [""],
        ["Callouts (10):"],
        ["متوافق مع ZATCA · REST API · XML + PDF/A-3 · دعم 24/7 بالعربية · بدون بطاقة ائتمان ·"],
        ["تجربة 14 يوم · ربط في دقائق · آلاف الشركات السعودية · ضمان الامتثال أو استرداد · تكامل مع منصة فاتورة"],
        [""],
        ["Structured snippets (4 — 2 EN-value + 2 AR-value):"],
        ["• Types (EN):           XML, PDF/A-3, REST API, QR Code, Encrypted Seal"],
        ["• Types (AR):           XML, PDF/A-3, REST API, QR Code, ختم مشفر"],
        ["• Service catalog (EN): e-invoicing, accounting, inventory, payroll, reports"],
        ["• Service catalog (AR): فوترة إلكترونية, محاسبة, مخزون, رواتب, تقارير"],
        [""],
        ["Call extension: 8004330088 (Qoyod 800 line)"],
        [""],

        ["5. OBSERVATION AUDIENCES (Smart Bidding signal layer)"],
        ["Mode: bid_only=True (no reach loss, only bid-adjustment signal)"],
        ["7 in-market audiences × 3 campaigns = 21 associations:"],
        ["• Financial Planning · Tax Preparation Services & Software · Accounting Software"],
        ["• Business Services · Enterprise Software · ERP Solutions · Network & Enterprise Security"],
        ["Age + Gender automatically observed by Smart Bidding (no manual setup needed)"],
        [""],

        ["6. CONVERSION OPTIMIZATION"],
        ["Bidding strategy: MAXIMIZE_CONVERSIONS (no tCPA — let algorithm find volume)"],
        ["Conversion goal: locked to 'HubSpot - Lead' SIGNUP via campaign-level override"],
        ["UI step still pending: each campaign → Conversion goals → un-check Account default → keep only HubSpot - Lead"],
        [""],
        ["After 30 days with real CPL data: add tCPA at observed median. Switch to QUALIFIED_LEAD"],
        ["goal when SQL volume ≥ 30/month per campaign."],
        [""],

        ["7. URL TRACKING"],
        ["final_url_suffix (canonical template, applied at campaign level):"],
        ["utm_source=Google&utm_medium=ppc&utm_campaign={_campaign}&utm_content={_adname}"],
        ["&utm_audience={_adgroupname}&campaign_id={campaignid}&ad_group_id={_adgroupid}"],
        ["&ad_id={creative}&utm_term={keyword}"],
        ["RSA final_urls = bare LP (no hardcoded UTMs — suffix handles all attribution)"],
        [""],

        ["8. WHAT'S STILL PENDING"],
        ["• UI: lock 'HubSpot - Lead' as only conversion goal per campaign (Settings → Conversion goals)"],
        ["• UI: archive OLD HubSpot - Lead conversion action (Tools → Conversions)"],
        ["• UI: review C2 + C3 (still PAUSED) and enable when ready — staggered: C2 → wait 24h → C3"],
        ["• OPTIONAL: top up Semrush API credits to pull daftra.com / wafeq.com actual paid-keyword + ad-copy reports"],
        [""],

        ["9. EXPECTED IMPACT — June"],
        ["Baseline: $0/mo on Phase 2 acquisition (campaigns didn't exist before)"],
        ["June added spend: $7,200 (3 campaigns × ~$80/d avg × 30 days)"],
        ["Target CPL @ signup: $25-35 (account avg)  →  ~200-290 signups from ZATCA campaigns"],
        ["Expected ZATCA→SQL rate: ~30% (Phase 2 is high-commercial-intent traffic)  →  60-87 SQLs"],
        ["After Wave 24 closes (30 June): traffic naturally tapers; re-evaluate end of July."],
    ]


def tab_zatca_actions_log() -> list[list]:
    """Day-by-day record of what was built and changed."""
    return [
        ["ZATCA PHASE 2 — ACTION LOG"],
        ["All actions from 2026-05-17 build session through 2026-05-18 optimization"],
        [""],
        ["Date", "Action", "Detail"],
        ["2026-05-17", "Account selection",
         "Compared Acc1 (1513020554) vs Acc2 (5753494964): Acc1 picked for 48.4% vs 27.2% IS, 1.48x vs 1.24x ROAS"],
        ["2026-05-17", "Created C1 (ZATCAPhase2)",
         "14 keywords (6 EXACT + 8 PHRASE), 18 negatives, $50/d, tCPA $90"],
        ["2026-05-17", "Created C2 (ZATCAVendorShop)",
         "15 keywords (6 EXACT + 9 PHRASE), 18 negatives, $35/d, tCPA $100"],
        ["2026-05-17", "Fixed Display Network OFF",
         "All 3 campaigns: Display+Partners disabled (Search-only)"],
        ["2026-05-17", "Fixed geo + language",
         "Saudi Arabia only (geoTargetConstants/2682), Arabic + English (languageConstants/1019, 1000)"],
        ["2026-05-17", "Fixed 2 truncated RSA headlines on C1", "Shortened headlines that exceeded 30 chars"],
        ["2026-05-17", "Added 19 extension assets to C1+C2",
         "5 unique sitelinks, 9 unique callouts, 2 structured snippets, 1 call (8004330088)"],
        ["2026-05-17", "Deduped wrong-phone call extension",
         "Removed placeholder +966112345678 — kept real Qoyod 800: 8004330088"],
        ["2026-05-18", "Created C3 (ZATCACompetitor)",
         "16 keywords (6 EXACT + 10 PHRASE) targeting competitor × ZATCA, 18 negatives, $25/d, tCPA $110"],
        ["2026-05-18", "Reused 19 existing assets from C1 on C3 + 2 new comparison sitelinks",
         "قارن قيود بالمنافسين + لماذا الشركات تنتقل إلينا"],
        ["2026-05-18", "Canonical UTM final_url_suffix applied to all 3",
         "Strip hardcoded UTMs from RSAs; custom params populated"],
        ["2026-05-18", "Stripped tCPA on C2 + C3",
         "Moved to pure MAXIMIZE_CONVERSIONS (no target) for first 30 days of learning"],
        ["2026-05-18", "Bumped budgets",
         "$50→$100 / $35→$80 / $25→$60 — meets Google's ≥3× tCPA rule when tCPA added later"],
        ["2026-05-18", "Renamed _AR_ → _AREN_",
         "Per CLAUDE.md naming convention for mixed Arabic+English keyword campaigns"],
        ["2026-05-18", "Split into AR + EN ad groups per campaign",
         "Each campaign now has _AR_AdGroup + _EN_AdGroup, language-matched RSAs"],
        ["2026-05-18", "Added high-volume keywords (Keyword Planner)",
         "5 AR additions total: 3 to C1, 1 to C2, 1 to C3"],
        ["2026-05-18", "Added LP-anchored sitelinks",
         "أسعار الفاتورة (#pricing), كيف تربط نظامك (#integration), مميزات الفاتورة (#features)"],
        ["2026-05-18", "Deduped overlapping sitelinks",
         "Kept higher-converting wording: أسعار الفاتورة vs خطط الأسعار; اربط منشأتك بـ4 خطوات vs كيف تربط نظامك"],
        ["2026-05-18", "Added Arabic-value structured snippets",
         "Types AR + Service catalog AR alongside existing EN versions"],
        ["2026-05-18", "C3 competitor brand-stem keywords (Rewaa)",
         "رواء (49,500/mo), منصة رواء (12,100), رواء المحاسبي (1,000), برنامج رواء (880), رواء منصة (590)"],
        ["2026-05-18", "C3 login negatives",
         "تسجيل الدخول, تسجيل دخول, login (BROAD) — block existing-user search intent"],
        ["2026-05-18", "Paused 12 RARELY_SERVED keywords on C3",
         "7 AR + 5 EN long-tails Google flagged too niche to serve"],
        ["2026-05-18", "Added 7 in-market audiences as observation",
         "21 associations × 3 campaigns — Financial Planning, Tax Prep, Accounting Software, etc."],
    ]


def tab_updated_june_budget() -> list[list]:
    """Replacement for tab 09 — includes ZATCA line."""
    return [
        ["JUNE 2026 BUDGET ALLOCATION (updated 2026-05-18 with ZATCA Phase 2)"],
        [""],
        ["Channel", "May actual", "May effective (after pauses)", "June target", "Δ", "Rationale"],
        ["Google Ads (existing)",  "$93,000", "$70,000",  "$75,000",  "-19%",
         "Pause bad PMax; hold Brand + E-invoice at right size"],
        ["Google Ads (ZATCA new)", "$0",      "$0",       "$7,200",   "NEW",
         "C1 $100/d + C2 $80/d + C3 $60/d × 30d — Phase 2 acquisition window closes 30 June"],
        ["Meta",                   "$24,000", "$24,000",  "$28,000",  "+17%",
         "Scale Bookkeeping_Lookalike + Websiteform; +2 duplications"],
        ["Snapchat",               "$19,000", "$19,000",  "$22,000",  "+16%",
         "Restore iPhone Instantform; launch Android + Bookkeeping"],
        ["Microsoft Ads",          "$13,000", "$8,000",   "$8,000",   "-38%",
         "Pause 5-pack; hold Brand + WebsiteTraffic at cap"],
        ["TikTok",                 "$10,000", "$10,000",  "$10,000",  "0%",
         "Hold; no Tier-1 actions queued"],
        ["LinkedIn",               "$0",      "$0",       "$0",       "0%",
         "Token expired since Mar; revisit Q3"],
        ["TOTAL",                  "$159,000","$131,000", "$150,200", "-5.5%",
         "Net -5.5% vs May actual; ZATCA capture window justifies the +$7.2k addition"],
        [""],
        ["ZATCA-specific projection: $7.2k spend at $30 CPL → ~240 signups → ~75 SQLs → $96 CPQL"],
        ["Combined June outcome: ~2,700 SQLs at $56 blended CPQL (vs status-quo 1,478 at $82)"],
    ]


def main():
    creds  = _creds()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # 1. Get current sheet info
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    print(f"[sheet] existing tabs: {list(existing.keys())}")

    # 2. Add new tabs (idempotent — skip if exist)
    new_tabs = [
        ("13 ZATCA Setup",      tab_zatca_setup()),
        ("14 ZATCA Action Log", tab_zatca_actions_log()),
    ]
    add_requests = []
    for title, _ in new_tabs:
        if title not in existing:
            add_requests.append({"addSheet": {"properties": {"title": title}}})
    if add_requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": add_requests},
        ).execute()
        print(f"[sheet] added {len(add_requests)} new tab(s)")

    # 3. Write content into new tabs
    data = []
    for title, rows in new_tabs:
        data.append({
            "range":          f"'{title}'!A1",
            "majorDimension": "ROWS",
            "values":         rows,
        })

    # 4. Replace tab 07 · June Budget content
    if "07 · June Budget" in existing:
        # Clear the existing range first
        sheets.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range="'07 · June Budget'!A1:Z100",
        ).execute()
        data.append({
            "range":          "'07 · June Budget'!A1",
            "majorDimension": "ROWS",
            "values":         tab_updated_june_budget(),
        })
        print("[sheet] tab 07 · June Budget will be overwritten with ZATCA addition")

    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    print(f"[sheet] wrote {len(data)} tab updates")

    print()
    print("=" * 70)
    print(f"  Sheet updated.")
    print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    print("=" * 70)


if __name__ == "__main__":
    main()
