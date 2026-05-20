"""Create the Qawaem campaign on Microsoft Ads via BulkServiceManager.

Bypasses the SOAP enum serialization issues we hit earlier by using
Microsoft's bulk-upload CSV interface — same path their UI tool uses
internally for 'Import from Google Ads'.

Creates: campaign + ad group + 16 keywords + 18 negatives + 1 RSA.
Extensions and audiences added in follow-up scripts after this succeeds.
"""
import sys, os, time, tempfile
from types import SimpleNamespace
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.v13.bulk import BulkServiceManager
from bingads.v13.bulk.entities import (
    BulkCampaign, BulkAdGroup, BulkKeyword,
    BulkResponsiveSearchAd, BulkCampaignNegativeKeyword,
)
from executors.microsoft_ads import _auth, ACCOUNT_ID

LP_URL = "https://lp.qoyod.com/qawaem/"

# Mirror Google: Google_Search_AR_FinancialStatemnt
CAMPAIGN_NAME = "Bing_Search_AR_FinancialStatemnt"
AD_GROUP_NAME = "FinancialSt_AR"

AR_KEYWORDS = [
    ("قرار وزاري 236",                              "Exact"),
    ("غرامة عدم إيداع القوائم المالية",             "Exact"),
    ("منصة قوائم وزارة التجارة",                    "Exact"),
    ("إيداع القوائم المالية في السعودية",            "Phrase"),
    ("غرامة التأخر في إيداع القوائم المالية",        "Phrase"),
    ("عقوبة عدم إيداع القوائم المالية",              "Phrase"),
    ("موعد إيداع القوائم المالية",                   "Phrase"),
    ("قوائم وزارة التجارة السعودية",                 "Phrase"),
    ("كيف أودع القوائم المالية على منصة قوائم",      "Phrase"),
    ("متى يجب إيداع القوائم المالية وزارة التجارة",  "Phrase"),
    ("الفرق بين قوائم وزاتكا",                        "Phrase"),
    ("خطوات إيداع القوائم المالية في منصة قوائم",    "Phrase"),
    ("قرار 236 وزارة التجارة 1447",                  "Phrase"),
    ("نظام الشركات السعودي إيداع القوائم",           "Phrase"),
    ("Qawaem platform Saudi Arabia",                  "Phrase"),
    ("Ministry of Commerce financial statements Saudi", "Phrase"),
]

NEGATIVES = [
    ("نموذج",  "Broad"), ("PDF", "Phrase"), ("تعريف", "Broad"),
    ("مفهوم",  "Broad"), ("شرح", "Broad"),  ("وظيفة", "Broad"),
    ("login",  "Phrase"), ("tutorial", "Phrase"), ("download", "Phrase"),
    ("free download", "Phrase"), ("course", "Phrase"), ("training", "Phrase"),
    ("دورة",  "Broad"), ("كورس", "Broad"),  ("تحميل", "Phrase"),
    ("مجاني", "Phrase"), ("حاسبة", "Broad"), ("غرامة محسوبة", "Phrase"),
]

HEADLINES = [
    "تجنب غرامة قرار 236",
    "أودع قوائمك المالية في دقائق",
    "موعد الإيداع: 30 يونيو 2026",
    "غرامة شخصية تصل 20,000 ريال",
    "متوافق مع منصة قوائم",
    "تصدير XBRL بنقرة واحدة",
    "أكثر من 50,000 شركة سعودية",
    "متوافق ZATCA + قوائم",
    "تجربة 14 يوم بدون بطاقة",
    "إعداد في 14 دقيقة",
    "أنت مسؤول شخصياً عن الإيداع",
    "احم المدير من غرامة 236",
    "احسب غرامة شركتك مجاناً",
    "ابدأ الإيداع في دقائق",
    "أودع قوائمك من 120 ريال/شهر",
]
DESCRIPTIONS = [
    "تجنب غرامة قرار 236 الشخصية. قيود يصدر قوائمك ويرفعها لمنصة قوائم في دقائق. ابدأ مجاناً.",
    "أكثر من 50,000 شركة سعودية تستخدم قيود. تجربة 14 يوم بدون بطاقة. ابدأ الآن.",
    "موعد إيداع قوائم 2025 ينتهي 30 يونيو 2026. غرامة شخصية تصل 20,000 ريال للمدير.",
    "موعد الإيداع 30 يونيو 2026. قيود يصدر قوائمك جاهزة لمنصة قوائم. سجل مجاناً الآن.",
]


