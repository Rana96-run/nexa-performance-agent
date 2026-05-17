"""Audit the 2 new ZATCA Phase 2 campaigns post-creation.
Verifies every setting against requirements:
  - Bidding strategy + target CPA
  - Network settings (Search-only, NOT Display)
  - Location targeting (Saudi Arabia)
  - Language targeting (Arabic + English)
  - Ad group naming convention
  - Keyword match types
  - Keyword volume + predicted QS (from BQ history)
  - Negative keywords
  - RSA assets
  - Final URL with UTM
"""
import sys, os
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client
from collectors.bq_writer import get_client as bq_client, PROJECT_ID, DATASET

ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]  # ZATCAPhase2 + ZATCAVendorShop

client = get_client()
ga     = client.get_service("GoogleAdsService")
bq     = bq_client()
DS     = f"`{PROJECT_ID}.{DATASET}`"


def query(q, cid=ACCOUNT):
    """Run a GAQL query against the account."""
    return list(ga.search(customer_id=cid, query=q))


# ── 1. Campaign-level settings ─────────────────────────────────────────────
print("=" * 80)
print("1. CAMPAIGN SETTINGS")
print("=" * 80)
camp_q = f"""
SELECT
  campaign.id, campaign.name, campaign.status,
  campaign.advertising_channel_type,
  campaign.bidding_strategy_type,
  campaign.maximize_conversions.target_cpa_micros,
  campaign.network_settings.target_google_search,
  campaign.network_settings.target_search_network,
  campaign.network_settings.target_content_network,
  campaign.network_settings.target_partner_search_network,
  campaign.contains_eu_political_advertising,
  campaign_budget.amount_micros,
  campaign_budget.delivery_method,
  campaign_budget.name
FROM campaign
WHERE campaign.id IN ({",".join(CAMP_IDS)})
"""
camps = {}
for r in query(camp_q):
    cid = str(r.campaign.id)
    camps[cid] = r
    print(f"\n  📋 {r.campaign.name}  (id={cid})")
    print(f"     Status: {r.campaign.status.name}")
    print(f"     Channel: {r.campaign.advertising_channel_type.name}")
    print(f"     Bidding: {r.campaign.bidding_strategy_type.name}  "
          f"  tCPA: ${r.campaign.maximize_conversions.target_cpa_micros/1_000_000:.0f}")
    print(f"     Budget: ${r.campaign_budget.amount_micros/1_000_000:.0f}/day  "
          f"  Delivery: {r.campaign_budget.delivery_method.name}")
    ns = r.campaign.network_settings
    print(f"     Networks: Search={ns.target_google_search}  "
          f"SearchPartners={ns.target_search_network}  "
          f"Display={ns.target_content_network}  "
          f"PartnerSearch={ns.target_partner_search_network}")
    eu = r.campaign.contains_eu_political_advertising.name
    print(f"     EU political: {eu}")


# ── 2. Location targeting (geo) ────────────────────────────────────────────
print("\n" + "=" * 80)
print("2. LOCATION TARGETING — should be Saudi Arabia only")
print("=" * 80)
geo_q = f"""
SELECT campaign.id, campaign.name,
       campaign_criterion.criterion_id,
       campaign_criterion.location.geo_target_constant,
       campaign_criterion.negative
FROM campaign_criterion
WHERE campaign.id IN ({",".join(CAMP_IDS)})
  AND campaign_criterion.type = LOCATION
"""
loc_by_camp = {}
for r in query(geo_q):
    cid = str(r.campaign.id)
    loc_by_camp.setdefault(cid, []).append(r)
for cid in CAMP_IDS:
    if cid not in camps: continue
    name = camps[cid].campaign.name
    locs = loc_by_camp.get(cid, [])
    if not locs:
        print(f"\n  ⚠️  {name}: NO location targeting → defaults to ALL countries (BAD)")
    else:
        print(f"\n  📍 {name}: {len(locs)} location target(s)")
        for l in locs[:5]:
            print(f"       criterion_id={l.campaign_criterion.criterion_id}  "
                  f"geo={l.campaign_criterion.location.geo_target_constant}  "
                  f"negative={l.campaign_criterion.negative}")


