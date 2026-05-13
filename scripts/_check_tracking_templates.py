"""
Check current Google Ads + Microsoft Ads tracking templates to see
if campaign/adgroup/ad IDs are already being passed as URL params.
"""
import sys, os
sys.path.insert(0, ".")

# ── Google Ads ────────────────────────────────────────────────────────────────
print("=== Google Ads tracking templates ===")
try:
    from collectors.google_ads_bq import _client, _customer_ids
    client = _client()
    ga = client.get_service("GoogleAdsService")
    for cid in _customer_ids():
        query = """
            SELECT
              campaign.id,
              campaign.name,
              campaign.tracking_url_template,
              campaign.url_custom_parameters
            FROM campaign
            WHERE campaign.status != 'REMOVED'
              AND campaign.tracking_url_template IS NOT NULL
            LIMIT 3
        """
        try:
            stream = ga.search_stream(customer_id=cid, query=query)
            for batch in stream:
                for row in batch.results:
                    c = row.campaign
                    print(f"  [{cid}] {c.name[:50]}")
                    print(f"    template: {c.tracking_url_template}")
                    for p in c.url_custom_parameters:
                        print(f"    param: {p.key}={p.value}")
        except Exception as e:
            print(f"  [{cid}] error: {e}")
except Exception as e:
    print(f"  import error: {e}")

# ── Microsoft Ads ─────────────────────────────────────────────────────────────
print("\n=== Microsoft Ads tracking templates ===")
try:
    from collectors.microsoft_ads_bq import _get_service_client, ACCOUNT_ID
    svc = _get_service_client("CampaignManagementService")
    resp = svc.GetCampaignsByAccountId(
        AccountId=int(ACCOUNT_ID),
        CampaignType="Search",
        ReturnAdditionalFields="TrackingUrlTemplate",
    )
    campaigns = resp.Campaign or []
    for c in campaigns[:3]:
        print(f"  {getattr(c, 'Name', '?')[:50]}")
        print(f"    template: {getattr(c, 'TrackingUrlTemplate', None)}")
except Exception as e:
    print(f"  error: {e}")
