"""Replay scripts/_copy_plan.json onto Acc 2 (5753494964).

Creates 2 campaigns PAUSED on Acc 2 mirroring source from Acc 1:
  - Google_Search_AREN_FinancialStatement (TARGET_SPEND, $80/day)
  - Google_Search_AREN_ZATCAPhase2        (MAXIMIZE_CONVERSIONS, $60/day)

Each campaign: same budget, bidding, network (search only), geo SA,
languages AR+EN, campaign-level negatives, then per-ad-group:
keywords (with original status), ad-group negatives, RSAs (headlines +
descriptions + path1/path2 + final urls).

Tracking URL template inherits from Acc 2 customer-level (we don't override
at campaign level — per CRITICAL_KPI_RULES rule 4).

# KPI-RULE-BYPASS — campaign duplication, not SQL-leads analysis.
"""
import sys, json
from datetime import datetime, timezone
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.api_core import exceptions as gax_exc
from executors.google_ads import get_client

DST = "5753494964"   # destination customer
client = get_client()

with open("scripts/_copy_plan.json", encoding="utf-8") as f:
    plan = json.load(f)

ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _err(e):
    msgs = []
    if hasattr(e, "failure"):
        for er in e.failure.errors:
            msgs.append(er.message)
    return " | ".join(msgs) if msgs else str(e)[:300]


def create_budget(name, micros):
    svc = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    b = op.create
    b.name = f"{name}_budget_{ts}"
    b.amount_micros = micros
    b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    return svc.mutate_campaign_budgets(customer_id=DST, operations=[op]).results[0].resource_name


def create_campaign(c):
    budget_rn = create_budget(c["name"], c["budget_micros"])
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    cam = op.create
    cam.name = c["name"]
    cam.status = client.enums.CampaignStatusEnum.PAUSED
    cam.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    cam.campaign_budget = budget_rn
    # Network: search-only, no partners/content
    cam.network_settings.target_google_search   = c["network"]["google_search"]
    cam.network_settings.target_search_network  = c["network"]["search_partners"]
    cam.network_settings.target_content_network = c["network"]["content"]
    cam.network_settings.target_partner_search_network = c["network"]["partner_search"]
    try:
        cam.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum
            .DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
    except AttributeError:
        pass
    # Bidding
    bs = c["bidding_strategy_type"]
    if bs == "MAXIMIZE_CONVERSIONS":
        cam.maximize_conversions.target_cpa_micros = c.get("max_conv_tcpa_micros") or 0
    elif bs == "TARGET_SPEND":
        # Max Clicks; cpc ceiling optional
        ceiling = c.get("target_spend_ceiling_micros") or 0
        if ceiling:
            cam.target_spend.cpc_bid_ceiling_micros = ceiling
        else:
            # touch sub-message
            cam.target_spend.cpc_bid_ceiling_micros = 0
    else:
        raise ValueError(f"unsupported bidding {bs}")
    r = svc.mutate_campaigns(customer_id=DST, operations=[op]).results[0]
    print(f"  ✅ campaign created: {r.resource_name} ({bs})")
    return r.resource_name


def add_geo_lang(camp_rn, c):
    svc = client.get_service("CampaignCriterionService")
    ops = []
    for geo in c["geos"]:
        op = client.get_type("CampaignCriterionOperation")
        cr = op.create
        cr.campaign = camp_rn
        cr.location.geo_target_constant = geo
        ops.append(op)
    for lang in c["langs"]:
        op = client.get_type("CampaignCriterionOperation")
        cr = op.create
        cr.campaign = camp_rn
        cr.language.language_constant = lang
        ops.append(op)
    # campaign-level negative keywords
    for nk in c["neg_keywords"]:
        op = client.get_type("CampaignCriterionOperation")
        cr = op.create
        cr.campaign = camp_rn
        cr.negative = True
        cr.keyword.text = nk["text"]
        cr.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, nk["match"])
        ops.append(op)
    if ops:
        svc.mutate_campaign_criteria(customer_id=DST, operations=ops)
        print(f"  ✅ geos+langs+neg ({len(ops)} criteria)")


def create_adgroup(camp_rn, ag):
    svc = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    a = op.create
    a.name = ag["name"]
    a.campaign = camp_rn
    a.status = client.enums.AdGroupStatusEnum.ENABLED
    a.cpc_bid_micros = ag["cpc_bid_micros"] or 0
    return svc.mutate_ad_groups(customer_id=DST, operations=[op]).results[0].resource_name


def add_kw(ag_rn, ag):
    svc = client.get_service("AdGroupCriterionService")
    ops = []
    for kw in ag["keywords"]:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ag_rn
        c.status = getattr(client.enums.AdGroupCriterionStatusEnum, kw["status"])
        c.keyword.text = kw["text"]
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, kw["match"])
        ops.append(op)
    for kw in ag["neg_keywords"]:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ag_rn
        c.negative = True
        c.keyword.text = kw["text"]
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, kw["match"])
        ops.append(op)
    if ops:
        try:
            svc.mutate_ad_group_criteria(customer_id=DST, operations=ops)
            print(f"  ✅ kw+neg ({len(ag['keywords'])}+{len(ag['neg_keywords'])})")
        except gax_exc.GoogleAPICallError as e:
            print(f"  ⚠️  kw err: {_err(e)[:200]}")


def add_rsas(ag_rn, ag):
    svc = client.get_service("AdGroupAdService")
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
            svc.mutate_ad_group_ads(customer_id=DST, operations=[op])
            print(f"  ✅ RSA #{i+1}")
        except gax_exc.GoogleAPICallError as e:
            print(f"  ⚠️  RSA #{i+1} err: {_err(e)[:250]}")


for src_id, c in plan.items():
    print(f"\n=== Copying {c['name']} → Acc {DST} ===")
    try:
        camp_rn = create_campaign(c)
    except gax_exc.GoogleAPICallError as e:
        print(f"  ❌ campaign create failed: {_err(e)}")
        continue
    add_geo_lang(camp_rn, c)
    for ag in c["adgroups"]:
        ag_rn = create_adgroup(camp_rn, ag)
        print(f"  ✅ adgroup: {ag['name']} -> {ag_rn}")
        add_kw(ag_rn, ag)
        add_rsas(ag_rn, ag)
    print(f"  ➡ created PAUSED. Review & enable in UI.")
