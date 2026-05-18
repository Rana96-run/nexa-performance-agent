"""Add 2 Arabic-value structured snippets + link to all 3 ZATCA campaigns.

Google Ads picks which snippet to show per auction based on locale + relevance,
so keeping both EN-value and AR-value variants gives broader coverage.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

SNIPPETS = [
    {
        "header": "Types",
        "values": ["XML", "PDF/A-3", "REST API", "QR Code", "ختم مشفر"],
        "label":  "Snippet_Types_AR",
    },
    {
        "header": "Service catalog",
        "values": ["فوترة إلكترونية", "محاسبة", "مخزون", "رواتب", "تقارير"],
        "label":  "Snippet_ServiceCatalog_AR",
    },
]

# Verify value lengths (25 max)
for sn in SNIPPETS:
    for v in sn["values"]:
        assert len(v) <= 25, f"value too long: {v}"

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# Create assets
print("Create snippets:")
new_rns = []
for sn in SNIPPETS:
    op = client.get_type("AssetOperation")
    co = op.create
    co.name = sn["label"]
    co.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        co.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    new_rns.append(rn)
    print(f"  ✅ {sn['header']}: {', '.join(sn['values'])}")
    print(f"     {rn}")

# Link to all 3 campaigns
print("\nLink to 3 campaigns:")
ops = []
for cid in CAMPS:
    for arn in new_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
        ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} associations  (2 snippets × 3 campaigns)")
