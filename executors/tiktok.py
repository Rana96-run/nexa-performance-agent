"""
executors/tiktok.py
===================
TikTok Marketing API executor — full mutation surface.
All resources are created in PAUSED state unless explicitly enabled.

Supported:
  Campaign — create / set status / change budget
  Ad Group — create / set status / change bid / change audience
  Ad       — create / set status

Campaign naming convention: {Channel}_{Type}_{Language}_{Product}_{Audience}
  Channel:  TikTok
  Type:     LeadGen | Awareness | Video | Remarketing | Conversion
  Language: AR | EN | AREN
  Product:  Invoice | Bookkeeping | Qflavours | General | {SeasonalName}
  Audience: Interests | Lookalike | Retargeting | Broad
  Rules:
    - Prospecting campaigns use Interests or Lookalike — never "Prospecting" alone
    - Retargeting campaigns use Retargeting — never combined with Prospecting
    - Product aliases auto-normalised: E-Invoice->Invoice, Qbookkeeping->Bookkeeping, etc.
  Examples:
    TikTok_LeadGen_AR_Invoice_Interests
    TikTok_LeadGen_AR_Invoice_Retargeting
    TikTok_LeadGen_AR_Ramadan_Lookalike

Deep Funnel Optimization (NON-NEGOTIABLE for all lead-gen campaigns):
  - Objective: LEAD_GENERATION
  - CRM pixel: TIKTOK_CRM_PIXEL env var (HubSpot <-> TikTok via CAPI)
  - Optimization event: INITIATE_CHECKOUT
    WHY: Toggle Deep Funnel Optimization (Instant Form / Website) → CRM pixel →
    "Initiate Checkout" as further optimization event. HubSpot SQLs are synced
    to TikTok as Initiate Checkout events via CAPI.
  - Bid type: MAX_BID (default) or TARGET_COST_CAP
  - Bid range enforced: $15–$17 (ValueError raised outside this range)
    WHY: TikTok deep funnel bids run higher than surface leads. $15–$17
    is the validated range for Saudi Arabia ICP for Qoyod products.

Accounts:
  TIKTOK_AD_ACCOUNT_2025 (default) | TIKTOK_AD_ACCOUNT_2024

Environment variables required:
  TIKTOK_ACCESS_TOKEN     — 24h lifetime; refresh via scripts/tiktok_oauth.py --refresh
  TIKTOK_REFRESH_TOKEN    — 365d lifetime
  TIKTOK_APP_ID           — Developer portal App ID
  TIKTOK_APP_SECRET       — Developer portal App secret
  TIKTOK_AD_ACCOUNT_2025  — Primary advertiser account ID
  TIKTOK_AD_ACCOUNT_2024  — Secondary advertiser account ID
  TIKTOK_CRM_PIXEL        — CRM pixel ID for deep funnel (HubSpot CAPI pixel)
"""
from __future__ import annotations

import os
import subprocess
import requests
from dotenv import load_dotenv, set_key

from executors.naming import prefixed as _naming_prefixed

load_dotenv(override=True)

_BASE = "https://business-api.tiktok.com/open_api/v1.3"

# Advertiser accounts
_ACCOUNT_2025    = os.getenv("TIKTOK_AD_ACCOUNT_2025", "")
_ACCOUNT_2024    = os.getenv("TIKTOK_AD_ACCOUNT_2024", "")
_DEFAULT_ACCOUNT = _ACCOUNT_2025 or _ACCOUNT_2024

# Deep funnel CRM pixel (HubSpot <-> TikTok CAPI — qualified leads synced as Checkout)
_CRM_PIXEL = os.getenv("TIKTOK_CRM_PIXEL", "")

# Bid enforcement: deep funnel bids for SA / Qoyod products
_BID_MIN = 15.0
_BID_MAX = 17.0

# Saudi Arabia TikTok location ID
# Verified via GET /open_api/v1.3/tool/region/ — SA = 6252001
_SA_LOCATION_ID = "6252001"

_CHANNEL_PREFIX = "TikTok"

# Valid bid types
BID_TYPE_MAX_BID     = "BID_TYPE_MAX_BID"
BID_TYPE_TARGET_COST = "BID_TYPE_TARGET_COST_CAP"


# ─── Naming ────────────────────────────────────────────────────────────────────

def _prefixed(name: str) -> str:
    """Enforce TikTok_ prefix and validate naming convention."""
    return _naming_prefixed(_CHANNEL_PREFIX, name)


