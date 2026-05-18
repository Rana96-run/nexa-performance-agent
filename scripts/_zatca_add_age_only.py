"""Add only age ranges as observation to all 3 ZATCA campaigns."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

AGE_RANGES = [
    "AGE_RANGE_18_24",
    "AGE_RANGE_25_34",
    "AGE_RANGE_35_44",
    "AGE_RANGE_45_54",
    "AGE_RANGE_55_64",
    "AGE_RANGE_65_UP",
    "AGE_RANGE_UNDETERMINED",
]

c = get_client()
cc_svc = c.get_service("CampaignCriterionService")

ops = []
for cid in CAMPS:
    for name in AGE_RANGES:
        op = c.get_type("CampaignCriterionOperation")
        op.create.campaign     = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.negative     = False
        op.create.age_range.type_ = getattr(c.enums.AgeRangeTypeEnum, name)
        ops.append(op)

try:
    r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"✅ added {len(r.results)} age-range criteria (7 × 3 campaigns)")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:5]: print(f"  ❌ {m}")
