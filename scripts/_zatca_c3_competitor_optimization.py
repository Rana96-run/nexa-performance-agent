"""Optimize C3 (ZATCACompetitor) based on URL-seeded research findings.

  1. Add 5 new high-volume AR brand-stem keywords (Rewaa variants) to AR ad group
  2. Add 3 LOGIN negatives at campaign level — block "wafeq login" / "rewaa login"
     buyer-irrelevant searches that triggered our existing keywords
  3. Pause keywords currently flagged LOW_SEARCH_VOLUME on C3 (not serving anyway,
     just diluting ad-group QS)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT     = "1513020554"
CAMP_ID     = "23861965426"   # C3 ZATCACompetitor
AR_AG_ID    = "193841456302"  # C3 AR ad group

# 5 new high-volume buyer-intent AR keywords (PHRASE)
NEW_AR_KEYWORDS = [
    ("رواء",                 "PHRASE"),   # 49,500/mo
    ("منصة رواء",            "PHRASE"),   # 12,100/mo
    ("رواء المحاسبي",        "PHRASE"),   # 1,000/mo
    ("برنامج رواء",          "PHRASE"),   # 880/mo
    ("رواء منصة",            "PHRASE"),   # 590/mo
]

# 3 login-intent negatives (block existing-user searches, not buyers)
LOGIN_NEGATIVES = [
    ("تسجيل الدخول", "BROAD"),
    ("تسجيل دخول",   "BROAD"),
    ("login",         "BROAD"),
]

client    = get_client()
ga        = client.get_service("GoogleAdsService")
agc_svc   = client.get_service("AdGroupCriterionService")
cc_svc    = client.get_service("CampaignCriterionService")


# ── 1. Add new AR keywords to AR ad group ──────────────────────────────────
print("=" * 70)
print("1. Add 5 new AR brand-stem keywords")
print("=" * 70)
ops = []
for text, mt in NEW_AR_KEYWORDS:
    op = client.get_type("AdGroupCriterionOperation")
    op.create.ad_group        = f"customers/{ACCOUNT}/adGroups/{AR_AG_ID}"
    op.create.keyword.text    = text
    op.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, mt)
    op.create.status          = client.enums.AdGroupCriterionStatusEnum.ENABLED
    ops.append(op)
    print(f"  + {text}  ({mt})")
r = agc_svc.mutate_ad_group_criteria(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ added {len(r.results)} keyword(s)")


# ── 2. Add 3 login negatives at campaign level ─────────────────────────────
print()
print("=" * 70)
print("2. Add 3 login-intent negatives at campaign level")
print("=" * 70)
ops = []
for text, mt in LOGIN_NEGATIVES:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign            = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.keyword.text        = text
    op.create.keyword.match_type  = getattr(client.enums.KeywordMatchTypeEnum, mt)
    op.create.negative            = True
    ops.append(op)
    print(f"  − {text}  ({mt})")
r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ added {len(r.results)} negative(s)")


# ── 3. Pause keywords with LOW_SEARCH_VOLUME status on C3 ──────────────────
print()
print("=" * 70)
print("3. Find + pause LOW_SEARCH_VOLUME keywords on C3")
print("=" * 70)
q = f"""
SELECT ad_group.id, ad_group.name,
       ad_group_criterion.criterion_id,
       ad_group_criterion.keyword.text,
       ad_group_criterion.system_serving_status,
       ad_group_criterion.status
FROM ad_group_criterion
WHERE campaign.id = {CAMP_ID}
  AND ad_group_criterion.type = 'KEYWORD'
  AND ad_group_criterion.negative = FALSE
  AND ad_group_criterion.status = 'ENABLED'
"""
to_pause = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    if r.ad_group_criterion.system_serving_status.name == "LOW_SEARCH_VOLUME":
        to_pause.append({
            "ag_id":   str(r.ad_group.id),
            "crit_id": str(r.ad_group_criterion.criterion_id),
            "text":    r.ad_group_criterion.keyword.text,
        })

print(f"Found {len(to_pause)} LOW_SEARCH_VOLUME keyword(s):")
for k in to_pause:
    print(f"  - {k['text']}")

if to_pause:
    ops = []
    for k in to_pause:
        op = client.get_type("AdGroupCriterionOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/adGroupCriteria/{k['ag_id']}~{k['crit_id']}"
        op.update.status        = client.enums.AdGroupCriterionStatusEnum.PAUSED
        from google.protobuf import field_mask_pb2
        client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["status"]))
        ops.append(op)
    r = agc_svc.mutate_ad_group_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ paused {len(r.results)} keyword(s)")
else:
    print("  (none — all C3 keywords have volume or are already paused)")


print("\n" + "=" * 70)
print("DONE — C3 now has higher-volume Arabic brand-stems + login negatives")
print("=" * 70)
