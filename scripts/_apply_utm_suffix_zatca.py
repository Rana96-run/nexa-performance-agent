"""Apply canonical final_url_suffix + custom parameters to the 3 ZATCA
campaigns, then strip the hardcoded UTM from each campaign's RSA final_url
(so we don't end up with double UTMs on click).

Canonical template lives in executors.google_ads.STANDARD_UTM_SUFFIX and
memory/utm_template.md.
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client, STANDARD_UTM_SUFFIX

ACCOUNT = "1513020554"

# Each campaign + its ad-group name + RSA final_url to clean
CAMPAIGNS = [
    {
        "id":      "23851270716",
        "name":    "Google_Search_AR_ZATCAPhase2_Broad",
        "adgroup_id":   "193836712858",   # discovered below if not set
        "adgroup_name": "Google_Search_AR_ZATCAPhase2_AdGroup",
        "ad_name":      "Google_Search_AR_ZATCAPhase2V1",
        "bare_lp":      "https://lp.qoyod.com/einvoice-integration/",
    },
    {
        "id":      "23861101390",
        "name":    "Google_Search_AR_ZATCAVendorShop_Broad",
        "adgroup_id":   "193836712946",
        "adgroup_name": "Google_Search_AR_ZATCAVendorShop_AdGroup",
        "ad_name":      "Google_Search_AR_ZATCAVendorShopV1",
        "bare_lp":      "https://lp.qoyod.com/einvoice-integration/",
    },
    {
        "id":      "23861965426",
        "name":    "Google_Search_AR_ZATCACompetitor_Broad",
        "adgroup_id":   "193841456302",
        "adgroup_name": "Google_Search_AR_ZATCACompetitor_AdGroup",
        "ad_name":      "Google_Search_AR_ZATCACompetitorV1",
        "bare_lp":      "https://lp.qoyod.com/einvoice-integration/",
    },
]

client = get_client()
camp_svc = client.get_service("CampaignService")
ad_svc   = client.get_service("AdService")
ga       = client.get_service("GoogleAdsService")


def discover_adgroup_ids():
    """Refresh ad-group IDs from API (in case any drifted)."""
    q = f"""
    SELECT campaign.id, ad_group.id, ad_group.name
    FROM ad_group
    WHERE campaign.id IN ({",".join(c["id"] for c in CAMPAIGNS)})
    """
    by_camp = {}
    for r in ga.search(customer_id=ACCOUNT, query=q):
        by_camp[str(r.campaign.id)] = (str(r.ad_group.id), r.ad_group.name)
    for c in CAMPAIGNS:
        if c["id"] in by_camp:
            c["adgroup_id"], c["adgroup_name"] = by_camp[c["id"]]


def discover_ad_resources():
    """Get the RSA resource_name for each campaign."""
    q = f"""
    SELECT campaign.id, ad_group_ad.resource_name, ad_group_ad.ad.final_urls
    FROM ad_group_ad
    WHERE campaign.id IN ({",".join(c["id"] for c in CAMPAIGNS)})
    """
    by_camp = {}
    for r in ga.search(customer_id=ACCOUNT, query=q):
        by_camp[str(r.campaign.id)] = {
            "resource_name": r.ad_group_ad.resource_name,
            "final_urls":    list(r.ad_group_ad.ad.final_urls),
        }
    return by_camp


print("=" * 78)
print("1. Discover live ad-group + RSA resources")
print("=" * 78)
discover_adgroup_ids()
ads_by_camp = discover_ad_resources()
for c in CAMPAIGNS:
    print(f"  {c['name']}")
    print(f"    adgroup_id : {c['adgroup_id']}")
    print(f"    RSA        : {ads_by_camp.get(c['id'], {}).get('resource_name')}")


# ── 2. Apply final_url_suffix + custom parameters per campaign ─────────────
print()
print("=" * 78)
print("2. Apply final_url_suffix + url_custom_parameters")
print("=" * 78)
print(f"Template:\n  {STANDARD_UTM_SUFFIX}\n")

camp_ops = []
for c in CAMPAIGNS:
    op = client.get_type("CampaignOperation")
    u = op.update
    u.resource_name     = f"customers/{ACCOUNT}/campaigns/{c['id']}"
    u.final_url_suffix  = STANDARD_UTM_SUFFIX
    # Set custom params so {_campaign}, {_adname}, {_adgroupname}, {_adgroupid}
    # resolve to actual values at click time.
    # Custom param keys are alphanumeric only (no underscores).
    # Reference syntax in URL: {_key}  →  Google looks up key (without _).
    custom_params = [
        ("campaign",     c["name"]),
        ("adname",       c["ad_name"]),
        ("adgroupname",  c["adgroup_name"]),
        ("adgroupid",    c["adgroup_id"]),
    ]
    for k, v in custom_params:
        p = client.get_type("CustomParameter")
        p.key   = k
        p.value = v
        u.url_custom_parameters.append(p)
    mask = field_mask_pb2.FieldMask(paths=[
        "final_url_suffix",
        "url_custom_parameters",
    ])
    client.copy_from(op.update_mask, mask)
    camp_ops.append(op)

r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=camp_ops)
for res in r.results:
    print(f"  ✅ {res.resource_name}")


# ── 3. Strip hardcoded UTMs from each RSA final_url ────────────────────────
print()
print("=" * 78)
print("3. Replace RSA final_url with bare LP (suffix handles UTMs now)")
print("=" * 78)

ad_ops = []
for c in CAMPAIGNS:
    rsa = ads_by_camp.get(c["id"])
    if not rsa:
        print(f"  ⚠ no RSA found for {c['name']}")
        continue
    op = client.get_type("AdOperation")
    u = op.update
    u.resource_name = rsa["resource_name"].replace("/adGroupAds/", "/ads/").split("~")[1]
    # AdService.mutate_ads works on Ad resource — get the ad ID from resource_name
    # adGroupAd resource: customers/CID/adGroupAds/AGID~ADID
    ad_id = rsa["resource_name"].split("~")[1]
    u.resource_name = f"customers/{ACCOUNT}/ads/{ad_id}"
    u.final_urls.append(c["bare_lp"])
    mask = field_mask_pb2.FieldMask(paths=["final_urls"])
    client.copy_from(op.update_mask, mask)
    ad_ops.append(op)

if ad_ops:
    try:
        r = ad_svc.mutate_ads(customer_id=ACCOUNT, operations=ad_ops)
        for res in r.results:
            print(f"  ✅ {res.resource_name}")
    except Exception as e:
        print(f"  ❌ {e}")


print()
print("=" * 78)
print("DONE — verify with _check_zatca_url_options.py")
print("=" * 78)
