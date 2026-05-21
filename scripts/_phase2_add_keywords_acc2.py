"""Add 8 missing high-volume keywords + 1 negative + 2 broad head terms
to ZATCAPhase2_AR_Auto on Acc 2 (5753494964 / 23865711095)."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

ACC2 = "5753494964"
CID  = "23865711095"
AG_ID_AR = None  # resolved below

client = get_client()
ga = client.get_service("GoogleAdsService")

# Resolve AR ad group id
for r in ga.search(customer_id=ACC2, query=f"""
    SELECT ad_group.id, ad_group.name FROM ad_group
    WHERE campaign.id = {CID} AND ad_group.name LIKE '%AR%'
"""):
    AG_ID_AR = r.ad_group.id
    print(f"AR ad group: {r.ad_group.name} ({AG_ID_AR})")

# Adds: 8 missing high-volume + 2 BROAD for head terms
ADDS = [
    ("فاتورة إلكترونية",          "EXACT"),
    ("الفاتورة الكترونية",        "EXACT"),
    ("فوترة إلكترونية",           "EXACT"),
    ("فوترة الكترونية",           "EXACT"),
    ("zatca portal",              "EXACT"),
    ("فواتير الكترونية",          "EXACT"),
    ("انشاء فاتورة الكترونية",    "PHRASE"),
    ("فاتورة ضريبية الكترونية",   "EXACT"),
    # 2 BROAD for Smart Bidding discovery
    ("فاتورة إلكترونية",          "BROAD"),
    ("ZATCA Phase 2",             "BROAD"),
]

# Campaign-level negative: PDF→Word converter (huge volume, unrelated)
CAMPAIGN_NEGATIVES = [
    ("تحويل بي دى اف الى وورد", "PHRASE"),
    ("pdf to word",             "BROAD"),
    ("تحويل pdf",                "BROAD"),
]


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


# 1. Add keywords to AR ad group
print(f"\n1. Adding {len(ADDS)} keywords to AR ad group")
svc = client.get_service("AdGroupCriterionService")
ag_rn = f"customers/{ACC2}/adGroups/{AG_ID_AR}"
ok = 0
for text, match in ADDS:
    op = client.get_type("AdGroupCriterionOperation")
    c = op.create
    c.ad_group = ag_rn
    c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    c.keyword.text = text
    c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
    try:
        svc.mutate_ad_group_criteria(customer_id=ACC2, operations=[op])
        ok += 1
        print(f"  ✅ [{match:<6}] {text}")
    except Exception as e:
        msg = _err(e)
        if "duplicate" in msg.lower() or "DUPLICATE" in msg:
            print(f"  ⊘ [{match:<6}] {text} (dup)")
        else:
            print(f"  ❌ [{match:<6}] {text}: {msg[:120]}")
print(f"  → added {ok}/{len(ADDS)}")


# 2. Add campaign-level negatives
print(f"\n2. Adding {len(CAMPAIGN_NEGATIVES)} prophylactic negatives")
svc_cc = client.get_service("CampaignCriterionService")
camp_rn = f"customers/{ACC2}/campaigns/{CID}"
for text, match in CAMPAIGN_NEGATIVES:
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = camp_rn
    c.negative = True
    c.keyword.text = text
    c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
    try:
        svc_cc.mutate_campaign_criteria(customer_id=ACC2, operations=[op])
        print(f"  ✅ NEG [{match:<6}] {text}")
    except Exception as e:
        msg = _err(e)
        if "duplicate" in msg.lower() or "DUPLICATE" in msg:
            print(f"  ⊘ NEG [{match:<6}] {text} (dup)")
        else:
            print(f"  ❌ NEG [{match:<6}] {text}: {msg[:120]}")
