"""On Acc 2 Search_E-invoice_AR (16851344135):
  Match each ad group's sitelinks to the URL its ads actually point to.

  AG برنامج محاسبة أون لاين (135985062192) → /accounting/ anchors
  AG قيود محاسبية          (135985062632) → /accounting/ anchors
  AG فوترة إلكترونية        (135985062232) → /einvoice-integration/ anchors
  AG هيئة الزكاة            (198303780841) → /zatca-einvoice/ anchors

Then unlink all 4 sitelinks at campaign level so changing one ad group's
sitelinks won't bleed to others. Reuses existing Asset RNs — no new sitelinks
created (already exist on Acc 2 from earlier ZATCA testimonials work).
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

ACCT = "5753494964"
CID  = "16851344135"

# Map ad_group_id → list of sitelink asset resource names to attach
PLAN = {
    # برنامج محاسبة أون لاين → /accounting/
    "135985062192": [
        "customers/5753494964/assets/362038688132",  # خطط الأسعار → #pricing
        "customers/5753494964/assets/362204404779",  # مميزات قيود → #features
        "customers/5753494964/assets/362038738793",  # كيف تبدأ → #how
        "customers/5753494964/assets/362123921233",  # الأسئلة الشائعة → #faq
    ],
    # قيود محاسبية → /accounting/
    "135985062632": [
        "customers/5753494964/assets/362038688132",
        "customers/5753494964/assets/362204404779",
        "customers/5753494964/assets/362038738793",
        "customers/5753494964/assets/362123921233",
    ],
    # فوترة إلكترونية → /einvoice-integration/
    "135985062232": [
        "customers/5753494964/assets/362044491044",  # أسعار الفاتورة → #pricing
        "customers/5753494964/assets/362209951764",  # مميزات الفاتورة → #features
        "customers/5753494964/assets/362129346316",  # اربط منشأتك → #integration
        "customers/5753494964/assets/362209951938",  # دليل المرحلة الثانية → #faq
        "customers/5753494964/assets/362209954740",  # قصص نجاح → #testimonials
    ],
    # هيئة الزكاة → /zatca-einvoice/
    "198303780841": [
        "customers/5753494964/assets/363006485030",  # أسعار قيود → #pricing
        "customers/5753494964/assets/363006497864",  # مميزات الفاتورة → #features
        "customers/5753494964/assets/363091064131",  # خطوات الربط → #integration
        "customers/5753494964/assets/363169961295",  # الأسئلة الشائعة → #faq
        "customers/5753494964/assets/363169976115",  # قصص نجاح → #testimonials
    ],
}

client  = get_client()
ga      = client.get_service("GoogleAdsService")
aga_svc = client.get_service("AdGroupAssetService")
ca_svc  = client.get_service("CampaignAssetService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


# 1. Attach matched sitelinks at ad-group level
print("=" * 72)
print("1. Attach URL-matched sitelinks at AD-GROUP level")
print("=" * 72)
for ag_id, asset_rns in PLAN.items():
    # Get ad group name + already-linked sitelinks
    ag_name = "?"
    for r in ga.search(customer_id=ACCT, query=f"""
        SELECT ad_group.name FROM ad_group WHERE ad_group.id = {ag_id}
    """):
        ag_name = r.ad_group.name

    already = set()
    for r in ga.search(customer_id=ACCT, query=f"""
        SELECT campaign.id, ad_group.id, ad_group_asset.asset
        FROM ad_group_asset
        WHERE ad_group.id = {ag_id}
          AND ad_group_asset.field_type = 'SITELINK'
          AND ad_group_asset.status = 'ENABLED'
    """):
        already.add(r.ad_group_asset.asset)

    print(f"\n  AG {ag_name} ({ag_id})")
    ok, dup = 0, 0
    for rn in asset_rns:
        if rn in already:
            dup += 1
            continue
        op = client.get_type("AdGroupAssetOperation")
        op.create.ad_group   = f"customers/{ACCT}/adGroups/{ag_id}"
        op.create.asset      = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        try:
            aga_svc.mutate_ad_group_assets(customer_id=ACCT, operations=[op])
            ok += 1
        except Exception as e:
            msg = _err(e)
            if "duplicate" in msg.lower(): dup += 1
            else: print(f"    ❌ {rn[-12:]}: {msg[:120]}")
    print(f"    ✅ {ok} linked  ⊘ {dup} already there")


# 2. Unlink the 4 sitelinks at campaign level
print(f"\n{'=' * 72}")
print(f"2. Unlink ALL sitelinks at campaign level")
print('=' * 72)
ca_rns = []
for r in ga.search(customer_id=ACCT, query=f"""
    SELECT campaign.id, campaign_asset.resource_name,
           asset.sitelink_asset.link_text
    FROM campaign_asset
    WHERE campaign.id = {CID}
      AND campaign_asset.field_type = 'SITELINK'
      AND campaign_asset.status = 'ENABLED'
"""):
    ca_rns.append((r.campaign_asset.resource_name, r.asset.sitelink_asset.link_text))

for rn, text in ca_rns:
    op = client.get_type("CampaignAssetOperation")
    op.remove = rn
    try:
        ca_svc.mutate_campaign_assets(customer_id=ACCT, operations=[op])
        print(f"  ⊘ unlinked: {text}")
    except Exception as e:
        print(f"  ❌ unlink {text}: {_err(e)[:120]}")

# 3. Verify
print(f"\n{'=' * 72}")
print(f"3. VERIFY — final state per ad group")
print('=' * 72)
for ag_id in PLAN:
    ag_name = "?"
    for r in ga.search(customer_id=ACCT, query=f"""
        SELECT ad_group.name FROM ad_group WHERE ad_group.id = {ag_id}
    """):
        ag_name = r.ad_group.name
    print(f"\n  AG {ag_name}")
    for r in ga.search(customer_id=ACCT, query=f"""
        SELECT campaign.id, ad_group.id, ad_group_asset.asset,
               asset.sitelink_asset.link_text, asset.final_urls
        FROM ad_group_asset
        WHERE ad_group.id = {ag_id}
          AND ad_group_asset.field_type = 'SITELINK'
          AND ad_group_asset.status = 'ENABLED'
    """):
        url = list(r.asset.final_urls)[0] if r.asset.final_urls else ""
        print(f"    {r.asset.sitelink_asset.link_text:<28} → {url}")
