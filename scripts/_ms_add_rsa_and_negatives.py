"""Add RSA + negatives to the already-created Qawaem campaign on MS Ads.
Campaign + ad group + keywords are live; just need the ad creative and
campaign-level negatives."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.microsoft_ads import get_service

CAMP_ID = 487816800
AG_ID   = 1238051567759836
LP_URL  = "https://lp.qoyod.com/qawaem/"

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
NEGATIVES = [
    ("نموذج",  "Broad"), ("PDF", "Phrase"), ("تعريف", "Broad"),
    ("مفهوم",  "Broad"), ("شرح", "Broad"),  ("وظيفة", "Broad"),
    ("login",  "Phrase"), ("tutorial", "Phrase"), ("download", "Phrase"),
    ("free download", "Phrase"), ("course", "Phrase"), ("training", "Phrase"),
    ("دورة",  "Broad"), ("كورس", "Broad"),  ("تحميل", "Phrase"),
    ("مجاني", "Phrase"), ("حاسبة", "Broad"), ("غرامة محسوبة", "Phrase"),
]


svc = get_service("CampaignManagementService")
f = svc.factory

# ── 1. Build RSA ──────────────────────────────────────────────────────────
print("1. Add RSA to ad group")
rsa = f.create("ResponsiveSearchAd")
rsa.Type   = "ResponsiveSearch"
rsa.Status = "Active"
rsa.FinalUrls = {"string": [LP_URL]}

# Headlines
headlines_arr = f.create("ArrayOfAssetLink")
for h in HEADLINES:
    al = f.create("AssetLink")
    ta = f.create("TextAsset")
    ta.Text = h
    ta.Type = "TextAsset"
    al.Asset = ta
    headlines_arr.AssetLink.append(al)
rsa.Headlines = headlines_arr

# Descriptions
descs_arr = f.create("ArrayOfAssetLink")
for d in DESCRIPTIONS:
    al = f.create("AssetLink")
    ta = f.create("TextAsset")
    ta.Text = d
    ta.Type = "TextAsset"
    al.Asset = ta
    descs_arr.AssetLink.append(al)
rsa.Descriptions = descs_arr

ads_arr = f.create("ArrayOfAd")
ads_arr.Ad.append(rsa)
try:
    r = svc.AddAds(AdGroupId=AG_ID, Ads=ads_arr)
    print(f"   ✅ RSA created: ad_id={r.AdIds.long[0]}")
    if hasattr(r, "PartialErrors") and r.PartialErrors and hasattr(r.PartialErrors, "BatchError"):
        for e in r.PartialErrors.BatchError:
            print(f"      ⚠ {e.ErrorCode}: {e.Message[:200]}")
except Exception as e:
    print(f"   ❌ {type(e).__name__}: {str(e)[:300]}")

# ── 2. Add campaign-level negatives ──────────────────────────────────────
print("\n2. Add 18 campaign-level negatives")
neg_arr = f.create("ArrayOfNegativeKeyword")
for text, mt in NEGATIVES:
    nk = f.create("NegativeKeyword")
    nk.Text = text
    nk.MatchType = mt
    neg_arr.NegativeKeyword.append(nk)

ent_arr = f.create("ArrayOfEntityNegativeKeyword")
ent = f.create("EntityNegativeKeyword")
ent.EntityId   = CAMP_ID
ent.EntityType = "Campaign"
ent.NegativeKeywords = neg_arr
ent_arr.EntityNegativeKeyword.append(ent)

try:
    r = svc.AddNegativeKeywordsToEntities(EntityNegativeKeywords=ent_arr)
    print(f"   ✅ negatives added")
    if hasattr(r, "PartialErrors") and r.PartialErrors and hasattr(r.PartialErrors, "BatchError"):
        for e in r.PartialErrors.BatchError:
            print(f"      ⚠ {e.ErrorCode}: {e.Message[:200]}")
except Exception as e:
    print(f"   ❌ {type(e).__name__}: {str(e)[:300]}")
