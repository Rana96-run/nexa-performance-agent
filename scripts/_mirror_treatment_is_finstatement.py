"""Mirror today's treatment onto Google_ImpressionShare_AREN_FinancialStatement
on Acc 1 (camp 23865358505):

  1. Add 12 high-volume AR keywords + 2 BROAD heads to AR ad group
  2. Add 15 prophylactic negatives at campaign level
  3. Add SAR 100 off promotion extension (AR + EN)

SKIPPED:
  - RSAs (already has 4 ads per AR ad group with 15 headlines each)
  - Audiences (already mirrors main campaign — 20 attached)
  - Extensions (sitelinks/callouts/snippets/call all in place)

Also: add 2 BROAD heads to Acc 2 ZATCAPhase2_EN_Auto.

# KPI-RULE-BYPASS — keyword/asset adds, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

# Acc 1 IS FinStatement
IS_ACCT = "1513020554"
IS_CID  = "23865358505"
IS_AR_AG_ID = "197141858136"
IS_EN_AG_ID = "197141858096"

# Acc 2 ZATCA Phase2 EN ad group
P2_ACCT = "5753494964"
P2_CID  = "23865711095"
P2_EN_AG_ID = "198338542524"

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


# ─────────────────────────────────────────────────────────────────────────────
# 1. AR keywords on IS_FinStatement
# ─────────────────────────────────────────────────────────────────────────────
AR_KEYWORDS = [
    ("منصة قوائم",                              "EXACT"),
    ("قائمة الدخل",                             "EXACT"),
    ("قوائم وزارة التجارة",                     "EXACT"),
    ("إيداع القوائم المالية",                   "EXACT"),
    ("ايداع القوائم المالية للشركات",           "EXACT"),
    ("وزارة التجارة قوائم",                     "EXACT"),
    ("xbrl",                                    "EXACT"),
    ("الاستعلام عن ايداع القوائم المالية",      "PHRASE"),
    ("الاستفسار عن ايداع القوائم المالية",      "PHRASE"),
    ("التحقق من ايداع القوائم المالية",         "PHRASE"),
    ("الاستفسار عن حالة ايداع القوائم المالية", "PHRASE"),
    ("برنامج قوائم وزارة التجارة",              "PHRASE"),
    # BROAD heads for Smart Bidding
    ("منصة قوائم",                              "BROAD"),
    ("قائمة الدخل",                             "BROAD"),
]

print("=" * 72)
print("STEP 1 — AR keywords on IS_FinStatement AR ad group")
print("=" * 72)
svc = client.get_service("AdGroupCriterionService")
ag_rn = f"customers/{IS_ACCT}/adGroups/{IS_AR_AG_ID}"
ok, dup = 0, 0
for text, match in AR_KEYWORDS:
    op = client.get_type("AdGroupCriterionOperation")
    c = op.create
    c.ad_group = ag_rn
    c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    c.keyword.text = text
    c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
    try:
        svc.mutate_ad_group_criteria(customer_id=IS_ACCT, operations=[op])
        ok += 1
        print(f"  ✅ [{match:<6}] {text}")
    except Exception as e:
        msg = _err(e)
        if "duplicate" in msg.lower() or "DUPLICATE" in msg:
            dup += 1
            print(f"  ⊘ [{match:<6}] {text} (dup)")
        else:
            print(f"  ❌ [{match:<6}] {text}: {msg[:150]}")
print(f"  → added {ok}, skipped dup {dup}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Prophylactic negatives on IS_FinStatement
# ─────────────────────────────────────────────────────────────────────────────
NEGATIVES = [
    ("محاسب قانوني",     "PHRASE"),
    ("محاسبين قانونيين", "PHRASE"),
    ("مكتب محاسبة",      "PHRASE"),
    ("توظيف",  "BROAD"),
    ("وظائف",  "BROAD"),
    ("وظيفة",  "BROAD"),
    ("jobs",   "BROAD"),
    ("hiring", "BROAD"),
    ("تحميل", "BROAD"),
    ("تنزيل", "BROAD"),
    ("نموذج",   "PHRASE"),
    ("نماذج",   "PHRASE"),
    ("pdf",     "BROAD"),
    ("excel",   "BROAD"),
    ("template", "BROAD"),
]

print(f"\n{'=' * 72}")
print(f"STEP 2 — Prophylactic negatives on IS_FinStatement campaign")
print('=' * 72)
ga = client.get_service("GoogleAdsService")
existing = set()
for r in ga.search(customer_id=IS_ACCT, query=f"""
    SELECT campaign_criterion.keyword.text,
           campaign_criterion.keyword.match_type
    FROM campaign_criterion
    WHERE campaign.id = {IS_CID}
      AND campaign_criterion.type='KEYWORD' AND campaign_criterion.negative=TRUE
