"""Append today's session work to Tab 14 ZATCA Action Log + add a 'status' column.
"""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from dotenv import load_dotenv; load_dotenv()
from google.oauth2 import service_account
from googleapiclient.discovery import build

creds = service_account.Credentials.from_service_account_file(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc = build("sheets", "v4", credentials=creds)
SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
TAB = "14 ZATCA Action Log"

# Ensure header has 5 cols (existing 4 + status). Read current header first.
hdr = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1:E1").execute().get("values", [[]])[0]
print(f"Current header ({len(hdr)} cols): {hdr}")
if len(hdr) < 5:
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"'{TAB}'!E1",
        valueInputOption="RAW",
        body={"values": [["status"]]},
    ).execute()
    print(f"  ✅ added 'status' column header")

# Today's session log
TODAY = "2026-05-22"
ROWS = [
    [TODAY, "Acc2",
     "campaigns_copied",
     "Copied Google_Search_AREN_FinancialStatement + ZATCAPhase2 from Acc1 to Acc2 (5753494964). All settings mirrored (budget, geo, langs, negatives, keywords, RSAs).",
     "Done"],
    [TODAY, "Acc1+Acc2 FinStatement",
     "keywords_added_high_volume",
     "+12 high-volume AR keywords per AR ad group (منصة قوائم 3.6k/mo, قائمة الدخل 1.6k, الاستعلام cluster 1.9k, etc.) + 2 BROAD heads for Smart Bidding discovery.",
     "Done"],
    [TODAY, "Acc1+Acc2 FinStatement",
     "prophylactic_negatives",
     "+15 negatives per campaign: محاسب قانوني cluster (hiring intent), jobs (وظائف/توظيف/jobs/hiring), AR download (تحميل/تنزيل), template seekers (نموذج/نماذج/pdf/excel/template).",
     "Done"],
    [TODAY, "Acc1+Acc2 FinStatement",
     "promotion_extension",
     "SAR 100 off Qoyod Annual Plan promo asset (AR + EN versions) linked at campaign level.",
     "Done"],
    [TODAY, "Acc1+Acc2 FinStatement",
     "excellent_rsa_v2",
     "Replaced previous RSAs with 15-headline diverse v2 (max 3 قوائم-root for EXCELLENT-strength) on AR + EN ad groups. Removed 7 paused experimental RSAs (cleanup).",
     "Done"],
    [TODAY, "Acc2 FinStatement",
     "mirror_full_bundle",
     "Acc2 FinStatement got full parity with Acc1 Qawaem bundle: 6 sitelinks + 8 callouts + 2 snippets + 19 audiences (11 in-market + 5 observe + 3 customer exclusions, bid_only=True).",
     "Done"],
    [TODAY, "Acc1 IS_FinStatement (23865358505)",
     "mirrored_main_campaign",
     "+14 AR keywords (12 high-vol + 2 BROAD) + 15 prophylactic negatives + 2 promo assets. Skipped RSAs (already 15-headline) + audiences (already mirror).",
     "Done"],
    [TODAY, "Acc2 ZATCAPhase2",
     "mirror_extensions",
     "5 sitelinks (einvoice-integration anchors) + 10 callouts + 4 structured snippets (Types/Service catalog × AR+EN) linked. Mirrors Acc1 Phase2.",
     "Done"],
    [TODAY, "Acc2 ZATCAPhase2",
     "keywords_added",
     "+10 high-vol kw (فاتورة إلكترونية variants 1k/mo, zatca portal 720/mo, فواتير الكترونية, انشاء فاتورة) + 2 BROAD AR heads + 3 BROAD EN heads (e-invoicing Saudi, ZATCA Phase 2, ZATCA integration) + 3 prophylactic negatives (PDF→Word converter).",
     "Done"],
    [TODAY, "4 ZATCA campaigns (Phase2/VendorShop/Competitor × Acc1+Acc2 Phase2)",
     "newlp_adgroups_created",
     "Created '<Campaign>_AR_NewLP' ad group per campaign. Each: 5 kw (duplicated from source AR) + 1 broader-themed RSA (15 headlines, 3 social-proof) routed to lp.qoyod.com/zatca-einvoice/#testimonials + 5 ad-group-level sitelinks anchored on /zatca-einvoice/ sections.",
     "Done"],
    [TODAY, "7 campaigns (4 ZATCA + 3 FinStatement)",
     "sitelink_isolation",
     "Migrated all sitelinks from CAMPAIGN level → AD-GROUP level on every ENABLED ad group. Campaign-level emptied. Each ad group now owns its sitelink set — editing one ad group doesn't leak to others.",
     "Done"],
    [TODAY, "Acc1 FinStatement (23861837000)",
     "cpc_ceiling_bumped",
     "Campaign CPC ceiling on TARGET_SPEND (Max Clicks) bumped $0 (legacy = no limit signal) → $4 → $10. Required to break QS=0 trap (87.5% rank-lost-IS).",
     "Done"],
    [TODAY, "Acc1 Search_AR_Brand v1 (22434988923)",
     "keyword_rich_rsa_deployed",
     "15-headline RSA with 4 brand-keyword variants PINNED to Position 1 (نظام قيود المحاسبي / برنامج قيود المحاسبي / منصة قيود الكاملة / برنامج قيود لإدارة منشأتك) + 11 unpinned value-prop headlines + 4 descriptions. Final URL qoyod.com. ENABLED alongside existing ads.",
     "Done"],
    [TODAY, "Acc1 Search_AR_Brand_v2 (23032247671)",
     "network_fix_display_off",
     "Diagnosed 7% CTR / $135 CPQL: campaign had Display Network + Search Partners ON. ~102k of 105k impressions were Display garbage. Disabled both networks (target_content_network=False, target_search_network=False). Expected CTR 25-35%, CPQL $40-60 within 7d.",
     "Done"],
    [TODAY, "Acc1 Search_AR_Brand_v2 (23032247671)",
     "negatives_added",
     "+14 negatives: competitors (odoo, foodics, mudad, tally, wafeq, neoleap, aliphia, الاستاذ المحاسبي, erp system) + login intent (sign in, login, تسجيل الدخول/دخول) + قائمة EXACT.",
     "Done"],
    [TODAY, "Acc2 Search_E-invoice_AR (16851344135)",
     "url_matched_sitelinks_per_adgroup",
     "Per-ad-group sitelinks matched to each ad group's destination URL: برنامج محاسبة + قيود محاسبية → /accounting/ anchors (4 each); فوترة إلكترونية → /einvoice-integration/ anchors (5); هيئة الزكاة → /zatca-einvoice/ anchors (5). Campaign-level emptied.",
     "Done"],
    [TODAY, "Infrastructure",
     "multi_account_compliance_monitor",
     "Wired Acc2 into scripts/audit_compliance_monitor.py via ACCOUNTS dict. Auto-graduates TARGET_SPEND→MAX_CONV at 5 leads/14d, flags underspending/disapprovals. Runs 06:45 + 18:00 Riyadh in operational_scheduler.",
     "Done"],
]

# Append rows
resp = svc.spreadsheets().values().append(
    spreadsheetId=SHEET_ID,
    range=f"'{TAB}'!A:E",
    valueInputOption="RAW",
    insertDataOption="INSERT_ROWS",
    body={"values": ROWS},
).execute()
print(f"\n✅ Appended {len(ROWS)} rows to '{TAB}'")
print(f"  range updated: {resp.get('updates', {}).get('updatedRange')}")
print(f"\n  https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=270092240")
