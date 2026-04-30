"""
Meta Ads executor — all mutations require prior Slack approval.
Budget values are always USD; the API takes cents (multiply × 100).

Supported:
  Campaign    — create / set status / change budget
  Ad set      — create / set status / change budget / change audience
  Ad          — create / set status / change creative URL
  Creative    — create image/video creative
  Lead form   — create Instant Form (lead gen form) for OUTCOME_LEADS campaigns

Campaign naming convention: {Channel}_{Type}_{Language}_{Product}_{Audience}
  Channel:  Meta
  Type:     LeadGen | Remarketing | Awareness | Video | Conversion
  Language: AR | EN | AREN
  Product:  Invoice (E-Invoice) | Bookkeeping (Qbookkeeping) | Qflavours | General | {SeasonalName}
  Audience: Interests | Lookalike | Retargeting | Broad
  Rules:
    - Prospecting campaigns use Interests or Lookalike — never "Prospecting" alone
    - Retargeting campaigns use Retargeting — never combined with Prospecting
    - Product aliases auto-normalised: E-Invoice->Invoice, Qbookkeeping->Bookkeeping, etc.
  Examples: Meta_LeadGen_AR_Invoice_Interests
            Meta_LeadGen_AR_Invoice_Retargeting
            Meta_LeadGen_AR_Ramadan_Broad
"""
from __future__ import annotations

import os
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

from executors.naming import prefixed as _naming_prefixed
from config_creatives import (
    META_CRM_PIXEL_ID, META_CRM_PIXEL_NAME,
    meta_form_name, web_form_url as _web_form_url,
    normalise_product,
)

load_dotenv(override=True)

_BASE = "https://graph.facebook.com/v21.0"

_ACCOUNT_1 = os.getenv("META_AD_ACCOUNT_1", "")   # act_1366192231206913
_ACCOUNT_2 = os.getenv("META_AD_ACCOUNT_2", "")   # act_835030860363827
_DEFAULT_ACCOUNT = _ACCOUNT_1 or _ACCOUNT_2

_CHANNEL_PREFIX = "Meta"


def _prefixed(name: str) -> str:
    return _naming_prefixed(_CHANNEL_PREFIX, name)


def _token() -> str:
    return os.getenv("META_ACCESS_TOKEN", "")


