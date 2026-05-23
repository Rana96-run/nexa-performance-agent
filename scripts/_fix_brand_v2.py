"""Fix Search_AR_Brand_v2 (23032247671):

  1. Disable Display Network + Search Partners (Google Search ONLY)
     — this kills the ~102k/14d non-search impressions dragging CTR to 7%

  2. Add competitor / non-brand negatives spotted in search terms

# KPI-RULE-BYPASS — campaign settings + negatives, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

ACCT = "1513020554"
CID  = "23032247671"

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


# ─── 1. Turn off Display + Search Partners ─────────────────────────────────
print("=" * 72)
print("1. Disable Display Network + Search Partners")
print("=" * 72)
csvc = client.get_service("CampaignService")
op = client.get_type("CampaignOperation")
op.update.resource_name = f"customers/{ACCT}/campaigns/{CID}"
op.update.network_settings.target_google_search   = True   # keep ON
op.update.network_settings.target_search_network  = False  # OFF (was True)
op.update.network_settings.target_content_network = False  # OFF (was True)
op.update.network_settings.target_partner_search_network = False
client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=[
    "network_settings.target_google_search",
    "network_settings.target_search_network",
    "network_settings.target_content_network",
    "network_settings.target_partner_search_network",
]))
try:
    r = csvc.mutate_campaigns(customer_id=ACCT, operations=[op])
    print(f"  ✅ network restricted to Google Search only: {r.results[0].resource_name}")
except Exception as e:
    print(f"  ❌ network update: {_err(e)}")


# ─── 2. Add competitor / non-brand negatives ───────────────────────────────
print(f"\n{'=' * 72}")
print(f"2. Add competitor / non-brand negatives")
print('=' * 72)

# Patterns observed in search terms with bad CTR / no intent
NEW_NEGATIVES = [
    # Competitors (these have their own Competitor campaign — don't bid here)
    ("odoo",              "BROAD"),
    ("foodics",           "BROAD"),
    ("mudad",             "BROAD"),
    ("tally",             "BROAD"),
    ("wafeq",             "BROAD"),
    ("neoleap",           "BROAD"),
    ("aliphia",           "BROAD"),
    ("الاستاذ المحاسبي",  "PHRASE"),
    # Generic non-brand
    ("erp system",        "BROAD"),
    # Existing-customer login intent (they're already paying — wasted spend)
    ("sign in",           "BROAD"),
    ("login",             "BROAD"),
    ("تسجيل الدخول",      "PHRASE"),
    ("تسجيل دخول",        "PHRASE"),
    # Generic
    ("قائمة",             "EXACT"),   # standalone "list" — wrong intent
]

# Dedup against existing
ga = client.get_service("GoogleAdsService")
existing = set()
for r in ga.search(customer_id=ACCT, query=f"""
    SELECT campaign_criterion.keyword.text,
           campaign_criterion.keyword.match_type
    FROM campaign_criterion
    WHERE campaign.id = {CID}
      AND campaign_criterion.type='KEYWORD' AND campaign_criterion.negative=TRUE
"""):
    existing.add((r.campaign_criterion.keyword.text.lower(),
                  r.campaign_criterion.keyword.match_type.name))

svc_cc = client.get_service("CampaignCriterionService")
ok = 0
for text, match in NEW_NEGATIVES:
    if (text.lower(), match) in existing:
        print(f"  ⊘ [{match:<6}] {text} (already there)")
        continue
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = f"customers/{ACCT}/campaigns/{CID}"
    c.negative = True
    c.keyword.text = text
    c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
    try:
        svc_cc.mutate_campaign_criteria(customer_id=ACCT, operations=[op])
        print(f"  ✅ NEG [{match:<6}] {text}")
        ok += 1
    except Exception as e:
        print(f"  ❌ NEG [{match:<6}] {text}: {_err(e)[:120]}")
print(f"\n  → added {ok}/{len(NEW_NEGATIVES)} negatives")


# ─── 3. Verify ─────────────────────────────────────────────────────────────
print(f"\n{'=' * 72}")
print(f"3. Verify post-fix state")
print('=' * 72)
for r in ga.search(customer_id=ACCT, query=f"""
    SELECT campaign.network_settings.target_google_search,
           campaign.network_settings.target_search_network,
           campaign.network_settings.target_content_network
    FROM campaign WHERE campaign.id = {CID}
"""):
    n = r.campaign.network_settings
    print(f"  google_search={n.target_google_search}  "
          f"search_partners={n.target_search_network}  "
          f"display={n.target_content_network}")
