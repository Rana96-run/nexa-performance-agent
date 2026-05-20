"""Verify the Qawaem campaign was fully created on Microsoft Ads."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.microsoft_ads import get_service, ACCOUNT_ID

CAMP_ID = 487816800

svc = get_service("CampaignManagementService")

# Campaign
print("=" * 70)
print("CAMPAIGN")
print("=" * 70)
campaigns = svc.GetCampaignsByIds(
    AccountId=ACCOUNT_ID,
    CampaignIds={"long": [CAMP_ID]},
    CampaignType="Search",
)
for camp in campaigns.Campaigns.Campaign:
    print(f"  id     : {camp.Id}")
    print(f"  name   : {camp.Name}")
    print(f"  status : {camp.Status}")
    print(f"  budget : ${camp.DailyBudget}/d  ({camp.BudgetType})")
    print(f"  tz     : {camp.TimeZone}")

# Ad Groups
print("\n" + "=" * 70)
print("AD GROUPS")
print("=" * 70)
ags = svc.GetAdGroupsByCampaignId(CampaignId=CAMP_ID)
ag_ids = []
for ag in ags.AdGroup:
    print(f"  id={ag.Id}  name={ag.Name}  status={ag.Status}")
    ag_ids.append(ag.Id)

# Keywords + ads per ad group
for ag_id in ag_ids:
    print(f"\n--- Ad group {ag_id} content ---")
    kws_resp = svc.GetKeywordsByAdGroupId(AdGroupId=ag_id)
    kws = kws_resp.Keyword if hasattr(kws_resp, "Keyword") else []
    print(f"  {len(kws)} keywords:")
    for k in kws[:5]:
        print(f"    [{k.MatchType:<6}] {k.Text}")
    if len(kws) > 5: print(f"    ... +{len(kws)-5} more")
    ads_resp = svc.GetAdsByAdGroupId(AdGroupId=ag_id, AdTypes={"AdType": ["ResponsiveSearch"]})
    ads = ads_resp.Ad if hasattr(ads_resp, "Ad") else []
    print(f"  {len(ads)} ads:")
    for ad in ads:
        print(f"    [{ad.Status}] type={ad.Type} id={ad.Id}")

# Campaign negatives
print("\n" + "=" * 70)
print("CAMPAIGN NEGATIVES")
print("=" * 70)
try:
    negs = svc.GetNegativeKeywordsByEntityIds(
        EntityIds={"long": [CAMP_ID]},
        EntityType="Campaign",
        ParentEntityId=ACCOUNT_ID,
    )
    if hasattr(negs, "EntityNegativeKeyword") and negs.EntityNegativeKeyword:
        for ent in negs.EntityNegativeKeyword:
            if hasattr(ent.NegativeKeywords, "NegativeKeyword"):
                nks = ent.NegativeKeywords.NegativeKeyword
                print(f"  {len(nks)} negatives at campaign-level")
                for nk in nks[:5]:
                    print(f"    [{nk.MatchType:<6}] {nk.Text}")
                if len(nks) > 5:
                    print(f"    ... +{len(nks)-5} more")
except Exception as e:
    print(f"  ⚠ negatives query failed: {str(e)[:200]}")
