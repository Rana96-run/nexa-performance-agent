"""Finalize the ZATCA × Competitor campaign (23861965426):
  1. Display Network OFF, Saudi geo, Arabic+English language
  2. Reuse existing assets from C1 — link all sitelinks/callouts/snippets/calls
     (by deduped asset resource_name, picking 1 per unique text)
  3. Create + link 2 new competitor-comparison sitelinks
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT     = "1513020554"
NEW_CAMP_ID = "23861965426"   # Google_Search_AR_ZATCACompetitor_Broad
SRC_CAMP_ID = "23851270716"   # ZATCAPhase2 — pull asset RNs from here
SAUDI_GEO   = "geoTargetConstants/2682"
LANG_AR     = "languageConstants/1019"
LANG_EN     = "languageConstants/1000"

client    = get_client()
camp_svc  = client.get_service("CampaignService")
crit_svc  = client.get_service("CampaignCriterionService")
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")
ga        = client.get_service("GoogleAdsService")


# ── 1. Network + geo + language ────────────────────────────────────────────
print("=" * 70)
print("1. Network OFF Display + Saudi geo + Arabic/English language")
print("=" * 70)

op = client.get_type("CampaignOperation")
upd = op.update
upd.resource_name = f"customers/{ACCOUNT}/campaigns/{NEW_CAMP_ID}"
upd.network_settings.target_google_search        = True
upd.network_settings.target_search_network        = True
upd.network_settings.target_content_network        = False
upd.network_settings.target_partner_search_network = False
client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=[
    "network_settings.target_google_search",
    "network_settings.target_search_network",
    "network_settings.target_content_network",
    "network_settings.target_partner_search_network",
]))
r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=[op])
print(f"  ✅ network updated: {r.results[0].resource_name}")

crit_ops = []
# Saudi
o = client.get_type("CampaignCriterionOperation")
o.create.campaign = f"customers/{ACCOUNT}/campaigns/{NEW_CAMP_ID}"
o.create.location.geo_target_constant = SAUDI_GEO
crit_ops.append(o)
# Arabic + English
for lang in [LANG_AR, LANG_EN]:
    o = client.get_type("CampaignCriterionOperation")
    o.create.campaign = f"customers/{ACCOUNT}/campaigns/{NEW_CAMP_ID}"
    o.create.language.language_constant = lang
    crit_ops.append(o)
r = crit_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=crit_ops)
print(f"  ✅ added {len(r.results)} criteria (1 geo + 2 languages)")


# ── 2. Pull existing assets from C1 — pick 1 per unique text ───────────────
print()
print("=" * 70)
print("2. Discover reusable assets from source campaign")
print("=" * 70)

q = f"""
SELECT campaign.id,
       campaign_asset.field_type,
       asset.resource_name,
       asset.sitelink_asset.link_text,
       asset.callout_asset.callout_text,
       asset.structured_snippet_asset.header,
       asset.call_asset.phone_number
FROM campaign_asset
WHERE campaign.id = {SRC_CAMP_ID}
"""
# (field_type, unique_text) -> asset_rn (first wins, dedup)
seen = {}
for r in ga.search(customer_id=ACCOUNT, query=q):
    ft  = r.campaign_asset.field_type.name
    a   = r.asset
    key = (a.sitelink_asset.link_text or a.callout_asset.callout_text
           or a.structured_snippet_asset.header or a.call_asset.phone_number)
    if not key:
        continue
    # Skip the placeholder phone — only keep the real Qoyod number
    if ft == "CALL" and key != "8004330088":
        continue
    seen.setdefault((ft, key), a.resource_name)

by_ft = {}
for (ft, txt), arn in seen.items():
    by_ft.setdefault(ft, []).append((txt, arn))

for ft, items in by_ft.items():
    print(f"  {ft}: {len(items)} unique")
    for txt, _ in items:
        print(f"    - {txt}")


# ── 3. Create 2 NEW competitor-comparison sitelinks ────────────────────────
print()
print("=" * 70)
print("3. Create 2 NEW competitor-comparison sitelinks")
print("=" * 70)

NEW_SITELINKS = [
    {
        "text":         "قارن قيود بالمنافسين",
        "description1": "الفرق بين Qoyod ودفترة ووافق",
        "description2": "محلي - متوافق - أسرع",
        "url":          "https://lp.qoyod.com/einvoice-integration/#comparison",
    },
    {
        "text":         "لماذا الشركات تنتقل إلينا",
        "description1": "قصص نجاح من السوق السعودي",
        "description2": "50,000+ شركة اختارتنا",
        "url":          "https://lp.qoyod.com/einvoice-integration/#testimonials",
    },
]

new_sitelink_rns = []
for sl in NEW_SITELINKS:
    op = client.get_type("AssetOperation")
    co = op.create
    co.name = f"Sitelink_{sl['text'][:20]}_competitor"
    co.sitelink_asset.link_text     = sl["text"]
    co.sitelink_asset.description1  = sl["description1"]
    co.sitelink_asset.description2  = sl["description2"]
    co.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    new_sitelink_rns.append(rn)
    print(f"  ✅ {sl['text']}: {rn}")


# ── 4. Link ALL assets to Campaign 3 ───────────────────────────────────────
print()
print("=" * 70)
print("4. Link reused + new assets to Campaign 3")
print("=" * 70)

def field_type_enum(name: str):
    return getattr(client.enums.AssetFieldTypeEnum, name)

link_ops = []
# Reused (from C1)
for ft, items in by_ft.items():
    for _, arn in items:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{NEW_CAMP_ID}"
        op.create.asset      = arn
        op.create.field_type = field_type_enum(ft)
        link_ops.append(op)

# 2 new comparison sitelinks
for arn in new_sitelink_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{NEW_CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = field_type_enum("SITELINK")
    link_ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=link_ops)
print(f"  ✅ linked {len(r.results)} assets to Campaign 3")


print()
print("=" * 70)
print("DONE")
print("=" * 70)
