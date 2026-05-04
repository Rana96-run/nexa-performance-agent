"""
scripts/create_campaign_from_best.py
=====================================
Creates a new Google Ads campaign by cloning the structure of the best-performing
existing campaign, filtered by CPQL and ROAS.

What it clones:
  - Campaign settings (bidding strategy, budget ratio)
  - Ad groups (renamed with new campaign name)
  - Keywords: only those with QS >= 5 OR (conv >= 3 AND CPA <= $90)
  - RSA headlines + descriptions from the source ad
  - UTM params auto-set using naming convention

Usage:
  # Interactive mode — prompts for all inputs
  python scripts/create_campaign_from_best.py

  # Non-interactive (CI/automation)
  python scripts/create_campaign_from_best.py \\
    --product Invoice \\
    --audience Broad \\
    --language AR \\
    --budget 50 \\
    --days 30 \\
    --yes

  # Audit only — shows best campaigns and their structure, no creation
  python scripts/create_campaign_from_best.py --audit --days 30
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from google.cloud import bigquery
from collectors.google_ads import get_client
from executors.google_ads import (
    create_campaign, create_adgroup, add_keywords,
    add_negative_keywords, create_rsa, best_customer,
)
from executors.naming import prefixed as _naming_prefixed

BQ = bigquery.Client()
GADS = get_client()
GA_SVC = GADS.get_service("GoogleAdsService")

PRIMARY_CID   = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "1513020554").replace("-", "")
ALL_CIDS      = [c.replace("-", "") for c in
                 os.getenv("GOOGLE_ADS_CUSTOMER_IDS", PRIMARY_CID).split(",")]

# ── Keyword keep rule ─────────────────────────────────────────────────────────
# Keep a keyword from the source campaign if:
#   QS >= 5  OR  (conv >= 3 AND cpa <= $90)
# Never remove keywords from source — just don't clone the bad ones.

KW_MIN_QS          = 5
KW_CONV_EXCEPTION  = 3      # conv threshold for CPA exception
KW_CPA_EXCEPTION   = 90.0  # CPA threshold for CPA exception


# ── BQ helpers ───────────────────────────────────────────────────────────────

def best_campaigns(days: int = 30, min_sqls: int = 5, top_n: int = 10) -> list[dict]:
    """
    Return top N Google Ads campaigns by CPQL from BQ (last N days).
    Filters to campaigns with at least min_sqls qualified leads.
    """
    q = f"""
        WITH hs AS (
          SELECT lower(lead_utm_campaign) AS key,
                 SUM(leads_total)     AS leads,
                 SUM(leads_qualified) AS sqls
          FROM qoyod_marketing.hubspot_leads_module_daily
          WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
            AND lead_utm_campaign IS NOT NULL
          GROUP BY 1
        ),
        camps AS (
          SELECT campaign_name, account_id,
                 SUM(spend)       AS spend,
                 SUM(impressions) AS impressions,
                 SUM(clicks)      AS clicks,
                 SUM(conversions) AS conv
          FROM qoyod_marketing.campaigns_daily
          WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
            AND channel = 'google_ads'
          GROUP BY campaign_name, account_id
        )
        SELECT
          c.campaign_name,
          c.account_id,
          ROUND(c.spend, 2)        AS spend,
          c.impressions,
          c.clicks,
          COALESCE(hs.leads, 0)    AS leads,
          COALESCE(hs.sqls, 0)     AS sqls,
          ROUND(SAFE_DIVIDE(c.spend, NULLIF(hs.sqls, 0)), 2) AS cpql,
          ROUND(SAFE_DIVIDE(c.spend, NULLIF(hs.leads, 0)), 2) AS cpl
        FROM camps c
        LEFT JOIN hs ON LOWER(c.campaign_name) = hs.key
        WHERE COALESCE(hs.sqls, 0) >= {min_sqls}
        ORDER BY cpql ASC
        LIMIT {top_n}
    """
    rows = []
    for r in BQ.query(q):
        rows.append({
            "campaign_name": r.campaign_name,
            "account_id":    r.account_id or PRIMARY_CID,
            "spend":         float(r.spend or 0),
            "leads":         int(r.leads or 0),
            "sqls":          int(r.sqls or 0),
            "cpql":          float(r.cpql or 0),
            "cpl":           float(r.cpl or 0),
        })
    return rows


# ── Google Ads API helpers ────────────────────────────────────────────────────

def _find_campaign_id(campaign_name: str, cid: str) -> str | None:
    """Return the Google Ads campaign ID for a given campaign name."""
    q = f"""
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.name = '{campaign_name.replace("'", "\\'")}'
          AND campaign.status != REMOVED
        LIMIT 1
    """
    for row in GA_SVC.search(customer_id=cid, query=q):
        return str(row.campaign.id)
    return None


def _get_adgroups(campaign_id: str, cid: str) -> list[dict]:
    """Return all enabled ad groups in a campaign."""
    q = f"""
        SELECT ad_group.id, ad_group.name, ad_group.cpc_bid_micros
        FROM ad_group
        WHERE ad_group.campaign.id = {campaign_id}
          AND ad_group.status = ENABLED
    """
    groups = []
    for row in GA_SVC.search(customer_id=cid, query=q):
        groups.append({
            "id":           str(row.ad_group.id),
            "resource_name": f"customers/{cid}/adGroups/{row.ad_group.id}",
            "name":         row.ad_group.name,
            "cpc_usd":      row.ad_group.cpc_bid_micros / 1e6,
        })
    return groups


def _get_keywords(adgroup_id: str, cid: str) -> list[dict]:
    """
    Return keywords for an ad group, with QS and 30d conversion data.
    Applies keep rule: QS >= 5 OR (conv >= 3 AND cpa <= $90).
    """
    q = f"""
        SELECT
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.quality_info.quality_score,
            ad_group_criterion.status,
            metrics.conversions,
            metrics.cost_micros
        FROM keyword_view
        WHERE ad_group_criterion.ad_group.id = {adgroup_id}
          AND ad_group_criterion.type = KEYWORD
          AND ad_group_criterion.status != REMOVED
          AND segments.date DURING LAST_30_DAYS
    """
    kws = []
    for row in GA_SVC.search(customer_id=cid, query=q):
        c     = row.ad_group_criterion
        qs    = c.quality_info.quality_score  # 0 = not set
        conv  = row.metrics.conversions
        spend = row.metrics.cost_micros / 1e6
        cpa   = spend / conv if conv > 0 else 9999

        # Keep rule
        keep_qs  = qs >= KW_MIN_QS
        keep_cpa = conv >= KW_CONV_EXCEPTION and cpa <= KW_CPA_EXCEPTION
        if not keep_qs and not keep_cpa:
            continue   # skip this keyword — low QS and doesn't meet CPA exception

        kws.append({
            "text":       c.keyword.text,
            "match_type": c.keyword.match_type.name,
            "qs":         qs,
            "conv":       conv,
            "cpa":        cpa,
        })
    return kws


def _get_rsa(adgroup_id: str, cid: str) -> dict | None:
    """Return headlines + descriptions from the first RSA in an ad group."""
    q = f"""
        SELECT
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.ad.final_urls
        FROM ad_group_ad
        WHERE ad_group_ad.ad_group.id = {adgroup_id}
          AND ad_group_ad.status != REMOVED
          AND ad_group_ad.ad.type = RESPONSIVE_SEARCH_AD
        LIMIT 1
    """
    for row in GA_SVC.search(customer_id=cid, query=q):
        rsa = row.ad_group_ad.ad.responsive_search_ad
        return {
            "headlines":    [h.text for h in rsa.headlines],
            "descriptions": [d.text for d in rsa.descriptions],
            "final_urls":   list(row.ad_group_ad.ad.final_urls),
        }
    return None


# ── UTM URL builder ───────────────────────────────────────────────────────────

def _utm_url(base_url: str, campaign_name: str, adgroup_name: str, ad_name: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return (
        f"{base_url}{sep}"
        f"utm_source=google&utm_medium=cpc"
        f"&utm_campaign={campaign_name}"
        f"&utm_audience={adgroup_name}"
        f"&utm_content={ad_name}"
    )


# ── Main clone logic ──────────────────────────────────────────────────────────

def clone_campaign(
    source_name: str,
    source_cid: str,
    new_product: str,
    new_campaign_type: str,
    new_language: str,
    new_audience: str,
    daily_budget_usd: float,
    landing_url: str,
    dry_run: bool = False,
) -> dict:
    """
    Clone a source campaign's ad groups, keywords (filtered), and RSA into a
    new campaign. New campaign is created PAUSED — review before enabling.
    """
    print(f"\n[campaign-clone] Source  : {source_name} (account {source_cid})")
    new_campaign_name = _naming_prefixed(
        "Google", f"{new_campaign_type}_{new_language}_{new_product}_{new_audience}"
    )
    print(f"[campaign-clone] New name: {new_campaign_name}")
    print(f"[campaign-clone] Budget  : ${daily_budget_usd}/day")

    # Find source campaign ID
    camp_id = _find_campaign_id(source_name, source_cid)
    if not camp_id:
        raise ValueError(f"Campaign not found in account {source_cid}: {source_name}")

    adgroups = _get_adgroups(camp_id, source_cid)
    print(f"[campaign-clone] Found {len(adgroups)} ad group(s) in source")

    if dry_run:
        print("\n[campaign-clone] DRY RUN — structure preview:")
        for ag in adgroups:
            kws = _get_keywords(ag["id"], source_cid)
            rsa = _get_rsa(ag["id"], source_cid)
            print(f"  Ad Group: {ag['name']}")
            print(f"    Keywords to clone ({len(kws)}): " +
                  ", ".join(f"{k['text']} [{k['match_type']}] QS={k['qs']}" for k in kws[:5]) +
                  ("..." if len(kws) > 5 else ""))
            print(f"    RSA: {'found' if rsa else 'NOT FOUND — no RSA to clone'}")
        return {"dry_run": True, "new_campaign_name": new_campaign_name}

    # Determine best account for new campaign
    target_cid = best_customer(new_campaign_name)
    print(f"[campaign-clone] Target account: {target_cid}")

    # Create new campaign (PAUSED)
    camp_result = create_campaign(
        name=f"{new_campaign_type}_{new_language}_{new_product}_{new_audience}",
        daily_budget_usd=daily_budget_usd,
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        customer_id=target_cid,
        advertising_channel="SEARCH",
    )
    new_camp_rn = camp_result["resource_name"]
    print(f"[campaign-clone] Created campaign (PAUSED): {new_campaign_name}")

    created_adgroups = []
    for ag in adgroups:
        # Strip old campaign prefix from ad group name, apply new
        ag_suffix = ag["name"].replace(source_name, "").strip("_- ")
        if not ag_suffix:
            ag_suffix = f"{new_campaign_type}_{new_language}_{new_product}_AdGroup"
        new_ag_name = f"{new_campaign_type}_{new_language}_{new_product}_{ag_suffix}"

        new_ag = create_adgroup(
            campaign_resource_name=new_camp_rn,
            name=new_ag_name,
            cpc_bid_usd=max(ag["cpc_usd"], 1.0),
            customer_id=target_cid,
        )
        new_ag_rn = new_ag["resource_name"]
        print(f"[campaign-clone]   Ad Group: {new_ag_name}")

        # Clone keywords (filtered by keep rule)
        kws = _get_keywords(ag["id"], source_cid)
        if kws:
            kw_payload = [{"text": k["text"], "match_type": k["match_type"]} for k in kws]
            add_keywords(new_ag_rn, kw_payload, customer_id=target_cid)
            print(f"[campaign-clone]     Keywords cloned: {len(kws)} "
                  f"(skipped low-QS/low-conv)")

        # Clone RSA
        rsa = _get_rsa(ag["id"], source_cid)
        if rsa:
            base_url = (rsa["final_urls"][0].split("?")[0]
                        if rsa["final_urls"] else landing_url)
            ad_name = f"Google_{new_campaign_type}_{new_language}_{new_product}_V1"
            utm_url = _utm_url(base_url, new_campaign_name, new_ag_name, ad_name)
            create_rsa(
                adgroup_resource_name=new_ag_rn,
                headlines=rsa["headlines"],
                descriptions=rsa["descriptions"],
                final_url=utm_url,
                customer_id=target_cid,
            )
            print(f"[campaign-clone]     RSA cloned (PAUSED). URL: {utm_url}")
        else:
            print(f"[campaign-clone]     No RSA found in source ad group — skipping ad")

        created_adgroups.append(new_ag_rn)

    print(f"\n[campaign-clone] Done. Campaign '{new_campaign_name}' created PAUSED.")
    print(f"[campaign-clone] Review in Google Ads, then enable when ready.")
    return {
        "campaign_resource": new_camp_rn,
        "campaign_name":     new_campaign_name,
        "adgroups_created":  len(created_adgroups),
        "target_cid":        target_cid,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    val = input(f"{prompt} [{default}]: ").strip()
    return val or default


def main():
    args = sys.argv[1:]
    audit_mode = "--audit" in args
    dry_run    = "--dry-run" in args or audit_mode
    yes_flag   = "--yes" in args
    days       = 30
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days = int(args[i + 1])

    print(f"\n[campaign-clone] Fetching top campaigns by CPQL (last {days} days)...\n")
    campaigns = best_campaigns(days=days, min_sqls=5, top_n=10)

    if not campaigns:
        print("[campaign-clone] No campaigns found with >= 5 SQLs in this period.")
        return

    print(f"{'#':<4} {'CPQL':>7} {'SQLS':>5} {'SPEND':>8} {'CPL':>7}  CAMPAIGN")
    print("-" * 80)
    for i, c in enumerate(campaigns):
        print(f"{i+1:<4} ${c['cpql']:>6.1f} {c['sqls']:>5} ${c['spend']:>7.0f} "
              f"${c['cpl']:>6.1f}  {c['campaign_name']}")

    if audit_mode:
        print("\n[campaign-clone] Audit mode — no campaign created.")
        return

    # Pick source campaign
    print()
    if yes_flag:
        choice = 1
        print(f"[campaign-clone] Auto-selecting #1: {campaigns[0]['campaign_name']}")
    else:
        raw = _ask("Select source campaign number", "1")
        choice = int(raw)

    if choice < 1 or choice > len(campaigns):
        print(f"[campaign-clone] Invalid choice.")
        return

    source = campaigns[choice - 1]
    source_cid = (source["account_id"] or PRIMARY_CID).replace("-", "")

    print(f"\n[campaign-clone] Source: {source['campaign_name']} "
          f"(CPQL=${source['cpql']:.1f}, {source['sqls']} SQLs)")

    # Collect new campaign params
    if yes_flag:
        product  = next((a for i, a in enumerate(args) if args[i-1] == "--product"), "Invoice")
        audience = next((a for i, a in enumerate(args) if args[i-1] == "--audience"), "Broad")
        language = next((a for i, a in enumerate(args) if args[i-1] == "--language"), "AR")
        budget   = float(next((a for i, a in enumerate(args) if args[i-1] == "--budget"), "50"))
        land_url = next((a for i, a in enumerate(args) if args[i-1] == "--url"),
                        "https://qoyod.com/accounting-software")
        camp_type = next((a for i, a in enumerate(args) if args[i-1] == "--type"), "Search")
    else:
        print("\nNew campaign parameters:")
        product   = _ask("Product (Invoice/Bookkeeping/Qflavours)", "Invoice")
        camp_type = _ask("Type (Search/PMax/Display/Video)", "Search")
        language  = _ask("Language (AR/EN/AREN)", "AR")
        audience  = _ask("Audience (Broad/Interests/Lookalike/Retargeting/Competitor)", "Broad")
        budget    = float(_ask("Daily budget USD", "50"))
        land_url  = _ask("Landing URL (leave blank to inherit from source)",
                          "https://qoyod.com/accounting-software")

    # Show dry-run preview first
    print("\n[campaign-clone] Previewing structure (dry run)...")
    clone_campaign(
        source_name=source["campaign_name"],
        source_cid=source_cid,
        new_product=product,
        new_campaign_type=camp_type,
        new_language=language,
        new_audience=audience,
        daily_budget_usd=budget,
        landing_url=land_url,
        dry_run=True,
    )

    if not yes_flag:
        confirm = _ask("\nCreate this campaign? (yes/no)", "no")
        if confirm.lower() not in ("yes", "y"):
            print("[campaign-clone] Cancelled.")
            return

    clone_campaign(
        source_name=source["campaign_name"],
        source_cid=source_cid,
        new_product=product,
        new_campaign_type=camp_type,
        new_language=language,
        new_audience=audience,
        daily_budget_usd=budget,
        landing_url=land_url,
        dry_run=False,
    )


if __name__ == "__main__":
    main()
