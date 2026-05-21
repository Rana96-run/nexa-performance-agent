"""Move all campaign-level sitelinks to ad-group level on the 3
FinancialStatement campaigns (Acc 1 main + IS variant + Acc 2 copy).

Simpler than the ZATCA migration — these campaigns currently have a
single sitelink set at campaign level pointing to /qawaem/ anchors,
inherited by every ad group. Migration: copy that set to every ad
group at ad-group level, then unlink at campaign level.

After: editing any one ad group's sitelinks affects only that ad group.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "23861837000", "Acc 1 FinStatement (Max Clicks)"),
    ("1513020554", "23865358505", "Acc 1 FinStatement (Impression Share)"),
    ("5753494964", "23870151040", "Acc 2 FinStatement"),
]

client  = get_client()
ga      = client.get_service("GoogleAdsService")
ca_svc  = client.get_service("CampaignAssetService")
aga_svc = client.get_service("AdGroupAssetService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, cid, label in TARGETS:
    print(f"\n{'=' * 76}")
    print(f"{label}")
    print('=' * 76)

    # 1. Current campaign-level sitelinks
    camp_sitelinks = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.id, campaign_asset.resource_name,
               campaign_asset.asset, asset.sitelink_asset.link_text,
               asset.final_urls
        FROM campaign_asset
        WHERE campaign.id = {cid}
          AND campaign_asset.field_type = 'SITELINK'
          AND campaign_asset.status = 'ENABLED'
    """):
        url = list(r.asset.final_urls)[0] if r.asset.final_urls else ""
        camp_sitelinks.append({
            "ca_rn":    r.campaign_asset.resource_name,
            "asset_rn": r.campaign_asset.asset,
            "text":     r.asset.sitelink_asset.link_text,
            "url":      url,
        })
    print(f"  campaign-level sitelinks: {len(camp_sitelinks)}")
    for s in camp_sitelinks:
        print(f"    {s['text']:<24} → {s['url']}")

    if not camp_sitelinks:
        print(f"  (nothing at campaign level — skipping)")
        continue

    # 2. All ENABLED ad groups
    ad_groups = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.id, ad_group.name FROM ad_group
        WHERE campaign.id = {cid} AND ad_group.status = 'ENABLED'
    """):
        ad_groups.append({"id": str(r.ad_group.id), "name": r.ad_group.name})
    print(f"  ENABLED ad groups: {len(ad_groups)}")

    # 3. Existing ad-group-level sitelinks per AG (dedupe)
    ag_existing = {a["id"]: set() for a in ad_groups}
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.id, ad_group.id, ad_group_asset.asset
        FROM ad_group_asset
        WHERE campaign.id = {cid}
          AND ad_group_asset.field_type = 'SITELINK'
          AND ad_group_asset.status = 'ENABLED'
    """):
        ag_existing.setdefault(str(r.ad_group.id), set()).add(r.ad_group_asset.asset)

    # 4. Link every campaign-level sitelink at every ad-group level
    ag_links_added = 0
    for ag in ad_groups:
        for s in camp_sitelinks:
            if s["asset_rn"] in ag_existing.get(ag["id"], set()):
                continue
            op = client.get_type("AdGroupAssetOperation")
            op.create.ad_group   = f"customers/{acct}/adGroups/{ag['id']}"
            op.create.asset      = s["asset_rn"]
            op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
            try:
                aga_svc.mutate_ad_group_assets(customer_id=acct, operations=[op])
                ag_links_added += 1
            except Exception as e:
                msg = _err(e)
                if "duplicate" not in msg.lower():
                    print(f"    ❌ {ag['name']}/{s['text']}: {msg[:120]}")
    print(f"  ✅ ad-group-level links added: {ag_links_added}")

    # 5. Unlink at campaign level
    rm_ok = 0
    for s in camp_sitelinks:
        op = client.get_type("CampaignAssetOperation")
        op.remove = s["ca_rn"]
        try:
            ca_svc.mutate_campaign_assets(customer_id=acct, operations=[op])
            rm_ok += 1
        except Exception as e:
            print(f"    ❌ unlink {s['text']}: {_err(e)[:120]}")
    print(f"  ⊘ campaign-level sitelinks unlinked: {rm_ok}/{len(camp_sitelinks)}")

print("\nDONE — all 3 FinancialStatement campaigns now have per-ad-group "
      "sitelink isolation. Edit one ad group → only that ad group changes.")