def _post(path: str, payload: dict) -> dict:
    r = requests.post(f"{_BASE}{path}",
                      params={"access_token": _token()},
                      json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def _patch(object_id: str, payload: dict) -> dict:
    r = requests.post(f"{_BASE}/{object_id}",
                      params={"access_token": _token()},
                      json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict | None = None) -> dict:
    p = {"access_token": _token()}
    if params:
        p.update(params)
    r = requests.get(f"{_BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Re-export pause helpers from collector ────────────────────────────────────
from collectors.meta import pause_ad, pause_adset  # noqa: E402


# ── Account selection ─────────────────────────────────────────────────────────

def best_account(campaign_name: str, days: int = 30) -> str:
    """
    Return the Meta account_id whose existing campaigns with a name similar to
    `campaign_name` have driven the most HubSpot-qualified leads (SQLs) over
    the last N days.

    The match is keyword-based: each '_'-separated token in campaign_name is
    checked against campaign_name in BQ (case-insensitive LIKE).  The account
    with the highest SUM(leads_qualified) wins.

    Falls back to _DEFAULT_ACCOUNT when BQ is unreachable or no match found.
    """
    try:
        import os as _os
        from google.cloud import bigquery as _bq
        from google.oauth2 import service_account as _sa
        from datetime import date as _date, timedelta as _td

        project  = _os.getenv("BQ_PROJECT_ID")
        dataset  = _os.getenv("BQ_DATASET", "qoyod_marketing")
        key_path = _os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
        creds    = _sa.Credentials.from_service_account_file(key_path)
        client   = _bq.Client(project=project, credentials=creds)

        since = (_date.today() - _td(days=days)).isoformat()

        # Build LIKE conditions from the meaningful tokens in the name
        # (skip single-char tokens like 'AR'/'EN' which match too broadly)
        tokens = [t.lower() for t in campaign_name.replace("-", "_").split("_") if len(t) > 2]
        if not tokens:
            tokens = [campaign_name.lower()]
        like_clauses = " AND ".join(
            f"LOWER(c.campaign_name) LIKE '%{t}%'" for t in tokens
        )

        sql = f"""
            SELECT c.account_id,
                   SUM(h.leads_qualified) AS sqls
            FROM `{project}.{dataset}.campaigns_daily` c
            JOIN `{project}.{dataset}.hubspot_leads_module_daily` h
              ON  c.date = h.date
             AND  LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
            WHERE c.channel = 'meta'
              AND c.date >= '{since}'
              AND c.account_id IS NOT NULL
              AND ({like_clauses})
            GROUP BY c.account_id
            ORDER BY sqls DESC
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        if rows and rows[0].account_id:
            acct = rows[0].account_id
            if not acct.startswith("act_"):
                acct = f"act_{acct}"
            print(f"[meta] best account for '{campaign_name}' "
                  f"({int(rows[0].sqls or 0)} SQLs last {days}d): {acct}")
            return acct
    except Exception as e:
        print(f"[meta] best_account BQ query failed ({e}), using default")
    return _DEFAULT_ACCOUNT


# ── Budget ────────────────────────────────────────────────────────────────────

def update_campaign_budget(campaign_id: str, daily_budget_usd: float) -> dict:
    """Set a campaign's daily budget. `daily_budget_usd` is plain USD dollars."""
    cents = int(round(daily_budget_usd * 100))
    result = _patch(campaign_id, {"daily_budget": cents})
    print(f"[meta] budget updated -> campaign {campaign_id} = ${daily_budget_usd}/day")
    return result


# ── Status ────────────────────────────────────────────────────────────────────

def set_campaign_status(campaign_id: str, status: str) -> dict:
    """status: ACTIVE | PAUSED | ARCHIVED"""
    result = _patch(campaign_id, {"status": status})
    print(f"[meta] status updated -> campaign {campaign_id} = {status}")
    return result


def activate_campaign(campaign_id: str, daily_budget_usd: float | None = None) -> dict:
    if daily_budget_usd is not None:
        update_campaign_budget(campaign_id, daily_budget_usd)
    return set_campaign_status(campaign_id, "ACTIVE")


def pause_campaign(campaign_id: str) -> dict:
    return set_campaign_status(campaign_id, "PAUSED")


# ── Create campaign (always created PAUSED for human review) ──────────────────

def create_campaign(
    name: str,
    daily_budget_usd: float,
    objective: str = "OUTCOME_LEADS",
    account_id: str | None = None,
) -> dict:
    """
    Create a new campaign in PAUSED state.
    If account_id is None, picks the better-performing account from BQ.
    Follow naming convention: {Type}_{Language}_{Product}_{Variant}
    e.g. Meta_LeadGen_AR_Invoice_Retargeting
    """
    name = _prefixed(name)
    if account_id is None:
        account_id = best_account(name)
    payload = {
        "name":                  name,
        "objective":             objective,
        "status":                "PAUSED",
        "daily_budget":          int(round(daily_budget_usd * 100)),
        "special_ad_categories": [],
    }
    r = _post(f"/{account_id}/campaigns", payload)
    print(f"[meta] campaign created (PAUSED) -> {r.get('id')} | {name} | account={account_id}")
    return r


# ── Ad set ────────────────────────────────────────────────────────────────────

def create_adset(
    campaign_id: str,
    name: str,
    daily_budget_usd: float,
    optimization_goal: str = "LEAD_GENERATION",
    billing_event: str = "IMPRESSIONS",
    targeting: dict | None = None,
    promoted_object: dict | None = None,
    status: str = "PAUSED",
) -> dict:
    """
    Create an ad set in PAUSED state.
    targeting: Meta targeting spec dict (age, geo, interests, custom_audiences, etc.)
    promoted_object: e.g. {"page_id": "...", "pixel_id": "..."} for lead gen
    """
    name = _prefixed(name)  # enforce naming convention
    account_id = campaign_id.split("_")[0] if "_" in campaign_id else None
    # Fetch account from campaign
    c = _get(f"/{campaign_id}", {"fields": "account_id"})
    account_id = c.get("account_id", "")

    payload: dict = {
        "name":              name,
        "campaign_id":       campaign_id,
        "status":            status,
        "optimization_goal": optimization_goal,
        "billing_event":     billing_event,
        "daily_budget":      int(round(daily_budget_usd * 100)),
        "targeting":         targeting or {
            "geo_locations":     {"countries": ["SA"]},
            "age_min":           25,
            "age_max":           55,
        },
    }
    if promoted_object:
        payload["promoted_object"] = promoted_object

    r = _post(f"/act_{account_id}/adsets", payload)
    print(f"[meta] adset created ({status}) -> {r.get('id')} | {_prefixed(name)}")
    return r


def set_adset_status(adset_id: str, status: str) -> dict:
    """status: ACTIVE | PAUSED | ARCHIVED | DELETED"""
    r = _patch(adset_id, {"status": status})
    print(f"[meta] adset {adset_id} -> {status}")
    return r


def set_adset_budget(adset_id: str, daily_budget_usd: float) -> dict:
    r = _patch(adset_id, {"daily_budget": int(round(daily_budget_usd * 100))})
    print(f"[meta] adset {adset_id} budget -> ${daily_budget_usd}/day")
    return r


def set_adset_targeting(adset_id: str, targeting: dict) -> dict:
    """Update audience targeting on an ad set."""
    r = _patch(adset_id, {"targeting": targeting})
    print(f"[meta] adset {adset_id} targeting updated")
    return r


def set_adset_custom_audience(adset_id: str, audience_ids: list[str],
                               exclude: bool = False) -> dict:
    """Add custom audiences (include or exclude) to an existing ad set."""
    current = _get(f"/{adset_id}", {"fields": "targeting"})
    targeting = current.get("targeting", {})
    key = "exclusions" if exclude else "custom_audiences"
    targeting[key] = [{"id": aid} for aid in audience_ids]
    return set_adset_targeting(adset_id, targeting)


# ── Ad ────────────────────────────────────────────────────────────────────────

def create_ad(
    adset_id: str,
    name: str,
    creative_id: str | None = None,
    creative_spec: dict | None = None,
    status: str = "PAUSED",
) -> dict:
    """
    Create an ad in PAUSED state.
    Supply either creative_id (existing creative) or creative_spec (inline).
    creative_spec example: {"object_story_spec": {"page_id": "...", "link_data": {...}}}
    """
    c = _get(f"/{adset_id}", {"fields": "account_id,campaign_id"})
    account_id = c.get("account_id", "")

    name = _prefixed(name)
    payload: dict = {"name": name, "adset_id": adset_id, "status": status}
    if creative_id:
        payload["creative"] = {"creative_id": creative_id}
    elif creative_spec:
        payload["creative"] = creative_spec

    r = _post(f"/act_{account_id}/ads", payload)
    print(f"[meta] ad created ({status}) -> {r.get('id')} | {name}")
    return r


def set_ad_status(ad_id: str, status: str) -> dict:
    r = _patch(ad_id, {"status": status})
    print(f"[meta] ad {ad_id} -> {status}")
    return r


def create_creative(
    account_id: str,
    name: str,
    page_id: str,
    image_url: str | None = None,
    video_id: str | None = None,
    message: str = "",
    link_url: str = "",
    call_to_action: str = "LEARN_MORE",
) -> dict:
    """Create a Meta ad creative (image or video link ad)."""
    link_data: dict = {
        "message":       message,
        "link":          link_url,
        "call_to_action": {"type": call_to_action, "value": {"link": link_url}},
    }
    if image_url:
        link_data["picture"] = image_url

    story_spec: dict = {"page_id": page_id, "link_data": link_data}
    if video_id:
        link_data.pop("picture", None)  # video uses video_data not link_data
        story_spec = {
            "page_id": page_id,
            "video_data": {
                "video_id":      video_id,
                "call_to_action": {"type": call_to_action, "value": {"link": link_url}},
                "message":       message,
            },
        }

    payload = {
        "name":               name,
        "object_story_spec":  story_spec,
    }
    r = _post(f"/act_{account_id}/adcreatives", payload)
    print(f"[meta] creative created -> {r.get('id')} | {name}")
    return r


# ── Lead gen form (Instant Form) ──────────────────────────────────────────────

def create_lead_form(
    page_id: str,
    name: str,
    questions: list[dict] | None = None,
    privacy_policy_url: str = "https://qoyod.com/privacy-policy",
    locale: str = "ar_AR",
    thank_you_title: str = "شكراً لك",
    thank_you_body: str = "سنتواصل معك قريباً",
    account_id: str | None = None,
) -> dict:
    """
    Create a Meta Instant Form (Lead Generation form) attached to a Page.
    Returns the form dict including 'id' (lead_gen_form_id).

    questions example:
      [
        {"type": "FULL_NAME"},
        {"type": "EMAIL"},
        {"type": "PHONE"},
        {"type": "CUSTOM", "label": "اسم الشركة", "key": "company_name"},
      ]
    The form id is then used in the creative via:
      {"call_to_action": {"type": "SIGN_UP", "value": {"lead_gen_form_id": "<id>"}}}

    account_id: if None, picks the better-performing account from BQ.
    """
    if account_id is None:
        account_id = best_account(name)
    if questions is None:
        questions = [
            {"type": "FULL_NAME"},
            {"type": "EMAIL"},
            {"type": "PHONE"},
        ]
    payload = {
        "name":            name,
        "page_id":         page_id,
        "locale":          locale,
        "questions":       questions,
        "privacy_policy":  {"url": privacy_policy_url, "link_text": "Privacy Policy"},
        "thank_you_page":  {"title": thank_you_title, "body": thank_you_body,
                            "button_text": "زيارة الموقع",
                            "website_url": "https://qoyod.com"},
        "follow_up_action_url": "https://qoyod.com",
    }
    act = account_id if account_id.startswith("act_") else f"act_{account_id}"
    r = _post(f"/{act}/leadgen_forms", payload)
    print(f"[meta] lead form created -> {r.get('id')} | {name}")
    return r


def create_lead_gen_creative(
    account_id: str,
    name: str,
    page_id: str,
    lead_form_id: str,
    image_hash: str | None = None,
    message: str = "",
    call_to_action: str = "SIGN_UP",
) -> dict:
    """
    Create a creative for a lead gen ad that references an Instant Form.
    image_hash: upload an image first via /act_{account_id}/adimages to get the hash.
    """
    link_data: dict = {
        "message":         message,
        "call_to_action":  {"type": call_to_action,
                            "value": {"lead_gen_form_id": lead_form_id}},
    }
    if image_hash:
        link_data["image_hash"] = image_hash

    payload = {
        "name":              name,
        "object_story_spec": {"page_id": page_id, "link_data": link_data},
    }
    act = account_id if account_id.startswith("act_") else f"act_{account_id}"
    r = _post(f"/{act}/adcreatives", payload)
    print(f"[meta] lead gen creative created -> {r.get('id')} | {name}")
    return r


def _build_utm_url(base_url: str,
                   campaign_name: str | None = None,
                   adset_name: str | None = None,
                   ad_name: str | None = None) -> str:
    """
    Build the landing page URL with ALL required UTM + HubSpot tracking parameters.
    Every value is a Meta dynamic parameter — resolved at ad-serve time by Meta.

    HubSpot property → Meta dynamic value (what Meta replaces it with):
      utm_source    → {{site_source_name}}  e.g. "facebook", "instagram", "audience_network"
      utm_medium    → {{placement}}          e.g. "feed", "story", "reels", "search"
      utm_campaign  → {{campaign.name}}      campaign name as set in Ads Manager
      utm_audience  → {{adset.name}}         adset name as set in Ads Manager
      utm_content   → {{ad.name}}            ad name as set in Ads Manager
      campaign_id   → {{campaign.id}}        numeric campaign ID
      ad_group_id   → {{adset.id}}           numeric adset ID
      ad_id         → {{ad.id}}              numeric ad ID

    All dynamic — no hardcoded strings. If campaign/adset/ad is renamed in Ads Manager,
    UTMs update automatically. utm_source correctly splits facebook vs instagram traffic.

    NEVER remove or rename these parameters — HubSpot lead module depends on all of them.
    """
    # Use raw string concat to preserve {{ }} — urlencode would encode the braces
    sep = "&" if "?" in base_url else "?"
    params = (
        f"utm_source={{{{site_source_name}}}}"
        f"&utm_medium={{{{placement}}}}"
        f"&utm_campaign={{{{campaign.name}}}}"
        f"&utm_audience={{{{adset.name}}}}"
        f"&utm_content={{{{ad.name}}}}"
        f"&campaign_id={{{{campaign.id}}}}"
        f"&ad_group_id={{{{adset.id}}}}"
        f"&ad_id={{{{ad.id}}}}"
    )
    return base_url + sep + params


def best_audience(product: str | None = None, days: int = 30) -> dict:
    """
    Return the Meta targeting dict from the best-performing Meta campaign
    by CPQL over the last N days, optionally filtered by product keyword.

    Falls back to Saudi Arabia defaults (age 25–55) if BQ or API fails.
    """
    _default = {
        "geo_locations": {"countries": ["SA"]},
        "age_min": 25,
        "age_max": 55,
    }
    try:
        import os as _os
        from google.cloud import bigquery as _bq
        from google.oauth2 import service_account as _sa
        from datetime import date as _date, timedelta as _td

        project  = _os.getenv("BQ_PROJECT_ID")
        dataset  = _os.getenv("BQ_DATASET", "qoyod_marketing")
        key_path = _os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
        creds    = _sa.Credentials.from_service_account_file(key_path)
        bq       = _bq.Client(project=project, credentials=creds)

        since = (_date.today() - _td(days=days)).isoformat()
        prod_filter = ""
        if product:
            prod_norm = normalise_product(product)
            if prod_norm != "generic":
                prod_filter = f"AND LOWER(c.campaign_name) LIKE '%{prod_norm}%'"

        sql = f"""
            WITH hs AS (
              SELECT date, lead_utm_campaign,
                     SUM(leads_qualified) AS sqls
              FROM `{project}.{dataset}.hubspot_leads_module_daily`
              GROUP BY date, lead_utm_campaign
            )
            SELECT c.campaign_name,
                   SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0)) AS cpql
            FROM `{project}.{dataset}.campaigns_daily` c
            LEFT JOIN hs ON c.date = hs.date
              AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
            WHERE c.channel = 'meta' AND c.date >= '{since}'
              {prod_filter}
            GROUP BY c.campaign_name
            HAVING SUM(c.spend) >= 50 AND SUM(hs.sqls) > 0
            ORDER BY cpql ASC LIMIT 1
        """
        rows = list(bq.query(sql).result())
        if not rows:
            print("[meta] best_audience: no qualifying campaigns — using default targeting")
            return _default

        best_camp = rows[0].campaign_name
        print(f"[meta] best_audience: '{best_camp}' CPQL=${float(rows[0].cpql):.0f} — pulling adset targeting")

        # Find that campaign's adset targeting via Meta API
        for acct in [a for a in [_ACCOUNT_1, _ACCOUNT_2] if a]:
            data = _get(f"/{acct}/campaigns", {
                "fields": "id,name", "limit": 100,
            })
            for camp in data.get("data", []):
                if camp.get("name", "").lower() == best_camp.lower():
                    adsets = _get(f"/{camp['id']}/adsets", {"fields": "targeting", "limit": 5})
                    for adset in adsets.get("data", []):
                        t = adset.get("targeting")
                        if t:
                            print(f"[meta] best_audience: targeting pulled from '{best_camp}'")
                            return t
    except Exception as e:
        print(f"[meta] best_audience failed ({e}) — using default targeting")
    return _default


_VALID_META_BIDDING = ("HIGHEST_VOLUME", "TARGET_COST")

# Conversion location options
_CONVERSION_LOCATION_WEBSITE      = "WEBSITE"
_CONVERSION_LOCATION_INSTANT_FORM = "INSTANT_FORMS"

# Performance goal → Meta optimization_goal mapping
# "Maximise number of leads"            → LEAD_GENERATION
# "Maximise number of conversion leads" → QUALITY_LEAD
PERFORMANCE_GOALS = {
    "leads":            "LEAD_GENERATION",
    "conversion_leads": "QUALITY_LEAD",
    # aliases
    "quality":          "QUALITY_LEAD",
    "volume":           "LEAD_GENERATION",
}


def create_full_campaign(
    product: str,
    campaign_type: str,
    language: str,
    audience_type: str,
    daily_budget_usd: float,
    page_id: str,
    conversion_location: str = "INSTANT_FORM",
    performance_goal: str = "leads",
    bid_strategy: str = "HIGHEST_VOLUME",
    target_cost_usd: float | None = None,
    landing_url: str | None = None,
    lead_form_id: str | None = None,
    creative_id: str | None = None,
    image_url: str | None = None,
    message: str = "",
    call_to_action: str = "SIGN_UP",
    targeting: dict | None = None,
    account_id: str | None = None,
    status: str = "PAUSED",
) -> dict:
    """
    Full Meta campaign setup in one call.

    conversion_location (required):
      "INSTANT_FORM" — leads captured in Meta native form (no pixel needed)
                       form auto-selected from config_creatives by product
      "WEBSITE"      — leads captured on landing page via Qoyod_CRM_PIXEL
                       URL auto-selected from config_creatives if not supplied
                       ALL UTM + HubSpot tracking params appended automatically

    performance_goal:
      "leads"            → Maximise number of leads       (LEAD_GENERATION)
      "conversion_leads" → Maximise number of conversion leads (QUALITY_LEAD)

    bid_strategy:
      "HIGHEST_VOLUME" — Meta optimises for max results, no cost cap (default)
      "TARGET_COST"    — target a specific CPL; pass target_cost_usd

    targeting: If None, pulled from best-performing Meta campaign by CPQL in BQ.
               Falls back to SA defaults (age 25–55) if BQ query fails.

    Naming (enforced automatically):
      Campaign : Meta_{campaign_type}_{language}_{product}_{audience_type}
      Ad Set   : same name
      Ad       : Meta_{campaign_type}_{language}_{product}V1

    UTM parameters (WEBSITE only — injected into every landing URL):
      utm_source, utm_campaign, utm_audience, utm_content,
      campaign_id={{campaign.id}}, ad_group_id={{adset.id}}, ad_id={{ad.id}}
    """
    # Validate
    if bid_strategy not in _VALID_META_BIDDING:
        raise ValueError(f"bid_strategy must be one of {_VALID_META_BIDDING}")
    if bid_strategy == "TARGET_COST" and not target_cost_usd:
        raise ValueError("TARGET_COST requires target_cost_usd")
    conv_loc = conversion_location.upper().replace(" ", "_")
    if conv_loc not in ("INSTANT_FORM", "INSTANT_FORMS", "WEBSITE"):
        raise ValueError(f"conversion_location must be INSTANT_FORM or WEBSITE, got {conversion_location!r}")
    conv_loc = "INSTANT_FORMS" if "INSTANT" in conv_loc else "WEBSITE"

    # Resolve optimization goal
    opt_goal = PERFORMANCE_GOALS.get(performance_goal.lower(), "LEAD_GENERATION")
    objective = "OUTCOME_LEADS"

    result: dict = {}
    full_name = f"{campaign_type}_{language}_{product}_{audience_type}"
    adset_name = _prefixed(full_name)
    acct = account_id or best_account(_prefixed(full_name))

    # ── Resolve form / pixel / URL ────────────────────────────────────────────
    if conv_loc == "INSTANT_FORMS":
        # Auto-select form name if not supplied (caller may pass lead_form_id directly)
        if not lead_form_id:
            form_name = meta_form_name(product, intent="higher")
            print(f"[meta] Instant form: {form_name} (resolve ID in Ads Manager or pass lead_form_id)")
            result["form_name"] = form_name
            result["form_note"] = "Attach form in Ads Manager or pass lead_form_id to create_full_campaign()"
        else:
            result["form_id"] = lead_form_id
        result["pixel_id"] = None   # pixel not used for instant form
    else:
        # WEBSITE — use Qoyod_CRM_PIXEL always
        pixel_id = META_CRM_PIXEL_ID
        result["pixel_id"]   = pixel_id
        result["pixel_name"] = META_CRM_PIXEL_NAME
        # Auto-select landing URL from config if not supplied
        if not landing_url:
            landing_url = _web_form_url(product)
            print(f"[meta] Auto-selected landing URL for '{product}': {landing_url}")

    # ── Resolve targeting from best-performing campaign ───────────────────────
    if targeting is None:
        targeting = best_audience(product=product)

    # 1. Campaign
    camp_payload: dict = {
        "name":                  _prefixed(full_name),
        "objective":             objective,
        "status":                status,
        "daily_budget":          int(round(daily_budget_usd * 100)),
        "special_ad_categories": [],
    }
    if bid_strategy == "HIGHEST_VOLUME":
        camp_payload["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"
    else:
        camp_payload["bid_strategy"] = "COST_CAP"
        camp_payload["bid_amount"]   = int(round(target_cost_usd * 100))

    campaign_r   = _post(f"/{acct}/campaigns", camp_payload)
    campaign_id  = campaign_r.get("id")
    campaign_name = _prefixed(full_name)
    result["campaign_id"]   = campaign_id
    result["campaign_name"] = campaign_name
    result["bid_strategy"]  = bid_strategy
    result["performance_goal"] = opt_goal
    print(f"[meta] campaign created ({status}, {bid_strategy}, {opt_goal}): {campaign_name} -> {campaign_id}")

    # 2. Ad Set
    promoted_object: dict = {"page_id": page_id}
    if conv_loc == "WEBSITE":
        promoted_object["pixel_id"]          = META_CRM_PIXEL_ID
        promoted_object["custom_event_type"] = "LEAD"

    adset_payload: dict = {
        "name":              adset_name,
        "campaign_id":       campaign_id,
        "status":            status,
        "optimization_goal": opt_goal,
        "billing_event":     "IMPRESSIONS",
        "daily_budget":      int(round(daily_budget_usd * 100)),
        "destination_type":  conv_loc,        # INSTANT_FORMS | WEBSITE
        "targeting":         targeting,
        "promoted_object":   promoted_object,
    }
    adset_r  = _post(f"/{acct}/adsets", adset_payload)
    adset_id = adset_r.get("id")
    result["adset_id"] = adset_id
    print(f"[meta] adset created ({conv_loc}, {opt_goal}): {adset_name} -> {adset_id}")

    # 3. Ad name
    ad_name_raw = f"{campaign_type}_{language}_{product}V1"
    ad_name     = _prefixed(ad_name_raw)

    # 4. Creative + Ad
    cid = None
    if conv_loc == "INSTANT_FORMS" and lead_form_id:
        cid = create_lead_gen_creative(
            account_id=acct,
            name=ad_name,
            page_id=page_id,
            lead_form_id=lead_form_id,
            message=message,
            call_to_action=call_to_action,
        ).get("id")
    elif conv_loc == "WEBSITE" and (image_url or creative_id):
        # Build URL with full UTM + HubSpot tracking params
        utm_url = _build_utm_url(landing_url, campaign_name, adset_name, ad_name)
        result["final_url"] = utm_url
        print(f"[meta] WEB_FORM URL (with all UTM params): {utm_url}")
        cid = creative_id or create_creative(
            account_id=acct,
            name=ad_name,
            page_id=page_id,
            image_url=image_url,
            message=message,
            link_url=utm_url,
            call_to_action=call_to_action,
        ).get("id")
    elif conv_loc == "WEBSITE" and not (image_url or creative_id):
        # URL ready — remind caller to attach creative
        utm_url = _build_utm_url(landing_url, campaign_name, adset_name, ad_name)
        result["final_url"] = utm_url
        print(f"[meta] WEB_FORM URL: {utm_url}")
        print("[meta] No creative supplied — attach creative in Ads Manager with this URL.")

    if cid:
        ad_r = create_ad(adset_id=adset_id, name=ad_name_raw, creative_id=cid, status=status)
        result["ad_id"]   = ad_r.get("id")
        result["ad_name"] = ad_name
    else:
        result["ad_id"]   = None
        result["ad_name"] = ad_name  # name is ready even if ad not yet created

    # Full UTM mapping — always present for reference (all Meta dynamic values)
    result["utm_mapping"] = {
        "utm_source":   "{{site_source_name}}",
        "utm_medium":   "{{placement}}",
        "utm_campaign": "{{campaign.name}}",
        "utm_audience": "{{adset.name}}",
        "utm_content":  "{{ad.name}}",
        "campaign_id":  "{{campaign.id}}",
        "ad_group_id":  "{{adset.id}}",
        "ad_id":        "{{ad.id}}",
    }

    print(f"\n[meta] Full campaign setup complete:")
    print(f"  Campaign          : {campaign_name} (id={campaign_id})")
    print(f"  Ad Set            : {adset_name} (id={adset_id})")
    print(f"  Conversion loc    : {conv_loc}")
    print(f"  Performance goal  : {opt_goal}")
    if conv_loc == "INSTANT_FORMS":
        print(f"  Form              : {result.get('form_name', lead_form_id)}")
    else:
        print(f"  Pixel             : {META_CRM_PIXEL_NAME} ({META_CRM_PIXEL_ID})")
        print(f"  Landing URL       : {result.get('final_url', landing_url)}")
    print(f"  Ad                : {ad_name} (id={result.get('ad_id', 'pending — attach in Ads Manager')})")
    return result


def list_creatives(limit: int = 20, account_id: str | None = None) -> list[dict]:
    """
    List ad creatives for a Meta ad account.
    Returns list of {id, name, thumbnail_url, object_type}.
    Also queries adimages for additional asset visibility.
    """
    acct = account_id or _DEFAULT_ACCOUNT
    if not acct:
        raise ValueError("No META_AD_ACCOUNT_1 or META_AD_ACCOUNT_2 set in env")

    results: list[dict] = []

    # 1. Ad Creatives
    try:
        data = _get(f"/{acct}/adcreatives", {
            "fields": "id,name,thumbnail_url,object_type,status",
            "limit":  limit,
        })
        for c in data.get("data", []):
            results.append({
                "id":           c.get("id"),
                "name":         c.get("name"),
                "thumbnail_url": c.get("thumbnail_url"),
                "object_type":  c.get("object_type"),
                "source":       "adcreatives",
            })
    except Exception as e:
        print(f"[meta] list_creatives adcreatives error: {e}")

    # 2. Ad Images (additional asset inventory)
    try:
        img_data = _get(f"/{acct}/adimages", {
            "fields": "hash,name,permalink_url,creatives",
            "limit":  limit,
        })
        for img in img_data.get("data", []):
            results.append({
                "id":           img.get("hash"),
                "name":         img.get("name"),
                "thumbnail_url": img.get("permalink_url"),
                "object_type":  "IMAGE",
                "source":       "adimages",
            })
    except Exception as e:
        print(f"[meta] list_creatives adimages error: {e}")

    print(f"[meta] list_creatives -> {len(results)} assets (account={acct})")
    return results


def create_lead_gen_adset(
    campaign_id: str,
    name: str,
    daily_budget_usd: float,
    page_id: str,
    pixel_id: str | None = None,
    targeting: dict | None = None,
    status: str = "PAUSED",
) -> dict:
    """
    Create an ad set optimized for LEAD_GENERATION (pairs with OUTCOME_LEADS campaign).
    promoted_object requires page_id; pixel_id optional but recommended for attribution.
    """
    promoted_object: dict = {"page_id": page_id}
    if pixel_id:
        promoted_object["pixel_id"] = pixel_id
    return create_adset(
        campaign_id=campaign_id,
        name=name,
        daily_budget_usd=daily_budget_usd,
        optimization_goal="LEAD_GENERATION",
        billing_event="IMPRESSIONS",
        targeting=targeting,
        promoted_object=promoted_object,
        status=status,
    )
