"""Read live config for the 2 campaigns we'll copy to Acc 2 (5753494964):
  - Google_Search_AREN_FinancialStatement  (id 23861837000) on Acc 1 (1513020554)
  - Google_Search_AREN_ZATCAPhase2        (id 23851270716) on Acc 1

Pulls: budget, bidding strategy, geo targets, language targets, network settings,
ad groups (+ CPC), keywords (+ match type, status), RSAs (headlines, descriptions,
path1/path2, final urls), negative campaign-level keywords.

Writes JSON to scripts/_copy_plan.json so the copy script can replay it.
"""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

SRC = "1513020554"
CAMPS = {
    "23861837000": "Google_Search_AREN_FinancialStatement",
    "23851270716": "Google_Search_AREN_ZATCAPhase2",
}

client = get_client()
ga = client.get_service("GoogleAdsService")


def q(sql: str):
    return list(ga.search(customer_id=SRC, query=sql))


plan: dict = {}
for camp_id, name in CAMPS.items():
    print(f"\n=== {name} ({camp_id}) ===")
    cdata: dict = {"name": name, "id": camp_id}

    # Campaign + budget + bidding
    rows = q(f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.advertising_channel_type,
               campaign.bidding_strategy_type,
               campaign.maximize_conversions.target_cpa_micros,
               campaign.target_spend.cpc_bid_ceiling_micros,
               campaign.network_settings.target_google_search,
               campaign.network_settings.target_search_network,
               campaign.network_settings.target_content_network,
               campaign.network_settings.target_partner_search_network,
               campaign_budget.amount_micros,
               campaign_budget.delivery_method,
               campaign.tracking_url_template,
               campaign.final_url_suffix
        FROM campaign
        WHERE campaign.id = {camp_id}
    """)
    r = rows[0]
    cdata["bidding_strategy_type"] = r.campaign.bidding_strategy_type.name
    cdata["max_conv_tcpa_micros"]  = r.campaign.maximize_conversions.target_cpa_micros
    cdata["target_spend_ceiling_micros"] = r.campaign.target_spend.cpc_bid_ceiling_micros
    cdata["budget_micros"]   = r.campaign_budget.amount_micros
    cdata["network"] = {
        "google_search":   r.campaign.network_settings.target_google_search,
        "search_partners": r.campaign.network_settings.target_search_network,
        "content":         r.campaign.network_settings.target_content_network,
        "partner_search":  r.campaign.network_settings.target_partner_search_network,
    }
    cdata["tracking_url_template"] = r.campaign.tracking_url_template or ""
    cdata["final_url_suffix"]      = r.campaign.final_url_suffix or ""
    print(f"  bidding={cdata['bidding_strategy_type']} budget=${cdata['budget_micros']/1e6:.0f}")

    # Geo
    cdata["geos"] = [
        row.campaign_criterion.location.geo_target_constant
        for row in q(f"""
            SELECT campaign_criterion.location.geo_target_constant,
                   campaign_criterion.negative
            FROM campaign_criterion
            WHERE campaign.id = {camp_id}
              AND campaign_criterion.type = 'LOCATION'
              AND campaign_criterion.negative = FALSE
        """)
    ]
    # Languages
    cdata["langs"] = [
        row.campaign_criterion.language.language_constant
        for row in q(f"""
            SELECT campaign_criterion.language.language_constant
            FROM campaign_criterion
            WHERE campaign.id = {camp_id}
              AND campaign_criterion.type = 'LANGUAGE'
        """)
    ]
    print(f"  geos={cdata['geos']}  langs={cdata['langs']}")

    # Campaign-level negative keywords
    cdata["neg_keywords"] = [
        {"text": row.campaign_criterion.keyword.text,
         "match": row.campaign_criterion.keyword.match_type.name}
        for row in q(f"""
            SELECT campaign_criterion.keyword.text,
                   campaign_criterion.keyword.match_type
            FROM campaign_criterion
            WHERE campaign.id = {camp_id}
              AND campaign_criterion.type = 'KEYWORD'
              AND campaign_criterion.negative = TRUE
        """)
    ]
    print(f"  campaign neg kw: {len(cdata['neg_keywords'])}")

    # Ad groups
    ag_rows = q(f"""
        SELECT ad_group.id, ad_group.name, ad_group.status,
               ad_group.cpc_bid_micros
        FROM ad_group
        WHERE campaign.id = {camp_id} AND ad_group.status != 'REMOVED'
    """)
    cdata["adgroups"] = []
    for ag in ag_rows:
        ag_id = ag.ad_group.id
        ag_obj = {
            "id": ag_id,
            "name": ag.ad_group.name,
            "cpc_bid_micros": ag.ad_group.cpc_bid_micros,
            "keywords": [],
            "neg_keywords": [],
            "rsas": [],
        }
        # Keywords (positive + adgroup-level negative)
        for row in q(f"""
            SELECT ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type,
                   ad_group_criterion.negative,
                   ad_group_criterion.status
            FROM ad_group_criterion
            WHERE ad_group.id = {ag_id}
              AND ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.status != 'REMOVED'
        """):
            entry = {
                "text": row.ad_group_criterion.keyword.text,
                "match": row.ad_group_criterion.keyword.match_type.name,
                "status": row.ad_group_criterion.status.name,
            }
            if row.ad_group_criterion.negative:
                ag_obj["neg_keywords"].append(entry)
            else:
                ag_obj["keywords"].append(entry)

        # RSAs
        for row in q(f"""
            SELECT ad_group_ad.ad.id, ad_group_ad.ad.type,
                   ad_group_ad.status,
                   ad_group_ad.ad.responsive_search_ad.headlines,
                   ad_group_ad.ad.responsive_search_ad.descriptions,
                   ad_group_ad.ad.responsive_search_ad.path1,
                   ad_group_ad.ad.responsive_search_ad.path2,
                   ad_group_ad.ad.final_urls
            FROM ad_group_ad
            WHERE ad_group.id = {ag_id}
              AND ad_group_ad.status != 'REMOVED'
              AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
        """):
            rsa = row.ad_group_ad.ad.responsive_search_ad
            ag_obj["rsas"].append({
                "headlines": [{"text": h.text, "pinned": h.pinned_field.name if h.pinned_field else None}
                              for h in rsa.headlines],
                "descriptions": [{"text": d.text, "pinned": d.pinned_field.name if d.pinned_field else None}
                                 for d in rsa.descriptions],
                "path1": rsa.path1,
                "path2": rsa.path2,
                "final_urls": list(row.ad_group_ad.ad.final_urls),
                "status": row.ad_group_ad.status.name,
            })

        cdata["adgroups"].append(ag_obj)
        print(f"  AG {ag.ad_group.name}: kw={len(ag_obj['keywords'])} "
              f"neg={len(ag_obj['neg_keywords'])} rsa={len(ag_obj['rsas'])} "
              f"cpc=${ag.ad_group.cpc_bid_micros/1e6:.2f}")

    plan[camp_id] = cdata

with open("scripts/_copy_plan.json", "w", encoding="utf-8") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)
print(f"\n✅ Written plan to scripts/_copy_plan.json")
