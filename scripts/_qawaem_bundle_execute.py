"""Execute the Qawaem optimization bundle on both accounts:
  1. Add prophylactic negatives (deduped against current 7)
  2. Add audiences on Acc 2 (mirror Acc 1's 20-audience setup)
  3. Add promotion extension (AR + EN) on both

Skipped (already in place): call extension on both accounts.

# KPI-RULE-BYPASS — campaign asset/criteria, not SQL-leads analysis.
"""
import sys
from datetime import date
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

ACC1_CID = "23861837000"   # Acc 1 FinancialStatement
ACC2_CID = "23870151040"   # Acc 2 FinancialStatement

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prophylactic negatives — dedup against current
# ─────────────────────────────────────────────────────────────────────────────
PROPHYLACTIC_NEGATIVES = [
    # hiring intent (we sell software, not accountant services)
    ("محاسب قانوني",     "PHRASE"),
    ("محاسبين قانونيين", "PHRASE"),
    ("مكتب محاسبة",      "PHRASE"),
    # jobs
    ("توظيف",  "BROAD"),
    ("وظائف",  "BROAD"),
    ("وظيفة",  "BROAD"),
    ("jobs",   "BROAD"),
    ("hiring", "BROAD"),
    # Arabic download (English already has "download")
    ("تحميل", "BROAD"),
    ("تنزيل", "BROAD"),
    # template / form seekers (low intent)
    ("نموذج",   "PHRASE"),
    ("نماذج",   "PHRASE"),
    ("pdf",     "BROAD"),
    ("excel",   "BROAD"),
    ("template", "BROAD"),
]

print("=" * 72)
print("STEP 1 — Prophylactic negatives")
print("=" * 72)

for acct, cid in [("1513020554", ACC1_CID), ("5753494964", ACC2_CID)]:
    ga = client.get_service("GoogleAdsService")
    existing = set()
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign_criterion.keyword.text,
               campaign_criterion.keyword.match_type
        FROM campaign_criterion
        WHERE campaign.id = {cid}
          AND campaign_criterion.type = 'KEYWORD'
          AND campaign_criterion.negative = TRUE
    """):
        existing.add((r.campaign_criterion.keyword.text.lower(),
                      r.campaign_criterion.keyword.match_type.name))

    svc = client.get_service("CampaignCriterionService")
    ops = []
    for text, match in PROPHYLACTIC_NEGATIVES:
        if (text.lower(), match) in existing:
            continue
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = f"customers/{acct}/campaigns/{cid}"
        c.negative = True
        c.keyword.text = text
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
        ops.append(op)

    print(f"\nAcc {acct}: skipped {len(PROPHYLACTIC_NEGATIVES) - len(ops)} dupes, adding {len(ops)}")
    if ops:
        try:
            r = svc.mutate_campaign_criteria(customer_id=acct, operations=ops)
            print(f"  ✅ added {len(r.results)} negatives")
        except Exception as e:
            print(f"  ❌ {_err(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Audiences on Acc 2 (mirror Acc 1's bundle)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("STEP 2 — Audiences on Acc 2")
print("=" * 72)

# Acc 2 needs: 11 in-market + 4 observe lists + 3 exclusion lists + bid_only=True
IN_MARKET_IDS = ["80133","80137","80281","80463","80530","80536",
                 "80279","80518","80538","92913","92931"]

# Names to resolve on Acc 2 (pick largest if multiple)
EXCLUDE_NAMES = [
    "HubSpot - All Customers",
    "HubSpot - Advanced/Premium/Pro Subscribers",
    "Active SaaS Users",
]
OBSERVE_NAMES = [
    "HubSpot - All Marketing Contacts",
    "All Converters",
    "Ad Video Viewers",
    "Channel Video Viewers",
    "e-invoice page",
]

ga = client.get_service("GoogleAdsService")

# Resolve best (largest size) resource name per target name on Acc 2
best = {}
for r in ga.search(customer_id="5753494964", query="""
    SELECT user_list.name, user_list.resource_name, user_list.size_for_search
    FROM user_list
