"""Replay scripts/_phase2_ext_plan.json onto ZATCAPhase2 on Acc 2.
Mirrors 5 sitelinks + 10 callouts + 4 structured snippets from Acc 1.

# KPI-RULE-BYPASS — asset creation, not SQL-leads analysis.
"""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"
CAMP_ID = "23865711095"   # Google_Search_AREN_ZATCAPhase2 on Acc 2

with open("scripts/_phase2_ext_plan.json", encoding="utf-8") as f:
    plan = json.load(f)

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

print(f"1. Creating {len(plan['sitelinks'])} sitelinks on Acc {ACCOUNT}")
sitelink_rns = []
for sl in plan["sitelinks"]:
    op = client.get_type("AssetOperation")
    op.create.name = f"Sitelink_phase2_acc2_{sl['text'][:18]}"
    op.create.sitelink_asset.link_text    = sl["text"]
    op.create.sitelink_asset.description1 = sl["d1"]
    op.create.sitelink_asset.description2 = sl["d2"]
    op.create.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    sitelink_rns.append(r.results[0].resource_name)
    print(f"   ✅ {sl['text']:<28} → {sl['url']}")

print(f"\n2. Creating {len(plan['callouts'])} callouts")
callout_rns = []
for text in plan["callouts"]:
    op = client.get_type("AssetOperation")
    op.create.name = f"Callout_phase2_acc2_{text[:20]}"
    op.create.callout_asset.callout_text = text
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    callout_rns.append(r.results[0].resource_name)
    print(f"   ✅ {text}")

print(f"\n3. Creating {len(plan['snippets'])} structured snippets")
snippet_rns = []
for sn in plan["snippets"]:
    op = client.get_type("AssetOperation")
    # Disambiguate AR vs EN variants by value-script in the asset name
    is_ar = any('؀' <= c <= 'ۿ' for c in "".join(sn["values"]))
    suffix = "AR" if is_ar else "EN"
    op.create.name = f"Snippet_phase2_acc2_{sn['header']}_{suffix}"
    op.create.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        op.create.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    snippet_rns.append(r.results[0].resource_name)
    print(f"   ✅ {sn['header']} ({suffix}): {', '.join(sn['values'])}")

print(f"\n4. Linking to campaign {CAMP_ID}")
camp_rn = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
ops = []
for arn in sitelink_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = camp_rn
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
for arn in callout_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = camp_rn
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
    ops.append(op)
for arn in snippet_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = camp_rn
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
    ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"   ✅ linked {len(r.results)} CampaignAsset records")

print(f"\nDONE — Acc 2 ZATCAPhase2 now mirrors Acc 1 extension bundle.")