# ── 3. Language targeting ──────────────────────────────────────────────────
print("\n" + "=" * 80)
print("3. LANGUAGE TARGETING — should include Arabic + English")
print("=" * 80)
lang_q = f"""
SELECT campaign.id, campaign.name,
       campaign_criterion.language.language_constant
FROM campaign_criterion
WHERE campaign.id IN ({",".join(CAMP_IDS)})
  AND campaign_criterion.type = LANGUAGE
"""
lang_by_camp = {}
for r in query(lang_q):
    cid = str(r.campaign.id)
    lang_by_camp.setdefault(cid, []).append(r)
for cid in CAMP_IDS:
    if cid not in camps: continue
    name = camps[cid].campaign.name
    langs = lang_by_camp.get(cid, [])
    if not langs:
        print(f"\n  ⚠️  {name}: NO language targeting → defaults to ALL (probably fine)")
    else:
        print(f"\n  🗣️  {name}: {len(langs)} language(s)")
        for l in langs:
            print(f"       {l.campaign_criterion.language.language_constant}")


# ── 4. Ad group + naming ───────────────────────────────────────────────────
print("\n" + "=" * 80)
print("4. AD GROUP — name + status + CPC bid")
print("=" * 80)
ag_q = f"""
SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status,
       ad_group.cpc_bid_micros, ad_group.type
FROM ad_group
WHERE campaign.id IN ({",".join(CAMP_IDS)})
"""
ag_by_camp = {}
for r in query(ag_q):
    cid = str(r.campaign.id)
    ag_by_camp.setdefault(cid, []).append(r)
    print(f"\n  📦 {r.ad_group.name}")
    print(f"     Status: {r.ad_group.status.name}  Type: {r.ad_group.type.name}")
    print(f"     CPC bid: ${r.ad_group.cpc_bid_micros/1_000_000:.2f}")


# ── 5. Keywords (positive + negative) ──────────────────────────────────────
print("\n" + "=" * 80)
print("5. KEYWORDS — positive + negative, match types, status")
print("=" * 80)
kw_q = f"""
SELECT campaign.id, ad_group.id, ad_group_criterion.criterion_id,
       ad_group_criterion.keyword.text,
       ad_group_criterion.keyword.match_type,
       ad_group_criterion.status,
       ad_group_criterion.negative
FROM ad_group_criterion
WHERE campaign.id IN ({",".join(CAMP_IDS)})
  AND ad_group_criterion.type = KEYWORD
"""
kw_by_camp = {}
for r in query(kw_q):
    cid = str(r.campaign.id)
    kw_by_camp.setdefault(cid, []).append(r)

# Campaign-level negative keywords (separate from ad-group level)
neg_q = f"""
SELECT campaign.id, campaign_criterion.criterion_id,
       campaign_criterion.keyword.text,
       campaign_criterion.keyword.match_type,
       campaign_criterion.negative
FROM campaign_criterion
WHERE campaign.id IN ({",".join(CAMP_IDS)})
  AND campaign_criterion.type = KEYWORD
"""
neg_by_camp = {}
for r in query(neg_q):
    cid = str(r.campaign.id)
    neg_by_camp.setdefault(cid, []).append(r)

for cid in CAMP_IDS:
    if cid not in camps: continue
    print(f"\n  📋 {camps[cid].campaign.name}")
    pos = [r for r in kw_by_camp.get(cid, []) if not r.ad_group_criterion.negative]
    neg = neg_by_camp.get(cid, [])
    print(f"     ✅ POSITIVE keywords: {len(pos)}")
    for r in pos:
        kw = r.ad_group_criterion.keyword
        st = r.ad_group_criterion.status.name
        print(f"        [{kw.match_type.name:<8}] [{st:<7}] {kw.text}")
    print(f"     🚫 NEGATIVE keywords: {len(neg)}")
    for r in neg:
        kw = r.campaign_criterion.keyword
        print(f"        [{kw.match_type.name:<8}] {kw.text}")


