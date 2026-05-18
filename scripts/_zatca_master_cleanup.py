"""ZATCA campaigns master cleanup — sequential atomic steps so one failure
doesn't block the others.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
HUBSPOT_LEAD_RN     = f"customers/{ACCOUNT}/conversionActions/7040304673"
OLD_HUBSPOT_LEAD_RN = f"customers/{ACCOUNT}/conversionActions/7037461117"

CAMPAIGNS = [
    {"id": "23851270716", "new_campaign_name": "Google_Search_AREN_ZATCAPhase2_Broad",
     "new_adgroup_name": "Google_Search_AREN_ZATCAPhase2_AdGroup",
     "ad_name": "Google_Search_AREN_ZATCAPhase2V1",
     "new_budget_usd": 100.0, "drop_tcpa": False, "fix_share": False},
    {"id": "23861101390", "new_campaign_name": "Google_Search_AREN_ZATCAVendorShop_Broad",
     "new_adgroup_name": "Google_Search_AREN_ZATCAVendorShop_AdGroup",
     "ad_name": "Google_Search_AREN_ZATCAVendorShopV1",
     "new_budget_usd": 80.0,  "drop_tcpa": True,  "fix_share": True},
    {"id": "23861965426", "new_campaign_name": "Google_Search_AREN_ZATCACompetitor_Broad",
     "new_adgroup_name": "Google_Search_AREN_ZATCACompetitor_AdGroup",
     "ad_name": "Google_Search_AREN_ZATCACompetitorV1",
     "new_budget_usd": 60.0,  "drop_tcpa": True,  "fix_share": True},
]

client     = get_client()
camp_svc   = client.get_service("CampaignService")
ag_svc     = client.get_service("AdGroupService")
agad_svc   = client.get_service("AdGroupAdService")
budget_svc = client.get_service("CampaignBudgetService")
conv_svc   = client.get_service("ConversionActionService")
ga         = client.get_service("GoogleAdsService")


def mask(*paths):
    return field_mask_pb2.FieldMask(paths=list(paths))


def hydrate():
    ids = ",".join(c["id"] for c in CAMPAIGNS)
    ag = {}
    for r in ga.search(customer_id=ACCOUNT, query=f"SELECT campaign.id, ad_group.id FROM ad_group WHERE campaign.id IN ({ids})"):
        ag.setdefault(str(r.campaign.id), str(r.ad_group.id))
    bg = {}
    for r in ga.search(customer_id=ACCOUNT, query=f"SELECT campaign.id, campaign_budget.resource_name FROM campaign WHERE campaign.id IN ({ids})"):
        bg[str(r.campaign.id)] = r.campaign_budget.resource_name
    for c in CAMPAIGNS:
        c["adgroup_id"] = ag[c["id"]]
        c["budget_rn"]  = bg[c["id"]]
hydrate()
for c in CAMPAIGNS:
    print(f"hydrated: cid={c['id']} ag={c['adgroup_id']} budget={c['budget_rn']}")


def step(label, fn):
    print(f"\n=== {label} ===")
    try:
        fn()
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {str(e)[:300]}")


# ── 1. Unshare C2/C3 budgets ────────────────────────────────────────────────
def s1():
    ops = []
    for c in CAMPAIGNS:
        if not c["fix_share"]: continue
        op = client.get_type("CampaignBudgetOperation")
        op.update.resource_name     = c["budget_rn"]
        op.update.explicitly_shared = False
        client.copy_from(op.update_mask, mask("explicitly_shared"))
        ops.append(op)
    if ops:
        r = budget_svc.mutate_campaign_budgets(customer_id=ACCOUNT, operations=ops)
        for res in r.results: print(f"  ✅ {res.resource_name}")
step("1. Unshare C2/C3 budgets", s1)

# ── 2. Bump budget amounts ─────────────────────────────────────────────────
def s2():
    ops = []
    for c in CAMPAIGNS:
        op = client.get_type("CampaignBudgetOperation")
        op.update.resource_name = c["budget_rn"]
        op.update.amount_micros = int(c["new_budget_usd"] * 1_000_000)
        client.copy_from(op.update_mask, mask("amount_micros"))
        ops.append(op)
    r = budget_svc.mutate_campaign_budgets(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("2. Bump budgets ($100 / $80 / $60)", s2)

# ── 3. Strip tCPA on C2/C3 (own update) ─────────────────────────────────────
def s3():
    ops = []
    for c in CAMPAIGNS:
        if not c["drop_tcpa"]: continue
        op = client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{c['id']}"
        op.update.maximize_conversions.target_cpa_micros = 0
        client.copy_from(op.update_mask, mask("maximize_conversions.target_cpa_micros"))
        ops.append(op)
    if ops:
        r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
        for res in r.results: print(f"  ✅ {res.resource_name}")
step("3. Strip tCPA on C2/C3", s3)

# ── 4. Rename campaigns (own update) ───────────────────────────────────────
def s4():
    ops = []
    for c in CAMPAIGNS:
        op = client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{c['id']}"
        op.update.name          = c["new_campaign_name"]
        client.copy_from(op.update_mask, mask("name"))
        ops.append(op)
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("4. Rename campaigns _AR_ → _AREN_", s4)

# ── 5. Refresh custom params (own update) ──────────────────────────────────
def s5():
    ops = []
    for c in CAMPAIGNS:
        op = client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{c['id']}"
        for k, v in [
            ("campaign",    c["new_campaign_name"]),
            ("adname",      c["ad_name"]),
            ("adgroupname", c["new_adgroup_name"]),
            ("adgroupid",   c["adgroup_id"]),
        ]:
            p = client.get_type("CustomParameter")
            p.key = k; p.value = v
            op.update.url_custom_parameters.append(p)
        client.copy_from(op.update_mask, mask("url_custom_parameters"))
        ops.append(op)
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("5. Refresh url_custom_parameters", s5)

# ── 6. Set selective_optimization = HubSpot - Lead (own update) ────────────
def s6():
    ops = []
    for c in CAMPAIGNS:
        op = client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{c['id']}"
        op.update.selective_optimization.conversion_actions.append(HUBSPOT_LEAD_RN)
        client.copy_from(op.update_mask, mask("selective_optimization.conversion_actions"))
        ops.append(op)
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("6. Lock selective_optimization → HubSpot - Lead", s6)

# ── 7. Rename ad groups ────────────────────────────────────────────────────
def s7():
    ops = []
    for c in CAMPAIGNS:
        op = client.get_type("AdGroupOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/adGroups/{c['adgroup_id']}"
        op.update.name          = c["new_adgroup_name"]
        client.copy_from(op.update_mask, mask("name"))
        ops.append(op)
    r = ag_svc.mutate_ad_groups(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("7. Rename ad groups", s7)

# ── 8. C1 RSA cleanup ──────────────────────────────────────────────────────
def s8():
    C1_AG = next(c["adgroup_id"] for c in CAMPAIGNS if c["id"] == "23851270716")
    old_rn = f"customers/{ACCOUNT}/adGroupAds/{C1_AG}~809146999138"
    new_rn = f"customers/{ACCOUNT}/adGroupAds/{C1_AG}~809226391157"
    op_rm = client.get_type("AdGroupAdOperation")
    op_rm.remove = old_rn
    op_en = client.get_type("AdGroupAdOperation")
    op_en.update.resource_name = new_rn
    op_en.update.status        = client.enums.AdGroupAdStatusEnum.ENABLED
    client.copy_from(op_en.update_mask, mask("status"))
    r = agad_svc.mutate_ad_group_ads(customer_id=ACCOUNT, operations=[op_rm, op_en])
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("8. C1 RSA cleanup — remove old, enable new", s8)

# ── 9. Archive OLD HubSpot - Lead ──────────────────────────────────────────
def s9():
    op = client.get_type("ConversionActionOperation")
    op.update.resource_name = OLD_HUBSPOT_LEAD_RN
    op.update.status        = client.enums.ConversionActionStatusEnum.REMOVED
    client.copy_from(op.update_mask, mask("status"))
    r = conv_svc.mutate_conversion_actions(customer_id=ACCOUNT, operations=[op])
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("9. Archive OLD HubSpot - Lead", s9)

print("\nDONE — run scripts/_audit_zatca_full.py to verify")
