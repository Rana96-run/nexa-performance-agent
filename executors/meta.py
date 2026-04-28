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
from dotenv import load_dotenv

from executors.naming import prefixed as _naming_prefixed

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
        del link_data["picture"]  # video uses video_data not link_data
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


def _build_utm_url(base_url: str, campaign_name: str,
                   adset_name: str, ad_name: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return (
        f"{base_url}{sep}"
        f"utm_source=facebook&utm_medium=paid"
        f"&utm_campaign={campaign_name}"
        f"&utm_content={ad_name}"
    )


_VALID_META_BIDDING = ("HIGHEST_VOLUME", "TARGET_COST")


def create_full_campaign(
    product: str,
    campaign_type: str,
    language: str,
    audience_type: str,
    daily_budget_usd: float,
    page_id: str,
    objective: str = "OUTCOME_LEADS",
    optimization_goal: str = "LEAD_GENERATION",
    bid_strategy: str = "HIGHEST_VOLUME",
    target_cost_usd: float | None = None,
    pixel_id: str | None = None,
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

    Naming (enforced automatically):
      Campaign : Meta_{campaign_type}_{language}_{product}_{audience_type}
      Ad Set   : same name
      Ad       : Meta_{campaign_type}_{language}_{product}V1

    bid_strategy (enforced):
      HIGHEST_VOLUME — Meta spends budget to get max leads (no cost cap)
      TARGET_COST    — Meta targets a specific cost per result; pass target_cost_usd

    For OUTCOME_LEADS       : pass lead_form_id + page_id (Instant Form)
    For OUTCOME_CONVERSIONS : pass landing_url (UTMs auto-appended) + pixel_id

    targeting defaults: Saudi Arabia, age 25-55.
    Override with full Meta targeting spec dict.

    Returns dict with campaign_id, adset_id, ad_id.
    """
    if bid_strategy not in _VALID_META_BIDDING:
        raise ValueError(f"bid_strategy must be one of {_VALID_META_BIDDING}, got {bid_strategy!r}")
    if bid_strategy == "TARGET_COST" and not target_cost_usd:
        raise ValueError("TARGET_COST bid_strategy requires target_cost_usd")
    result: dict = {}
    full_name = f"{campaign_type}_{language}_{product}_{audience_type}"
    acct = account_id or best_account(_prefixed(full_name))

    # 1. Campaign — bid strategy set at campaign level
    camp_payload: dict = {
        "name":                  _prefixed(full_name),
        "objective":             objective,
        "status":                status,
        "daily_budget":          int(round(daily_budget_usd * 100)),
        "special_ad_categories": [],
    }
    if bid_strategy == "HIGHEST_VOLUME":
        camp_payload["bid_strategy"] = "LOWEST_COST_WITHOUT_CAP"
    else:  # TARGET_COST
        camp_payload["bid_strategy"] = "COST_CAP"
        camp_payload["bid_amount"]   = int(round(target_cost_usd * 100))

    campaign_r = _post(f"/{acct}/campaigns", camp_payload)
    campaign_id = campaign_r.get("id")
    campaign_name = _prefixed(full_name)
    result["campaign_id"] = campaign_id
    result["campaign_name"] = campaign_name
    result["bid_strategy"] = bid_strategy
    print(f"[meta] campaign created ({status}, {bid_strategy}): {campaign_name} -> {campaign_id}")

    # 2. Ad Set — Saudi Arabia default, age 25-55
    default_targeting = targeting or {
        "geo_locations": {"countries": ["SA"]},
        "age_min": 25,
        "age_max": 55,
    }
    promoted_object: dict = {"page_id": page_id}
    if pixel_id and objective == "OUTCOME_CONVERSIONS":
        promoted_object["pixel_id"] = pixel_id
        promoted_object["custom_event_type"] = "LEAD"

    adset_r = create_adset(
        campaign_id=campaign_id,
        name=full_name,
        daily_budget_usd=daily_budget_usd,
        optimization_goal=optimization_goal,
        billing_event="IMPRESSIONS",
        targeting=default_targeting,
        promoted_object=promoted_object,
        status=status,
    )
    adset_id = adset_r.get("id")
    result["adset_id"] = adset_id

    # 3. Creative + Ad
    ad_name_raw = f"{campaign_type}_{language}_{product}V1"
    ad_name = _prefixed(ad_name_raw)

    if lead_form_id and objective == "OUTCOME_LEADS":
        # Lead gen creative
        cid = create_lead_gen_creative(
            account_id=acct,
            name=ad_name,
            page_id=page_id,
            lead_form_id=lead_form_id,
            message=message,
            call_to_action=call_to_action,
        ).get("id")
    elif image_url or creative_id:
        # Conversion creative with UTM URL
        utm_url = _build_utm_url(landing_url or "https://qoyod.com",
                                 campaign_name, ad_name, ad_name)
        cid = creative_id or create_creative(
            account_id=acct,
            name=ad_name,
            page_id=page_id,
            image_url=image_url,
            message=message,
            link_url=utm_url,
            call_to_action=call_to_action,
        ).get("id")
    else:
        cid = None
        print("[meta] No creative supplied — add Ad manually in Ads Manager.")

    if cid:
        ad_r = create_ad(
            adset_id=adset_id,
            name=ad_name_raw,
            creative_id=cid,
            status=status,
        )
        result["ad_id"] = ad_r.get("id")
        result["ad_name"] = ad_name
    else:
        result["ad_id"] = None
        result["ad_name"] = None

    result["utm_mapping"] = {
        "utm_source":   "facebook",
        "utm_medium":   "paid",
        "utm_campaign": campaign_name,
        "utm_content":  ad_name,
    }
    print(f"\n[meta] Full campaign setup complete:")
    print(f"  Campaign : {campaign_name} (id={campaign_id})")
    print(f"  Ad Set   : {adset_id}")
    print(f"  Ad       : {result.get('ad_name', 'pending')} (id={result.get('ad_id', 'pending')})")
    return result


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
