"""Migrate sitelinks from CAMPAIGN level to AD-GROUP level so each ad
group has its own dedicated set with no inheritance leakage.

For each of 4 ENABLED ZATCA campaigns:
  1. Inspect current campaign-level sitelinks (their URLs)
  2. Find all ENABLED ad groups
  3. Decide which sitelinks belong to which ad group based on URL:
     - /zatca-einvoice/ sitelinks → only the *_NewLP ad group
     - /einvoice-integration/ (or other original) sitelinks → only the
       ORIGINAL ad groups (everything except *_NewLP)
  4. Link the appropriate set at ad-group level (skip if already there)
  5. Unlink ALL sitelinks at campaign level (remove CampaignAsset records)

After this run, editing ad-group X's sitelinks affects ONLY ad group X.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "23851270716", "Acc 1 ZATCAPhase2"),
    ("1513020554", "23861101390", "Acc 1 ZATCAVendorShop"),
    ("1513020554", "23861965426", "Acc 1 ZATCACompetitor"),
    ("5753494964", "23865711095", "Acc 2 ZATCAPhase2"),
]

client = get_client()
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

    # 1. Current campaign-level sitelinks → group by URL family
    camp_sitelinks = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.id, campaign_asset.resource_name,
               campaign_asset.asset,
               asset.sitelink_asset.link_text,
               asset.final_urls
        FROM campaign_asset
        WHERE campaign.id = {cid}
          AND campaign_asset.field_type = 'SITELINK'
          AND campaign_asset.status = 'ENABLED'
    """):
        url = list(r.asset.final_urls)[0] if r.asset.final_urls else ""
        camp_sitelinks.append({
            "ca_rn":     r.campaign_asset.resource_name,
            "asset_rn":  r.campaign_asset.asset,
            "text":      r.asset.sitelink_asset.link_text,
            "url":       url,
            "family":    "zatca-einvoice" if "zatca-einvoice" in url else "other",
        })
    print(f"  campaign-level sitelinks: {len(camp_sitelinks)}")
    for s in camp_sitelinks:
        print(f"    [{s['family']:<14}] {s['text']:<26} → {s['url']}")

    # 2. Ad groups
    ad_groups = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.id, ad_group.name FROM ad_group
        WHERE campaign.id = {cid} AND ad_group.status = 'ENABLED'
    """):
        ad_groups.append({
            "id":   str(r.ad_group.id),
            "name": r.ad_group.name,
            "is_newlp": "NewLP" in r.ad_group.name,
        })
    print(f"  ad groups: {len(ad_groups)}  ({sum(1 for a in ad_groups if a['is_newlp'])} NewLP)")

    # 3. Current ad-group-level sitelinks per AG (for de-dupe)
    ag_existing = {a["id"]: set() for a in ad_groups}
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.id, ad_group.id, ad_group_asset.asset
        FROM ad_group_asset
        WHERE campaign.id = {cid}
          AND ad_group_asset.field_type = 'SITELINK'
          AND ad_group_asset.status = 'ENABLED'
    """):
        ag_existing.setdefault(str(r.ad_group.id), set()).add(r.ad_group_asset.asset)

    # 4. Link to appropriate ad groups
    #    "zatca-einvoice" sitelinks → only NewLP ad groups
    #    "other" sitelinks → only NON-NewLP ad groups
    ag_links_added = 0
    for ag in ad_groups:
        if ag["is_newlp"]:
            wanted = [s for s in camp_sitelinks if s["family"] == "zatca-einvoice"]
        else:
            wanted = [s for s in camp_sitelinks if s["family"] == "other"]

        for s in wanted:
            if s["asset_rn"] in ag_existing.get(ag["id"], set()):
                continue  # already linked at ad-group level
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
                    print(f"    ❌ ag-link {ag['name']}/{s['text']}: {msg[:120]}")
    print(f"  ✅ ad-group-level links added: {ag_links_added}")

    # 5. Unlink ALL sitelinks at campaign level
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

print("\nDONE — every ad group now has its own dedicated sitelinks. "
      "Edit one ad group → only that ad group changes.")
