"""Create the Qawaem (Decision 236) campaign on Microsoft Ads Account 1
mirroring Google_Search_AR_FinancialStatemnt as closely as possible.

Mirrors:
  Google: Google_Search_AR_FinancialStatemnt (23861837000)
  MS:     Bing_Search_AR_FinancialStatemnt (PAUSED on create, $120/d)

Single-script run — creates campaign + ad group + keywords + RSA.
Extensions + audiences in follow-up scripts.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.microsoft_ads import get_service, ACCOUNT_ID

LP_URL = "https://lp.qoyod.com/qawaem/"

# Mirror the Google AR ad group's keyword set
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
    ("نموذج",  "Broad"),
    ("PDF",    "Phrase"),
    ("تعريف",  "Broad"),
    ("مفهوم",  "Broad"),
    ("شرح",    "Broad"),
    ("وظيفة",  "Broad"),
    ("login",  "Phrase"),
    ("tutorial", "Phrase"),
    ("download", "Phrase"),
    ("free download", "Phrase"),
    ("course", "Phrase"),
    ("training", "Phrase"),
    ("دورة", "Broad"),
    ("كورس", "Broad"),
    ("تحميل", "Phrase"),
    ("مجاني", "Phrase"),
    ("غرامة محسوبة", "Phrase"),
    ("حاسبة", "Broad"),
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
    svc = get_service("CampaignManagementService")

    # ── 1. Create campaign ─────────────────────────────────────────────────
    print("1. Create campaign — Bing_Search_AR_FinancialStatemnt (PAUSED, $120/d)")
    camp = svc.factory.create("Campaign")
    camp.Name         = "Bing_Search_AR_FinancialStatemnt"
    camp.Status       = "Paused"
    camp.CampaignType = ["Search"]
    camp.DailyBudget  = 120.0
    camp.BudgetType   = "DailyBudgetStandard"
    camp.TimeZone     = "KuwaitRiyadh"
    camp.Languages    = {"string": ["Arabic", "English"]}
    # Manual CPC default — MS lets us promote to MaxConversions later once
    # conversion data accumulates anyway. Setting MaxConversionsBiddingScheme
    # at creation triggers suds enum-deserialization issues.

    campaigns = svc.factory.create("ArrayOfCampaign")
    campaigns.Campaign.append(camp)
    result = svc.AddCampaigns(AccountId=ACCOUNT_ID, Campaigns=campaigns)
    camp_id = result.CampaignIds.long[0]
    print(f"  ✅ campaign_id = {camp_id}")
    if hasattr(result, "PartialErrors") and result.PartialErrors and result.PartialErrors.BatchError:
        for e in result.PartialErrors.BatchError:
            print(f"     ⚠ partial: {e.ErrorCode} {e.Message[:200]}")

    # ── 2. Set Saudi geo at campaign level via criterion ──────────────────
    print("\n2. Set Saudi geo (location code 144 = Saudi Arabia)")
    # Microsoft uses LocationCriterion with Geo Target Code
    crit = svc.factory.create("CampaignCriterion")
    crit.CampaignId = camp_id
    crit.Type = "LocationCriterion"
    loc = svc.factory.create("LocationCriterion")
    loc.LocationId = 144  # Saudi Arabia
    loc.Type = "LocationCriterion"
    crit.Criterion = loc

    crits = svc.factory.create("ArrayOfCampaignCriterion")
    crits.CampaignCriterion.append(crit)
    try:
        r = svc.AddCampaignCriterions(CampaignCriterions=crits, CriterionType="Targets")
        print(f"  ✅ Saudi location criterion added")
    except Exception as e:
        print(f"  ⚠ location criterion: {str(e)[:200]}")

    # ── 3. Create ad group ────────────────────────────────────────────────
    print("\n3. Create ad group — FinancialSt_AR (ACTIVE)")
    ag = svc.factory.create("AdGroup")
    ag.Name           = "FinancialSt_AR"
    ag.Status         = "Active"
    ag.PricingModel   = "Cpc"
    ag.Network        = "OwnedAndOperatedAndSyndicatedSearch"

    ag_array = svc.factory.create("ArrayOfAdGroup")
    ag_array.AdGroup.append(ag)
    result = svc.AddAdGroups(CampaignId=camp_id, AdGroups=ag_array)
    ag_id = result.AdGroupIds.long[0]
    print(f"  ✅ ad_group_id = {ag_id}")

    # ── 4. Add keywords (positive) ────────────────────────────────────────
    print(f"\n4. Add {len(AR_KEYWORDS)} positive keywords")
    kw_array = svc.factory.create("ArrayOfKeyword")
    for text, mt in AR_KEYWORDS:
        k = svc.factory.create("Keyword")
        k.Text = text
        k.MatchType = mt
        k.Status = "Active"
        bid = svc.factory.create("Bid")
        bid.Amount = 2.0
        k.Bid = bid
        kw_array.Keyword.append(k)
    result = svc.AddKeywords(AdGroupId=ag_id, Keywords=kw_array)
    n_added = sum(1 for kid in result.KeywordIds.long if kid)
    print(f"  ✅ added {n_added} keyword(s)")

    # ── 5. Add negatives at campaign level ────────────────────────────────
    print(f"\n5. Add {len(NEGATIVES)} negative keywords at campaign level")
    neg_array = svc.factory.create("ArrayOfNegativeKeyword")
    for text, mt in NEGATIVES:
        nk = svc.factory.create("NegativeKeyword")
        nk.Text = text
        nk.MatchType = mt
        neg_array.NegativeKeyword.append(nk)
    try:
        result = svc.AddNegativeKeywordsToEntities(
            EntityNegativeKeywords=_build_entity_negs(svc, camp_id, neg_array)
        )
        print(f"  ✅ added campaign-level negatives")
    except Exception as e:
        print(f"  ⚠ negatives: {str(e)[:300]}")

    # ── 6. Create RSA ─────────────────────────────────────────────────────
    print(f"\n6. Create Responsive Search Ad ({len(HEADLINES)} headlines + {len(DESCRIPTIONS)} descriptions)")
    rsa = svc.factory.create("ResponsiveSearchAd")
    rsa.Type   = "ResponsiveSearch"
    rsa.Status = "Active"
    rsa.FinalUrls = {"string": [LP_URL]}

    rsa.Headlines = svc.factory.create("ArrayOfAssetLink")
    for h in HEADLINES:
        al = svc.factory.create("AssetLink")
        ta = svc.factory.create("TextAsset")
        ta.Text = h
        ta.Type = "TextAsset"
        al.Asset = ta
        rsa.Headlines.AssetLink.append(al)

    rsa.Descriptions = svc.factory.create("ArrayOfAssetLink")
    for d in DESCRIPTIONS:
        al = svc.factory.create("AssetLink")
        ta = svc.factory.create("TextAsset")
        ta.Text = d
        ta.Type = "TextAsset"
        al.Asset = ta
        rsa.Descriptions.AssetLink.append(al)

    ads_array = svc.factory.create("ArrayOfAd")
    ads_array.Ad.append(rsa)
    try:
        result = svc.AddAds(AdGroupId=ag_id, Ads=ads_array)
        print(f"  ✅ RSA created: ad_id={result.AdIds.long[0]}")
        if hasattr(result, "PartialErrors") and result.PartialErrors and result.PartialErrors.BatchError:
            for e in result.PartialErrors.BatchError:
                print(f"     ⚠ {e.ErrorCode}: {e.Message[:200]}")
    except Exception as e:
        print(f"  ❌ RSA failed: {str(e)[:400]}")

    print("\n" + "=" * 70)
    print("DONE — Bing_Search_AR_FinancialStatemnt created (PAUSED)")
    print(f"  campaign_id = {camp_id}")
    print(f"  ad_group_id = {ag_id}")
    print("=" * 70)


def _build_entity_negs(svc, camp_id, neg_array):
    """Wrap negatives into the EntityNegativeKeyword structure."""
    arr = svc.factory.create("ArrayOfEntityNegativeKeyword")
    ent = svc.factory.create("EntityNegativeKeyword")
    ent.EntityId   = camp_id
    ent.EntityType = "Campaign"
    ent.NegativeKeywords = neg_array
    arr.EntityNegativeKeyword.append(ent)
    return arr


if __name__ == "__main__":
    main()
