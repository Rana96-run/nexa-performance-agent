"""Complete extension setup for the 2 ZATCA Phase 2 campaigns:
  1. Find and remove duplicate campaign_asset links from earlier retries
  2. Remove the wrong-number call extension
  3. Add new assets following Wafeq best practice for Phase 2:
       - 2 more sitelinks (success stories, Phase 2 guides) → 6 total
       - 2 more callouts (money-back, Fatoora platform tie) → 10 total
       - 1 more structured snippet (Service catalog) → 2 snippets
       - 1 new call extension with REAL Qoyod 800 number (8004330088)
  4. Link new assets to both campaigns
  5. Verify final state
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client
from collections import defaultdict

ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]

# Real Qoyod number from qoyod.com footer
QOYOD_PHONE         = "8004330088"
WRONG_PHONE_PLACEHOLDER = "+966112345678"

client          = get_client()
ga              = client.get_service("GoogleAdsService")
asset_svc       = client.get_service("AssetService")
camp_asset_svc  = client.get_service("CampaignAssetService")


# ── 1. Discover current state — find duplicates + wrong-number call ────────
print("=" * 70)
print("1. SCAN current campaign_asset associations")
print("=" * 70)

q = f"""
SELECT campaign.id, campaign_asset.resource_name,
       campaign_asset.field_type, asset.resource_name,
       asset.sitelink_asset.link_text,
       asset.callout_asset.callout_text,
       asset.structured_snippet_asset.header,
       asset.call_asset.phone_number
FROM campaign_asset
WHERE campaign.id IN ({",".join(CAMP_IDS)})
"""
# Group by (campaign, field_type, unique_text) → list of campaign_asset RNs
grouped = defaultdict(list)
wrong_call_links = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    cid = str(r.campaign.id)
    ft  = r.campaign_asset.field_type.name
    a   = r.asset
    text = (
        a.sitelink_asset.link_text or
        a.callout_asset.callout_text or
        a.structured_snippet_asset.header or
        a.call_asset.phone_number or
        a.resource_name
    )
    grouped[(cid, ft, text)].append({
        "ca_rn":     r.campaign_asset.resource_name,
        "asset_rn":  a.resource_name,
    })
    # Flag the wrong phone
    if a.call_asset.phone_number == WRONG_PHONE_PLACEHOLDER:
        wrong_call_links.append(r.campaign_asset.resource_name)

# Print summary + identify duplicates
print(f"\n  Total unique (campaign × field_type × text): {len(grouped)}")
to_remove = []
for key, links in grouped.items():
    if len(links) > 1:
        cid, ft, text = key
        print(f"  ⚠ DUPLICATE: campaign={cid[-4:]} field={ft} text={text[:30]} count={len(links)}")
        # Keep the first, remove the rest
        for extra in links[1:]:
            to_remove.append(extra["ca_rn"])

# Also remove wrong call extension entirely (even if not duplicated)
for rn in wrong_call_links:
    if rn not in to_remove:
        to_remove.append(rn)
print(f"\n  Wrong-number call links to remove: {len(wrong_call_links)}")
print(f"  TOTAL campaign_asset links to remove: {len(to_remove)}")


# ── 2. Remove duplicates + wrong-number call ────────────────────────────────
print()
print("=" * 70)
print("2. REMOVE duplicate associations + wrong-number call")
print("=" * 70)
if to_remove:
    ops = []
    for rn in to_remove:
        op = client.get_type("CampaignAssetOperation")
        op.remove = rn
        ops.append(op)
    r = camp_asset_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ removed {len(r.results)} campaign_asset link(s)")
else:
    print("  (none to remove)")


# ── 3. Create new assets — additions following Phase 2 best practice ───────
print()
print("=" * 70)
print("3. CREATE new assets — comprehensive ZATCA Phase 2 set")
print("=" * 70)


def create_asset(builder, label: str) -> str:
    op = client.get_type("AssetOperation")
    builder(op.create)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    print(f"  ✅ {label}: {rn}")
    return rn

# 2 NEW sitelinks — bringing total to 6
NEW_SITELINKS = [
    {
        "text":         "قصص نجاح العملاء",         # 15 chars
        "description1": "اقرأ تجارب 50,000+ شركة",
        "description2": "في السعودية",
        "url":          "https://lp.qoyod.com/einvoice-integration/#testimonials",
    },
    {
        "text":         "دليل المرحلة الثانية",       # 18 chars
        "description1": "كل ما تحتاجه عن Phase 2",
        "description2": "مع موعد إلزامك",
        "url":          "https://lp.qoyod.com/einvoice-integration/#faq",
    },
]
new_sitelink_rns = []
for sl in NEW_SITELINKS:
    def b(co, sl=sl):
        co.name = f"Sitelink_{sl['text'][:20]}_v2"
        co.sitelink_asset.link_text     = sl["text"]
        co.sitelink_asset.description1  = sl["description1"]
        co.sitelink_asset.description2  = sl["description2"]
        co.final_urls.append(sl["url"])
    new_sitelink_rns.append(create_asset(b, f"sitelink: {sl['text']}"))

# 2 NEW callouts — bringing total to 10
NEW_CALLOUTS = [
    "ضمان الامتثال أو استرداد",     # 21 chars — money-back guarantee
    "تكامل مع منصة فاتورة",         # 18 chars — direct platform tie
]
new_callout_rns = []
for c in NEW_CALLOUTS:
    def b(co, c=c):
        co.name = f"Callout_{c[:20]}_v2"
        co.callout_asset.callout_text = c
    new_callout_rns.append(create_asset(b, f"callout: {c}"))

# 1 NEW structured snippet — Service catalog header
SC_HEADER = "Service catalog"
SC_VALUES = ["e-invoicing", "accounting", "inventory", "payroll", "reports"]
def b_sc(co):
    co.name = "Snippet_ServiceCatalog"
    co.structured_snippet_asset.header = SC_HEADER
    for v in SC_VALUES:
        co.structured_snippet_asset.values.append(v)
new_snippet_rn = create_asset(b_sc, f"snippet: {SC_HEADER}: {', '.join(SC_VALUES)}")

# 1 NEW call extension — REAL Qoyod 800 number
def b_call(co):
    co.name = f"Call_Qoyod_{QOYOD_PHONE}"
    co.call_asset.country_code = "SA"
    co.call_asset.phone_number = QOYOD_PHONE
    co.call_asset.call_conversion_reporting_state = (
        client.enums.CallConversionReportingStateEnum
        .USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION
    )
new_call_rn = create_asset(b_call, f"call: +{QOYOD_PHONE}")


# ── 4. Link new assets to both campaigns ────────────────────────────────────
print()
print("=" * 70)
print("4. LINK new assets to both campaigns")
print("=" * 70)

def link(asset_rns, field_type_name):
    ops = []
    ft = getattr(client.enums.AssetFieldTypeEnum, field_type_name)
    for cid in CAMP_IDS:
        for arn in asset_rns:
            op = client.get_type("CampaignAssetOperation")
            op.create.campaign  = f"customers/{ACCOUNT}/campaigns/{cid}"
            op.create.asset     = arn
            op.create.field_type = ft
            ops.append(op)
    r = camp_asset_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ linked {len(r.results)} {field_type_name} associations")

link(new_sitelink_rns, "SITELINK")
link(new_callout_rns, "CALLOUT")
link([new_snippet_rn], "STRUCTURED_SNIPPET")
link([new_call_rn], "CALL")

print()
print("=" * 70)
print("5. DONE — verify with _verify_extensions.py")
print("=" * 70)