# ─── Auth helpers ──────────────────────────────────────────────────────────────

def _refresh_token() -> str:
    """Exchange TIKTOK_REFRESH_TOKEN for a new access_token and persist it."""
    app_id  = os.getenv("TIKTOK_APP_ID", "")
    secret  = os.getenv("TIKTOK_APP_SECRET", "")
    rt      = os.getenv("TIKTOK_REFRESH_TOKEN", "")
    if not rt:
        raise RuntimeError(
            "TIKTOK_REFRESH_TOKEN not set. Run: python scripts/tiktok_oauth.py"
        )
    r = requests.post(
        f"{_BASE}/oauth2/refresh_token/",
        json={"app_id": app_id, "secret": secret, "refresh_token": rt},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(
            f"TikTok token refresh failed ({body.get('code')}): {body.get('message')}"
        )
    data   = body.get("data", {})
    access = data.get("access_token", "")
    if not access:
        raise RuntimeError("No access_token in refresh response")

    set_key(".env", "TIKTOK_ACCESS_TOKEN", access)
    # Push to Railway if CLI available
    try:
        subprocess.run(
            ["railway", "variables", "--set", f"TIKTOK_ACCESS_TOKEN={access}"],
            check=True, capture_output=True,
        )
    except Exception:
        pass  # Railway CLI optional — .env updated above

    return access


def _headers() -> dict:
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        token = _refresh_token()
    return {"Access-Token": token, "Content-Type": "application/json"}


def _post(path: str, payload: dict) -> dict:
    """POST to TikTok API; auto-refreshes token on 401."""
    r = requests.post(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=20)
    if r.status_code == 401:
        _refresh_token()
        r = requests.post(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=20)
    if not r.ok:
        raise RuntimeError(f"TikTok POST {path} -> {r.status_code}: {r.text[:400]}")
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(
            f"TikTok API error on {path}: code={body.get('code')} msg={body.get('message')}"
        )
    return body.get("data", {})


def _get(path: str, params: dict | None = None) -> dict:
    """GET from TikTok API; auto-refreshes token on 401."""
    r = requests.get(f"{_BASE}{path}", headers=_headers(), params=params, timeout=20)
    if r.status_code == 401:
        _refresh_token()
        r = requests.get(f"{_BASE}{path}", headers=_headers(), params=params, timeout=20)
    if not r.ok:
        raise RuntimeError(f"TikTok GET {path} -> {r.status_code}: {r.text[:400]}")
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(
            f"TikTok API error on {path}: code={body.get('code')} msg={body.get('message')}"
        )
    return body.get("data", {})


# ─── Campaign ─────────────────────────────────────────────────────────────────

def create_campaign(
    name: str,
    daily_budget: float,
    *,
    advertiser_id: str | None = None,
    objective: str = "LEAD_GENERATION",  # non-negotiable for Qoyod
    status: str = "CAMPAIGN_STATUS_DISABLE",  # always start paused
) -> str:
    """
    Create a TikTok campaign and return its campaign_id.

    Objective is hardcoded to LEAD_GENERATION for all Qoyod campaigns.
    All campaigns start PAUSED (CAMPAIGN_STATUS_DISABLE) — enable manually.
    """
    if objective != "LEAD_GENERATION":
        raise ValueError(
            f"Only LEAD_GENERATION campaigns are supported. Got: {objective!r}. "
            "Qoyod's TikTok strategy is lead-gen only — adjust the objective."
        )
    # Launch-policy gate: 1 new campaign per channel per 7 days.
    from executors.launch_policy import enforce_launch_policy, LaunchBlocked
    try:
        enforce_launch_policy("tiktok")
    except LaunchBlocked as e:
        print(f"[tiktok.create_campaign] BLOCKED: {e}")
        raise
    acct = advertiser_id or _DEFAULT_ACCOUNT
    name = _prefixed(name)

    payload = {
        "advertiser_id": acct,
        "campaign_name": name,
        "objective_type": "LEAD_GENERATION",
        "budget_mode": "BUDGET_MODE_DAY",
        "budget": round(daily_budget, 2),
        "operation_status": status,
        "campaign_type": "REGULAR_CAMPAIGN",
    }
    data = _post("/campaign/create/", payload)
    cid  = data.get("campaign_id", "")
    print(f"[tiktok] campaign created: {name!r} id={cid} budget=${daily_budget}/day (PAUSED)")
    return cid


def set_campaign_status(campaign_id: str, enable: bool = False,
                        advertiser_id: str | None = None):
    """Enable or pause a campaign."""
    acct   = advertiser_id or _DEFAULT_ACCOUNT
    status = "CAMPAIGN_STATUS_ENABLE" if enable else "CAMPAIGN_STATUS_DISABLE"
    _post("/campaign/status/update/", {
        "advertiser_id": acct,
        "campaign_ids": [campaign_id],
        "operation_status": status,
    })
    print(f"[tiktok] campaign {campaign_id} -> {'ENABLED' if enable else 'PAUSED'}")


def set_campaign_budget(campaign_id: str, daily_budget: float,
                        advertiser_id: str | None = None):
    """Update daily budget for an existing campaign."""
    acct = advertiser_id or _DEFAULT_ACCOUNT
    _post("/campaign/update/", {
        "advertiser_id": acct,
        "campaign_id": campaign_id,
        "budget": round(daily_budget, 2),
    })
    print(f"[tiktok] campaign {campaign_id} budget -> ${daily_budget:.2f}/day")


def pause_campaign(campaign_id: str, advertiser_id: str | None = None):
    """Pause a campaign (for health-task auto-pause)."""
    set_campaign_status(campaign_id, enable=False, advertiser_id=advertiser_id)


# ─── Ad Group (TikTok equivalent of Ad Set) ───────────────────────────────────

def create_adgroup(
    campaign_id: str,
    name: str,
    daily_budget: float,
    bid: float,
    *,
    advertiser_id: str | None = None,
    bid_type: str = BID_TYPE_MAX_BID,
    pixel_id: str | None = None,
    conversion_event: str = "INITIATE_CHECKOUT",
    location_ids: list[str] | None = None,
    age_groups: list[str] | None = None,
    gender: str = "GENDER_UNLIMITED",
    status: str = "ADGROUP_STATUS_DISABLE",
) -> str:
    """
    Create a TikTok ad group with Deep Funnel Optimization enforced.

    Deep Funnel wiring:
      pixel_id         = TIKTOK_CRM_PIXEL (HubSpot <-> TikTok CAPI)
      conversion_event = INITIATE_CHECKOUT
        (HubSpot SQLs synced to TikTok as Initiate Checkout via CAPI)
      optimization_goal = CONVERT (optimize toward the CRM pixel's Initiate Checkout event)

    This is what toggles "Deep Funnel Optimization" in the TikTok UI.

    Bid enforcement: $15–$17 USD (ValueError if outside range).
    Location default: Saudi Arabia (6252001).
    Age default: 18–44 (ICP for Qoyod B2B SaaS).
    """
    if not (_BID_MIN <= bid <= _BID_MAX):
        raise ValueError(
            f"TikTok bid ${bid:.2f} is outside the enforced range "
            f"${_BID_MIN}–${_BID_MAX}. "
            "Adjust the bid within this range to proceed."
        )
    if bid_type not in (BID_TYPE_MAX_BID, BID_TYPE_TARGET_COST):
        raise ValueError(
            f"bid_type must be {BID_TYPE_MAX_BID!r} or {BID_TYPE_TARGET_COST!r}. "
            f"Got: {bid_type!r}"
        )

    acct     = advertiser_id or _DEFAULT_ACCOUNT
    px_id    = pixel_id or _CRM_PIXEL
    loc_ids  = location_ids or [_SA_LOCATION_ID]
    age_grps = age_groups or ["AGE_18_24", "AGE_25_34", "AGE_35_44"]

    if not px_id:
        raise ValueError(
            "TIKTOK_CRM_PIXEL env var not set. "
            "Deep Funnel Optimization requires the CRM pixel ID. "
            "Check Railway / .env and set TIKTOK_CRM_PIXEL."
        )

    payload = {
        "advertiser_id":    acct,
        "campaign_id":      campaign_id,
        "adgroup_name":     name,
        "operation_status": status,

        # Budget & bid
        "budget_mode":  "BUDGET_MODE_DAY",
        "budget":       round(daily_budget, 2),
        "bid_type":     bid_type,
        "bid":          round(bid, 2),

        # Deep Funnel Optimization:
        # optimization_goal = CONVERT routes TikTok's algorithm toward the
        # CRM pixel's Checkout event (= SQL synced from HubSpot via CAPI).
        # This is the API equivalent of toggling "Deep Funnel Optimization" in the UI.
        "optimization_goal":   "CONVERT",
        "pixel_id":            px_id,
        "conversion_event":    conversion_event,   # CHECKOUT = qualified lead
        "conversion_window":   "7D_CLICK_1D_VIEW",

        # Targeting — Saudi Arabia, ICP age range
        "location_ids": loc_ids,
        "age_groups":   age_grps,
        "gender":       gender,

        # Placement — TikTok feed only (most effective for SA B2B)
        "placement_type":  "PLACEMENT_TYPE_NORMAL",
        "placements":      ["PLACEMENT_TIKTOK"],

        # Inventory filter — safe content only (brand safety)
        "brand_safety_type": "BRAND_SAFETY_PARTNER",

        # Device: all mobile (TikTok is mobile-only)
        "device_type": ["DEVICE_TYPE_MOBILE_PHONE", "DEVICE_TYPE_TABLET"],
    }

    data   = _post("/adgroup/create/", payload)
    ag_id  = data.get("adgroup_id", "")
    print(
        f"[tiktok] ad group created: {name!r} id={ag_id} "
        f"budget=${daily_budget}/day bid=${bid} "
        f"pixel={px_id} event={conversion_event} (PAUSED)"
    )
    return ag_id


def set_adgroup_status(adgroup_id: str, enable: bool = False,
                       advertiser_id: str | None = None):
    """Enable or pause an ad group."""
    acct   = advertiser_id or _DEFAULT_ACCOUNT
    status = "ADGROUP_STATUS_ENABLE" if enable else "ADGROUP_STATUS_DISABLE"
    _post("/adgroup/update/", {
        "advertiser_id": acct,
        "adgroup_id":    adgroup_id,
        "operation_status": status,
    })
    print(f"[tiktok] adgroup {adgroup_id} -> {'ENABLED' if enable else 'PAUSED'}")


def set_adgroup_bid(adgroup_id: str, bid: float,
                    advertiser_id: str | None = None):
    """Update bid for an existing ad group. Enforces $15–$17 range."""
    if not (_BID_MIN <= bid <= _BID_MAX):
        raise ValueError(
            f"Bid ${bid:.2f} outside enforced range ${_BID_MIN}–${_BID_MAX}."
        )
    acct = advertiser_id or _DEFAULT_ACCOUNT
    _post("/adgroup/update/", {
        "advertiser_id": acct,
        "adgroup_id":    adgroup_id,
        "bid": round(bid, 2),
    })
    print(f"[tiktok] adgroup {adgroup_id} bid -> ${bid:.2f}")


# ─── Ad ───────────────────────────────────────────────────────────────────────

def create_ad(
    adgroup_id: str,
    name: str,
    creative_id: str,
    *,
    advertiser_id: str | None = None,
    status: str = "AD_STATUS_DISABLE",
) -> str:
    """
    Create an ad using an existing creative.
    All ads start PAUSED — enable after review.

    Parameters
    ----------
    adgroup_id   : The ad group this ad belongs to.
    name         : Ad name (follow naming convention: TikTok_{CreativeVariant}_{Language}).
    creative_id  : Existing creative ID from TikTok Ad Library / uploaded asset.
    """
    acct = advertiser_id or _DEFAULT_ACCOUNT
    payload = {
        "advertiser_id":    acct,
        "adgroup_id":       adgroup_id,
        "ads": [{
            "ad_name":          name,
            "creative_type":    "SINGLE_VIDEO",   # all Qoyod ads are single-video
            "ad_format":        "SINGLE_VIDEO",
            "creative_id":      creative_id,
            "operation_status": status,
        }],
    }
    data   = _post("/ad/create/", payload)
    ads    = data.get("ad_ids", [])
    ad_id  = ads[0] if ads else ""
    print(f"[tiktok] ad created: {name!r} id={ad_id} (PAUSED)")
    return ad_id


def list_creatives(limit: int = 20, advertiser_id: str | None = None) -> list[dict]:
    """
    List creatives (images and videos) for a TikTok advertiser account.
    Tries /creative/list/ first; falls back to /file/image/get/ and /file/video/get/.
    Returns list of {id, name, thumbnail_url}.
    """
    acct = advertiser_id or _DEFAULT_ACCOUNT
    if not acct:
        raise ValueError("No TIKTOK_AD_ACCOUNT_2025 or TIKTOK_AD_ACCOUNT_2024 set in env")

    results: list[dict] = []

    # 1. Try /creative/list/ (may not be available on all accounts)
    try:
        data = _get("/creative/list/", {
            "advertiser_id": acct,
            "page_size":     limit,
        })
        for c in (data.get("list") or data.get("creatives") or []):
            results.append({
                "id":           str(c.get("creative_id") or c.get("id", "")),
                "name":         c.get("creative_name") or c.get("name", ""),
                "thumbnail_url": c.get("thumbnail_url") or c.get("preview_url"),
                "source":       "creative/list",
            })
        if results:
            print(f"[tiktok] list_creatives via /creative/list/ -> {len(results)} items")
            return results
    except Exception as e:
        print(f"[tiktok] list_creatives /creative/list/ error: {e}")

    # 2. Fallback: images via /file/image/get/
    try:
        img_data = _get("/file/image/get/", {
            "advertiser_id": acct,
            "page_size":     limit,
        })
        for img in (img_data.get("list") or []):
            results.append({
                "id":           str(img.get("image_id", "")),
                "name":         img.get("file_name") or img.get("display_name", ""),
                "thumbnail_url": img.get("url") or img.get("image_url"),
                "source":       "file/image",
            })
    except Exception as e:
        print(f"[tiktok] list_creatives /file/image/get/ error: {e}")

    # 3. Fallback: videos via /file/video/get/
    try:
        vid_data = _get("/file/video/get/", {
            "advertiser_id": acct,
            "page_size":     limit,
        })
        for vid in (vid_data.get("list") or []):
            results.append({
                "id":           str(vid.get("video_id", "")),
                "name":         vid.get("file_name") or vid.get("display_name", ""),
                "thumbnail_url": vid.get("cover_url") or vid.get("preview_url"),
                "source":       "file/video",
            })
    except Exception as e:
        print(f"[tiktok] list_creatives /file/video/get/ error: {e}")

    print(f"[tiktok] list_creatives -> {len(results)} assets (account={acct})")
    return results


def pause_ad(ad_id: str, advertiser_id: str | None = None):
    """Pause a specific ad (used by main.py approval flow)."""
    acct = advertiser_id or _DEFAULT_ACCOUNT
    _post("/ad/status/update/", {
        "advertiser_id": acct,
        "ad_ids":         [ad_id],
        "operation_status": "DISABLE",
    })
    print(f"[tiktok] ad {ad_id} PAUSED")


# ─── Lead gen / Instant Form ───────────────────────────────────────────────────

def create_instant_form(
    name: str,
    questions: list[dict] | None = None,
    privacy_url: str = "https://qoyod.com/privacy",
    thank_you_message: str = "شكراً لك! سنتواصل معك قريباً",
    advertiser_id: str | None = None,
) -> str:
    """
    Create a TikTok Instant Form (lead gen form) via the Marketing API v1.3.

    The form is created in DRAFT state; activate it in TikTok Ads Manager
    before attaching it to an ad group.

    Parameters
    ----------
    name             : Form name — should follow naming convention, e.g.
                       "TikTok_LeadGen_AR_Invoice_Form".
    questions        : List of question dicts. Each dict must contain a
                       ``type`` key. Supported types: PHONE_NUMBER, FULL_NAME,
                       COMPANY_NAME, JOB_TITLE, CUSTOM_QUESTION.
                       Defaults to full name, phone number, company name,
                       and job title.
    privacy_url      : URL of the privacy policy page (required by TikTok).
    thank_you_message: Body text shown on the post-submission screen.
    advertiser_id    : Advertiser account ID. Defaults to _DEFAULT_ACCOUNT.

    Returns
    -------
    str  — the form_id returned by the TikTok API.
    """
    acct = advertiser_id or _DEFAULT_ACCOUNT

    if questions is None:
        questions = [
            {"type": "FULL_NAME"},
            {"type": "PHONE_NUMBER"},
            {"type": "COMPANY_NAME"},
            {"type": "JOB_TITLE"},
        ]

    payload = {
        "advertiser_id": acct,
        "name":          name,
        "form_type":     "INSTANT_FORM",
        "questions":     questions,
        "settings": {
            "privacy_policy": {
                "url": privacy_url,
            },
            "completion_status": {
                "title":       "شكراً لك",
                "description": thank_you_message,
            },
        },
    }

    data    = _post("/lead/form/create/", payload)
    form_id = str(data.get("form_id", ""))
    print(f"[tiktok] form created: {form_id}")
    return form_id


# ─── Full campaign builder ─────────────────────────────────────────────────────

def create_full_campaign(
    *,
    type_: str = "LeadGen",
    language: str = "AR",
    product: str,
    audience: str,
    daily_budget: float,
    bid: float = 16.0,
    bid_type: str = BID_TYPE_MAX_BID,
    creative_id: str | None = None,
    advertiser_id: str | None = None,
    location_ids: list[str] | None = None,
    age_groups: list[str] | None = None,
) -> dict:
    """
    Create a complete TikTok lead-gen campaign (Campaign + Ad Group).
    Ad is created only when creative_id is provided.

    ENFORCED (non-negotiable per playbook):
      - Objective:           LEAD_GENERATION
      - CRM pixel:           TIKTOK_CRM_PIXEL
      - Deep funnel event:   INITIATE_CHECKOUT (HubSpot SQLs synced via CAPI)
      - Bid range:           $15–$17 (ValueError outside range)
      - Bid type:            MAX_BID (default) or TARGET_COST_CAP
      - Start state:         PAUSED (enable manually after review)

    Parameters
    ----------
    product        : e.g. "Invoice", "E-Invoice" (auto-normalised), "Ramadan"
    audience       : "Interests" | "Lookalike" | "Retargeting" | "Broad"
    daily_budget   : Campaign daily budget in USD
    bid            : Ad group bid in USD — must be $15–$17
    bid_type       : MAX_BID (default, safer) or TARGET_COST_CAP
    creative_id    : Existing creative ID; if None, ad layer is skipped
    location_ids   : Defaults to Saudi Arabia [6252001]
    age_groups     : Defaults to 18–44 (B2B ICP)

    Returns
    -------
    dict with campaign_id, adgroup_id, ad_id (if created), campaign_name

    Example
    -------
    create_full_campaign(
        product="Invoice",
        audience="Interests",
        daily_budget=200,
        bid=16.0,
        creative_id="7412345678901234567",
    )
    -> {
        "campaign_name": "TikTok_LeadGen_AR_Invoice_Interests",
        "campaign_id":   "7412345678901234001",
        "adgroup_id":    "7412345678901234002",
        "ad_id":         "7412345678901234003",  # or None
    }
    """
    from executors.naming import build_name
    campaign_name = build_name("TikTok", type_, language, product, audience)

    print(f"\n[tiktok] ── Creating full campaign: {campaign_name} ──")
    print(f"[tiktok]   objective     : LEAD_GENERATION (enforced)")
    print(f"[tiktok]   deep funnel   : ON — CRM pixel {_CRM_PIXEL}, event=INITIATE_CHECKOUT")
    print(f"[tiktok]   bid           : ${bid:.2f} ({bid_type})")
    print(f"[tiktok]   daily budget  : ${daily_budget:.2f}")

    # 1. Campaign
    campaign_id = create_campaign(
        name=campaign_name,
        daily_budget=daily_budget,
        advertiser_id=advertiser_id,
    )

    # 2. Ad group (deep funnel wired in)
    adgroup_name = f"{campaign_name}_AdGroup"
    adgroup_id = create_adgroup(
        campaign_id=campaign_id,
        name=adgroup_name,
        daily_budget=daily_budget,
        bid=bid,
        bid_type=bid_type,
        advertiser_id=advertiser_id,
        location_ids=location_ids,
        age_groups=age_groups,
    )

    # 3. Ad (optional — requires existing creative)
    ad_id = None
    if creative_id:
        ad_name = f"{campaign_name}_Ad"
        ad_id = create_ad(
            adgroup_id=adgroup_id,
            name=ad_name,
            creative_id=creative_id,
            advertiser_id=advertiser_id,
        )

    result = {
        "campaign_name": campaign_name,
        "campaign_id":   campaign_id,
        "adgroup_id":    adgroup_id,
        "ad_id":         ad_id,
    }
    print(f"\n[tiktok] ✅ Campaign stack created (all PAUSED — enable manually after review)")
    print(f"[tiktok]   campaign_id : {campaign_id}")
    print(f"[tiktok]   adgroup_id  : {adgroup_id}")
    if ad_id:
        print(f"[tiktok]   ad_id       : {ad_id}")
    print(f"[tiktok] ─────────────────────────────────────────────\n")
    return result
