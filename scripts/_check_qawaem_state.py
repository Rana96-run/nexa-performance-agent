"""Check current state of Google_Search_AR_FinancialStatemnt — ad groups,
keywords, RSAs."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23861837000"
c = get_client(); ga = c.get_service("GoogleAdsService")

print("=== AD GROUPS ===")
q1 = f"SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.id = {CAMP_ID}"
for r in ga.search(customer_id=ACCOUNT, query=q1):
    print(f"  ag={r.ad_group.id}  {r.ad_group.name}  [{r.ad_group.status.name}]")

print("\n=== KEYWORDS PER AD GROUP ===")
q2 = f"""
SELECT ad_group.name, ad_group_criterion.keyword.text,
       ad_group_criterion.keyword.match_type, ad_group_criterion.status,
       ad_group_criterion.negative
FROM ad_group_criterion
WHERE campaign.id = {CAMP_ID} AND ad_group_criterion.type = 'KEYWORD'
  AND ad_group_criterion.status != 'REMOVED'
ORDER BY ad_group.name
"""
by_ag = {}
for r in ga.search(customer_id=ACCOUNT, query=q2):
    n = r.ad_group.name
    by_ag.setdefault(n, []).append({
        "text": r.ad_group_criterion.keyword.text,
        "mt":   r.ad_group_criterion.keyword.match_type.name,
        "neg":  r.ad_group_criterion.negative,
    })
for ag, kws in by_ag.items():
    pos = [k for k in kws if not k["neg"]]
    print(f"  {ag}: {len(pos)} positive keywords")

print("\n=== RSAs ===")
q3 = f"""
SELECT ad_group.name, ad_group_ad.status,
       ad_group_ad.ad.responsive_search_ad.headlines,
       ad_group_ad.ad.final_urls
FROM ad_group_ad
WHERE campaign.id = {CAMP_ID} AND ad_group_ad.status != 'REMOVED'
"""
for r in ga.search(customer_id=ACCOUNT, query=q3):
    n_h = len(r.ad_group_ad.ad.responsive_search_ad.headlines)
    urls = list(r.ad_group_ad.ad.final_urls)
    print(f"  {r.ad_group.name}  [{r.ad_group_ad.status.name}]  hl={n_h}  url={urls[0] if urls else '(none)'}")
