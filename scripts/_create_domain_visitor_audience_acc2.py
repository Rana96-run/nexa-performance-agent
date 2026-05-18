"""Replicate the domain-filtered website-visitor remarketing list on Acc2
and link to all 15 enabled prospecting Search campaigns there as observation."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"

# All 15 enabled prospecting Search campaigns on Acc2 (per the earlier audit)
TARGET_CAMPS = [
    "1624813104",   # Search AR CPA Best Converters
    "13910658414",  # Leads-Search-Arabic-Jul#1-(EXP)
    "13913291987",  # E-Invoice-Search-Arabic(EXP)
    "14051112466",  # E-Invoice-Search-Arabic(EXP2)
    "14051278536",  # Leads-Search-Arabic-Jul#2(EXP2)
    "14054086994",  # Leads-Search-Arabic-Jul#1(EXP2)
    "14353048311",  # Leads-Arabic-Search-Aug-1(Exp)
    "14353071777",  # Leads-Arabic-Search-Aug-2(Exp)
    "14353925266",  # Leads-English-Search-Aug-3(Exp)
    "14354680547",  # Leads-E-invoice-Arabic-Search-Aug-4(Exp)
    "16851344135",  # Search_E-invoice_AR
    # SKIP: PMax_AR_Invoice (22790330091) — PMax uses asset_group_signal, not campaign_criterion
    "23348517003",  # ImpressionShare_Search_AR_Invoice
    "23835392373",  # Search_E-invoice_AR_Test
    # SKIP: PMax_AR_Invoice_Technology (23844719995) — same reason
]

INCLUDE_DOMAINS = ["www.qoyod.com", "lp.qoyod.com", "campaigns.qoyod.com"]
EXCLUDE_DOMAINS = ["app.qoyod.com"]
LIST_NAME = "Qoyod Site Visitors (www + lp + campaigns, excl. app)"


def make_url_operand(client, domain):
    operand = client.get_type("FlexibleRuleOperandInfo")
    operand.rule.rule_item_groups.append(client.get_type("UserListRuleItemGroupInfo"))
    group = operand.rule.rule_item_groups[0]
    item  = client.get_type("UserListRuleItemInfo")
    item.name = "url__"
    item.string_rule_item.operator = client.enums.UserListStringRuleItemOperatorEnum.CONTAINS
    item.string_rule_item.value = domain
    group.rule_items.append(item)
    operand.lookback_window_days = 540
    return operand


client = get_client()
ul_svc = client.get_service("UserListService")
cc_svc = client.get_service("CampaignCriterionService")

# 1. Get the existing list (already created in previous run)
ga = client.get_service("GoogleAdsService")
LIST_RN = None
q = f"SELECT user_list.resource_name FROM user_list WHERE user_list.name = '{LIST_NAME}'"
for r in ga.search(customer_id=ACCOUNT, query=q):
    LIST_RN = r.user_list.resource_name
    break
if not LIST_RN:
    # Create if missing
    op = client.get_type("UserListOperation")
    co = op.create
    co.name = LIST_NAME
    co.description = "Visitors to qoyod.com domains except app subdomain"
    co.membership_life_span = 540
    co.membership_status = client.enums.UserListMembershipStatusEnum.OPEN
    flex = co.rule_based_user_list.flexible_rule_user_list
    flex.inclusive_rule_operator = client.enums.UserListFlexibleRuleOperatorEnum.OR
    for d in INCLUDE_DOMAINS:
        flex.inclusive_operands.append(make_url_operand(client, d))
    for d in EXCLUDE_DOMAINS:
        flex.exclusive_operands.append(make_url_operand(client, d))
    r = ul_svc.mutate_user_lists(customer_id=ACCOUNT, operations=[op])
    LIST_RN = r.results[0].resource_name
print(f"  using list: {LIST_RN}")

# 2. Link to all 15 enabled campaigns on Acc2 as observation
print(f"\n2. Link to {len(TARGET_CAMPS)} prospecting campaigns on Acc2 (observation)")
ops = []
for cid in TARGET_CAMPS:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign      = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.create.user_list.user_list = LIST_RN
    op.create.negative      = False
    ops.append(op)
r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} associations")
