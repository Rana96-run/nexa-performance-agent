"""Inspect what's already linked to each FinancialStatement campaign:
campaign-level negatives, audiences, call assets, promotion assets.
Use this to dedupe before adding."""
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

out = {}
for acct, cid, label in TARGETS:
    print(f"\n=== {label} ({acct}/{cid}) ===")
    info = {"negatives": [], "audiences": [], "call_assets": [],
            "promo_assets": [], "user_lists": []}

    # 1. Campaign-level negatives
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign_criterion.keyword.text,
               campaign_criterion.keyword.match_type
        FROM campaign_criterion
        WHERE campaign.id = {cid}
          AND campaign_criterion.type = 'KEYWORD'
          AND campaign_criterion.negative = TRUE
    """):
        info["negatives"].append({
            "text": r.campaign_criterion.keyword.text,
            "match": r.campaign_criterion.keyword.match_type.name,
        })
    print(f"  negatives: {len(info['negatives'])}")

    # 2. Audiences on the campaign (user_interest + user_list + custom_audience)
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign_criterion.type,
               campaign_criterion.user_list.user_list,
               campaign_criterion.user_interest.user_interest_category,
               campaign_criterion.negative
        FROM campaign_criterion
        WHERE campaign.id = {cid}
          AND campaign_criterion.type IN ('USER_LIST','USER_INTEREST','CUSTOM_AUDIENCE')
    """):
        kind = r.campaign_criterion.type.name
        rn = (r.campaign_criterion.user_list.user_list
              or r.campaign_criterion.user_interest.user_interest_category)
        info["audiences"].append({
            "kind": kind, "rn": rn,
            "negative": r.campaign_criterion.negative,
        })
    print(f"  audiences: {len(info['audiences'])}")

    # 3. Call + Promotion assets linked
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.id,
               campaign_asset.field_type, asset.id, asset.type,
               asset.call_asset.phone_number,
               asset.promotion_asset.promotion_target
        FROM campaign_asset
        WHERE campaign.id = {cid}
          AND campaign_asset.field_type IN ('CALL','PROMOTION')
    """):
        ft = r.campaign_asset.field_type.name
        if ft == "CALL":
            info["call_assets"].append({"phone": r.asset.call_asset.phone_number,
                                        "id": r.asset.id})
        elif ft == "PROMOTION":
            info["promo_assets"].append({
                "target": r.asset.promotion_asset.promotion_target,
                "id": r.asset.id,
            })
    print(f"  call_assets:  {len(info['call_assets'])}")
    print(f"  promo_assets: {len(info['promo_assets'])}")

    # 4. User lists on the account (resolve names for parity with Acc 1)
    TARGET_NAMES = [
        "HubSpot - All Customers",
        "HubSpot - Advanced/Premium/Pro Subscribers",
        "Active SaaS Users",
        "HubSpot - All Marketing Contacts",
        "All Converters",
        "Ad Video Viewers",
        "Channel Video Viewers",
        "e-invoice page",
    ]
    for r in ga.search(customer_id=acct, query="""
        SELECT user_list.resource_name, user_list.name,
               user_list.size_for_search
        FROM user_list
    """):
        if r.user_list.name in TARGET_NAMES:
            info["user_lists"].append({
                "name": r.user_list.name,
                "rn":   r.user_list.resource_name,
                "size": r.user_list.size_for_search,
            })
    print(f"  user_lists matching targets: {len(info['user_lists'])}")
    for ul in info["user_lists"]:
        print(f"    - {ul['name']:<46} size={ul['size']}")

    out[acct] = info

with open("scripts/_qawaem_bundle_state.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n✅ saved scripts/_qawaem_bundle_state.json")
