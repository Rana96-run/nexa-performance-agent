"""Add just the RSA to the existing Qawaem MS Ads ad group via Bulk."""
import sys, os, tempfile
from types import SimpleNamespace
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.v13.bulk import BulkServiceManager, EntityUploadParameters
from bingads.v13.bulk.entities import BulkResponsiveSearchAd
from executors.microsoft_ads import _auth

AG_ID  = 1238051567759836
LP_URL = "https://lp.qoyod.com/qawaem/"

HEADLINES = [
    "تجنب غرامة قرار 236", "أودع قوائمك المالية في دقائق",
    "موعد الإيداع: 30 يونيو 2026", "غرامة شخصية تصل 20,000 ريال",
    "متوافق مع منصة قوائم", "تصدير XBRL بنقرة واحدة",
    "أكثر من 50,000 شركة سعودية", "متوافق ZATCA + قوائم",
    "تجربة 14 يوم بدون بطاقة", "إعداد في 14 دقيقة",
    "أنت مسؤول شخصياً عن الإيداع", "احم المدير من غرامة 236",
    "احسب غرامة شركتك مجاناً", "ابدأ الإيداع في دقائق",
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

    from bingads.service_client import ServiceClient
    camp_svc = ServiceClient(
        service="CampaignManagementService", version="v13",
        authorization_data=auth, environment="production",
    )
    f = camp_svc.factory

    rsa = f.create("ResponsiveSearchAd")
    rsa.Type   = "ResponsiveSearch"
    rsa.Status = "Active"
    rsa.FinalUrls = SimpleNamespace(string=[LP_URL])

    def make_al(text):
        return SimpleNamespace(
            Asset=SimpleNamespace(Text=text, Type="TextAsset"),
            PinnedField=None,
            EditorialStatus=None,
            AssetPerformanceLabel=None,
        )

    rsa.Headlines    = SimpleNamespace(AssetLink=[make_al(h) for h in HEADLINES])
    rsa.Descriptions = SimpleNamespace(AssetLink=[make_al(d) for d in DESCRIPTIONS])

    bulk_rsa = BulkResponsiveSearchAd()
    bulk_rsa.ad_group_id = AG_ID
    bulk_rsa.responsive_search_ad = rsa

    # Use Windows-correct path
    out_dir = os.path.normpath(tempfile.gettempdir())
    params = EntityUploadParameters(
        entities=[bulk_rsa],
        response_mode="ErrorsAndResults",
        result_file_directory=out_dir,
        result_file_name="qawaem_rsa_result.csv",
        overwrite_result_file=True,
    )

    print(f"Uploading 1 RSA via bulk")
    try:
        result_generator = mgr.upload_entities(params)
        results = list(result_generator)
        print(f"  Upload returned {len(results)} entities")
        for r in results:
            print(f"  Entity: {type(r).__name__}")
            if hasattr(r, "responsive_search_ad") and r.responsive_search_ad:
                print(f"    Ad Id: {r.responsive_search_ad.Id}")
                print(f"    Status: {r.responsive_search_ad.Status}")
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {str(e)[:400]}")

    # Try to read the result file
    rf = os.path.join(out_dir, "qawaem_rsa_result.csv")
    if os.path.exists(rf):
        print(f"\nResult file: {rf}")
        with open(rf, "r", encoding="utf-8-sig") as fh:
            print(fh.read()[:3000])
    else:
        print(f"\n  (result file not at {rf})")


if __name__ == "__main__":
    main()
