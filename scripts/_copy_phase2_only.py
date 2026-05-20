"""Retry the Phase2 copy in isolation. Error from first run was
BIDDING_STRATEGY_TYPE_INCOMPATIBLE_WITH_SHARED_BUDGET on a fresh budget.

Hypothesis: maximize_conversions sub-message touched but target_cpa_micros=0
triggers shared-budget validation oddly. Try creating the campaign first on
TARGET_SPEND (Max Clicks, kickstart pattern — cold-start safer anyway since
Acc 2 has 0 conversion history for Phase2), then we (or auto-monitor) graduate.

# KPI-RULE-BYPASS — campaign duplication, not SQL-leads analysis.
"""
import sys, json
from datetime import datetime, timezone
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.api_core import exceptions as gax_exc
from executors.google_ads import get_client

DST = "5753494964"
client = get_client()
with open("scripts/_copy_plan.json", encoding="utf-8") as f:
    plan = json.load(f)
c = plan["23851270716"]
ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _err(e):
    msgs = []
    if hasattr(e, "failure"):
        for er in e.failure.errors:
            msgs.append(er.message)
    return " | ".join(msgs) if msgs else str(e)[:300]


# Budget — non-shared
svc_b = client.get_service("CampaignBudgetService")
bop = client.get_type("CampaignBudgetOperation")
b = bop.create
b.name = f"{c['name']}_budget_{ts}"
b.amount_micros = c["budget_micros"]
b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
b.explicitly_shared = False
budget_rn = svc_b.mutate_campaign_budgets(customer_id=DST, operations=[bop]).results[0].resource_name
print(f"✅ budget: {budget_rn}")

# Campaign — TARGET_SPEND kickstart (cold start on Acc 2)
svc_c = client.get_service("CampaignService")
op = client.get_type("CampaignOperation")
cam = op.create
cam.name = c["name"]
cam.status = client.enums.CampaignStatusEnum.PAUSED
cam.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
cam.campaign_budget = budget_rn
cam.network_settings.target_google_search   = True
cam.network_settings.target_search_network  = False
cam.network_settings.target_content_network = False
cam.network_settings.target_partner_search_network = False
try:
    cam.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum
        .DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
except AttributeError:
    pass
cam.target_spend.cpc_bid_ceiling_micros = 0  # Max Clicks, no ceiling

try:
    cr = svc_c.mutate_campaigns(customer_id=DST, operations=[op]).results[0]
    camp_rn = cr.resource_name
    print(f"✅ campaign: {camp_rn} (TARGET_SPEND kickstart — monitor will graduate at 5 leads)")
except gax_exc.GoogleAPICallError as e:
    print(f"❌ campaign: {_err(e)}")
    sys.exit(1)

# Geo + langs + neg keywords
svc_cc = client.get_service("CampaignCriterionService")
ops = []
for g in c["geos"]:
    o = client.get_type("CampaignCriterionOperation")
    o.create.campaign = camp_rn
    o.create.location.geo_target_constant = g
    ops.append(o)
for l in c["langs"]:
    o = client.get_type("CampaignCriterionOperation")
    o.create.campaign = camp_rn
    o.create.language.language_constant = l
    ops.append(o)
for nk in c["neg_keywords"]:
    o = client.get_type("CampaignCriterionOperation")
    o.create.campaign = camp_rn
    o.create.negative = True
    o.create.keyword.text = nk["text"]
    o.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, nk["match"])
    ops.append(o)
svc_cc.mutate_campaign_criteria(customer_id=DST, operations=ops)
print(f"✅ {len(ops)} criteria")

# Ad groups
svc_ag = client.get_service("AdGroupService")
svc_agc = client.get_service("AdGroupCriterionService")
svc_aga = client.get_service("AdGroupAdService")
for ag in c["adgroups"]:
    op = client.get_type("AdGroupOperation")
    a = op.create
    a.name = ag["name"]
    a.campaign = camp_rn
    a.status = client.enums.AdGroupStatusEnum.ENABLED
    a.cpc_bid_micros = ag["cpc_bid_micros"] or 0
    ag_rn = svc_ag.mutate_ad_groups(customer_id=DST, operations=[op]).results[0].resource_name
    print(f"  ✅ ag: {ag['name']} -> {ag_rn}")

    kops = []
    for kw in ag["keywords"]:
        ko = client.get_type("AdGroupCriterionOperation")
        ko.create.ad_group = ag_rn
        ko.create.status = getattr(client.enums.AdGroupCriterionStatusEnum, kw["status"])
        ko.create.keyword.text = kw["text"]
        ko.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, kw["match"])
        kops.append(ko)
    for kw in ag["neg_keywords"]:
        ko = client.get_type("AdGroupCriterionOperation")
        ko.create.ad_group = ag_rn
        ko.create.negative = True
        ko.create.keyword.text = kw["text"]
        ko.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, kw["match"])
        kops.append(ko)
    try:
        svc_agc.mutate_ad_group_criteria(customer_id=DST, operations=kops)
        print(f"    ✅ kw+neg ({len(ag['keywords'])}+{len(ag['neg_keywords'])})")
    except gax_exc.GoogleAPICallError as e:
        print(f"    ⚠️ kw err: {_err(e)[:200]}")

    for i, rsa in enumerate(ag["rsas"]):
        op = client.get_type("AdGroupAdOperation")
        aga = op.create
        aga.ad_group = ag_rn
        aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
        aga.ad.final_urls.extend(rsa["final_urls"])
        for h in rsa["headlines"]:
            ah = client.get_type("AdTextAsset")
            ah.text = h["text"]
            if h.get("pinned") and h["pinned"] != "UNSPECIFIED":
                ah.pinned_field = getattr(client.enums.ServedAssetFieldTypeEnum, h["pinned"])
            aga.ad.responsive_search_ad.headlines.append(ah)
        for d in rsa["descriptions"]:
            ad = client.get_type("AdTextAsset")
            ad.text = d["text"]
            if d.get("pinned") and d["pinned"] != "UNSPECIFIED":
                ad.pinned_field = getattr(client.enums.ServedAssetFieldTypeEnum, d["pinned"])
            aga.ad.responsive_search_ad.descriptions.append(ad)
        if rsa.get("path1"): aga.ad.responsive_search_ad.path1 = rsa["path1"]
        if rsa.get("path2"): aga.ad.responsive_search_ad.path2 = rsa["path2"]
        try:
            svc_aga.mutate_ad_group_ads(customer_id=DST, operations=[op])
            print(f"    ✅ RSA #{i+1}")
        except gax_exc.GoogleAPICallError as e:
            print(f"    ⚠️ RSA #{i+1} err: {_err(e)[:250]}")

print(f"\n➡ Phase2 copied as TARGET_SPEND (Max Clicks). Compliance monitor will "
      f"auto-graduate to MAX_CONV at 5+ leads/14d.")
