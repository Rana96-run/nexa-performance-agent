"""Create a testimonial-angled ad group + RSA + ad-group-level sitelinks
in all 4 ENABLED ZATCA campaigns, pointing to lp.qoyod.com/zatca-einvoice/.

Sitelinks attach at AD GROUP level via AdGroupAssetService — this is the
override layer that won't disturb existing campaign-level sitelinks on
other ad groups.

Per campaign:
  1. New ad group: <CampName>_Testimonials_AR  (CPC bid inherited from campaign)
  2. Duplicate top 5 head-term keywords from the largest existing AR ad group
  3. 1 testimonial-themed RSA (15 headlines + 4 descriptions, EXCELLENT target)
  4. 5 new sitelinks (anchored on /zatca-einvoice/ sub-sections)
  5. Attach sitelinks via AdGroupAsset (ad-group-level override)

# KPI-RULE-BYPASS — campaign asset/ad group creation, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

LP_URL = "https://lp.qoyod.com/zatca-einvoice/#testimonials"

TARGETS = [
    ("1513020554", "23851270716", "Acc 1 ZATCAPhase2"),
    ("1513020554", "23861101390", "Acc 1 ZATCAVendorShop"),
    ("1513020554", "23861965426", "Acc 1 ZATCACompetitor"),
    ("5753494964", "23865711095", "Acc 2 ZATCAPhase2"),
]

# Testimonial-themed AR RSA — 15 headlines (≤30 chars), 4 descs (≤90)
RSA_HEADLINES = [
    "آلاف الشركات تثق بقيود",
    "اقرأ تجارب عملاء قيود",
    "قصص نجاح ZATCA Phase 2",
    "شركات سعودية تعتمد قيود",
    "تجارب حقيقية مع ZATCA",
    "ربط ZATCA في دقائق",
    "متوافق ZATCA 100%",
    "REST API + XML + PDF/A-3",
    "تجربة 14 يوم مجاناً",
    "قيود — الأكثر استخداماً",
    "دعم عربي 24/7",
    "بدون بطاقة ائتمان",
    "تكامل مع منصة فاتورة",
    "موثوق من خبراء المحاسبة",
    "ابدأ كآلاف عملائنا",
]
RSA_DESCRIPTIONS = [
    "اقرأ قصص نجاح آلاف الشركات السعودية التي ربطت ZATCA Phase 2 مع قيود بسهولة.",
    "ربط ZATCA المرحلة الثانية في دقائق. تجارب عملاء حقيقية. تجربة 14 يوم مجاناً.",
    "قيود — برنامج المحاسبة الذي تثق به شركات سعودية. اقرأ تجاربهم وانضم إليهم.",
    "تكامل ZATCA Phase 2 مع REST API. مدعوم من فريق دعم عربي 24/7.",
]

# Sitelinks anchored on /zatca-einvoice/ sections
SITELINKS = [
    {"text": "مميزات الفاتورة",
     "d1": "متوافق ZATCA + REST API", "d2": "كل ما تحتاجه للامتثال",
     "url": "https://lp.qoyod.com/zatca-einvoice/#features"},
    {"text": "خطوات الربط",
     "d1": "ربط ZATCA في 4 خطوات", "d2": "REST API + XML + PDF/A-3",
     "url": "https://lp.qoyod.com/zatca-einvoice/#integration"},
    {"text": "أسعار قيود",
     "d1": "خطط شفافة بدون رسوم خفية", "d2": "تجربة 14 يوم مجاناً",
     "url": "https://lp.qoyod.com/zatca-einvoice/#pricing"},
    {"text": "الأسئلة الشائعة",
     "d1": "كل ما تحتاج عن ZATCA Phase 2", "d2": "إجابات من خبراء قيود",
     "url": "https://lp.qoyod.com/zatca-einvoice/#faq"},
    {"text": "قصص نجاح العملاء",
     "d1": "تجارب 50,000+ شركة سعودية", "d2": "اقرأها قبل اتخاذ القرار",
     "url": "https://lp.qoyod.com/zatca-einvoice/#testimonials"},
]

# Validate
for h in RSA_HEADLINES:
    assert len(h) <= 30, f"HL {len(h)}: {h}"
for d in RSA_DESCRIPTIONS:
    assert len(d) <= 90, f"DSC {len(d)}: {d}"
print(f"✓ Validated {len(RSA_HEADLINES)} headlines, {len(RSA_DESCRIPTIONS)} descriptions")

client = get_client()
ga = client.get_service("GoogleAdsService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, cid, label in TARGETS:
    print(f"\n{'=' * 72}")
    print(f"{label} (campaign {cid})")
    print('=' * 72)

    # 1. Pick source ad group: prefer one with "AR" in name, else first
    ag_list = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.id, ad_group.name, ad_group.cpc_bid_micros,
               ad_group.status
        FROM ad_group
        WHERE campaign.id = {cid}
          AND ad_group.status = 'ENABLED'
    """):
        ag_list.append((str(r.ad_group.id), r.ad_group.name, r.ad_group.cpc_bid_micros))
    if not ag_list:
        print(f"  ⚠ no enabled ad groups; skipping")
        continue
    ar_ones = [t for t in ag_list if "AR" in t[1] or "ar" in t[1].lower()]
    src_ag_id, src_ag_name, src_cpc = (ar_ones[0] if ar_ones else ag_list[0])
    print(f"  source ad group: {src_ag_name} ({src_ag_id})  cpc=${src_cpc/1e6:.2f}")

    # 2. Top 5 keywords from that ad group (by impressions if any, else first 5)
    src_kws = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               metrics.impressions
        FROM keyword_view
        WHERE ad_group.id = {src_ag_id}
          AND ad_group_criterion.status = 'ENABLED'
          AND segments.date DURING LAST_30_DAYS
        ORDER BY metrics.impressions DESC
        LIMIT 5
    """):
        src_kws.append((r.ad_group_criterion.keyword.text,
                        r.ad_group_criterion.keyword.match_type.name))
    if not src_kws:
        # Fallback — no metrics, just grab any 5
        for r in ga.search(customer_id=acct, query=f"""
            SELECT ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type
            FROM ad_group_criterion
            WHERE ad_group.id = {src_ag_id}
              AND ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.negative = FALSE
              AND ad_group_criterion.status = 'ENABLED'
            LIMIT 5
        """):
            src_kws.append((r.ad_group_criterion.keyword.text,
                            r.ad_group_criterion.keyword.match_type.name))
    print(f"  source kw to duplicate: {len(src_kws)}")

    # 3. Create new ad group "<Campaign>_Testimonials_AR"
    new_ag_name = f"{src_ag_name}_Testimonials" if "Testimonials" not in src_ag_name \
                  else f"{src_ag_name}_v2"
    # Hard cap name length
    if len(new_ag_name) > 80:
        new_ag_name = new_ag_name[:80]

    ag_svc = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    a = op.create
    a.name = new_ag_name
    a.campaign = f"customers/{acct}/campaigns/{cid}"
    a.status = client.enums.AdGroupStatusEnum.ENABLED
    a.cpc_bid_micros = src_cpc if src_cpc > 0 else 2_000_000  # fallback $2
    try:
        r = ag_svc.mutate_ad_groups(customer_id=acct, operations=[op])
        new_ag_rn = r.results[0].resource_name
        new_ag_id = new_ag_rn.split("/")[-1]
        print(f"  ✅ ad group created: {new_ag_name} ({new_ag_id})")
    except Exception as e:
        print(f"  ❌ ad group: {_err(e)[:200]}")
        continue

    # 4. Add 5 duplicated keywords to new ad group
    svc_kw = client.get_service("AdGroupCriterionService")
    kw_ok = 0
    for text, match in src_kws:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = new_ag_rn
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = text
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
        try:
            svc_kw.mutate_ad_group_criteria(customer_id=acct, operations=[op])
            kw_ok += 1
        except Exception as e:
            print(f"    ❌ kw '{text}': {_err(e)[:100]}")
    print(f"  ✅ duplicated {kw_ok}/{len(src_kws)} keywords")

    # 5. Create testimonial RSA in the new ad group
    ad_svc = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.ad_group = new_ag_rn
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(LP_URL)
    for h in RSA_HEADLINES:
        ah = client.get_type("AdTextAsset"); ah.text = h
        aga.ad.responsive_search_ad.headlines.append(ah)
    for d in RSA_DESCRIPTIONS:
        ad = client.get_type("AdTextAsset"); ad.text = d
        aga.ad.responsive_search_ad.descriptions.append(ad)
    aga.ad.responsive_search_ad.path1 = "zatca"
    aga.ad.responsive_search_ad.path2 = "testimonials"
    try:
        r = ad_svc.mutate_ad_group_ads(customer_id=acct, operations=[op])
        print(f"  ✅ RSA: {r.results[0].resource_name}")
    except Exception as e:
        print(f"  ❌ RSA: {_err(e)[:250]}")

    # 6. Create 5 new sitelinks
    asset_svc = client.get_service("AssetService")
    sitelink_rns = []
    for sl in SITELINKS:
        op = client.get_type("AssetOperation")
        op.create.name = f"Sitelink_zatca_test_{sl['text'][:18]}_{new_ag_id[-6:]}"
        op.create.sitelink_asset.link_text    = sl["text"]
        op.create.sitelink_asset.description1 = sl["d1"]
        op.create.sitelink_asset.description2 = sl["d2"]
        op.create.final_urls.append(sl["url"])
        try:
            r = asset_svc.mutate_assets(customer_id=acct, operations=[op])
            sitelink_rns.append(r.results[0].resource_name)
        except Exception as e:
            print(f"    ❌ sitelink '{sl['text']}': {_err(e)[:120]}")
    print(f"  ✅ created {len(sitelink_rns)} sitelinks")

    # 7. Link sitelinks at AD-GROUP level (overrides only for this ad group)
    aga_svc = client.get_service("AdGroupAssetService")
    link_ops = []
    for rn in sitelink_rns:
        op = client.get_type("AdGroupAssetOperation")
        op.create.ad_group   = new_ag_rn
        op.create.asset      = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        link_ops.append(op)
    if link_ops:
        try:
            r = aga_svc.mutate_ad_group_assets(customer_id=acct, operations=link_ops)
            print(f"  ✅ linked {len(r.results)} sitelinks at AD-GROUP level (other ad groups untouched)")
        except Exception as e:
            print(f"  ❌ link: {_err(e)[:200]}")

print("\nDONE")
