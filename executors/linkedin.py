"""
LinkedIn Ads executor — full campaign setup surface.
All mutations create resources in DRAFT state unless explicitly enabled.

Supported:
  Campaign  — create / set status (UI: Campaign; API: adCampaignGroups)
  Ad Set    — create with full config: bidding, audience, region, landing/form
  Ad        — create sponsored content / lead gen form ad
  Targeting — audience segments, matched audiences (HubSpot lists)

LinkedIn UI now matches Meta — Campaign / Ad Set / Ad (updated 2025).
API endpoint names are unchanged internally.

Conversion tracking — LinkedIn uses HubSpot Lead Event Sync:
  LinkedIn Insight Tag fires on page load.
  HubSpot sends "Lead" conversion event back to LinkedIn via the
  LinkedIn-HubSpot integration (Campaign Manager → Analyze → Conversion Tracking).
  No manual pixel needed — the HubSpot form submission IS the conversion event.
  Conversion action name in LinkedIn: "HubSpot Lead" (set up once in account).

LinkedIn UTM mapping (DIFFERENT from all other channels):
  Campaign → utm_campaign   name: LinkedIn_{Product}
                             e.g.  LinkedIn_Invoice | LinkedIn_Bookkeeping
  Ad Set   → utm_audience   name: LinkedIn_{Type}_{Language}_{Audience}
                             e.g.  LinkedIn_LeadGen_AR_Interests
  Ad       → utm_content    name: LinkedIn_{CreativeVariant}
                             e.g.  LinkedIn_VideoV1_AR | LinkedIn_CarouselV2_EN

  Audience rules:
    - Prospecting → use Interests or Lookalike. "Prospecting" alone is invalid.
    - Retargeting → use Retargeting. Never combine with Prospecting.
  Product aliases auto-normalised: E-Invoice→Invoice, Qbookkeeping→Bookkeeping, qflavours→Qflavours

UTM auto-build for conversion campaigns:
  ?utm_source=linkedin&utm_medium=paid
  &utm_campaign={campaign_name}
  &utm_audience={adset_name}
  &utm_content={ad_name}

Lead Gen Form campaigns: attach lead_gen_form_urn instead of a landing URL.

Bidding options (costType):
  CPM  — cost per 1000 impressions (brand/awareness)
  CPC  — cost per click (conversion/traffic)
  CPV  — cost per video view
  NONE — let LinkedIn optimise (automated / max delivery)

Saudi Arabia geo URN: urn:li:geo:101470098

Common targeting facet URNs:
  Locations : urn:li:adTargetingFacet:locations
  Job funcs : urn:li:adTargetingFacet:jobFunctions
  Industries: urn:li:adTargetingFacet:industries
  Seniority : urn:li:adTargetingFacet:seniorities
  Company sz: urn:li:adTargetingFacet:staffCountRanges
  Matched   : urn:li:adTargetingFacet:audienceMatchingSegments
"""
from __future__ import annotations

import os
import time
import requests
from dotenv import load_dotenv

from executors.naming import prefixed as _naming_prefixed

load_dotenv(override=True)

_TOKEN       = os.getenv("LI_ACCESS_TOKEN")
_ACCOUNT_URN = os.getenv("LI_AD_ACCOUNT_URN")          # urn:li:sponsoredAccount:XXXXX
_ACCOUNT_ID  = (_ACCOUNT_URN or "").split(":")[-1]
_ORG_URN     = os.getenv("LI_ORGANIZATION_URN")         # urn:li:organization:XXXXX
_BASE        = "https://api.linkedin.com/rest"
_VER         = "202502"

_CHANNEL_PREFIX = "LinkedIn"

# Saudi Arabia geo URN (used as default region)
_SA_GEO_URN = "urn:li:geo:101470098"

# Default audience: Finance & Accounting job functions in Saudi Arabia
# Job function URNs: 7=Accounting, 8=Finance, 4=Business Development
_DEFAULT_JOB_FUNCTIONS = [
    "urn:li:function:7",   # Accounting
    "urn:li:function:8",   # Finance
    "urn:li:function:4",   # Business Development
]