def main():
    auth = _auth()
    mgr  = BulkServiceManager(
        authorization_data=auth,
        poll_interval_in_milliseconds=5000,
        environment="production",
    )

    # Use a SOAP service to get the proto factory (for entity objects).
    # We don't actually CALL the SOAP service — just use its factory to build
    # objects that the Bulk service understands.
    from bingads.service_client import ServiceClient
    camp_svc = ServiceClient(
        service="CampaignManagementService", version="v13",
        authorization_data=auth, environment="production",
    )
    f = camp_svc.factory

    # ── Build Campaign ─────────────────────────────────────────────────────
    campaign = f.create("Campaign")
    campaign.Id            = -1   # negative ref for bulk create
    campaign.Name          = CAMPAIGN_NAME
    campaign.Status        = "Paused"
    campaign.CampaignType  = ["Search"]
    campaign.DailyBudget   = 120.0
    campaign.BudgetType    = "DailyBudgetStandard"
    campaign.TimeZone      = "KuwaitRiyadh"
    campaign.Languages     = SimpleNamespace(string=["Arabic", "English"])

    bulk_campaign = BulkCampaign()
    bulk_campaign.campaign = campaign
    bulk_campaign.client_id = "qawaem_camp"

    # ── Build Ad Group ─────────────────────────────────────────────────────
    ad_group = f.create("AdGroup")
    ad_group.Id            = -2
    ad_group.Name          = AD_GROUP_NAME
    ad_group.Status        = "Active"
    ad_group.PricingModel  = "Cpc"

    bulk_ad_group = BulkAdGroup()
    bulk_ad_group.campaign_id = -1
    bulk_ad_group.ad_group    = ad_group
    bulk_ad_group.client_id   = "qawaem_ag"

    # ── Build Keywords ─────────────────────────────────────────────────────
    bulk_keywords = []
    for i, (text, mt) in enumerate(AR_KEYWORDS):
        kw = f.create("Keyword")
        kw.Text = text
        kw.MatchType = mt
        kw.Status = "Active"
        bid = f.create("Bid"); bid.Amount = 2.0
        kw.Bid = bid

        bkw = BulkKeyword()
        bkw.ad_group_id = -2
        bkw.keyword     = kw
        bkw.client_id   = f"qawaem_kw_{i}"
        bulk_keywords.append(bkw)

    # ── Build Campaign Negatives ──────────────────────────────────────────
    bulk_negs = []
    for i, (text, mt) in enumerate(NEGATIVES):
        nk = f.create("NegativeKeyword")
        nk.Text = text
        nk.MatchType = mt

        bn = BulkCampaignNegativeKeyword()
        bn.campaign_id      = -1
        bn.negative_keyword = nk
        bn.client_id        = f"qawaem_neg_{i}"
        bulk_negs.append(bn)

    # ── Build RSA ──────────────────────────────────────────────────────────
    rsa = f.create("ResponsiveSearchAd")
    rsa.Type   = "ResponsiveSearch"
    rsa.Status = "Active"
    rsa.FinalUrls = SimpleNamespace(string=[LP_URL])

    def make_asset_link(text):
        # Use SimpleNamespace to avoid suds' empty-enum wrappers that don't
        # JSON-serialize for the Bulk writer
        return SimpleNamespace(
            Asset=SimpleNamespace(Text=text, Type="TextAsset"),
            PinnedField=None,
            EditorialStatus=None,
            AssetPerformanceLabel=None,
        )

    rsa.Headlines    = SimpleNamespace(AssetLink=[make_asset_link(h) for h in HEADLINES])
    rsa.Descriptions = SimpleNamespace(AssetLink=[make_asset_link(d) for d in DESCRIPTIONS])

    bulk_rsa = BulkResponsiveSearchAd()
    bulk_rsa.ad_group_id           = -2
    bulk_rsa.responsive_search_ad  = rsa
    bulk_rsa.client_id             = "qawaem_rsa"

    # ── Upload ─────────────────────────────────────────────────────────────
    entities = [bulk_campaign, bulk_ad_group] + bulk_keywords + bulk_negs + [bulk_rsa]
    print(f"Uploading {len(entities)} entities (campaign + adgroup + "
          f"{len(bulk_keywords)} kw + {len(bulk_negs)} negs + 1 RSA)")

    out_dir = tempfile.gettempdir()

    from bingads.v13.bulk import EntityUploadParameters
    params = EntityUploadParameters(
        entities=entities,
        response_mode="ErrorsAndResults",
        result_file_directory=out_dir,
        result_file_name="qawaem_upload_result.csv",
        overwrite_result_file=True,
    )

    print(f"  poll interval 5s, output → {out_dir}/qawaem_upload_result.csv")
    result_entities = mgr.upload_entities(params)

    # Inspect results
    print(f"\n  Upload complete. {len(list(result_entities))} result entities (re-read file):")
    # Re-read since the generator may have been consumed
    result_file = os.path.join(out_dir, "qawaem_upload_result.csv")
    if os.path.exists(result_file):
        with open(result_file, "r", encoding="utf-8") as fh:
            print(fh.read()[:3000])
    else:
        print("  (no result file found)")


if __name__ == "__main__":
    main()
