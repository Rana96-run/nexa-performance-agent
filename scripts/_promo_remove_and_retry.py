"""Remove the 1% promotions and find the max accepted percent_off."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:100]}" for er in e.failure.errors[:2])
    return str(e)[:200]


# 1. Remove existing 1% promo campaign-asset links (let assets stay; just unlink)
ga = client.get_service("GoogleAdsService")
ca_svc = client.get_service("CampaignAssetService")
for acct, cid in [("1513020554", "23861837000"), ("5753494964", "23870151040")]:
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.id, campaign_asset.resource_name
        FROM campaign_asset
        WHERE campaign.id = {cid}
          AND campaign_asset.field_type = 'PROMOTION'
    """):
        op = client.get_type("CampaignAssetOperation")
        op.remove = r.campaign_asset.resource_name
        try:
            ca_svc.mutate_campaign_assets(customer_id=acct, operations=[op])
            print(f"  ⊘ unlinked {r.campaign_asset.resource_name}")
        except Exception as e:
            print(f"  ❌ unlink: {_err(e)}")

# 2. Probe max percent_off on Acc 1
asset_svc = client.get_service("AssetService")
for pct in [10, 5, 3, 2]:
    op = client.get_type("AssetOperation")
    a = op.create
    a.name = f"_probe_pct_{pct}"
    a.final_urls.append("https://lp.qoyod.com/qawaem/")
    pa = a.promotion_asset
    pa.promotion_target = "Qoyod Trial"
    pa.percent_off = pct * 1_000_000
    pa.language_code = "en"
    try:
        r = asset_svc.mutate_assets(customer_id="1513020554", operations=[op])
        print(f"  ✅ {pct}% accepted → {r.results[0].resource_name}")
        # Remove probe asset
        op_rm = client.get_type("AssetOperation")
        op_rm.remove = r.results[0].resource_name
        # AssetService doesn't accept remove on operational assets;
        # leave it (orphan, no-op).
        break
    except Exception as e:
        print(f"  ❌ {pct}% rejected: {_err(e)}")
