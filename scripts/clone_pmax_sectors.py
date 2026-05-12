"""
scripts/clone_pmax_sectors.py
==============================
Clone sector asset_groups from PMax_AR_Invoice_FiveSectors into individual
PMax campaigns, each with a hardcoded utm_content in its tracking template
(so spend joins to HubSpot leads in BQ).

Why this exists:
  PMax_AR_Invoice_FiveSectors uses `utm_content={_adname}` in its tracking
  template, with the actual value set per-asset-group as a URL custom
  parameter — which Google Ads API does NOT expose via GAQL. That breaks
  attribution. The fix is one PMax campaign per sector with the
  utm_content baked into the campaign-level template as a literal string.

What the script does:
  1. Finds the source FiveSectors campaign + its named asset_groups
  2. Reads the asset references + audience signals from each source asset_group
  3. Creates new PMax campaigns (PAUSED) with proper tracking templates
     — skips any campaign that already exists
  4. Creates one asset_group per new campaign, linking the SAME assets
     (by resource_name — no re-upload, instant)
     — skips any asset_group that already has assets linked
  5. Copies search themes over (audience signals require manual re-add via UI)
  6. Prints campaign IDs for review in Google Ads UI

Usage:
  python scripts/clone_pmax_sectors.py                 # DRY-RUN: shows plan
  python scripts/clone_pmax_sectors.py --execute       # actually creates

After running with --execute:
  - Review the new campaigns in Google Ads UI (they will be PAUSED)
  - Pause the corresponding asset_groups in PMax_AR_Invoice_FiveSectors
    (so spend doesn't double up)
  - Re-attach audience signals in UI (API can't read source audience signals)
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
    """Return list of (asset_resource_name, field_type_enum) tied to an asset_group.

    Per-type caps are enforced here to avoid RESOURCE_LIMIT errors:
      LONG_HEADLINE (17): max 5 per asset group
      HEADLINE (2): max 15
      DESCRIPTION (3): max 5
    """
    _LIMITS = {17: 5, 2: 15, 3: 5, 7: 5, 21: 5, 22: 5}  # field_type → max count
    q = f"""
        SELECT
            asset_group_asset.asset,
            asset_group_asset.field_type,
            asset_group_asset.status
        FROM asset_group_asset
        WHERE asset_group_asset.asset_group = '{asset_group_resource}'
          AND asset_group_asset.status != 'REMOVED'
    """
    from collections import Counter
    counts: Counter = Counter()
    out = []
    for r in ga.search(customer_id=customer_id, query=q):
        ft = r.asset_group_asset.field_type
        limit = _LIMITS.get(ft, 9999)
        if counts[ft] >= limit:
            print(f"    [cap] skipping extra {ft} asset (limit={limit})")
            continue
        counts[ft] += 1
        out.append((r.asset_group_asset.asset, ft))
    return out


def get_campaign_level_assets(ga, customer_id: str, campaign_name: str):
    """Return campaign-level LOGO (21), LANDSCAPE_LOGO (22), BUSINESS_NAME (18)
    assets from the source campaign — these don't appear in asset_group_asset
    queries but are required for a valid asset group.

    Logos are dimension-validated: asset_group level requires min 128x128 for
    square LOGO and min 512x128 for LANDSCAPE_LOGO. Campaign-level logos can
    include small favicons (32x32) that fail asset_group validation.
    """
    _WANT = {18, 21, 22}   # BUSINESS_NAME, LOGO, LANDSCAPE_LOGO
    q = f"""
        SELECT campaign.name, campaign_asset.field_type, campaign_asset.asset
        FROM campaign_asset
        WHERE campaign.name = '{campaign_name}'
          AND campaign_asset.status != 'REMOVED'
    """
    logo_rns: list[str] = []
    text_assets: list[tuple] = []
    for r in ga.search(customer_id=customer_id, query=q):
        ft = r.campaign_asset.field_type
        if ft not in _WANT:
            continue
        if ft == 18:  # BUSINESS_NAME — not an image, include directly
            text_assets.append((r.campaign_asset.asset, ft))
        else:
            logo_rns.append((r.campaign_asset.asset, ft))

    if not logo_rns:
        return text_assets

    # Fetch dimensions for image assets to filter out undersized logos
    rn_list = ", ".join(f"'{rn}'" for rn, _ in logo_rns)
    dim_q = f"""
        SELECT
            asset.resource_name,
            asset.image_asset.full_size.width_pixels,
            asset.image_asset.full_size.height_pixels
        FROM asset
        WHERE asset.resource_name IN ({rn_list})
    """
    dims: dict[str, tuple[int, int]] = {}
    for r in ga.search(customer_id=customer_id, query=dim_q):
        a = r.asset
        dims[a.resource_name] = (
            a.image_asset.full_size.width_pixels,
            a.image_asset.full_size.height_pixels,
        )

    # Asset_group minimums: LOGO ≥ 128×128 (1:1), LANDSCAPE_LOGO ≥ 512×128 (4:1)
    _MIN = {
        21: (128, 128),   # LOGO
        22: (512, 128),   # LANDSCAPE_LOGO
    }
    out = list(text_assets)
    for rn, ft in logo_rns:
        w, h = dims.get(rn, (0, 0))
        min_w, min_h = _MIN.get(ft, (1, 1))
        if w >= min_w and h >= min_h:
            out.append((rn, ft))
        else:
            print(f"    [skip] logo {rn} {w}x{h} below min {min_w}x{min_h} "
                  f"for field_type={ft}")
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


def create_asset_group_with_assets(client, customer_id: str,
                                   campaign_resource: str,
                                   name: str, final_url: str,
                                   asset_links: list) -> str:
    """Create an asset_group AND link assets in ONE atomic batch mutate.

    Google Ads API rejects empty asset_groups — minimum headline, long_headline,
    description, image, square_image, business_name, and logo must all be present
    at creation time.  The only way to satisfy this is to include the
    AssetGroupAsset operations in the SAME GoogleAdsService.mutate() call,
    using a temp resource_name (-1) so the ops can reference each other.

    Returns the real asset_group resource_name after the batch succeeds.
    """
    ga_svc      = client.get_service("GoogleAdsService")
    temp_ag_rn  = f"customers/{customer_id}/assetGroups/-1"

    mutate_ops = []

    # ── 1. Asset group create op ───────────────────────────────────────────
    ag_mop = client.get_type("MutateOperation")
    ag     = ag_mop.asset_group_operation.create
    ag.resource_name = temp_ag_rn
    ag.name          = name
    ag.campaign      = campaign_resource
    ag.final_urls.append(final_url)
    ag.status        = client.enums.AssetGroupStatusEnum.PAUSED
    mutate_ops.append(ag_mop)

    # ── 2. Asset link ops (same temp_ag_rn) ───────────────────────────────
    for asset_rn, field_type in asset_links:
        aga_mop = client.get_type("MutateOperation")
        aga     = aga_mop.asset_group_asset_operation.create
        aga.asset_group = temp_ag_rn
        aga.asset       = asset_rn
        aga.field_type  = field_type
        mutate_ops.append(aga_mop)

    response = ga_svc.mutate(customer_id=customer_id, mutate_operations=mutate_ops)

    # First result is the asset_group; the rest are asset_group_asset links
    real_ag_rn = response.mutate_operation_responses[0].asset_group_result.resource_name
    return real_ag_rn, len(mutate_ops) - 1  # (ag_resource, n_assets_linked)


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

    # Campaign-level LOGO + BUSINESS_NAME from source (shared across all sectors)
    campaign_level_assets = get_campaign_level_assets(
        ga, SOURCE_CUSTOMER_ID, SOURCE_CAMPAIGN_NAME,
    )
    print(f"Campaign-level assets (LOGO/BUSINESS_NAME/LANDSCAPE_LOGO): "
          f"{len(campaign_level_assets)}")
    for rn, ft in campaign_level_assets:
        print(f"  field_type={ft}  {rn}")
    print()

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
        # Merge in campaign-level LOGO/BUSINESS_NAME so the asset group batch
        # satisfies Google's minimum-asset validation (source keeps them at
        # campaign level, not asset group level, so they're not in asset_links)
        all_assets = asset_links + campaign_level_assets
        print(f"  Found source asset_group_id={ag_id}")
        print(f"    assets to clone:     {len(asset_links)} ag-level "
              f"+ {len(campaign_level_assets)} campaign-level = {len(all_assets)} total")
        print(f"    audience signals:    {len(audiences)}")
        print(f"    search themes:       {len(search_themes)}")
        print(f"    new campaign:        {sec['new_campaign_name']}")
        print(f"    daily budget:        ${sec['daily_budget_usd']}")
        print(f"    final_url:           {sec['final_url']}")
        print(f"    utm_content:         {sec['utm_content']}")
        plans.append({
            "sec":           sec,
            "asset_links":   all_assets,
            "audiences":     audiences,
            "search_themes": search_themes,
        })
        print()

    if not execute:
        print("DRY-RUN complete. Pass --execute to actually create.")
        return

    print("=== EXECUTING (campaigns + asset_groups + assets + search themes) ===\n")

    # ── Step 1: collect existing campaigns + asset_groups ────────────────────
    existing_campaigns: dict[str, str] = {}   # name → resource_name
    q = "SELECT campaign.id, campaign.name, campaign.resource_name FROM campaign"
    for r in ga.search(customer_id=SOURCE_CUSTOMER_ID, query=q):
        existing_campaigns[r.campaign.name] = r.campaign.resource_name

    # Map campaign_resource → list of asset_group names already under it
    existing_ag_by_campaign: dict[str, list[str]] = {}
    q2 = "SELECT campaign.resource_name, asset_group.name FROM asset_group"
    for r in ga.search(customer_id=SOURCE_CUSTOMER_ID, query=q2):
        c_rn = r.campaign.resource_name
        existing_ag_by_campaign.setdefault(c_rn, []).append(r.asset_group.name)

    # ── Step 2: create missing campaigns ─────────────────────────────────────
    campaign_resources: dict[str, str] = {}  # sector_name → campaign resource_name
    for p in plans:
        sec     = p["sec"]
        name    = sec["new_campaign_name"]
        if name in existing_campaigns:
            camp_rn = existing_campaigns[name]
            print(f"SKIP campaign {name} — already exists ({camp_rn})")
            campaign_resources[name] = camp_rn
            continue
        print(f"Creating campaign {name}...")
        try:
            budget_rn = create_budget(
                client, SOURCE_CUSTOMER_ID, name, sec["daily_budget_usd"],
            )
            tracking = _tracking_template(sec["utm_content"], SOURCE_CUSTOMER_ID)
            camp_rn  = create_pmax_campaign(
                client, SOURCE_CUSTOMER_ID, name, budget_rn, tracking,
            )
            camp_id  = camp_rn.split("/")[-1]
            print(f"  OK — campaign_id={camp_id}")
            print(f"       https://ads.google.com/aw/overview?campaignId={camp_id}")
            campaign_resources[name] = camp_rn
        except Exception as e:
            print(f"  FAIL: {e}")

    # ── Step 3: create asset_groups + link assets ─────────────────────────────
    print()
    for p in plans:
        sec      = p["sec"]
        name     = sec["new_campaign_name"]
        camp_rn  = campaign_resources.get(name)
        if not camp_rn:
            print(f"SKIP asset_group for {name} — no campaign resource (earlier failure)")
            continue

        ag_name  = sec["source_asset_group_name"]   # reuse same name for clarity
        existing = existing_ag_by_campaign.get(camp_rn, [])
        if existing:
            print(f"SKIP asset_group for {name} — already has: {existing}")
            continue

        n_total = len(p["asset_links"])
        print(f"Creating asset_group '{ag_name}' in {name} "
              f"(atomic batch: {n_total} asset links)...")
        try:
            ag_rn, n_assets = create_asset_group_with_assets(
                client, SOURCE_CUSTOMER_ID, camp_rn,
                ag_name, sec["final_url"], p["asset_links"],
            )
            print(f"  asset_group: {ag_rn}  ({n_assets} assets linked)")
        except Exception as e:
            print(f"  FAIL creating asset_group: {e}")
            continue

        # Search themes (separate call is fine after the group exists)
        n_themes = link_search_themes(
            client, SOURCE_CUSTOMER_ID, ag_rn, p["search_themes"],
        )
        print(f"  linked {n_themes}/{len(p['search_themes'])} search themes")
        print()

    # ── Step 4: summary ───────────────────────────────────────────────────────
    print("\n=== DONE ===")
    print("All campaigns are PAUSED. Next steps:")
    print("  1. Open each new campaign in Google Ads UI and verify asset_group quality.")
    print("  2. Re-attach audience signals manually in UI (search 'HubSpot - SQL' etc.)")
    print("     — the API cannot read source audience signals, only search themes.")
    print("  3. Pause the corresponding asset_groups in PMax_AR_Invoice_FiveSectors")
    print("     to avoid double-spend.")
    print("  4. Enable the new campaigns.")


if __name__ == "__main__":
    main(execute="--execute" in sys.argv)
