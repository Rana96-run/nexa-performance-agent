"""Verify the AR/EN ad-group split across all 3 ZATCA campaigns."""
import sys, re
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

c = get_client(); ga = c.get_service("GoogleAdsService")

def is_ar(t): return bool(re.search(r"[؀-ۿ]", t))

q = f"""
SELECT campaign.name, ad_group.id, ad_group.name, ad_group.status,
       ad_group_criterion.keyword.text,
       ad_group_criterion.status,
       ad_group_criterion.negative
FROM ad_group_criterion
WHERE campaign.id IN ({",".join(CAMPS)})
  AND ad_group_criterion.type = 'KEYWORD'
  AND ad_group_criterion.status != 'REMOVED'
"""
by_camp = {}
for r in ga.search(customer_id=ACCOUNT, query=q):
    cn = r.campaign.name
    by_camp.setdefault(cn, {}).setdefault(r.ad_group.name, []).append({
        "text": r.ad_group_criterion.keyword.text,
        "status": r.ad_group_criterion.status.name,
        "neg": r.ad_group_criterion.negative,
    })

for cn in sorted(by_camp):
    print(f"\n{cn}")
    for ag, kws in by_camp[cn].items():
        enabled = [k for k in kws if not k["neg"] and k["status"] == "ENABLED"]
        paused  = [k for k in kws if not k["neg"] and k["status"] == "PAUSED"]
        ar = sum(1 for k in enabled if is_ar(k["text"]))
        en = sum(1 for k in enabled if not is_ar(k["text"]))
        print(f"  {ag}")
        print(f"    enabled : {len(enabled)}  (AR={ar}  EN={en})")
        if paused:
            print(f"    paused  : {len(paused)}")

# RSAs
print("\n--- RSAs ---")
q2 = f"""
SELECT campaign.name, ad_group.name, ad_group_ad.status,
       ad_group_ad.ad.responsive_search_ad.headlines
FROM ad_group_ad
WHERE campaign.id IN ({",".join(CAMPS)})
  AND ad_group_ad.status != 'REMOVED'
"""
for r in ga.search(customer_id=ACCOUNT, query=q2):
    n_head = len(r.ad_group_ad.ad.responsive_search_ad.headlines)
    print(f"  {r.campaign.name} / {r.ad_group.name}  [{r.ad_group_ad.status.name}]  {n_head} headlines")
