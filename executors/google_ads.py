"""
Google Ads executor — full mutation surface.

All write operations require prior Slack approval and are logged.
Multi-account: pass customer_id explicitly; defaults to primary account.

Supported:
  Campaign  — pause / enable / remove / change budget / create
  Ad group  — pause / enable / change CPC bid / create
  Keyword   — pause / enable / add (exact/phrase/broad) / add negatives
  Ad        — pause / enable / create RSA
  Planning  — keyword ideas, reach forecasts

Campaign naming convention: {Channel}_{Type}_{Language}_{Product}_{Audience}
  Channel:  Google
  Type:     Search | PMax | Display | Video | Remarketing
  Language: AR | EN | AREN
  Product:  Invoice (E-Invoice) | Bookkeeping (Qbookkeeping) | Qflavours | General | {SeasonalName}
  Audience: Interests | Lookalike | Retargeting | Broad | Competitor | ImpressionShare
  Rules:
    - Prospecting campaigns use Interests or Lookalike — never "Prospecting" alone
    - Retargeting campaigns use Retargeting — never combined with Prospecting
    - Product aliases auto-normalised: E-Invoice->Invoice, Qbookkeeping->Bookkeeping, etc.
  Examples: Google_Search_AR_Invoice_Competitor
            Google_PMax_AR_Bookkeeping_Broad
            Google_Search_AR_Ramadan_Interests

Accounts: 1513020554 (Acc1/primary) | 5753494964 (Acc2)
Use best_customer() to pick the one with better CPL from BQ.
"""
from __future__ import annotations

import os
from typing import Sequence

from collectors.google_ads import get_client, pause_keyword, pause_ad  # noqa: F401 — re-export
from config import GOOGLE_ADS_CONFIG, USD_SAR_PEG
from executors.naming import prefixed as _naming_prefixed

_DEFAULT_CID = GOOGLE_ADS_CONFIG["customer_id"]
_ALL_CIDS    = [c.replace("-", "") for c in
                os.getenv("GOOGLE_ADS_CUSTOMER_IDS", _DEFAULT_CID).split(",")]

_CHANNEL_PREFIX = "Google"


def _prefixed(name: str) -> str:
    return _naming_prefixed(_CHANNEL_PREFIX, name)


