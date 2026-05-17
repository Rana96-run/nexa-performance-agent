"""Diagnostic — print campaign_asset resource names exactly as search returns
them, and try a single-resource removal with partial_failure to see the
specific error."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client
client = get_client()
ga = client.get_service("GoogleAdsService")
cas = client.get_service("CampaignAssetService")
ACCOUNT = "1513020554"

q = """
SELECT campaign.id,
       campaign_asset.resource_name,
       campaign_asset.asset,
       campaign_asset.campaign,
       campaign_asset.field_type,
       asset.call_asset.phone_number
FROM campaign_asset
WHERE campaign.id = 23861101390
  AND campaign_asset.field_type = CALL
"""
print("CALL extensions on campaign 23861101390:")
target_rn = None
for r in ga.search(customer_id=ACCOUNT, query=q):
    rn   = r.campaign_asset.resource_name
    a    = r.campaign_asset.asset
    c    = r.campaign_asset.campaign
    ft   = r.campaign_asset.field_type.name
    ph   = r.asset.call_asset.phone_number
    print(f"  rn  : {rn}")
    print(f"  asset: {a}")
    print(f"  camp : {c}")
    print(f"  ft  : {ft}")
    print(f"  phone: {ph!r}")
    print()
    if ph and "112345678" in ph:
        target_rn = rn

if target_rn:
    print(f"Attempting removal of wrong-phone call: {target_rn}")
    # Build full request object with partial_failure on the request
    req = client.get_type("MutateCampaignAssetsRequest")
    req.customer_id = ACCOUNT
    req.partial_failure = True
    op = client.get_type("CampaignAssetOperation")
    op.remove = target_rn
    req.operations.append(op)
    try:
        r = cas.mutate_campaign_assets(request=req)
        print(f"  results.len = {len(r.results)}")
        if r.results:
            print(f"  result[0].resource_name = {r.results[0].resource_name!r}")
        if r.partial_failure_error.message:
            print(f"  partial_failure_error: {r.partial_failure_error.message}")
        else:
            print(f"  no partial_failure_error — SUCCESS")
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {str(e)[:300]}")
