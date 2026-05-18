"""Split each ZATCA campaign into AR + EN ad groups.

Strategy (live-safe — C1 is ENABLED, C2/C3 PAUSED):
  1. Rename existing _AdGroup → _AR_AdGroup
  2. Pause any EN keywords currently in _AR_AdGroup
  3. Add new high-volume AR keywords to _AR_AdGroup
  4. Create _EN_AdGroup (PAUSED)
  5. Add EN keywords (PAUSED) to _EN_AdGroup
  6. Create EN-dominant RSA in _EN_AdGroup (PAUSED)

Keyword sets = existing commercial-intent + new high-volume from Keyword
Planner + competitor brand terms (C3 only).
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

import re
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
LP_URL  = "https://lp.qoyod.com/einvoice-integration/"

# ── Keyword sets per campaign per language ────────────────────────────────
KEYWORDS = {
    "23851270716": {  # C1 ZATCAPhase2
        "ar_add": [
            # NEW high-volume from Keyword Planner
            ("الربط مع هيئة الزكاة والدخل المرحلة الثانية", "PHRASE"),
            ("الربط مع هيئة الزكاة والدخل", "PHRASE"),
            ("برنامج الفاتورة", "PHRASE"),
        ],
        "en_keywords": [
            # Existing commercial-intent (already there in mixed _AdGroup — moving to EN)
            ("ZATCA Phase 2", "PHRASE"),
            ("ZATCA integration", "PHRASE"),
            ("fatoora portal", "PHRASE"),
            ("fatoora platform", "PHRASE"),
            ("ZATCA e-invoicing", "PHRASE"),
            # NEW high-volume from Planner (skip bare "zatca" — too broad/informational)
            ("zatca phase 2 integration", "PHRASE"),
            ("zatca e invoicing phase 2", "PHRASE"),
            ("zatca phase 2 requirements", "PHRASE"),
            ("zatca integration", "EXACT"),
            ("fatoora portal", "EXACT"),
        ],
    },
    "23861101390": {  # C2 ZATCAVendorShop
        "ar_add": [
            ("أفضل برنامج محاسبة", "PHRASE"),
            ("افضل برامج المحاسبه", "PHRASE"),
            ("أفضل برنامج محاسبة في السعودية", "EXACT"),
        ],
        "en_keywords": [
            ("ZATCA approved software", "EXACT"),
            ("best e-invoice software saudi", "PHRASE"),
            ("best accounting software saudi", "PHRASE"),
            ("ZATCA certified", "PHRASE"),
        ],
    },
    "23861965426": {  # C3 ZATCACompetitor
        "ar_add": [
            ("منصة فاتورة", "PHRASE"),   # 1900/mo Semrush
        ],
        "en_keywords": [
            # Existing
            ("Daftra ZATCA integration", "EXACT"),
            ("Wafeq Phase 2", "EXACT"),
            ("Qoyod vs Daftra", "PHRASE"),
            ("Qoyod vs Wafeq", "PHRASE"),
            ("Daftra vs Qoyod", "PHRASE"),
            ("Wafeq vs Qoyod", "PHRASE"),
            ("Rewaa ZATCA", "PHRASE"),
            ("Zoho ZATCA Saudi", "PHRASE"),
            # NEW competitor brand (Semrush)
            ("daftra", "PHRASE"),
            ("wafeq", "PHRASE"),
            ("rewaa", "PHRASE"),
        ],
    },
}

# EN-dominant RSAs per campaign (12 headlines, 4 descriptions each)
EN_RSAS = {
    "23851270716": {
        "headlines": [
            "ZATCA Phase 2 Integration",
            "Connect to Fatoora in Minutes",
            "ZATCA Certified E-Invoicing",
            "REST API + XML + PDF/A-3",
            "50,000+ Saudi Businesses Trust Us",
            "14-Day Free Trial - No Card",
            "Wave 24 Deadline: 30 June 2026",
            "Arabic 24/7 Support",
            "Phase 2 Compliance in 7 Days",
            "Qoyod - Saudi's #1 E-Invoice",
            "Compliance Guaranteed or Refund",
            "Compliant Phase 1 + Phase 2",
        ],
        "descriptions": [
            "Connect your business to Fatoora portal easily. XML, PDF/A-3, REST API. ZATCA approved.",
            "50,000+ Saudi companies use Qoyod. 14-day free trial. No credit card. Start now.",
            "Wave 24 of Phase 2 ends 30 June 2026. Integrate in 7 days or your fees back.",
            "Arabic-first customer support, 24/7. Specialized in the Saudi market.",
        ],
    },
    "23861101390": {
        "headlines": [
            "Best E-Invoice Software 2026",
            "ZATCA Approved Software",
            "Compare Saudi Accounting Tools",
            "Qoyod - Saudi's #1 Choice",
            "Phase 1 & Phase 2 Compliant",
            "50,000+ Businesses Trust Us",
            "14-Day Free Trial",
            "Arabic Support 24/7",
            "Easy Integration + Fast Setup",
            "Saudi Tax Experts",
            "Compliance Guaranteed or Refund",
            "Start Free - No Credit Card",
        ],
        "descriptions": [
            "Compare top e-invoicing platforms in Saudi Arabia. Qoyod: certified, local, specialized.",
            "Discover why 50,000+ Saudi businesses chose Qoyod. Full free trial. Start today.",
            "Phase 2 compliance guaranteed. Integrate in 7 days or full refund of fees.",
            "What sets Qoyod apart: locally certified, fully Arabic, 24/7 support.",
        ],
    },
    "23861965426": {
        "headlines": [
            "Best Daftra Alternative",
            "Better Than Wafeq + Rewaa",
            "ZATCA Approved - Saudi #1",
            "Why Businesses Switch to Us",
            "Phase 2 Integration in Minutes",
            "Arabic 24/7 Support - Local",
            "50,000+ Saudi Businesses",
            "14-Day Free Trial",
            "No Credit Card Required",
            "Compliance Guaranteed",
            "REST API + XML + PDF/A-3",
            "Qoyod - Saudi's #1 Platform",
        ],
        "descriptions": [
            "Looking for a Daftra or Wafeq alternative? Qoyod: ZATCA-certified, fully Saudi, faster integration.",
            "Compare Qoyod with competitors: 24/7 Arabic support, easier setup, local service. Start free today.",
            "50,000+ Saudi businesses switched to Qoyod. 14-day free trial, no card. Discover why.",
            "Wave 24 ends 30 June 2026. Faster + easier integration than any competitor - or refund.",
        ],
    },
}

CAMPAIGN_META = {
    "23851270716": {"name": "Google_Search_AREN_ZATCAPhase2_Broad",      "code": "ZATCAPhase2"},
    "23861101390": {"name": "Google_Search_AREN_ZATCAVendorShop_Broad",  "code": "ZATCAVendorShop"},
    "23861965426": {"name": "Google_Search_AREN_ZATCACompetitor_Broad",  "code": "ZATCACompetitor"},
}


client       = get_client()
ag_svc       = client.get_service("AdGroupService")
agc_svc      = client.get_service("AdGroupCriterionService")
agad_svc     = client.get_service("AdGroupAdService")
ga           = client.get_service("GoogleAdsService")


def mask(*p): return field_mask_pb2.FieldMask(paths=list(p))

# Detect Arabic vs Latin
def is_arabic(text: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", text))


# ── 1. Discover existing ad groups + keywords ──────────────────────────────
def discover():
    state = {}
    for cid in KEYWORDS:
        q = f"""
        SELECT ad_group.id, ad_group.name
        FROM ad_group WHERE campaign.id = {cid} AND ad_group.status != 'REMOVED'
        """
        ag_list = []
        for r in ga.search(customer_id=ACCOUNT, query=q):
            ag_list.append((str(r.ad_group.id), r.ad_group.name))
        state[cid] = {"adgroups": ag_list}

        # Keywords in current ad group(s)
        q2 = f"""
        SELECT ad_group.id, ad_group_criterion.criterion_id,
               ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.status,
               ad_group_criterion.negative
        FROM ad_group_criterion
        WHERE campaign.id = {cid} AND ad_group_criterion.type = 'KEYWORD'
          AND ad_group_criterion.status != 'REMOVED'
        """
        kws = []
        for r in ga.search(customer_id=ACCOUNT, query=q2):
            kws.append({
                "ag_id":      str(r.ad_group.id),
                "crit_id":    str(r.ad_group_criterion.criterion_id),
                "text":       r.ad_group_criterion.keyword.text,
                "mt":         r.ad_group_criterion.keyword.match_type.name,
                "status":     r.ad_group_criterion.status.name,
                "negative":   r.ad_group_criterion.negative,
            })
        state[cid]["keywords"] = kws
    return state


print("=" * 78)
print("PHASE 1 — Discover current state")
print("=" * 78)
state = discover()
for cid, s in state.items():
    print(f"\n{CAMPAIGN_META[cid]['name']} (cid={cid})")
    for ag_id, ag_name in s["adgroups"]:
        en = sum(1 for k in s["keywords"] if k["ag_id"] == ag_id and not is_arabic(k["text"]) and not k["negative"])
        ar = sum(1 for k in s["keywords"] if k["ag_id"] == ag_id and is_arabic(k["text"]) and not k["negative"])
        print(f"  ag={ag_id}  {ag_name}  AR={ar}  EN={en}")


# ── 2. Rename existing ad group → _AR_AdGroup ──────────────────────────────
print()
print("=" * 78)
print("PHASE 2 — Rename existing ad groups to _AR_AdGroup")
print("=" * 78)
ops = []
ar_adgroup_id_by_camp = {}
for cid, s in state.items():
    # If there's already an _AR_AdGroup, skip rename
    ar_ag = next(((agid, n) for agid, n in s["adgroups"] if n.endswith("_AR_AdGroup")), None)
    if ar_ag:
        ar_adgroup_id_by_camp[cid] = ar_ag[0]
        print(f"  ⏭ {cid}: already has {ar_ag[1]}")
        continue
    # Else rename the existing single ad group
    ag_id, ag_name = s["adgroups"][0]
    new_name = f"Google_Search_AREN_{CAMPAIGN_META[cid]['code']}_AR_AdGroup"
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/adGroups/{ag_id}"
    op.update.name          = new_name
    client.copy_from(op.update_mask, mask("name"))
    ops.append(op)
    ar_adgroup_id_by_camp[cid] = ag_id
    print(f"  → {ag_id}: {ag_name} → {new_name}")

if ops:
    r = ag_svc.mutate_ad_groups(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")


# ── 3. Pause EN keywords in the _AR_AdGroup ────────────────────────────────
print()
print("=" * 78)
print("PHASE 3 — Pause EN (Latin-script) keywords in _AR_AdGroup")
print("=" * 78)
ops = []
for cid, s in state.items():
    ar_ag_id = ar_adgroup_id_by_camp[cid]
    for k in s["keywords"]:
        if k["ag_id"] != ar_ag_id: continue
        if k["negative"]: continue
        if is_arabic(k["text"]): continue
        if k["status"] == "PAUSED": continue
        op = client.get_type("AdGroupCriterionOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/adGroupCriteria/{ar_ag_id}~{k['crit_id']}"
        op.update.status        = client.enums.AdGroupCriterionStatusEnum.PAUSED
        client.copy_from(op.update_mask, mask("status"))
        ops.append(op)
        print(f"  pause: {k['text']}")

if ops:
    r = agc_svc.mutate_ad_group_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ paused {len(r.results)} EN keyword(s)")
else:
    print("  (none — already clean)")


# ── 4. Add new AR keywords to _AR_AdGroup ──────────────────────────────────
print()
print("=" * 78)
print("PHASE 4 — Add new AR keywords to _AR_AdGroup")
print("=" * 78)
for cid in KEYWORDS:
    ar_ag_id = ar_adgroup_id_by_camp[cid]
    additions = KEYWORDS[cid]["ar_add"]
    if not additions: continue
    # Skip dupes — check what's already in the ad group
    existing = {(k["text"].lower(), k["mt"]) for k in state[cid]["keywords"]
                if k["ag_id"] == ar_ag_id and not k["negative"]}
    ops = []
    for text, mt in additions:
        if (text.lower(), mt) in existing: continue
        op = client.get_type("AdGroupCriterionOperation")
        op.create.ad_group        = f"customers/{ACCOUNT}/adGroups/{ar_ag_id}"
        op.create.keyword.text    = text
        op.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, mt)
        op.create.status          = client.enums.AdGroupCriterionStatusEnum.ENABLED
        ops.append(op)
        print(f"  + AR  ({mt}) {text}  [{CAMPAIGN_META[cid]['code']}]")
    if ops:
        try:
            r = agc_svc.mutate_ad_group_criteria(customer_id=ACCOUNT, operations=ops)
            print(f"  ✅ added {len(r.results)} AR keyword(s) to {CAMPAIGN_META[cid]['code']}")
        except Exception as e:
            print(f"  ❌ {str(e)[:200]}")


# ── 5. Create _EN_AdGroup + add EN keywords + EN RSA ───────────────────────
print()
print("=" * 78)
print("PHASE 5 — Create _EN_AdGroup + EN keywords + EN RSA")
print("=" * 78)

en_adgroup_id_by_camp = {}

for cid in KEYWORDS:
    code = CAMPAIGN_META[cid]["code"]
    name = f"Google_Search_AREN_{code}_EN_AdGroup"

    # Check if already exists
    existing_en = next((agid for agid, n in state[cid]["adgroups"] if n.endswith("_EN_AdGroup")), None)
    if existing_en:
        en_adgroup_id_by_camp[cid] = existing_en
        print(f"  ⏭ {code}: _EN_AdGroup already exists ({existing_en})")
        continue

    # Create
    op = client.get_type("AdGroupOperation")
    op.create.name      = name
    op.create.campaign  = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.create.status    = client.enums.AdGroupStatusEnum.PAUSED
    op.create.type_     = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    try:
        r = ag_svc.mutate_ad_groups(customer_id=ACCOUNT, operations=[op])
        en_ag_rn = r.results[0].resource_name
        en_ag_id = en_ag_rn.split("/")[-1]
        en_adgroup_id_by_camp[cid] = en_ag_id
        print(f"  ✅ created {name}  ({en_ag_id})")
    except Exception as e:
        print(f"  ❌ failed to create {name}: {str(e)[:200]}")
        continue

    # Add EN keywords
    en_ops = []
    for text, mt in KEYWORDS[cid]["en_keywords"]:
        op = client.get_type("AdGroupCriterionOperation")
        op.create.ad_group        = f"customers/{ACCOUNT}/adGroups/{en_ag_id}"
        op.create.keyword.text    = text
        op.create.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, mt)
        op.create.status          = client.enums.AdGroupCriterionStatusEnum.ENABLED
        en_ops.append(op)
    try:
        r = agc_svc.mutate_ad_group_criteria(customer_id=ACCOUNT, operations=en_ops)
        print(f"  ✅ added {len(r.results)} EN keyword(s) to {code}")
    except Exception as e:
        print(f"  ❌ keywords: {str(e)[:200]}")

    # Add EN RSA (PAUSED — for review)
    rsa = EN_RSAS[cid]
    ad_op = client.get_type("AdGroupAdOperation")
    ad_op.create.ad_group  = f"customers/{ACCOUNT}/adGroups/{en_ag_id}"
    ad_op.create.status    = client.enums.AdGroupAdStatusEnum.PAUSED
    ad_op.create.ad.final_urls.append(LP_URL)
    for h in rsa["headlines"]:
        a = client.get_type("AdTextAsset")
        a.text = h
        ad_op.create.ad.responsive_search_ad.headlines.append(a)
    for d in rsa["descriptions"]:
        a = client.get_type("AdTextAsset")
        a.text = d
        ad_op.create.ad.responsive_search_ad.descriptions.append(a)
    try:
        r = agad_svc.mutate_ad_group_ads(customer_id=ACCOUNT, operations=[ad_op])
        print(f"  ✅ created EN RSA (PAUSED) in {code}")
    except Exception as e:
        print(f"  ❌ EN RSA: {str(e)[:300]}")


print("\n" + "=" * 78)
print("DONE — run scripts/_audit_zatca_full.py to verify")
print("=" * 78)