"""):
    existing.add((r.campaign_criterion.keyword.text.lower(),
                  r.campaign_criterion.keyword.match_type.name))

svc_cc = client.get_service("CampaignCriterionService")
ok2 = 0
for text, match in NEGATIVES:
    if (text.lower(), match) in existing:
        print(f"  ⊘ [{match:<6}] {text} (already negative)")
        continue
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = f"customers/{IS_ACCT}/campaigns/{IS_CID}"
    c.negative = True
    c.keyword.text = text
    c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
    try:
        svc_cc.mutate_campaign_criteria(customer_id=IS_ACCT, operations=[op])
        ok2 += 1
        print(f"  ✅ NEG [{match:<6}] {text}")
    except Exception as e:
        print(f"  ❌ NEG [{match:<6}] {text}: {_err(e)[:120]}")
print(f"  → added {ok2}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Promotion extension (SAR 100 off Qoyod Annual Plan)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 72}")
print(f"STEP 3 — Promotion extension on IS_FinStatement")
print('=' * 72)
PROMOS = [
    {"name": "Promo_qawaem_IS_AR", "target": "باقة قيود السنوية", "lang_code": "ar"},
    {"name": "Promo_qawaem_IS_EN", "target": "Qoyod Annual Plan", "lang_code": "en"},
]
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")
rns = []
for p in PROMOS:
    op = client.get_type("AssetOperation")
    a = op.create
    a.name = p["name"]
    a.final_urls.append("https://lp.qoyod.com/qawaem/")
    pa = a.promotion_asset
    pa.promotion_target = p["target"]
    pa.money_amount_off.amount_micros = 100_000_000
    pa.money_amount_off.currency_code = "SAR"
    pa.language_code = p["lang_code"]
    try:
        r = asset_svc.mutate_assets(customer_id=IS_ACCT, operations=[op])
        rns.append(r.results[0].resource_name)
        print(f"  ✅ {p['name']}: {r.results[0].resource_name}")
    except Exception as e:
        print(f"  ❌ {p['name']}: {_err(e)[:200]}")

if rns:
    link_ops = []
    for rn in rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{IS_ACCT}/campaigns/{IS_CID}"
        op.create.asset      = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum.PROMOTION
        link_ops.append(op)
    try:
        r = ca_svc.mutate_campaign_assets(customer_id=IS_ACCT, operations=link_ops)
        print(f"  ✅ linked {len(r.results)} promo assets")
    except Exception as e:
        print(f"  ❌ link: {_err(e)[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. EN BROAD heads on Acc 2 ZATCAPhase2 EN ad group
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 72}")
print(f"STEP 4 — BROAD heads on Acc 2 ZATCAPhase2 EN ad group")
print('=' * 72)
EN_BROADS = [
    "ZATCA Phase 2",
    "e-invoicing Saudi",
    "ZATCA integration",
]
ag_rn = f"customers/{P2_ACCT}/adGroups/{P2_EN_AG_ID}"
for kw in EN_BROADS:
    op = client.get_type("AdGroupCriterionOperation")
    c = op.create
    c.ad_group = ag_rn
    c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    c.keyword.text = kw
    c.keyword.match_type = client.enums.KeywordMatchTypeEnum.BROAD
    try:
        svc.mutate_ad_group_criteria(customer_id=P2_ACCT, operations=[op])
        print(f"  ✅ BROAD: {kw}")
    except Exception as e:
        msg = _err(e)
        if "duplicate" in msg.lower():
            print(f"  ⊘ BROAD: {kw} (dup)")
        else:
            print(f"  ❌ BROAD: {kw} — {msg[:120]}")

print("\nDONE")