def best_customer(campaign_name: str, days: int = 30) -> str:
    """
    Return the Google Ads customer_id whose existing campaigns with a name
    similar to `campaign_name` have driven the most HubSpot-qualified leads
    (SQLs) over the last N days.
    Falls back to _DEFAULT_CID when BQ is unreachable or no match found.
    """
    if len(_ALL_CIDS) < 2:
        return _DEFAULT_CID
    try:
        from google.cloud import bigquery as _bq
        from google.oauth2 import service_account as _sa
        from datetime import date as _date, timedelta as _td

        project  = os.getenv("BQ_PROJECT_ID")
        dataset  = os.getenv("BQ_DATASET", "qoyod_marketing")
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
        creds    = _sa.Credentials.from_service_account_file(key_path)
        client   = _bq.Client(project=project, credentials=creds)

        since  = (_date.today() - _td(days=days)).isoformat()
        tokens = [t.lower() for t in campaign_name.replace("-", "_").split("_") if len(t) > 2]
        if not tokens:
            tokens = [campaign_name.lower()]
        like_clauses = " AND ".join(
            f"LOWER(c.campaign_name) LIKE '%{t}%'" for t in tokens
        )
        acct_list = ", ".join(f"'{a}'" for a in _ALL_CIDS)

        sql = f"""
            SELECT c.account_id,
                   SUM(h.leads_qualified) AS sqls
            FROM `{project}.{dataset}.campaigns_daily` c
            JOIN `{project}.{dataset}.hubspot_leads_module_daily` h
              ON  c.date = h.date
             AND  LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
            WHERE c.channel = 'google_ads'
              AND c.date >= '{since}'
              AND c.account_id IN ({acct_list})
              AND ({like_clauses})
            GROUP BY c.account_id
            ORDER BY sqls DESC
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        if rows and rows[0].account_id:
            cid = rows[0].account_id.replace("-", "")
            print(f"[gads] best customer for '{campaign_name}' "
                  f"({int(rows[0].sqls or 0)} SQLs last {days}d): {cid}")
            return cid
    except Exception as e:
        print(f"[gads] best_customer BQ query failed ({e}), using default")
    return _DEFAULT_CID


def _usd_to_micros(usd: float) -> int:
    return int(round(usd * 1_000_000))


# ── Campaign ──────────────────────────────────────────────────────────────────

def _campaign_resource(customer_id: str, campaign_id: str | int) -> str:
    return f"customers/{customer_id}/campaigns/{campaign_id}"


def set_campaign_status(campaign_id: str | int, status: str,
                        customer_id: str = _DEFAULT_CID) -> dict:
    """status: ENABLED | PAUSED | REMOVED"""
    client   = get_client()
    svc      = client.get_service("CampaignService")
    op       = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = _campaign_resource(customer_id, campaign_id)
    campaign.status        = getattr(client.enums.CampaignStatusEnum, status)
    op.update_mask.paths.append("status")
    r = svc.mutate_campaigns(customer_id=customer_id, operations=[op])
    print(f"[gads] campaign {campaign_id} -> {status}")
    return {"resource_name": r.results[0].resource_name}


def pause_campaign(campaign_id: str | int, customer_id: str = _DEFAULT_CID) -> dict:
    return set_campaign_status(campaign_id, "PAUSED", customer_id)


def enable_campaign(campaign_id: str | int, customer_id: str = _DEFAULT_CID) -> dict:
    return set_campaign_status(campaign_id, "ENABLED", customer_id)


def set_campaign_budget(campaign_id: str | int, daily_budget_usd: float,
                        customer_id: str = _DEFAULT_CID) -> dict:
    """
    Update a campaign's shared budget OR its own budget.
    Fetches the budget resource name first, then patches it.
    """
    client  = get_client()
    ga_svc  = client.get_service("GoogleAdsService")

    # Find the budget resource name attached to this campaign
    query = f"""
        SELECT campaign.id, campaign_budget.resource_name,
               campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.id = {campaign_id}
        LIMIT 1
    """
    rows = list(ga_svc.search(customer_id=customer_id, query=query))
    if not rows:
        raise ValueError(f"Campaign {campaign_id} not found in account {customer_id}")
    budget_rn = rows[0].campaign_budget.resource_name

    bsvc = client.get_service("CampaignBudgetService")
    op   = client.get_type("CampaignBudgetOperation")
    b    = op.update
    b.resource_name   = budget_rn
    b.amount_micros   = _usd_to_micros(daily_budget_usd)
    op.update_mask.paths.append("amount_micros")
    r = bsvc.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
    print(f"[gads] campaign {campaign_id} budget -> ${daily_budget_usd}/day")
    return {"resource_name": r.results[0].resource_name}


_VALID_BIDDING = ("TARGET_CPA", "MAXIMIZE_CONVERSIONS", "TARGET_ROAS", "MAXIMIZE_CONVERSION_VALUE")


def create_campaign(
    name: str,
    daily_budget_usd: float,
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_usd: float | None = None,
    target_roas: float | None = None,
    customer_id: str | None = None,
    advertising_channel: str = "SEARCH",
) -> dict:
    """
    Create a new campaign in PAUSED state. Returns campaign resource name.
    If customer_id is None, picks the better-performing account from BQ.

    bidding_strategy (enforced):
      MAXIMIZE_CONVERSIONS      — default, no extra param
      TARGET_CPA                — pass target_cpa_usd
      TARGET_ROAS               — pass target_roas (e.g. 2.0 = 200%)
      MAXIMIZE_CONVERSION_VALUE — no extra param

    Naming: Google_{Type}_{Language}_{Product}_{Audience}
    e.g. Google_Search_AR_Invoice_Broad
    """
    # Launch-policy gate: 1 new campaign per channel per 7 days.
    # Pass force=True or set FORCE_LAUNCH=1 to bypass (log justification!).
    from executors.launch_policy import enforce_launch_policy, LaunchBlocked
    try:
        enforce_launch_policy("google_ads")
    except LaunchBlocked as e:
        print(f"[google_ads.create_campaign] BLOCKED: {e}")
        return {"error": "launch_blocked", "message": str(e), "blocker": e.blocker}

    name = _prefixed(name)
    if customer_id is None:
        customer_id = best_customer(name)
    client  = get_client()
    bsvc    = client.get_service("CampaignBudgetService")
    csvc    = client.get_service("CampaignService")

    # 1. Create budget
    bop  = client.get_type("CampaignBudgetOperation")
    bgt  = bop.create
    bgt.name           = f"{name}_budget"
    bgt.amount_micros  = _usd_to_micros(daily_budget_usd)
    bgt.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    br   = bsvc.mutate_campaign_budgets(customer_id=customer_id, operations=[bop])
    budget_rn = br.results[0].resource_name

    # 2. Create campaign (PAUSED)
    cop      = client.get_type("CampaignOperation")
    campaign = cop.create
    campaign.name             = name
    campaign.status           = client.enums.CampaignStatusEnum.PAUSED
    campaign.advertising_channel_type = getattr(
        client.enums.AdvertisingChannelTypeEnum, advertising_channel)
    campaign.campaign_budget  = budget_rn

    # Bidding — only the four approved strategies
    if bidding_strategy == "TARGET_CPA":
        if not target_cpa_usd:
            raise ValueError("TARGET_CPA requires target_cpa_usd")
        campaign.target_cpa.target_cpa_micros = _usd_to_micros(target_cpa_usd)
    elif bidding_strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions.CopyFrom(client.get_type("MaximizeConversions"))
    elif bidding_strategy == "TARGET_ROAS":
        if not target_roas:
            raise ValueError("TARGET_ROAS requires target_roas (e.g. 2.0 = 200%)")
        campaign.target_roas.target_roas = target_roas
    elif bidding_strategy == "MAXIMIZE_CONVERSION_VALUE":
        campaign.maximize_conversion_value.CopyFrom(client.get_type("MaximizeConversionValue"))
    else:
        raise ValueError(f"bidding_strategy must be one of {_VALID_BIDDING}")

    cr = csvc.mutate_campaigns(customer_id=customer_id, operations=[cop])
    rn = cr.results[0].resource_name
    print(f"[gads] campaign created (PAUSED): {name} -> {rn}")
    try:
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="campaign_creator", action="campaign_created",
            channel="google_ads", campaign_name=name, rows_affected=1,
            details={"resource_name": rn, "budget_usd": daily_budget_usd,
                     "bidding_strategy": bidding_strategy},
        )
    except Exception:
        pass
    return {"resource_name": rn, "name": name}


# ── Ad group ──────────────────────────────────────────────────────────────────

def set_adgroup_status(adgroup_resource_name: str, status: str,
                       customer_id: str = _DEFAULT_CID) -> dict:
    """status: ENABLED | PAUSED | REMOVED"""
    client = get_client()
    svc    = client.get_service("AdGroupService")
    op     = client.get_type("AdGroupOperation")
    ag     = op.update
    ag.resource_name = adgroup_resource_name
    ag.status        = getattr(client.enums.AdGroupStatusEnum, status)
    op.update_mask.paths.append("status")
    r = svc.mutate_ad_groups(customer_id=customer_id, operations=[op])
    print(f"[gads] adgroup {adgroup_resource_name} -> {status}")
    return {"resource_name": r.results[0].resource_name}


def set_adgroup_cpc_bid(adgroup_resource_name: str, cpc_bid_usd: float,
                        customer_id: str = _DEFAULT_CID) -> dict:
    client = get_client()
    svc    = client.get_service("AdGroupService")
    op     = client.get_type("AdGroupOperation")
    ag     = op.update
    ag.resource_name   = adgroup_resource_name
    ag.cpc_bid_micros  = _usd_to_micros(cpc_bid_usd)
    op.update_mask.paths.append("cpc_bid_micros")
    r = svc.mutate_ad_groups(customer_id=customer_id, operations=[op])
    print(f"[gads] adgroup bid -> ${cpc_bid_usd}")
    return {"resource_name": r.results[0].resource_name}


def create_adgroup(campaign_resource_name: str, name: str,
                   cpc_bid_usd: float = 2.0,
                   customer_id: str = _DEFAULT_CID) -> dict:
    name = _prefixed(name)
    client = get_client()
    svc    = client.get_service("AdGroupService")
    op     = client.get_type("AdGroupOperation")
    ag     = op.create
    ag.name           = name
    ag.campaign       = campaign_resource_name
    ag.status         = client.enums.AdGroupStatusEnum.ENABLED
    ag.cpc_bid_micros = _usd_to_micros(cpc_bid_usd)
    r = svc.mutate_ad_groups(customer_id=customer_id, operations=[op])
    rn = r.results[0].resource_name
    print(f"[gads] adgroup created: {name} -> {rn}")
    return {"resource_name": rn}


# ── Keywords ──────────────────────────────────────────────────────────────────

_MATCH = {
    "EXACT":  "EXACT",
    "PHRASE": "PHRASE",
    "BROAD":  "BROAD",
}


def add_keywords(adgroup_resource_name: str,
                 keywords: list[dict],
                 customer_id: str = _DEFAULT_CID) -> list:
    """
    keywords: [{"text": "...", "match_type": "EXACT|PHRASE|BROAD", "cpc_bid_usd": 1.5}, ...]
    cpc_bid_usd is optional — omit to inherit ad group bid.
    """
    client = get_client()
    svc    = client.get_service("AdGroupCriterionService")
    ops    = []
    for kw in keywords:
        op   = client.get_type("AdGroupCriterionOperation")
        crit = op.create
        crit.ad_group          = adgroup_resource_name
        crit.status            = client.enums.AdGroupCriterionStatusEnum.ENABLED
        crit.keyword.text      = kw["text"]
        crit.keyword.match_type = getattr(
            client.enums.KeywordMatchTypeEnum, _MATCH.get(kw["match_type"].upper(), "BROAD"))
        if kw.get("cpc_bid_usd"):
            crit.cpc_bid_micros = _usd_to_micros(kw["cpc_bid_usd"])
        ops.append(op)
    r = svc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops)
    print(f"[gads] added {len(ops)} keyword(s) to {adgroup_resource_name}")
    try:
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="keyword_management", action="positive_keywords_added",
            channel="google_ads", rows_affected=len(ops),
            details={"keywords": [kw["text"] for kw in keywords[:20]],
                     "adgroup_resource": adgroup_resource_name},
        )
    except Exception:
        pass
    return [res.resource_name for res in r.results]


def add_negative_keywords(campaign_resource_name: str,
                          keywords: list[dict],
                          customer_id: str = _DEFAULT_CID) -> list:
    """
    keywords: [{"text": "...", "match_type": "EXACT|PHRASE|BROAD"}, ...]
    """
    client = get_client()
    svc    = client.get_service("CampaignCriterionService")
    ops    = []
    for kw in keywords:
        op   = client.get_type("CampaignCriterionOperation")
        crit = op.create
        crit.campaign          = campaign_resource_name
        crit.negative          = True
        crit.keyword.text      = kw["text"]
        crit.keyword.match_type = getattr(
            client.enums.KeywordMatchTypeEnum, _MATCH.get(kw["match_type"].upper(), "BROAD"))
        ops.append(op)
    r = svc.mutate_campaign_criteria(customer_id=customer_id, operations=ops)
    print(f"[gads] added {len(ops)} negative keyword(s) to {campaign_resource_name}")
    try:
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="keyword_management", action="negative_keywords_added",
            channel="google_ads", rows_affected=len(ops),
            details={"terms": [kw["text"] for kw in keywords[:20]],
                     "campaign_resource": campaign_resource_name},
        )
    except Exception:
        pass
    return [res.resource_name for res in r.results]


def set_keyword_status(resource_name: str, status: str,
                       customer_id: str = _DEFAULT_CID) -> dict:
    """status: ENABLED | PAUSED | REMOVED"""
    client = get_client()
    svc    = client.get_service("AdGroupCriterionService")
    op     = client.get_type("AdGroupCriterionOperation")
    crit   = op.update
    crit.resource_name = resource_name
    crit.status        = getattr(client.enums.AdGroupCriterionStatusEnum, status)
    op.update_mask.paths.append("status")
    r = svc.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
    print(f"[gads] keyword {resource_name} -> {status}")
    return {"resource_name": r.results[0].resource_name}


# ── Ads ───────────────────────────────────────────────────────────────────────

def set_ad_status(ad_resource_name: str, status: str,
                  customer_id: str = _DEFAULT_CID) -> dict:
    """status: ENABLED | PAUSED | REMOVED"""
    client = get_client()
    svc    = client.get_service("AdGroupAdService")
    op     = client.get_type("AdGroupAdOperation")
    ad     = op.update
    ad.resource_name = ad_resource_name
    ad.status        = getattr(client.enums.AdGroupAdStatusEnum, status)
    op.update_mask.paths.append("status")
    r = svc.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
    print(f"[gads] ad -> {status}")
    return {"resource_name": r.results[0].resource_name}


def create_rsa(adgroup_resource_name: str,
               headlines: list[str],
               descriptions: list[str],
               final_url: str,
               path1: str = "",
               path2: str = "",
               customer_id: str = _DEFAULT_CID) -> dict:
    """
    Create a Responsive Search Ad. Always created PAUSED for review.
    headlines: 3–15 strings (max 30 chars each)
    descriptions: 2–4 strings (max 90 chars each)
    """
    client = get_client()
    svc    = client.get_service("AdGroupAdService")
    op     = client.get_type("AdGroupAdOperation")
    aga    = op.create
    aga.ad_group = adgroup_resource_name
    aga.status   = client.enums.AdGroupAdStatusEnum.PAUSED

    ad = aga.ad
    ad.final_urls.append(final_url)
    if path1:
        ad.responsive_search_ad.path1 = path1
    if path2:
        ad.responsive_search_ad.path2 = path2

    for h in headlines[:15]:
        asset = client.get_type("AdTextAsset")
        asset.text = h[:30]
        ad.responsive_search_ad.headlines.append(asset)

    for d in descriptions[:4]:
        asset = client.get_type("AdTextAsset")
        asset.text = d[:90]
        ad.responsive_search_ad.descriptions.append(asset)

    r = svc.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
    rn = r.results[0].resource_name
    print(f"[gads] RSA created (PAUSED): {rn}")
    return {"resource_name": rn}


def update_ad_final_url(ad_resource_name: str, final_url: str,
                        customer_id: str = _DEFAULT_CID) -> dict:
    client = get_client()
    svc    = client.get_service("AdService")
    op     = client.get_type("AdOperation")
    ad     = op.update
    ad.resource_name = ad_resource_name.split("/ads/")[0] + "/ads/" + ad_resource_name.split("/ads/")[1]
    ad.final_urls[:] = [final_url]
    op.update_mask.paths.append("final_urls")
    r = svc.mutate_ads(customer_id=customer_id, operations=[op])
    print(f"[gads] final URL updated -> {final_url}")
    return {"resource_name": r.results[0].resource_name}


# ── Lead form extension ───────────────────────────────────────────────────────

def create_lead_form_extension(
    customer_id: str,
    campaign_resource_name: str,
    headline: str,
    description: str,
    questions: list[dict] | None = None,
    privacy_policy_url: str = "https://qoyod.com/privacy",
    call_to_action_type: str = "LEARN_MORE",
    business_name: str = "Qoyod",
) -> str:
    """
    Create a Google Ads Lead Form Asset and link it to a campaign.

    The asset is created and immediately attached to the campaign as a
    CampaignAsset.  The containing campaign should remain PAUSED until the
    form content has been reviewed.

    Parameters
    ----------
    customer_id             : Google Ads customer ID (no dashes).
    campaign_resource_name  : Resource name of the campaign to link the form
                              to, e.g. ``customers/1234/campaigns/5678``.
    headline                : Short headline shown on the lead form unit
                              (max 30 chars).
    description             : Description shown below the headline
                              (max 90 chars).
    questions               : List of question dicts. Each dict must contain a
                              ``field_type`` key mapping to a
                              ``LeadFormFieldUserInputTypeEnum`` value.
                              Supported types: FULL_NAME, PHONE_NUMBER,
                              COMPANY_NAME, JOB_TITLE.
                              Defaults to all four standard Qoyod fields.
    privacy_policy_url      : URL of the privacy policy page (required by
                              Google Ads).
    call_to_action_type     : CTA shown on the trigger button.
                              Supported values: LEARN_MORE, GET_QUOTE,
                              APPLY_NOW, SIGN_UP, CONTACT_US, SUBSCRIBE,
                              DOWNLOAD, BOOK_NOW, GET_OFFER, REGISTER,
                              GET_INFO, REQUEST_DEMO, JOIN_NOW, GET_STARTED.
                              Defaults to LEARN_MORE.
    business_name           : Business name shown in the form header
                              (max 25 chars).

    Returns
    -------
    str  — the asset resource name, e.g. ``customers/1234/assets/9999``.
    """
    if questions is None:
        questions = [
            {"field_type": "FULL_NAME"},
            {"field_type": "PHONE_NUMBER"},
            {"field_type": "COMPANY_NAME"},
            {"field_type": "JOB_TITLE"},
        ]

    client   = get_client()
    asset_svc = client.get_service("AssetService")
    camp_asset_svc = client.get_service("CampaignAssetService")

    # 1. Build the LeadFormAsset
    asset_op   = client.get_type("AssetOperation")
    asset      = asset_op.create
    lead_form  = asset.lead_form_asset

    lead_form.business_name      = business_name[:25]
    lead_form.headline           = headline[:30]
    lead_form.description        = description[:90]
    lead_form.privacy_policy_url = privacy_policy_url
    lead_form.call_to_action_type = getattr(
        client.enums.LeadFormCallToActionTypeEnum, call_to_action_type
    )

    # Append question fields
    for q in questions:
        field = client.get_type("LeadFormField")
        field.input_type = getattr(
            client.enums.LeadFormFieldUserInputTypeEnum, q["field_type"]
        )
        lead_form.fields.append(field)

    asset_r    = asset_svc.mutate_assets(customer_id=customer_id, operations=[asset_op])
    asset_rn   = asset_r.results[0].resource_name

    # 2. Link the asset to the campaign
    ca_op      = client.get_type("CampaignAssetOperation")
    ca         = ca_op.create
    ca.asset    = asset_rn
    ca.campaign = campaign_resource_name
    ca.field_type = client.enums.AssetFieldTypeEnum.LEAD_FORM

    camp_asset_svc.mutate_campaign_assets(customer_id=customer_id, operations=[ca_op])

    print(f"[gads] form created: {asset_rn}")
    return asset_rn


# ── Full campaign setup (one call) ───────────────────────────────────────────

def _build_utm_url(base_url: str, campaign_name: str,
                   adgroup_name: str, ad_name: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return (
        f"{base_url}{sep}"
        f"utm_source=google&utm_medium=cpc"
        f"&utm_campaign={campaign_name}"
        f"&utm_audience={adgroup_name}"
        f"&utm_content={ad_name}"
    )


# _VALID_BIDDING defined above near create_campaign — kept here as marker only


def create_full_campaign(
    product: str,
    campaign_type: str,
    language: str,
    audience_type: str,
    daily_budget_usd: float,
    landing_url: str,
    headlines: list[str],
    descriptions: list[str],
    keywords: list[dict] | None = None,
    negative_keywords: list[dict] | None = None,
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_usd: float | None = None,
    target_roas: float | None = None,
    cpc_bid_usd: float = 2.0,
    advertising_channel: str = "SEARCH",
    customer_id: str | None = None,
) -> dict:
    """
    Full Google Ads campaign setup in one call.

    Naming (enforced automatically):
      Campaign : Google_{campaign_type}_{language}_{product}_{audience_type}
      Ad Group : Google_{campaign_type}_{language}_{product}_AdGroup
      Ad       : RSA (Responsive Search Ad) — always created PAUSED

    landing_url: UTMs (utm_source=google, utm_medium=cpc, utm_campaign, utm_content) auto-appended.
    keywords   : [{"text": "...", "match_type": "EXACT|PHRASE|BROAD"}, ...]

    bidding_strategy options (enforced):
      TARGET_CPA              — pass target_cpa_usd
      MAXIMIZE_CONVERSIONS    — no extra param needed
      TARGET_ROAS             — pass target_roas (e.g. 2.0 = 200%)
      MAXIMIZE_CONVERSION_VALUE — no extra param needed

    Returns dict with campaign_resource, adgroup_resource, ad_resource.
    """
    if bidding_strategy not in _VALID_BIDDING:
        raise ValueError(
            f"bidding_strategy must be one of {_VALID_BIDDING}, got {bidding_strategy!r}"
        )
    result: dict = {}
    cid = customer_id or best_customer(_prefixed(f"{campaign_type}_{language}_{product}_{audience_type}"))

    # Auto-research keywords for Search campaigns when none supplied
    if advertising_channel == "SEARCH" and not keywords:
        print(f"[gads] No keywords provided — researching from product: {product!r}")
        try:
            lang_code = "ar" if language.lower() == "ar" else "en"
            seeds = [product.lower()]
            if lang_code == "ar":
                seeds += [f"{product.lower()} برنامج", f"{product.lower()} نظام"]
            ideas = keyword_ideas(seed_keywords=seeds, language=lang_code, customer_id=cid)
            keywords = [
                {"text": idea["keyword"], "match_type": "EXACT"}
                for idea in ideas[:15]
                if idea["avg_monthly"] > 0
            ] or [{"text": product.lower(), "match_type": "BROAD"}]
            result["keywords_researched"] = True
            result["keyword_ideas_count"] = len(ideas)
            print(f"[gads] Auto-selected {len(keywords)} keywords from {len(ideas)} ideas")
        except Exception as e:
            print(f"[gads] Keyword research failed — proceeding without: {e}")

    # 1. Campaign
    camp_name = f"{campaign_type}_{language}_{product}_{audience_type}"
    camp = create_campaign(
        name=camp_name,
        daily_budget_usd=daily_budget_usd,
        bidding_strategy=bidding_strategy,
        target_cpa_usd=target_cpa_usd,
        customer_id=cid,
        advertising_channel=advertising_channel,
    )
    camp_rn = camp["resource_name"]
    campaign_name = camp["name"]
    result["campaign_resource"] = camp_rn
    result["campaign_name"] = campaign_name

    # 2. Ad Group
    ag_name = f"{campaign_type}_{language}_{product}_AdGroup"
    ag = create_adgroup(
        campaign_resource_name=camp_rn,
        name=ag_name,
        cpc_bid_usd=cpc_bid_usd,
        customer_id=cid,
    )
    ag_rn = ag["resource_name"]
    result["adgroup_resource"] = ag_rn

    # 3. Keywords
    if keywords:
        add_keywords(ag_rn, keywords, customer_id=cid)
    if negative_keywords:
        add_negative_keywords(camp_rn, negative_keywords, customer_id=cid)
    result["keywords_added"] = len(keywords or [])
    result["negatives_added"] = len(negative_keywords or [])

    # 4. RSA with UTM URL
    ad_name = _prefixed(f"{campaign_type}_{language}_{product}V1")
    utm_url = _build_utm_url(landing_url, campaign_name, ag_name, ad_name)
    ad = create_rsa(
        adgroup_resource_name=ag_rn,
        headlines=headlines,
        descriptions=descriptions,
        final_url=utm_url,
        customer_id=cid,
    )
    result["ad_resource"] = ad["resource_name"]
    result["ad_name"] = ad_name
    result["final_url"] = utm_url

    result["utm_mapping"] = {
        "utm_source":   "google",
        "utm_medium":   "cpc",
        "utm_campaign": campaign_name,
        "utm_content":  ad_name,
    }
    print(f"\n[gads] Full campaign setup complete:")
    print(f"  Campaign : {campaign_name}")
    print(f"  Ad Group : {ag_rn}")
    print(f"  Ad (RSA) : PAUSED — review in Google Ads before enabling")
    print(f"  URL      : {utm_url}")
    return result


# ── Asset / creative library ──────────────────────────────────────────────────

def list_creatives(limit: int = 20, customer_id: str = _DEFAULT_CID) -> list[dict]:
    """
    List image and video assets from the Google Ads Asset service.
    Returns list of {id, name, type, thumbnail_url}.
    """
    client  = get_client()
    ga_svc  = client.get_service("GoogleAdsService")

    # Note: cannot filter by enum in WHERE for VIDEO/IMAGE in all API versions;
    # use two separate queries and merge results.
    results_raw = []
    for asset_type in ("IMAGE", "VIDEO"):
        q = f"""
            SELECT asset.id, asset.name, asset.type,
                   asset.image_asset.full_size.url
            FROM asset
            WHERE asset.type = '{asset_type}'
            LIMIT {limit}
        """
        try:
            for row in ga_svc.search(customer_id=customer_id, query=q):
                results_raw.append(row)
        except Exception as e:
            print(f"[gads] list_creatives {asset_type} query error: {e}")
    rows = results_raw

    results = []
    for row in rows:
        asset = row.asset
        results.append({
            "id":           str(asset.id),
            "name":         asset.name,
            "type":         asset.type_.name if hasattr(asset.type_, "name") else str(asset.type_),
            "thumbnail_url": asset.image_asset.full_size.url if asset.image_asset.full_size.url else None,
            "source":       "asset_service",
        })

    print(f"[gads] list_creatives -> {len(results)} assets (customer={customer_id})")
    return results


# ── Keyword planning ──────────────────────────────────────────────────────────

def keyword_ideas(seed_keywords: list[str],
                  seed_url: str | None = None,
                  language: str = "ar",
                  customer_id: str = _DEFAULT_CID,
                  location_ids: list[int] | None = None) -> list[dict]:
    """
    Returns keyword ideas with avg monthly searches + competition.
    language: 'ar' (Arabic) or 'en'. Saudi Arabia geo = 2682 (location_id).
    """
    client    = get_client()
    kp_svc    = client.get_service("KeywordPlanIdeaService")
    geo_svc   = client.get_service("GeoTargetConstantService")

    lang_rn = f"languageConstants/{1019 if language == 'ar' else 1000}"
    locs    = location_ids or [2682]  # Saudi Arabia
    loc_rns = [f"geoTargetConstants/{lid}" for lid in locs]

    req = client.get_type("GenerateKeywordIdeasRequest")
    req.customer_id          = customer_id
    req.language             = lang_rn
    req.geo_target_constants.extend(loc_rns)
    req.include_adult_keywords = False
    req.keyword_plan_network   = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

    if seed_url:
        req.url_seed.url = seed_url
    if seed_keywords:
        req.keyword_seed.keywords.extend(seed_keywords)

    ideas = []
    for idea in kp_svc.generate_keyword_ideas(request=req):
        ideas.append({
            "keyword":      idea.text,
            "avg_monthly":  idea.keyword_idea_metrics.avg_monthly_searches,
            "competition":  idea.keyword_idea_metrics.competition.name,
            "low_cpc_usd":  (idea.keyword_idea_metrics.low_top_of_page_bid_micros or 0) / 1e6,
            "high_cpc_usd": (idea.keyword_idea_metrics.high_top_of_page_bid_micros or 0) / 1e6,
        })
    ideas.sort(key=lambda x: x["avg_monthly"], reverse=True)
    print(f"[gads] keyword ideas: {len(ideas)} results")
    return ideas


# ── Weekly search term review ─────────────────────────────────────────────────

def list_search_terms(
    days: int = 7,
    customer_id: str = _DEFAULT_CID,
    min_impressions: int = 1,
) -> list[dict]:
    """
    Pull search terms report for the last `days` days.

    Returns a list of dicts sorted by conversions desc, then cost desc:
      {
        query, impressions, clicks, conversions, cost_usd,
        ctr, cvr, cpc_usd,
        campaign_id, campaign_name,
        ad_group_id, ad_group_name, ad_group_resource_name,
      }

    Usage in weekly cadence:
      terms = list_search_terms(days=7)
      # Converting: clicks>=3, conversions>=1  → add_keywords()
      # Negatives : clearly off-topic           → add_negative_keywords()
      # Watch     : clicks>=3, conv=0, cost<$10 → flag in Asana
    """
    client = get_client()
    ga_svc = client.get_service("GoogleAdsService")

    q = f"""
        SELECT
            search_term_view.search_term,
            search_term_view.status,
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group.resource_name,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.cost_micros,
            metrics.ctr,
            metrics.conversions_from_interactions_rate
        FROM search_term_view
        WHERE segments.date DURING LAST_{days}_DAYS
          AND metrics.impressions >= {min_impressions}
        ORDER BY metrics.conversions DESC, metrics.cost_micros DESC
        LIMIT 500
    """

    rows = []
    try:
        for row in ga_svc.search(customer_id=customer_id, query=q):
            stv = row.search_term_view
            m   = row.metrics
            rows.append({
                "query":                   stv.search_term,
                "status":                  stv.status.name,   # ADDED / EXCLUDED / NONE
                "impressions":             m.impressions,
                "clicks":                  m.clicks,
                "conversions":             m.conversions,
                "cost_usd":                m.cost_micros / 1e6,
                "ctr":                     round(m.ctr, 4),
                "cvr":                     round(m.conversions_from_interactions_rate, 4),
                "cpc_usd":                 round(m.cost_micros / 1e6 / m.clicks, 2) if m.clicks else 0,
                "campaign_id":             str(row.campaign.id),
                "campaign_name":           row.campaign.name,
                "ad_group_id":             str(row.ad_group.id),
                "ad_group_name":           row.ad_group.name,
                "ad_group_resource_name":  row.ad_group.resource_name,
            })
    except Exception as e:
        print(f"[gads] list_search_terms error: {e}")

    print(f"[gads] list_search_terms({days}d): {len(rows)} terms, "
          f"{sum(r['conversions'] for r in rows):.0f} total conversions")
    return rows


def classify_search_terms(
    terms: list[dict],
    existing_keywords: list[str] | None = None,
) -> dict:
    """
    Auto-classify search terms into action buckets.

    Rules (matches weekly cadence in qoyod-paid-media-agent.md):
      - convert:  clicks >= 3, conversions >= 1, not already a keyword
      - negative: clearly irrelevant (job/career/free/competitor patterns)
      - watch:    clicks >= 3, conversions == 0, cost_usd < 10
      - ignore:   everything else (low traffic, already added)

    Returns:
      {
        "convert":  [terms to add as keywords],
        "negative": [terms to add as negatives],
        "watch":    [terms to flag in Asana next week],
        "ignore":   [skipped],
      }
    """
    existing = {kw.lower().strip() for kw in (existing_keywords or [])}

    _NEGATIVE_PATTERNS = [
        "وظيفة", "وظائف", "توظيف", "مطلوب", "راتب",
        "job", "jobs", "career", "hiring", "salary", "cv", "resume",
        "مجاناً", "مجانا", "مجاني", "free", "تحميل", "download",
        "شرح", "tutorial", "how to", "ما هو", "تعريف",
        "quickbooks", "zoho", "odoo", "xero", "sage",    # competitors
    ]

    buckets: dict[str, list] = {"convert": [], "negative": [], "watch": [], "ignore": []}

    for t in terms:
        q_lower = t["query"].lower()

        # Already excluded → skip
        if t["status"] == "EXCLUDED":
            buckets["ignore"].append(t)
            continue

        # Negative patterns
        if any(pat in q_lower for pat in _NEGATIVE_PATTERNS):
            buckets["negative"].append(t)
            continue

        # Already a keyword
        if q_lower in existing:
            buckets["ignore"].append(t)
            continue

        # Converting
        if t["clicks"] >= 3 and t["conversions"] >= 1:
            buckets["convert"].append(t)
            continue

        # Watch
        if t["clicks"] >= 3 and t["conversions"] == 0 and t["cost_usd"] < 10:
            buckets["watch"].append(t)
            continue

        buckets["ignore"].append(t)

    print(f"[gads] classify_search_terms: "
          f"{len(buckets['convert'])} convert, "
          f"{len(buckets['negative'])} negative, "
          f"{len(buckets['watch'])} watch, "
          f"{len(buckets['ignore'])} ignore")
    return buckets
