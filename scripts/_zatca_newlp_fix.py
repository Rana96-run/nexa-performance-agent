"""Fix overconstrained testimonial-only ads:
  1. Rename the 4 ad groups from "..._Testimonials" → "..._NewLP"
  2. Pause the testimonial-themed RSAs (they exist as one option)
  3. Create new broader RSAs with full ZATCA Phase 2 e-invoice messaging
     (3 of 15 headlines are social-proof, the rest are core value props)

Final URL stays the same: lp.qoyod.com/zatca-einvoice/#testimonials
(the # anchor lands on social proof; rest of LP is the e-invoice product).
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

LP_URL = "https://lp.qoyod.com/zatca-einvoice/#testimonials"

# (account, ad_group_id, old_rsa_id, new_name)
TARGETS = [
    ("1513020554", "195984671999", "809712673820", "ZATCAPhase2_AR_NewLP"),
    ("1513020554", "196833050356", "809712625427", "ZATCAVendorShop_AR_NewLP"),
    ("1513020554", "199622505071", "809712576215", "ZATCACompetitor_AR_NewLP"),
    ("5753494964", "199817378314", "809712543290", "ZATCAPhase2_AR_Auto_NewLP"),
]

# Broader RSA — full LP topic with only 3 social-proof headlines mixed in
RSA_HEADLINES = [
    "ربط ZATCA المرحلة الثانية",       # core product
    "فاتورة إلكترونية متوافقة",         # core product
    "ربط منصة فاتورة في دقائق",         # speed
    "REST API + XML + PDF/A-3",        # tech depth
    "متوافق ZATCA 100%",                # compliance
    "تكامل ZATCA Phase 2",              # core product
    "تجربة 14 يوم مجاناً",              # offer
    "بدون بطاقة ائتمان",                # friction remover
    "آلاف الشركات تثق بقيود",           # social proof #1
    "قصص نجاح ZATCA Phase 2",           # social proof #2
    "اقرأ تجارب عملاء قيود",            # social proof #3
    "قيود — برنامج المحاسبة",           # brand
    "دعم عربي 24/7",                   # support
    "ضمان الامتثال أو استرداد",         # guarantee
    "ابدأ الربط اليوم",                # CTA
]
RSA_DESCRIPTIONS = [
    "ربط ZATCA المرحلة الثانية مع قيود. REST API + XML + PDF/A-3. تجربة 14 يوم مجاناً.",
    "فاتورة إلكترونية متوافقة مع ZATCA 100%. ربط مباشر بمنصة فاتورة في دقائق.",
    "آلاف الشركات السعودية تثق بقيود لربط ZATCA Phase 2. اقرأ تجاربهم وانضم إليهم.",
    "قيود — برنامج المحاسبة الأول في السعودية. دعم عربي 24/7. ضمان الامتثال.",
]

# Validate
for h in RSA_HEADLINES:
    assert len(h) <= 30, f"HL {len(h)}: {h}"
for d in RSA_DESCRIPTIONS:
    assert len(d) <= 90, f"DSC {len(d)}: {d}"
print(f"✓ Validated {len(RSA_HEADLINES)} headlines, {len(RSA_DESCRIPTIONS)} descriptions")

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, ag_id, old_rsa_id, new_name in TARGETS:
    print(f"\n=== {new_name} ({ag_id}) ===")

    # 1. Rename ad group
    ag_svc = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = f"customers/{acct}/adGroups/{ag_id}"
    op.update.name = new_name
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["name"]))
    try:
        ag_svc.mutate_ad_groups(customer_id=acct, operations=[op])
        print(f"  ✅ renamed → {new_name}")
    except Exception as e:
        print(f"  ❌ rename: {_err(e)[:200]}")

    # 2. Pause the testimonial-themed RSA
    svc = client.get_service("AdGroupAdService")
    op_p = client.get_type("AdGroupAdOperation")
    op_p.update.resource_name = f"customers/{acct}/adGroupAds/{ag_id}~{old_rsa_id}"
    op_p.update.status = client.enums.AdGroupAdStatusEnum.PAUSED
    op_p.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
        svc.mutate_ad_group_ads(customer_id=acct, operations=[op_p])
        print(f"  ⊘ paused old testimonial RSA {old_rsa_id}")
    except Exception as e:
        print(f"  ❌ pause: {_err(e)[:200]}")

    # 3. Create new broader RSA
    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.ad_group = f"customers/{acct}/adGroups/{ag_id}"
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(LP_URL)
    for h in RSA_HEADLINES:
        ah = client.get_type("AdTextAsset"); ah.text = h
        aga.ad.responsive_search_ad.headlines.append(ah)
    for d in RSA_DESCRIPTIONS:
        ad = client.get_type("AdTextAsset"); ad.text = d
        aga.ad.responsive_search_ad.descriptions.append(ad)
    aga.ad.responsive_search_ad.path1 = "zatca"
    aga.ad.responsive_search_ad.path2 = "ايداع"
    try:
        r = svc.mutate_ad_group_ads(customer_id=acct, operations=[op])
        print(f"  ✅ new RSA: {r.results[0].resource_name}")
    except Exception as e:
        print(f"  ❌ new RSA: {_err(e)[:300]}")

    # 4. Remove the paused old RSA so we don't have 2 ads in this group
    op_rm = client.get_type("AdGroupAdOperation")
    op_rm.remove = f"customers/{acct}/adGroupAds/{ag_id}~{old_rsa_id}"
    try:
        svc.mutate_ad_group_ads(customer_id=acct, operations=[op_rm])
        print(f"  ⊘ removed old paused RSA {old_rsa_id}")
    except Exception as e:
        print(f"  ⚠ remove old RSA: {_err(e)[:120]}")

print("\nDONE — ad groups renamed, RSAs replaced with broader e-invoice messaging.")
