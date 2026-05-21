"""Inspect existing AR keywords on both accounts' FinancialSt_AR ad groups
to pick the 2 weakest to remove (Path A)."""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "23861837000", "Acc 1"),
    ("5753494964", "23870151040", "Acc 2"),
]

client = get_client()
ga = client.get_service("GoogleAdsService")

state = {}
for acct, cid, label in TARGETS:
    print(f"\n=== {label} — AR ad group existing keywords ===")
    ag_id = None
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.id, ad_group.name FROM ad_group
        WHERE campaign.id = {cid} AND ad_group.name LIKE '%AR%'
    """):
        ag_id = r.ad_group.id
        print(f"  ad group: {r.ad_group.name} ({ag_id})")

    # Pull current AR keywords + lifetime metrics + first-page bid
    rows = list(ga.search(customer_id=acct, query=f"""
        SELECT ad_group_criterion.criterion_id,
               ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.status,
               metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM keyword_view
        WHERE ad_group.id = {ag_id}
          AND ad_group_criterion.status != 'REMOVED'
          AND ad_group_criterion.negative = FALSE
          AND segments.date DURING LAST_30_DAYS
    """))
    # Group by criterion_id (date segments)
    kws = {}
    for r in rows:
        k = r.ad_group_criterion.criterion_id
        if k not in kws:
            kws[k] = {
                "id": k,
                "text": r.ad_group_criterion.keyword.text,
                "match": r.ad_group_criterion.keyword.match_type.name,
                "status": r.ad_group_criterion.status.name,
                "imp": 0, "clk": 0, "cost": 0.0,
            }
        kws[k]["imp"]  += r.metrics.impressions
        kws[k]["clk"]  += r.metrics.clicks
        kws[k]["cost"] += r.metrics.cost_micros / 1e6
    # If no metric rows, still list keyword
    if not kws:
        for r in ga.search(customer_id=acct, query=f"""
            SELECT ad_group_criterion.criterion_id,
                   ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type,
                   ad_group_criterion.status
            FROM ad_group_criterion
            WHERE ad_group.id = {ag_id}
              AND ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.status != 'REMOVED'
              AND ad_group_criterion.negative = FALSE
        """):
            kws[r.ad_group_criterion.criterion_id] = {
                "id": r.ad_group_criterion.criterion_id,
                "text": r.ad_group_criterion.keyword.text,
                "match": r.ad_group_criterion.keyword.match_type.name,
                "status": r.ad_group_criterion.status.name,
                "imp": 0, "clk": 0, "cost": 0.0,
            }
    print(f"  total keywords: {len(kws)}")
    sorted_kws = sorted(kws.values(), key=lambda x: (x["imp"], x["clk"]))
    for k in sorted_kws:
        flag = "  ← drop candidate" if k["imp"] == 0 and k["clk"] == 0 else ""
        print(f"    [{k['match']:<6}] {k['text'][:42]:<42} imp={k['imp']:>3} clk={k['clk']:>2} cost=${k['cost']:.2f}{flag}")
    state[acct] = {"ag_id": ag_id, "kws": sorted_kws}

with open("scripts/_qawaem_pathA_state.json", "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print(f"\n✅ saved to scripts/_qawaem_pathA_state.json")
