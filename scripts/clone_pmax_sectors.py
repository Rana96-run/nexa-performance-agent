"""
scripts/clone_pmax_sectors.py
==============================
Clone Services + Technology asset_groups from PMax_AR_Invoice_FiveSectors
into 2 new PMax campaigns, each with a proper hardcoded utm_content in
its tracking template (so spend joins to HubSpot leads in BQ).

Why this exists:
  PMax_AR_Invoice_FiveSectors uses `utm_content={_adname}` in its tracking
  template, with the actual value set per-asset-group as a URL custom
  parameter — which Google Ads API does NOT expose via GAQL. That breaks
  attribution. The fix is one PMax campaign per sector with the
  utm_content baked into the campaign-level template as a literal string.

What the script does:
  1. Finds the source FiveSectors campaign + its Services/Technology asset_groups
  2. Reads the asset references + audience signals from each source asset_group
  3. Creates 2 new PMax campaigns (PAUSED) with proper tracking templates
  4. Creates one asset_group per new campaign, linking the SAME assets
     (by resource_name — no re-upload, instant)
  5. Copies audience signals over
  6. Prints campaign IDs for review in Google Ads UI

Usage:
  python scripts/clone_pmax_sectors.py                 # DRY-RUN: shows plan
  python scripts/clone_pmax_sectors.py --execute       # actually creates

After running with --execute:
  - Review the 2 new campaigns in Google Ads UI (they will be PAUSED)
  - Pause the corresponding Services + Technology asset_groups in
    PMax_AR_Invoice_FiveSectors (so spend doesn't double up)
  - Enable the new campaigns
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from collectors.google_ads import get_client


# ── Configuration ─────────────────────────────────────────────────────────────
SOURCE_CAMPAIGN_NAME = "PMax_AR_Invoice_FiveSectors"
SOURCE_CUSTOMER_ID   = "5753494964"  # Acc2 — where FiveSectors lives

# Common base for the tracking template; only utm_content differs per sector
def _tracking_template(utm_content: str, customer_id: str) -> str:
    # Mirrors the structure used by PMax_AR_Generic and PMax_AR_Invoice.
    # utm_content is hardcoded literal so the Google Ads API surfaces it
    # when we query the campaign's tracking_url_template.
    return (
        f"{{lpurl}}?utm_content={utm_content}"
        f"&utm_audience={{_assetgroup}}"
        f"&utm_campaign={{_campaign}}"
        f"&utm_source=Google&utm_medium=ppc&utm_term={{keyword}}"
        f"&hsa_ad={{creative}}&hsa_grp={{adgroupid}}&hsa_kw={{keyword}}"
        f"&hsa_ver=3&hsa_net=adwords&hsa_acc={customer_id}"
        f"&hsa_src={{network}}&hsa_cam={{campaignid}}"
        f"&hsa_mt={{matchtype}}&hsa_tgt={{targetid}}"
    )


SECTORS = [
    {
        "source_asset_group_name": "Services",
        "new_campaign_name":       "PMax_AR_Invoice_Services",
        "utm_content":             "Google_Pmax_AR_Feature_Services_HubSpot",
        "final_url":               "https://campaigns.qoyod.com/ar/services-sector",
        "daily_budget_usd":        15.0,
    },
    {
        "source_asset_group_name": "Technology",
        "new_campaign_name":       "PMax_AR_Invoice_Technology",
        "utm_content":             "Google_Pmax_AR_Feature_Technology_HubSpot",
        "final_url":               "https://campaigns.qoyod.com/ar/technology-sector",
        "daily_budget_usd":        90.0,
    },
    {
        "source_asset_group_name": "Real Estate",
        "new_campaign_name":       "PMax_AR_Invoice_RealEstate",
        "utm_content":             "Google_Pmax_AR_Feature_RealEstate_HubSpot",
        "final_url":               "https://campaigns.qoyod.com/ar/real-estate-sector",
        "daily_budget_usd":        30.0,
    },
    {
        "source_asset_group_name": "Retail",
        "new_campaign_name":       "PMax_AR_Invoice_Retail",
        "utm_content":             "Google_Pmax_AR_Feature_Retail_HubSpot",
        "final_url":               "https://campaigns.qoyod.com/ar/retail-sector",
        "daily_budget_usd":        30.0,
    },
    {
        "source_asset_group_name": "Pmax_E-Invoice_WP",
        "new_campaign_name":       "PMax_AR_Invoice_WP",
        "utm_content":             "Google_Pmax_AR_Feature_WP_HubSpot",
        "final_url":               "https://qoyod.com/ar/",
        "daily_budget_usd":        30.0,
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _usd_to_micros(usd: float) -> int:
    return int(round(usd * 1_000_000))


def find_source_asset_group(ga, customer_id: str, sector_name: str):
    """Return (campaign_resource, asset_group_resource, asset_group_id) for
    the named asset_group within SOURCE_CAMPAIGN_NAME."""
    q = f"""
        SELECT
            campaign.id, campaign.name, campaign.resource_name,
            asset_group.id, asset_group.name, asset_group.resource_name
        FROM asset_group
        WHERE campaign.name = '{SOURCE_CAMPAIGN_NAME}'
          AND asset_group.name = '{sector_name}'
    """
    for r in ga.search(customer_id=customer_id, query=q):
        return (r.campaign.resource_name,
                r.asset_group.resource_name,
                r.asset_group.id)
    return (None, None, None)


def get_asset_links(ga, customer_id: str, asset_group_resource: str):
    """Return list of (asset_resource_name, field_type_enum) tied to an asset_group."""
    # asset_group_asset.field_type tells us how to link the asset in the new group
    # (HEADLINE, DESCRIPTION, LONG_HEADLINE, MARKETING_IMAGE, SQUARE_MARKETING_IMAGE,
    #  LOGO, LANDSCAPE_LOGO, BUSINESS_NAME, YOUTUBE_VIDEO, etc.)
    q = f"""
        SELECT
            asset_group_asset.asset,
            asset_group_asset.field_type,
            asset_group_asset.status
        FROM asset_group_asset
        WHERE asset_group_asset.asset_group = '{asset_group_resource}'
          AND asset_group_asset.status != 'REMOVED'
    """
    out = []
    for r in ga.search(customer_id=customer_id, query=q):
        out.append((r.asset_group_asset.asset,
                    r.asset_group_asset.field_type))
    return out


def get_audience_signals(ga, customer_id: str, asset_group_resource: str):
    """Return (audiences, search_themes) for the source asset_group.

    Note: GAQL doesn't allow asset_group_signal.audience in SELECT clauses,
    so we can only pull search_themes via API. Audience signals must be
    re-added manually in Google Ads UI after the new campaigns are created.
    """
    audiences = []  # always empty — see note above
    search_themes = []
    q = f"""
        SELECT asset_group_signal.search_theme.text
        FROM asset_group_signal
        WHERE asset_group_signal.asset_group = '{asset_group_resource}'
    """
    try:
        for r in ga.search(customer_id=customer_id, query=q):
            t = r.asset_group_signal.search_theme.text
            if t:
                search_themes.append(t)
    except Exception as e:
        print(f"  [warn] search_themes fetch failed: {e}")
    return audiences, search_themes


# ── Mutations ─────────────────────────────────────────────────────────────────

def create_budget(client, customer_id: str, name: str, daily_usd: float) -> str:
    import time
    bsvc = client.get_service("CampaignBudgetService")
    op   = client.get_type("CampaignBudgetOperation")
    bgt  = op.create
    # Timestamp suffix avoids DUPLICATE_NAME errors on retry / re-run
    bgt.name              = f"{name}_budget_{int(time.time())}"
    bgt.amount_micros     = _usd_to_micros(daily_usd)
    bgt.delivery_method   = client.enums.BudgetDeliveryMethodEnum.STANDARD
    bgt.explicitly_shared = False  # PMax + non-experiment campaigns need this
    r = bsvc.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
    return r.results[0].resource_name


def create_pmax_campaign(client, customer_id: str, name: str,
                         budget_resource: str, tracking_template: str) -> str:
    csvc = client.get_service("CampaignService")
    op   = client.get_type("CampaignOperation")
    c    = op.create
    c.name                       = name
    c.status                     = client.enums.CampaignStatusEnum.PAUSED
    c.advertising_channel_type   = client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    c.campaign_budget            = budget_resource
    c.tracking_url_template      = tracking_template
    # Bidding strategy — proto-plus assignment (avoids CopyFrom incompatibility).
    # PMax allows only MAXIMIZE_CONVERSIONS or MAXIMIZE_CONVERSION_VALUE.
    c.maximize_conversions = client.get_type("MaximizeConversions")
    # Required since 2024: EU political advertising disclosure
    c.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    # Disable Brand Guidelines so we don't need to attach business_name +
    # logo as CampaignAssets up-front. Assets at asset_group level still work.
    try:
        c.brand_guidelines_enabled = False
    except (AttributeError, Exception):
        # Field name may differ in some API versions; ignore gracefully
        pass
    # PMax requires url_expansion_opt_out=False to use Google's URL expansion;
    # leave default unless we know better.
    r = csvc.mutate_campaigns(customer_id=customer_id, operations=[op])
    return r.results[0].resource_name


def create_asset_group(client, customer_id: str, campaign_resource: str,
                       name: str, final_url: str) -> str:
    svc = client.get_service("AssetGroupService")
    op  = client.get_type("AssetGroupOperation")
    ag  = op.create
    ag.name           = name
    ag.campaign       = campaign_resource
    ag.final_urls.append(final_url)
    ag.status         = client.enums.AssetGroupStatusEnum.PAUSED
    r = svc.mutate_asset_groups(customer_id=customer_id, operations=[op])
    return r.results[0].resource_name


def link_assets_to_group(client, customer_id: str, asset_group_resource: str,
                         asset_links: list) -> int:
    """Link existing assets (by resource_name) to the new asset_group with
    the same field_type they had in the source asset_group."""
    if not asset_links:
        return 0
    svc = client.get_service("AssetGroupAssetService")
    ops = []
    for asset_rn, field_type in asset_links:
        op = client.get_type("AssetGroupAssetOperation")
        a  = op.create
        a.asset_group = asset_group_resource
        a.asset       = asset_rn
        a.field_type  = field_type
        ops.append(op)
    try:
        r = svc.mutate_asset_group_assets(customer_id=customer_id, operations=ops)
        return len(r.results)
    except Exception as e:
        print(f"    [warn] asset linking partial failure: {e}")
        return 0


def link_search_themes(client, customer_id: str, asset_group_resource: str,
                       themes: list) -> int:
    """Add search themes as asset_group_signals."""
    if not themes:
        return 0
    svc = client.get_service("AssetGroupSignalService")
    ops = []
    for theme in themes:
        op = client.get_type("AssetGroupSignalOperation")
        s  = op.create
        s.asset_group = asset_group_resource
        s.search_theme.text = theme
        ops.append(op)
    try:
        r = svc.mutate_asset_group_signals(customer_id=customer_id, operations=ops)
        return len(r.results)
    except Exception as e:
        print(f"    [warn] search themes partial failure: {e}")
        return 0


def link_audience_signals(client, customer_id: str, asset_group_resource: str,
                          audiences: list) -> int:
    """Attach audience signals (audience resource_names) to the new asset_group."""
    if not audiences:
        return 0
    svc = client.get_service("AssetGroupSignalService")
    ops = []
    for audience_rn in audiences:
        op = client.get_type("AssetGroupSignalOperation")
        s  = op.create
        s.asset_group = asset_group_resource
        s.audience    = audience_rn
        ops.append(op)
    try:
        r = svc.mutate_asset_group_signals(customer_id=customer_id, operations=ops)
        return len(r.results)
    except Exception as e:
        print(f"    [warn] audience signals partial failure: {e}")
        return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main(execute: bool):
    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"=== Clone PMax sectors ({mode}) ===")
    print(f"Source: {SOURCE_CAMPAIGN_NAME}  (customer {SOURCE_CUSTOMER_ID})\n")

    client = get_client()
    ga     = client.get_service("GoogleAdsService")

    plans = []
    for sec in SECTORS:
        print(f"--- Sector: {sec['source_asset_group_name']} ---")
        camp_rn, ag_rn, ag_id = find_source_asset_group(
            ga, SOURCE_CUSTOMER_ID, sec["source_asset_group_name"],
        )
        if not ag_rn:
            print(f"  ERROR: source asset_group not found, skipping")
            continue
        asset_links            = get_asset_links(ga, SOURCE_CUSTOMER_ID, ag_rn)
        audiences, search_themes = get_audience_signals(ga, SOURCE_CUSTOMER_ID, ag_rn)
        print(f"  Found source asset_group_id={ag_id}")
        print(f"    assets to clone:     {len(asset_links)}")
        print(f"    audience signals:    {len(audiences)}")
        print(f"    search themes:       {len(search_themes)}")
        print(f"    new campaign:        {sec['new_campaign_name']}")
        print(f"    daily budget:        ${sec['daily_budget_usd']}")
        print(f"    final_url:           {sec['final_url']}")
        print(f"    utm_content:         {sec['utm_content']}")
        plans.append({
            "sec":           sec,
            "asset_links":   asset_links,
            "audiences":     audiences,
            "search_themes": search_themes,
        })
        print()

    if not execute:
        print("DRY-RUN complete. Pass --execute to actually create.")
        return

    print("=== EXECUTING (campaign + budget only — asset_groups in UI) ===")
    print("Note: PMax asset_groups can't be created atomically with assets via")
    print("normal API calls (requires atomic mutate). Easier to copy in UI:")
    print("  Google Ads → new campaign → Asset groups → '+ Add' → copy from")
    print("  PMax_AR_Invoice_FiveSectors → pick Services / Technology.\n")
    # Idempotency: check which campaigns already exist
    existing_names = set()
    q = "SELECT campaign.id, campaign.name FROM campaign"
    for r in ga.search(customer_id=SOURCE_CUSTOMER_ID, query=q):
        existing_names.add(r.campaign.name)
    created = []
    for p in plans:
        sec = p["sec"]
        if sec["new_campaign_name"] in existing_names:
            print(f"\nSKIP {sec['new_campaign_name']} — already exists.")
            continue
        print(f"\nCreating {sec['new_campaign_name']}...")
        try:
            budget_rn = create_budget(
                client, SOURCE_CUSTOMER_ID, sec["new_campaign_name"],
                sec["daily_budget_usd"],
            )
            print(f"  budget: {budget_rn}")
            tracking = _tracking_template(sec["utm_content"], SOURCE_CUSTOMER_ID)
            camp_rn = create_pmax_campaign(
                client, SOURCE_CUSTOMER_ID, sec["new_campaign_name"],
                budget_rn, tracking,
            )
            print(f"  campaign: {camp_rn}")
            camp_id = camp_rn.split('/')[-1]
            created.append({"sec": sec["new_campaign_name"],
                            "campaign_id": camp_id,
                            "source_ag": sec["source_asset_group_name"]})
            print(f"  Review: https://ads.google.com/aw/overview?ocid=&campaignId={camp_id}")
        except Exception as e:
            print(f"  FAIL for {sec['new_campaign_name']}: {e}")
            continue

    print("\n=== CAMPAIGNS CREATED (PAUSED) ===")
    for c in created:
        print(f"  • {c['sec']} (id={c['campaign_id']})")
    print("\nNext steps (manual, ~3 min each in Google Ads UI):")
    for c in created:
        print(f"  {c['sec']}:")
        print(f"    1. Open campaign in Ads UI")
        print(f"    2. Asset groups → '+ Add' → 'Copy from existing'")
        print(f"    3. Pick '{c['source_ag']}' from PMax_AR_Invoice_FiveSectors")
        print(f"    4. Update the asset_group's final_url to its new sector URL")
        print(f"    5. Re-attach audience signals (search 'HubSpot - Sales Qualified Lead' etc.)")
    print("\n  Then:")
    print("  • In PMax_AR_Invoice_FiveSectors, PAUSE the Services + Technology asset_groups")
    print("  • Enable the new campaigns")


if __name__ == "__main__":
    main(execute="--execute" in sys.argv)