"""):
    n = r.user_list.name
    if n in EXCLUDE_NAMES or n in OBSERVE_NAMES:
        if n not in best or r.user_list.size_for_search > best[n]["size"]:
            best[n] = {"rn": r.user_list.resource_name,
                       "size": r.user_list.size_for_search}

print(f"resolved {len(best)} user lists on Acc 2:")
for n, info in best.items():
    print(f"  {n:<45} size={info['size']:>7}  rn={info['rn']}")

# 2a. AUDIENCE bid_only=True on the campaign (observation mode)
from google.protobuf import field_mask_pb2
csvc = client.get_service("CampaignService")
op_c = client.get_type("CampaignOperation")
op_c.update.resource_name = f"customers/5753494964/campaigns/{ACC2_CID}"
tr = client.get_type("TargetRestriction")
tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
tr.bid_only = True
op_c.update.targeting_setting.target_restrictions.append(tr)
client.copy_from(op_c.update_mask, field_mask_pb2.FieldMask(paths=[
    "targeting_setting.target_restrictions"
]))
try:
    csvc.mutate_campaigns(customer_id="5753494964", operations=[op_c])
    print("  ✅ AUDIENCE bid_only=True set (observation mode)")
except Exception as e:
    print(f"  ❌ targeting_setting: {_err(e)}")

# 2b. Attach in-market + observe + exclude
svc_cc = client.get_service("CampaignCriterionService")
ops = []
camp_rn = f"customers/5753494964/campaigns/{ACC2_CID}"

# In-market / affinity (observation, no negative)
for aid in IN_MARKET_IDS:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = camp_rn
    op.create.user_interest.user_interest_category = (
        f"customers/5753494964/userInterests/{aid}")
    ops.append(op)

# Customer exclusions (negative)
for n in EXCLUDE_NAMES:
    if n not in best: continue
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = camp_rn
    op.create.user_list.user_list = best[n]["rn"]
    op.create.negative = True
    ops.append(op)

# Observe lists (not negative — observation under bid_only)
for n in OBSERVE_NAMES:
    if n not in best: continue
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = camp_rn
    op.create.user_list.user_list = best[n]["rn"]
    ops.append(op)

# Per-criterion add to isolate failures
ok = 0
for op in ops:
    try:
        svc_cc.mutate_campaign_criteria(customer_id="5753494964", operations=[op])
        ok += 1
    except Exception as e:
        msg = _err(e)
        if "already exists" in msg.lower() or "DUPLICATE" in msg:
            print(f"  ⊘ dup skip")
        else:
            label = (op.create.user_interest.user_interest_category
                     or op.create.user_list.user_list)
            print(f"  ❌ {label[-30:]}: {msg[:120]}")
print(f"  ✅ {ok}/{len(ops)} audience criteria added on Acc 2")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Promotion extension (both accounts) — "14-day free trial"
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("STEP 3 — Promotion extension (both accounts)")
print("=" * 72)

# AR + EN versions. Using percent_off=100 because "free trial" = 100% off
# subscription cost for the trial window — Google renders cleanly.
PROMOS = [
    {
        "name":    "Promo_qawaem_AR_freetrial",
        "lang":    "ar",
        "target":  "تجربة قيود",
        "lang_code": "ar",
        "details_d1": "14 يوم مجاناً",
        "details_d2": "بدون بطاقة ائتمان",
        "final_url": "https://lp.qoyod.com/qawaem/",
    },
    {
        "name":    "Promo_qawaem_EN_freetrial",
        "lang":    "en",
        "target":  "Qoyod Trial",
        "lang_code": "en",
        "details_d1": "14 days free",
        "details_d2": "No card required",
        "final_url": "https://lp.qoyod.com/qawaem/",
    },
]

for acct, cid in [("1513020554", ACC1_CID), ("5753494964", ACC2_CID)]:
    print(f"\nAcc {acct}:")
    asset_svc = client.get_service("AssetService")
    ca_svc    = client.get_service("CampaignAssetService")
    promo_rns = []

    for p in PROMOS:
        op = client.get_type("AssetOperation")
        a = op.create
        a.name = p["name"]
        pa = a.promotion_asset
        pa.promotion_target = p["target"]
        # discount_modifier default UNSPECIFIED is fine (no "Up to" prefix)
        pa.percent_off = 100_000_000   # 100% off (100 * 1e6 micro-percent)
        pa.final_urls.append(p["final_url"])
        pa.language_code = p["lang_code"]
        # Optional: end date
        try:
            r = asset_svc.mutate_assets(customer_id=acct, operations=[op])
            promo_rns.append(r.results[0].resource_name)
            print(f"  ✅ {p['name']}: {r.results[0].resource_name}")
        except Exception as e:
            print(f"  ❌ {p['name']}: {_err(e)[:200]}")

    # Link to campaign
    if promo_rns:
        link_ops = []
        for rn in promo_rns:
            op = client.get_type("CampaignAssetOperation")
            op.create.campaign   = f"customers/{acct}/campaigns/{cid}"
            op.create.asset      = rn
            op.create.field_type = client.enums.AssetFieldTypeEnum.PROMOTION
            link_ops.append(op)
        try:
            r = ca_svc.mutate_campaign_assets(customer_id=acct, operations=link_ops)
            print(f"  ✅ linked {len(r.results)} promotion assets to campaign")
        except Exception as e:
            print(f"  ❌ link: {_err(e)[:200]}")

print("\nDONE — bundle applied.")