# Seniority URNs: 3=Manager, 4=Director, 5=VP, 6=CXO, 7=Partner, 8=Owner
_DEFAULT_SENIORITIES = [
    "urn:li:seniority:3",  # Manager
    "urn:li:seniority:4",  # Director
    "urn:li:seniority:5",  # VP
    "urn:li:seniority:6",  # CXO
    "urn:li:seniority:8",  # Owner
]


def _prefixed(name: str) -> str:
    return _naming_prefixed(_CHANNEL_PREFIX, name)


def _headers() -> dict:
    token = os.getenv("LI_ACCESS_TOKEN") or _TOKEN
    return {
        "Authorization":             f"Bearer {token}",
        "LinkedIn-Version":          _VER,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type":              "application/json",
    }


def _post(path: str, payload: dict) -> dict:
    r = requests.post(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=15)
    if not r.ok:
        raise RuntimeError(f"LinkedIn POST {path} -> {r.status_code}: {r.text[:400]}")
    # Return ID from header + empty body (LinkedIn 201s return no body)
    result = r.json() if r.content else {}
    result["_restli_id"] = r.headers.get("x-restli-id", "")
    return result


def _patch(path: str, payload: dict) -> dict:
    r = requests.patch(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=15)
    if not r.ok:
        raise RuntimeError(f"LinkedIn PATCH {path} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{_BASE}{path}", headers=_headers(), params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _build_utm_url(base_url: str, campaign_name: str,
                   adset_name: str, ad_name: str) -> str:
    """Append standard UTM params to a landing page URL."""
    sep = "&" if "?" in base_url else "?"
    return (
        f"{base_url}{sep}"
        f"utm_source=linkedin&utm_medium=paid"
        f"&utm_campaign={campaign_name}"
        f"&utm_audience={adset_name}"
        f"&utm_content={ad_name}"
    )


# ── Campaign (UI) — API: adCampaignGroups ────────────────────────────────────
# LinkedIn renamed Campaign Group → Campaign in the UI (2025).
# API endpoint (adCampaignGroups) is unchanged.
# Initial status must be DRAFT — API rejects PAUSED on creation.

def create_campaign_group(name: str, status: str = "DRAFT") -> dict:
    """Create a Campaign (top level). Name: LinkedIn_{Product}."""
    name = _prefixed(name)
    now_ms = int(time.time() * 1000)
    payload = {
        "account":     _ACCOUNT_URN,
        "name":        name,
        "status":      status,
        "runSchedule": {"start": now_ms},
    }
    r = _post(f"/adAccounts/{_ACCOUNT_ID}/adCampaignGroups", payload)
    cg_id = r.get("_restli_id") or r.get("id")
    print(f"[li] Campaign created ({status}): {name} -> id={cg_id}")
    return {"id": cg_id, "name": name, "status": status}


# ── Ad Set (UI) — API: adCampaigns ───────────────────────────────────────────
# LinkedIn renamed Campaign → Ad Set in the UI (2025).
# API endpoint (adCampaigns) is unchanged.

def create_adset(
    name: str,
    daily_budget_usd: float,
    campaign_group_id: str,
    objective: str = "LEAD_GENERATION",
    cost_type: str = "CPC",
    bid_amount_usd: float | None = None,
    geo_urns: list[str] | None = None,
    job_function_urns: list[str] | None = None,
    seniority_urns: list[str] | None = None,
    audience_match_urns: list[str] | None = None,
    landing_url: str | None = None,
    status: str = "DRAFT",
) -> dict:
    """
    Create a fully configured Ad Set.

    objective : LEAD_GENERATION | WEBSITE_CONVERSIONS | BRAND_AWARENESS | ENGAGEMENT | VIDEO_VIEWS
    cost_type : CPC | CPM | CPV | NONE (automated max delivery)
    bid_amount_usd : optional manual bid; omit for automated
    geo_urns  : defaults to Saudi Arabia only
    job_function_urns : defaults to Accounting + Finance + Business Dev
    seniority_urns    : defaults to Manager → Owner
    audience_match_urns : matched/retargeting segments (optional)
    landing_url : for WEBSITE_CONVERSIONS campaigns (UTMs added automatically)
    """
    adset_name = _prefixed(name)
    now_ms = int(time.time() * 1000)

    # Build targeting criteria
    targeting_and: list[dict] = []

    # Region (default: Saudi Arabia)
    geos = geo_urns or [_SA_GEO_URN]
    targeting_and.append(
        {"or": {"urn:li:adTargetingFacet:locations": geos}}
    )

    # Job functions
    funcs = job_function_urns or _DEFAULT_JOB_FUNCTIONS
    targeting_and.append(
        {"or": {"urn:li:adTargetingFacet:jobFunctions": funcs}}
    )

    # Seniority
    seniors = seniority_urns or _DEFAULT_SENIORITIES
    targeting_and.append(
        {"or": {"urn:li:adTargetingFacet:seniorities": seniors}}
    )

    # Matched audiences (retargeting / lookalike) — optional
    if audience_match_urns:
        targeting_and.append(
            {"or": {"urn:li:adTargetingFacet:audienceMatchingSegments": audience_match_urns}}
        )

    payload: dict = {
        "account":       _ACCOUNT_URN,
        "campaignGroup": f"urn:li:sponsoredCampaignGroup:{campaign_group_id}",
        "name":          adset_name,
        "status":        status,
        "type":          "SPONSORED_UPDATES",
        "objectiveType": objective,
        "dailyBudget":   {"amount": str(daily_budget_usd), "currencyCode": "USD"},
        "costType":      cost_type,
        "runSchedule":   {"start": now_ms},
        "locale":        {"country": "US", "language": "en"},
        "offsiteDeliveryEnabled": False,
        "targetingCriteria": {"include": {"and": targeting_and}},
    }

    # Manual bid (optional — omit for automated delivery)
    if bid_amount_usd and cost_type != "NONE":
        payload["unitCost"] = {"amount": str(bid_amount_usd), "currencyCode": "USD"}

    # Landing page for conversion campaigns
    if landing_url and objective == "WEBSITE_CONVERSIONS":
        payload["destinationUrl"] = landing_url  # UTMs added at ad level

    r = _post(f"/adAccounts/{_ACCOUNT_ID}/adCampaigns", payload)
    adset_id = r.get("_restli_id") or r.get("id")
    print(f"[li] Ad Set created ({status}): {adset_name} -> id={adset_id}")
    return {"id": adset_id, "name": adset_name, "status": status}


# ── Ad — sponsored content or lead gen form ───────────────────────────────────

def create_ad_sponsored(
    name: str,
    adset_id: str,
    share_urn: str,
) -> dict:
    """
    Create a sponsored content Ad from an existing organic post.
    share_urn: urn:li:ugcPost:XXXX or urn:li:share:XXXX
    Ad name: LinkedIn_{CreativeVariant} e.g. LinkedIn_VideoV1_AR
    """
    ad_name = _prefixed(name)
    payload = {
        "campaign":  f"urn:li:sponsoredCampaign:{adset_id}",
        "reference": share_urn,
        "status":    "DRAFT",
        "name":      ad_name,
        "type":      "SPONSORED_STATUS_UPDATE",
    }
    r = _post("/adCreatives", payload)
    ad_id = r.get("_restli_id") or r.get("id")
    print(f"[li] Ad (sponsored) created: {ad_name} -> id={ad_id}")
    return {"id": ad_id, "name": ad_name}


def create_ad_lead_gen(
    name: str,
    adset_id: str,
    share_urn: str,
    lead_gen_form_urn: str,
) -> dict:
    """
    Create a Lead Gen Form Ad.
    name: LinkedIn_{CreativeVariant} e.g. LinkedIn_InvoiceFormV1_AR
    lead_gen_form_urn: urn:li:leadGenForm:XXXX
    share_urn: organic post to sponsor
    """
    ad_name = _prefixed(name)
    payload = {
        "campaign":       f"urn:li:sponsoredCampaign:{adset_id}",
        "reference":      share_urn,
        "leadGenFormRef": lead_gen_form_urn,
        "status":         "DRAFT",
        "name":           ad_name,
        "type":           "SPONSORED_STATUS_UPDATE",
    }
    r = _post("/adCreatives", payload)
    ad_id = r.get("_restli_id") or r.get("id")
    print(f"[li] Ad (lead gen form) created: {ad_name} -> id={ad_id}")
    return {"id": ad_id, "name": ad_name}


# ── Full campaign setup (one call) ────────────────────────────────────────────

def create_full_campaign(
    product: str,
    campaign_type: str,
    language: str,
    audience_type: str,
    daily_budget_usd: float,
    objective: str = "LEAD_GENERATION",
    cost_type: str = "CPC",
    bid_amount_usd: float | None = None,
    landing_url: str | None = None,
    lead_gen_form_urn: str | None = None,
    share_urn: str | None = None,
    geo_urns: list[str] | None = None,
    job_function_urns: list[str] | None = None,
    seniority_urns: list[str] | None = None,
    audience_match_urns: list[str] | None = None,
) -> dict:
    """
    Full LinkedIn campaign setup in one call.

    Naming (enforced automatically):
      Campaign: LinkedIn_{product}
      Ad Set:   LinkedIn_{campaign_type}_{language}_{audience_type}
      Ad:       LinkedIn_{product}V1_{language}  (placeholder — update with real creative)

    For LEAD_GENERATION:   pass lead_gen_form_urn + share_urn
    For WEBSITE_CONVERSIONS: pass landing_url (UTMs auto-appended) + share_urn

    Returns dict with campaign_id, adset_id, ad_id (if share_urn provided).

    Example:
      create_full_campaign(
          product="Invoice",
          campaign_type="LeadGen",
          language="AR",
          audience_type="Interests",
          daily_budget_usd=10.0,
          objective="LEAD_GENERATION",
          cost_type="CPC",
          lead_gen_form_urn="urn:li:leadGenForm:12345",
          share_urn="urn:li:ugcPost:67890",
      )
    """
    result: dict = {}

    # 1. Campaign
    cg = create_campaign_group(product)
    campaign_id = cg["id"]
    campaign_name = cg["name"]
    result["campaign_id"] = campaign_id
    result["campaign_name"] = campaign_name

    # 2. Ad Set
    adset_name_raw = f"{campaign_type}_{language}_{audience_type}"
    adset = create_adset(
        name=adset_name_raw,
        daily_budget_usd=daily_budget_usd,
        campaign_group_id=campaign_id,
        objective=objective,
        cost_type=cost_type,
        bid_amount_usd=bid_amount_usd,
        geo_urns=geo_urns,
        job_function_urns=job_function_urns,
        seniority_urns=seniority_urns,
        audience_match_urns=audience_match_urns,
        landing_url=landing_url,
    )
    adset_id = adset["id"]
    adset_name = adset["name"]
    result["adset_id"] = adset_id
    result["adset_name"] = adset_name

    # 3. Ad (only if share_urn provided — can be added later otherwise)
    if share_urn:
        ad_name_raw = f"{product}V1_{language}"
        if objective == "LEAD_GENERATION" and lead_gen_form_urn:
            ad = create_ad_lead_gen(
                name=ad_name_raw,
                adset_id=adset_id,
                share_urn=share_urn,
                lead_gen_form_urn=lead_gen_form_urn,
            )
        else:
            # Conversion / awareness — sponsored content ads inherit the URL from the
            # original organic post (share_urn). LinkedIn API does not support
            # overriding the click URL on sponsored content ads via adCreatives.
            # The UTM URL is returned in utm_mapping so the team can manually
            # update the organic post before sponsoring, or use a UTM-tagged post.
            if landing_url:
                utm_url = _build_utm_url(landing_url, campaign_name, adset_name, f"LinkedIn_{product}V1_{language}")
                print(f"[li] Target UTM URL (apply to organic post before sponsoring): {utm_url}")
                result["utm_url_for_post"] = utm_url
            ad = create_ad_sponsored(
                name=ad_name_raw,
                adset_id=adset_id,
                share_urn=share_urn,
            )
        result["ad_id"] = ad.get("id")
        result["ad_name"] = ad.get("name")
    else:
        result["ad_id"] = None
        result["ad_name"] = None
        print("[li] No share_urn provided — add Ad manually in Campaign Manager.")

    # 4. Log UTM mapping for tracking
    result["utm_mapping"] = {
        "utm_campaign": campaign_name,
        "utm_audience": adset_name,
        "utm_content":  result.get("ad_name", ""),
        "utm_source":   "linkedin",
        "utm_medium":   "paid",
    }
    result["conversion_tracking"] = (
        "HubSpot Lead Event Sync — LinkedIn Insight Tag + HubSpot integration. "
        "Conversion fires when HubSpot form is submitted. "
        "Verify in LinkedIn Campaign Manager → Analyze → Conversion Tracking → 'HubSpot Lead'."
    )
    print(f"[li] Conversion tracking: HubSpot Lead Event Sync")
    print(f"\n[li] Full campaign setup complete:")
    print(f"  Campaign : {campaign_name} (id={campaign_id})")
    print(f"  Ad Set   : {adset_name} (id={adset_id})")
    print(f"  Ad       : {result.get('ad_name', 'pending')} (id={result.get('ad_id', 'pending')})")
    print(f"  UTM      : utm_campaign={campaign_name}&utm_audience={adset_name}")
    return result


# ── Status controls ───────────────────────────────────────────────────────────

def set_campaign_status(campaign_id: str | int, status: str) -> dict:
    """status: ACTIVE | PAUSED | ARCHIVED | CANCELED"""
    r = _patch(f"/adCampaigns/{campaign_id}", {"status": status})
    print(f"[li] Ad Set {campaign_id} -> {status}")
    return r


def pause_campaign(campaign_id: str | int) -> dict:
    return set_campaign_status(campaign_id, "PAUSED")


def enable_campaign(campaign_id: str | int) -> dict:
    return set_campaign_status(campaign_id, "ACTIVE")


def set_campaign_budget(campaign_id: str | int, daily_budget_usd: float) -> dict:
    r = _patch(f"/adCampaigns/{campaign_id}", {
        "dailyBudget": {"amount": str(daily_budget_usd), "currencyCode": "USD"}
    })
    print(f"[li] Ad Set {campaign_id} budget -> ${daily_budget_usd}/day")
    return r


# ── Lead gen forms ────────────────────────────────────────────────────────────

def list_lead_gen_forms() -> list[dict]:
    """List all lead gen forms on the account."""
    r = _get("/leadGenForms", params={
        "q":       "account",
        "account": _ACCOUNT_URN,
        "count":   50,
    })
    forms = r.get("elements", [])
    for f in forms:
        print(f"  Form: {f.get('name')} | URN: {f.get('id')} | Status: {f.get('status')}")
    return forms


def create_instant_form(
    name: str,
    questions: list[dict] | None = None,
    privacy_url: str = "https://qoyod.com/privacy",
    thank_you_message: str = "شكراً لك! سنتواصل معك قريباً",
    locale_country: str = "SA",
    locale_language: str = "ar",
) -> str:
    """
    Create a LinkedIn Lead Gen Form via the Marketing API (/v2/leadGenForms).

    The form URN returned can be passed to ``create_ad_lead_gen()`` as
    ``lead_gen_form_urn``.

    LinkedIn returns the new form ID in the ``X-RestLi-Id`` response header
    (no JSON body on 201).  This function wraps it in a ``urn:li:leadGenForm:``
    URN and returns that string.

    Parameters
    ----------
    name             : Form name — e.g. "LinkedIn_LeadGen_AR_Invoice_Form".
    questions        : List of question dicts. Each dict must contain a
                       ``fieldType`` key. Supported types: FULL_NAME,
                       PHONE_NUMBER, WORK_COMPANY, JOB_TITLE, EMAIL.
                       Defaults to full name, phone number, company name,
                       job title, and email.
    privacy_url      : URL of the privacy policy page (required by LinkedIn).
    thank_you_message: Body text shown on the post-submission confirmation.
    locale_country   : ISO 3166-1 alpha-2 country code for the form locale
                       (default "SA").
    locale_language  : ISO 639-1 language code for the form locale
                       (default "ar").

    Returns
    -------
    str  — full lead gen form URN, e.g. ``urn:li:leadGenForm:123456789``.
    """
    if questions is None:
        questions = [
            {"fieldType": "FULL_NAME"},
            {"fieldType": "PHONE_NUMBER"},
            {"fieldType": "WORK_COMPANY"},
            {"fieldType": "JOB_TITLE"},
            {"fieldType": "EMAIL"},
        ]

    payload = {
        "name":            name,
        "locale":          {"country": locale_country, "language": locale_language},
        "leadGenFormType": "SPONSORED_CONTENT",
        "formElements":    questions,
        "privacyPolicyUrl": privacy_url,
        "thankYouPage": {
            "message": thank_you_message,
        },
    }

    r       = _post("/leadGenForms", payload)
    form_id = r.get("_restli_id", "")
    urn     = f"urn:li:leadGenForm:{form_id}"
    print(f"[li] form created: {urn}")
    return urn


# ── Matched audiences (HubSpot lists → LinkedIn) ─────────────────────────────

def list_matched_audiences() -> list[dict]:
    r = _get("/adTargetingEntities", params={
        "q":         "adAccount",
        "adAccount": _ACCOUNT_URN,
        "facet":     "urn:li:adTargetingFacet:matchedAudiences",
    })
    return r.get("elements", [])


def get_dmp_segments() -> list[dict]:
    r = _get("/dmpSegments", params={
        "q":       "account",
        "account": _ACCOUNT_URN,
        "count":   100,
    })
    return r.get("elements", [])


# ── Creatives / image library ─────────────────────────────────────────────────

def list_creatives(limit: int = 20) -> list[dict]:
    """
    List image assets owned by the LinkedIn organization.
    Uses GET /rest/images?q=owner&owner={org_urn}&count={limit}.
    Returns list of {id, name, thumbnail_url}.
    """
    # Accept either LI_ORGANIZATION_URN (full URN) or LI_ORG_ID (bare numeric ID)
    org_urn = _ORG_URN or os.getenv("LI_ORG_ID", "")
    if org_urn and not org_urn.startswith("urn:"):
        org_urn = f"urn:li:organization:{org_urn}"
    if not org_urn:
        raise ValueError("Neither LI_ORGANIZATION_URN nor LI_ORG_ID env var is set — needed for LinkedIn image library")

    r = requests.get(
        f"{_BASE}/images",
        headers=_headers(),
        params={"q": "owner", "owner": org_urn, "count": limit},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    elements = data.get("elements", [])
    results = []
    for el in elements:
        results.append({
            "id":           el.get("id"),
            "name":         el.get("title") or el.get("id", ""),
            "thumbnail_url": (el.get("downloadUrl") or
                              (el.get("originalImage") or {}).get("downloadUrl")),
            "source":       "images",
        })

    print(f"[li] list_creatives -> {len(results)} assets (org={org_urn})")
    return results


# ── Targeting helpers ─────────────────────────────────────────────────────────

def get_geo_urns(country: str = "Saudi Arabia") -> list[str]:
    r = _get("/adTargetingEntities", params={
        "q":      "typeahead",
        "query":  country,
        "facet":  "urn:li:adTargetingFacet:locations",
        "count":  5,
    })
    return [e["urn"] for e in r.get("elements", [])]


def get_job_function_urns(query: str) -> list[dict]:
    r = _get("/adTargetingEntities", params={
        "q":      "typeahead",
        "query":  query,
        "facet":  "urn:li:adTargetingFacet:jobFunctions",
        "count":  10,
    })
    return r.get("elements", [])


def get_industry_urns(query: str) -> list[dict]:
    r = _get("/adTargetingEntities", params={
        "q":      "typeahead",
        "query":  query,
        "facet":  "urn:li:adTargetingFacet:industries",
        "count":  10,
    })
    return r.get("elements", [])