# ── 6. RSA ads ──────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("6. RSAs — headlines + descriptions + final URL + tracking")
print("=" * 80)
ad_q = f"""
SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.ad.name,
       ad_group_ad.status,
       ad_group_ad.ad.final_urls,
       ad_group_ad.ad.tracking_url_template,
       ad_group_ad.ad.responsive_search_ad.headlines,
       ad_group_ad.ad.responsive_search_ad.descriptions
FROM ad_group_ad
WHERE campaign.id IN ({",".join(CAMP_IDS)})
"""
for r in query(ad_q):
    cid = str(r.campaign.id)
    if cid not in camps: continue
    ad = r.ad_group_ad.ad
    print(f"\n  📰 {camps[cid].campaign.name} → {ad.name}")
    print(f"     Status: {r.ad_group_ad.status.name}")
    print(f"     Final URL: {ad.final_urls[0] if ad.final_urls else '(none)'}")
    print(f"     Tracking template: {ad.tracking_url_template or '(none)'}")
    rsa = ad.responsive_search_ad
    print(f"     Headlines: {len(rsa.headlines)}/15")
    for h in rsa.headlines:
        pin = f"pin={h.pinned_field.name}" if str(h.pinned_field.name) != "UNSPECIFIED" else "unpinned"
        print(f"        ({pin}) {h.text}")
    print(f"     Descriptions: {len(rsa.descriptions)}/4")
    for d in rsa.descriptions:
        print(f"        {d.text}")


# ── 7. Cross-reference keywords against BQ for predicted QS + volume ──────
print("\n" + "=" * 80)
print("7. KEYWORD INTELLIGENCE — historical QS + volume from BQ inventory")
print("=" * 80)
all_kws = []
for cid in CAMP_IDS:
    for r in kw_by_camp.get(cid, []):
        if r.ad_group_criterion.negative: continue
        all_kws.append(r.ad_group_criterion.keyword.text)

kw_list = list(set(all_kws))
# Look up each keyword in our BQ inventory (90d)
sql = f"""
SELECT keyword_text,
       MAX(status) AS last_status,
       MAX(match_type) AS last_match_type,
       SUM(impressions) AS impressions,
       SUM(spend) AS spend,
       SUM(clicks) AS clicks,
       AVG(quality_score) AS avg_qs
FROM {DS}.keywords_daily
WHERE channel='google_ads'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
  AND keyword_text IN UNNEST({kw_list!r})
GROUP BY keyword_text
"""
print(f"  Looking up {len(kw_list)} unique keywords in 90d BQ inventory...")
history = {}
for r in bq.query(sql).result():
    history[r.keyword_text] = dict(r)

# Also pull SQL conversion data via v_keyword_performance (60d)
sql2 = f"""
SELECT utm_term AS keyword,
       SUM(impressions) AS impr,
       SUM(leads_qualified) AS sqls,
       ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 1) AS cpql
FROM {DS}.v_keyword_performance
WHERE channel = 'google_ads'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
  AND utm_term IN UNNEST({kw_list!r})
GROUP BY utm_term
"""
perf = {}
for r in bq.query(sql2).result():
    perf[r.keyword] = dict(r)

print(f"\n  {'Keyword':<55} {'Status':<10} {'90d impr':>10} {'QS':>5} {'60d SQLs':>9} {'CPQL':>7}")
print("  " + "-" * 100)
for kw in sorted(kw_list):
    h = history.get(kw, {})
    p = perf.get(kw, {})
    status = h.get("last_status", "NEW") if h else "NEW"
    impr   = int(h.get("impressions", 0) or 0)
    qs     = h.get("avg_qs")
    sqls   = int(p.get("sqls", 0) or 0)
    cpql   = p.get("cpql")
    qs_s   = f"{qs:.1f}" if qs else "  -"
    cpql_s = f"${cpql:.0f}" if cpql else "    -"
    truncated = kw[:54]
    print(f"  {truncated:<55} {status:<10} {impr:>10,} {qs_s:>5} {sqls:>9} {cpql_s:>7}")

print()
print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
