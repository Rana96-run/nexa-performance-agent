"""Promote the 5 /zatca-einvoice/ sitelinks (currently linked only at the
NewLP ad group level) to CAMPAIGN level too — so all ads in the campaign
see them, not just the NewLP ad group's ad.

Existing campaign-level sitelinks (pointing to /einvoice-integration/) stay
untouched — additive, not replacement. Google picks per impression."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

# (account, campaign_id, ad_group_id_of_NewLP)
TARGETS = [
    ("1513020554", "23851270716", "195984671999", "Acc 1 ZATCAPhase2"),
    ("1513020554", "23861101390", "196833050356", "Acc 1 ZATCAVendorShop"),
    ("1513020554", "23861965426", "199622505071", "Acc 1 ZATCACompetitor"),
    ("5753494964", "23865711095", "199817378314", "Acc 2 ZATCAPhase2"),
]

client = get_client()
ga = client.get_service("GoogleAdsService")
ca_svc = client.get_service("CampaignAssetService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, cid, ag_id, label in TARGETS:
    print(f"\n=== {label} ===")

    # 1. Find the 5 sitelinks linked to this NewLP ad group
    sitelink_rns = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.id,
               ad_group_asset.asset, asset.sitelink_asset.link_text,
               asset.final_urls
        FROM ad_group_asset
        WHERE ad_group.id = {ag_id}
          AND ad_group_asset.field_type = 'SITELINK'
          AND ad_group_asset.status = 'ENABLED'
    """):
        url = list(r.asset.final_urls)[0] if r.asset.final_urls else ""
        if "zatca-einvoice" in url:
            sitelink_rns.append((r.ad_group_asset.asset,
                                 r.asset.sitelink_asset.link_text, url))
    print(f"  found {len(sitelink_rns)} /zatca-einvoice/ sitelinks at ad-group level")
    for rn, text, url in sitelink_rns:
        print(f"    {text:<26} → {url}")

    # 2. Link the same assets at CAMPAIGN level
    link_ops = []
    for rn, text, url in sitelink_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{acct}/campaigns/{cid}"
        op.create.asset      = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        link_ops.append(op)

    ok, dup = 0, 0
    for op in link_ops:
        try:
            ca_svc.mutate_campaign_assets(customer_id=acct, operations=[op])
            ok += 1
        except Exception as e:
            msg = _err(e)
            if "duplicate" in msg.lower() or "DUPLICATE" in msg or "already" in msg.lower():
                dup += 1
            else:
                print(f"    ❌ link: {msg[:140]}")
    print(f"  ✅ linked at campaign level: {ok}  (skipped dupes: {dup})")
