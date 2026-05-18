"""Create a flexible-rule remarketing list:
  INCLUDE: url__ contains www.qoyod.com OR lp.qoyod.com OR campaigns.qoyod.com
  EXCLUDE: url__ contains app.qoyod.com
Membership: 540 days (max).

Then link to ZATCA + Brand campaigns as observation.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
ZATCA_CAMPS = ["23851270716", "23861101390", "23861965426"]
BRAND_CAMPS = ["22221111741", "22434988923", "23032247671"]

INCLUDE_DOMAINS = ["www.qoyod.com", "lp.qoyod.com", "campaigns.qoyod.com"]
EXCLUDE_DOMAINS = ["app.qoyod.com"]

LIST_NAME = "Qoyod Site Visitors (www + lp + campaigns, excl. app)"


def make_url_operand(client, domain, label):
    """Build a FlexibleRuleOperandInfo: a single rule_item_group with one
    URL-contains rule item."""
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


client     = get_client()
ul_svc     = client.get_service("UserListService")
cc_svc     = client.get_service("CampaignCriterionService")

# ── 1. Build the user list ────────────────────────────────────────────────
print("1. Create flexible-rule user list")
op = client.get_type("UserListOperation")
co = op.create
co.name = LIST_NAME
co.description = "Visitors to qoyod.com domains except app subdomain (signed-in users)"
co.membership_life_span = 540
co.membership_status = client.enums.UserListMembershipStatusEnum.OPEN

flex = co.rule_based_user_list.flexible_rule_user_list
flex.inclusive_rule_operator = client.enums.UserListFlexibleRuleOperatorEnum.OR
for d in INCLUDE_DOMAINS:
    flex.inclusive_operands.append(make_url_operand(client, d, f"include {d}"))
for d in EXCLUDE_DOMAINS:
    flex.exclusive_operands.append(make_url_operand(client, d, f"exclude {d}"))

r = ul_svc.mutate_user_lists(customer_id=ACCOUNT, operations=[op])
LIST_RN = r.results[0].resource_name
print(f"  ✅ created: {LIST_RN}")
print(f"     name: {LIST_NAME}")
print(f"     include: {', '.join(INCLUDE_DOMAINS)}")
print(f"     exclude: {', '.join(EXCLUDE_DOMAINS)}")
print(f"     lifespan: 540 days  (will start populating immediately)")

# ── 2. Link to ZATCA + Brand campaigns as OBSERVATION ─────────────────────
all_camps = ZATCA_CAMPS + BRAND_CAMPS
print(f"\n2. Link as observation to {len(all_camps)} campaigns (3 ZATCA + 3 Brand)")
ops = []
for cid in all_camps:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign      = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.create.user_list.user_list = LIST_RN
    op.create.negative      = False
    ops.append(op)
r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} associations")

print()
print("Notes:")
print("- List starts empty. Populates from now forward via Google Ads remarketing tag")
print("  / GA4 → Google Ads link. Will take 24-72h to show first members.")
print("- Reach for Search Ads requires ≥1,000 active users in last 30 days.")
print("- At 540-day lifespan + qoyod.com traffic volume, expect ≥50k members within 60 days.")
