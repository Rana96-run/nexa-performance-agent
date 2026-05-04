"""
Snapchat Ads executor — full mutation surface.
All mutations create resources in PAUSED state unless explicitly enabled.

Supported:
  Campaign  — create / set status / change budget
  Ad Squad  — create / set status / change bid / change audience
  Ad        — create / set status

Campaign naming convention: {Channel}_{Type}_{Language}_{Product}_{Audience}
  Channel:  Snapchat
  Type:     LeadGen | Awareness | Video | Remarketing | Conversion
  Language: AR | EN | AREN
  Product:  Invoice (E-Invoice) | Bookkeeping (Qbookkeeping) | Qflavours | General | {SeasonalName}
  Audience: Interests | Lookalike | Retargeting | Broad
  Rules:
    - Prospecting campaigns use Interests or Lookalike — never "Prospecting" alone
    - Retargeting campaigns use Retargeting — never combined with Prospecting
    - Product aliases auto-normalised: E-Invoice->Invoice, Qbookkeeping->Bookkeeping, etc.
  Examples: Snapchat_LeadGen_AR_Invoice_Interests
            Snapchat_LeadGen_AR_Invoice_Retargeting
            Snapchat_LeadGen_AR_Ramadan_Lookalike

Accounts: SNAPCHAT_AD_ACCOUNT_2025 (default) | SNAPCHAT_AD_ACCOUNT_2024
Use best_account() to pick the one with better CPL from BQ.
"""
from __future__ import annotations

import os
import requests
from dotenv import load_dotenv, set_key

from executors.naming import prefixed as _naming_prefixed
from config_creatives import (
    SNAPCHAT_PIXEL_ID,
    snapchat_form,
    snapchat_account_key,
    normalise_product,
)

load_dotenv(override=True)

_BASE        = "https://adsapi.snapchat.com/v1"
_TOKEN_URL   = "https://accounts.snapchat.com/login/oauth2/access_token"
_ACCOUNT_2024 = os.getenv("SNAPCHAT_AD_ACCOUNT_2024")
_ACCOUNT_2025 = os.getenv("SNAPCHAT_AD_ACCOUNT_2025")
_DEFAULT_ACCOUNT = _ACCOUNT_2025

_CHANNEL_PREFIX = "Snapchat"


def _prefixed(name: str) -> str:
    return _naming_prefixed(_CHANNEL_PREFIX, name)


def _refresh_token() -> str:
    r = requests.post(_TOKEN_URL, data={
        "refresh_token": os.getenv("SNAPCHAT_REFRESH_TOKEN"),
        "client_id":     os.getenv("SNAPCHAT_CLIENT_ID"),
        "client_secret": os.getenv("SNAPCHAT_CLIENT_SECRET"),
        "grant_type":    "refresh_token",
    }, timeout=15)
    r.raise_for_status()
    token = r.json()["access_token"]
    set_key(".env", "SNAPCHAT_ACCESS_TOKEN", token)
    os.environ["SNAPCHAT_ACCESS_TOKEN"] = token   # update live process env
    return token


def _headers() -> dict:
    token = os.getenv("SNAPCHAT_ACCESS_TOKEN") or _refresh_token()
    return {"Authorization": f"Bearer {token}"}


def _post(path: str, payload: dict) -> dict:
    r = requests.post(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=15)
    if r.status_code == 401:
        # Token expired — refresh once and retry
        _refresh_token()
        r = requests.post(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=15)
    if not r.ok:
        raise RuntimeError(f"Snapchat POST {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def _put(path: str, payload: dict) -> dict:
    r = requests.put(f"{_BASE}{path}", headers=_headers(), json=payload, timeout=15)
    if not r.ok:
        raise RuntimeError(f"Snapchat PUT {path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def _get_one(path: str) -> dict:
    r = requests.get(f"{_BASE}{path}", headers=_headers(), timeout=10)
    r.raise_for_status()
    items = list(r.json().values())
    return items[0][0] if items else {}


# ── Account selection ─────────────────────────────────────────────────────────

def best_account(campaign_name: str, days: int = 30) -> str:
    """
    Return the Snapchat account_id whose existing campaigns with a name similar
    to `campaign_name` have driven the most HubSpot-qualified leads (SQLs) over
    the last N days.  Falls back to _DEFAULT_ACCOUNT when BQ is unreachable or
    no matching campaigns found.
    """
    accounts = [a for a in [_ACCOUNT_2025, _ACCOUNT_2024] if a]
    if len(accounts) < 2:
        return _DEFAULT_ACCOUNT or (accounts[0] if accounts else "")
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

        since  = (_date.today() - _td(days=days)).isoformat()
        tokens = [t.lower() for t in campaign_name.replace("-", "_").split("_") if len(t) > 2]
        if not tokens:
            tokens = [campaign_name.lower()]
        like_clauses = " AND ".join(
            f"LOWER(c.campaign_name) LIKE '%{t}%'" for t in tokens
        )
        acct_list = ", ".join(f"'{a}'" for a in accounts)

        sql = f"""
            SELECT c.account_id,
                   SUM(h.leads_qualified) AS sqls
            FROM `{project}.{dataset}.campaigns_daily` c
            JOIN `{project}.{dataset}.hubspot_leads_module_daily` h
              ON  c.date = h.date
             AND  LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
            WHERE c.channel = 'snapchat'
              AND c.date >= '{since}'
              AND c.account_id IN ({acct_list})
              AND ({like_clauses})
            GROUP BY c.account_id
            ORDER BY sqls DESC
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        if rows and rows[0].account_id:
            print(f"[snap] best account for '{campaign_name}' "
                  f"({int(rows[0].sqls or 0)} SQLs last {days}d): {rows[0].account_id}")
            return rows[0].account_id
    except Exception as e:
        print(f"[snap] best_account BQ query failed ({e}), using default")
    return _DEFAULT_ACCOUNT


def best_audience(product: str | None = None, days: int = 30) -> dict:
    """
    Return the Snapchat targeting dict from the best-performing campaign
    by CPQL (lowest) over the last N days, optionally filtered by product.

    Strategy:
      1. Query BQ for the Snapchat campaign with lowest CPQL
      2. Look up its ad squad(s) via the Snapchat API
      3. Return the targeting dict from the first active ad squad
      4. Fall back to default SA targeting if BQ or API fails

    Returns a Snapchat-compatible targeting dict ready for create_full_campaign().
    """
    _default = {
        "geos": [{"country_code": "SA"}],
        "demographics": [{"age_groups": ["18-24", "25-34", "35-49"]}],
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
        client   = _bq.Client(project=project, credentials=creds)

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
            SELECT
              c.campaign_name,
              SUM(c.spend)  AS spend,
              SUM(hs.sqls)  AS sqls,
              SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0)) AS cpql
            FROM `{project}.{dataset}.campaigns_daily` c
            LEFT JOIN hs ON c.date = hs.date
              AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
            WHERE c.channel = 'snapchat'
              AND c.date >= '{since}'
              {prod_filter}
            GROUP BY c.campaign_name
            HAVING SUM(c.spend) >= 70 AND SUM(hs.sqls) > 0
            ORDER BY cpql ASC
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        if not rows:
            print("[snap] best_audience: no qualifying Snapchat campaigns in BQ — using default targeting")
            return _default

        best_campaign = rows[0].campaign_name
        cpql = float(rows[0].cpql or 0)
        print(f"[snap] best_audience: '{best_campaign}' CPQL=${cpql:.0f} — pulling targeting")

        # Find that campaign in the Snapchat API
        for acct in [a for a in [_ACCOUNT_2025, _ACCOUNT_2024] if a]:
            r = requests.get(
                f"{_BASE}/adaccounts/{acct}/campaigns",
                headers=_headers(), params={"limit": 50}, timeout=10
            )
            if not r.ok:
                continue
            camps = r.json().get("campaigns", [])
            for c in camps:
                camp = c.get("campaign", c)
                if camp.get("name", "").lower() == best_campaign.lower():
                    camp_id = camp.get("id")
                    # Get its ad squads
                    r2 = requests.get(
                        f"{_BASE}/campaigns/{camp_id}/adsquads",
                        headers=_headers(), timeout=10
                    )
                    if r2.ok:
                        squads = r2.json().get("adsquads", [])
                        for sq in squads:
                            squad = sq.get("adsquad", sq)
                            targeting = squad.get("targeting")
                            if targeting:
                                print(f"[snap] best_audience: using targeting from squad '{squad.get('name')}'")
                                return targeting

    except Exception as e:
        print(f"[snap] best_audience failed ({e}) — using default targeting")

    return _default


# ── Campaign ──────────────────────────────────────────────────────────────────

def create_campaign(
    name: str,
    daily_budget_usd: float | None = None,
    lifetime_budget_usd: float | None = None,
    objective: str = "LEAD_GENERATION",
    status: str = "PAUSED",
    account_id: str | None = None,
) -> dict:
    """
    Create a Snapchat campaign. Supply either daily or lifetime budget.
    objective: LEAD_GENERATION | WEBSITE_CONVERSIONS | BRAND_AWARENESS | APP_INSTALLS
    If account_id is None, picks the better-performing account from BQ.
    Follow naming convention: {Type}_{Language}_{Product}_{Variant}
    e.g. Snap_LeadGen_AR_Invoice_Retargeting
    """
    name = _prefixed(name)
    if account_id is None:
        account_id = best_account(name)
    campaign: dict = {
        "name":      name,
        "ad_account_id": account_id,
        "status":    status,
        "objective": objective,
    }
    if daily_budget_usd is not None:
        campaign["daily_budget_micro"] = int(daily_budget_usd * 1_000_000)
    if lifetime_budget_usd is not None:
        campaign["lifetime_spend_cap_micro"] = int(lifetime_budget_usd * 1_000_000)

    r = _post(f"/adaccounts/{account_id}/campaigns", {"campaigns": [{"campaign": campaign}]})
    result = r.get("campaigns", [{}])[0].get("campaign", {})
    print(f"[snap] campaign created ({status}): {name} -> {result.get('id')}")
    return result


def set_campaign_status(campaign_id: str, status: str,
                        account_id: str = _DEFAULT_ACCOUNT) -> dict:
    """status: ACTIVE | PAUSED | DELETED"""
    current = _get_one(f"/campaigns/{campaign_id}")
    current["status"] = status
    r = _put(f"/adaccounts/{account_id}/campaigns",
             {"campaigns": [{"campaign": current}]})
    result = r.get("campaigns", [{}])[0].get("campaign", {})
    print(f"[snap] campaign {campaign_id} -> {status}")
    return result


def pause_campaign(campaign_id: str, account_id: str = _DEFAULT_ACCOUNT) -> dict:
    return set_campaign_status(campaign_id, "PAUSED", account_id)


def enable_campaign(campaign_id: str, account_id: str = _DEFAULT_ACCOUNT) -> dict:
    return set_campaign_status(campaign_id, "ACTIVE", account_id)


def set_campaign_budget(campaign_id: str, daily_budget_usd: float,
                        account_id: str = _DEFAULT_ACCOUNT) -> dict:
    current = _get_one(f"/campaigns/{campaign_id}")
    current["daily_budget_micro"] = int(daily_budget_usd * 1_000_000)
    r = _put(f"/adaccounts/{account_id}/campaigns",
             {"campaigns": [{"campaign": current}]})
    result = r.get("campaigns", [{}])[0].get("campaign", {})
    print(f"[snap] campaign {campaign_id} budget -> ${daily_budget_usd}/day")
    return result


# ── Ad squad (ad set) ─────────────────────────────────────────────────────────

def create_ad_squad(
    campaign_id: str,
    name: str,
    daily_budget_usd: float,
    bid_usd: float,
    optimization_goal: str = "SWIPES",
    placement: str = "SNAP_ADS",
    targeting: dict | None = None,
    status: str = "PAUSED",
    account_id: str = _DEFAULT_ACCOUNT,
) -> dict:
    """
    optimization_goal: SWIPES | IMPRESSIONS | VIDEO_VIEWS | APP_INSTALLS | LEAD_GENERATION
    placement: SNAP_ADS | STORIES | PUBLISHER_NETWORK | ALL
    targeting: Snapchat targeting spec dict (age, gender, geos, interests, etc.)
    """
    name = _prefixed(name)
    squad: dict = {
        "name":               name,
        "campaign_id":        campaign_id,
        "status":             status,
        "type":               "SNAP_ADS",
        "placement_v2":       {"config": placement},
        "optimization_goal":  optimization_goal,
        "bid_micro":          int(bid_usd * 1_000_000),
        "daily_budget_micro": int(daily_budget_usd * 1_000_000),
        "auto_bid":           False,
        "targeting":          targeting or {
            "geos": [{"country_code": "SA"}],
        },
    }
    r = _post(f"/campaigns/{campaign_id}/adsquads",
              {"adsquads": [{"adsquad": squad}]})
    result = r.get("adsquads", [{}])[0].get("adsquad", {})
    print(f"[snap] ad squad created ({status}): {name} -> {result.get('id')}")
    return result


def set_adsquad_status(adsquad_id: str, status: str,
                       account_id: str = _DEFAULT_ACCOUNT) -> dict:
    current = _get_one(f"/adsquads/{adsquad_id}")
    current["status"] = status
    r = _put(f"/adaccounts/{account_id}/adsquads",
             {"adsquads": [{"adsquad": current}]})
    result = r.get("adsquads", [{}])[0].get("adsquad", {})
    print(f"[snap] adsquad {adsquad_id} -> {status}")
    return result


def set_adsquad_budget(adsquad_id: str, daily_budget_usd: float,
                       account_id: str = _DEFAULT_ACCOUNT) -> dict:
    current = _get_one(f"/adsquads/{adsquad_id}")
    current["daily_budget_micro"] = int(daily_budget_usd * 1_000_000)
    r = _put(f"/adaccounts/{account_id}/adsquads",
             {"adsquads": [{"adsquad": current}]})
    result = r.get("adsquads", [{}])[0].get("adsquad", {})
    print(f"[snap] adsquad {adsquad_id} budget -> ${daily_budget_usd}/day")
    return result


def set_adsquad_targeting(adsquad_id: str, targeting: dict,
                          account_id: str = _DEFAULT_ACCOUNT) -> dict:
    """Update audience targeting on an ad squad."""
    current = _get_one(f"/adsquads/{adsquad_id}")
    current["targeting"] = targeting
    r = _put(f"/adaccounts/{account_id}/adsquads",
             {"adsquads": [{"adsquad": current}]})
    result = r.get("adsquads", [{}])[0].get("adsquad", {})
    print(f"[snap] adsquad {adsquad_id} targeting updated")
    return result


# ── Ads ───────────────────────────────────────────────────────────────────────

def create_ad(
    adsquad_id: str,
    name: str,
    creative_id: str,
    status: str = "PAUSED",
    account_id: str = _DEFAULT_ACCOUNT,
) -> dict:
    """Attach a creative to an ad squad as an ad (PAUSED by default)."""
    name = _prefixed(name)
    ad = {
        "name":       name,
        "ad_squad_id": adsquad_id,
        "creative_id": creative_id,
        "status":     status,
        "type":       "SNAP_AD",
    }
    r = _post(f"/adsquads/{adsquad_id}/ads",
              {"ads": [{"ad": ad}]})
    result = r.get("ads", [{}])[0].get("ad", {})
    print(f"[snap] ad created ({status}): {name} -> {result.get('id')}")
    return result


def set_ad_status(ad_id: str, status: str,
                  account_id: str = _DEFAULT_ACCOUNT) -> dict:
    current = _get_one(f"/ads/{ad_id}")
    current["status"] = status
    r = _put(f"/adaccounts/{account_id}/ads",
             {"ads": [{"ad": current}]})
    result = r.get("ads", [{}])[0].get("ad", {})
    print(f"[snap] ad {ad_id} -> {status}")
    return result


# ── Lead gen / Instant Form ───────────────────────────────────────────────────

def create_instant_form(
    name: str,
    questions: list[dict] | None = None,
    privacy_url: str = "https://qoyod.com/privacy",
    thank_you_message: str = "شكراً لك! سنتواصل معك قريباً",
    account_id: str | None = None,
) -> str:
    """
    Create a Snapchat Lead Gen Form via the Snap Ads API.

    The form is created with status ACTIVE so it is immediately ready to
    attach to an ad squad.  Pause the containing ad squad first if you
    need to review before traffic runs.

    Parameters
    ----------
    name              : Form name — should follow naming convention, e.g.
                        "Snapchat_LeadGen_AR_Invoice_Form".
    questions         : List of question dicts. Each dict must contain a
                        ``type`` key. Supported types: NAME, PHONE, EMAIL,
                        COMPANY, JOB_TITLE.
                        Defaults to name, phone number, company name,
                        and job title.
    privacy_url       : URL of the privacy policy page (required by Snap).
    thank_you_message : Thank-you body text shown after submission.
    account_id        : Ad account ID. Defaults to _DEFAULT_ACCOUNT.

    Returns
    -------
    str  — the lead_gen_form id returned by the Snap Ads API.
    """
    acct = account_id or _DEFAULT_ACCOUNT

    if questions is None:
        questions = [
            {"type": "NAME"},
            {"type": "PHONE"},
            {"type": "COMPANY"},
            {"type": "JOB_TITLE"},
        ]

    payload = {
        "lead_gen_form": {
            "name":                  name,
            "organization_name":     "Qoyod",
            "status":                "ACTIVE",
            "questions":             questions,
            "privacy_policy_url":    privacy_url,
            "terms_and_conditions_url": privacy_url,
            "thank_you_headline":    "شكراً لك",
            "thank_you_body":        thank_you_message,
        }
    }

    r      = _post(f"/adaccounts/{acct}/leadgenforms", payload)
    form   = r.get("lead_gen_form", {})
    form_id = str(form.get("id", ""))
    print(f"[snap] form created: {form_id}")
    return form_id


# ── Full campaign setup (one call) ───────────────────────────────────────────

def _build_utm_url(base_url: str, campaign_name: str,
                   squad_name: str, ad_name: str) -> str:
    """
    Build WEB_FORM landing URL with all UTM + HubSpot tracking parameters.

    Snapchat dynamic macros (resolved at serve time by Snap):
      utm_source    → {{site_source_name}}   always "snapchat"
      utm_medium    → {{placement}}           e.g. "feed", "stories", "discover"
      campaign_id   → {{campaign_id}}         numeric Snap campaign ID
      ad_group_id   → {{ad_squad_id}}         numeric Snap ad squad ID
      ad_id         → {{ad_id}}               numeric Snap ad ID

    Name fields (set at creation — Snapchat has no name macros unlike Meta):
      utm_campaign  → campaign_name           e.g. Snapchat_LeadGen_AR_Invoice_Interests
      utm_audience  → squad_name              e.g. Snapchat_LeadGen_AR_Invoice_Interests
      utm_content   → ad_name                 e.g. Snapchat_LeadGen_AR_InvoiceV1

    NEVER remove or rename these — HubSpot lead module depends on all 8 parameters.
    """
    # NOTE: Snapchat only supports these dynamic macros:
    #   {{campaign_id}}, {{ad_squad_id}}, {{ad_id}}
    # It does NOT support {{site_source_name}} or {{placement}} — those are Meta-only.
    # utm_source and utm_medium are hardcoded for Snap.
    sep = "&" if "?" in base_url else "?"
    return (
        f"{base_url}{sep}"
        f"utm_source=snapchat"
        f"&utm_medium=paid_social"
        f"&utm_campaign={campaign_name}"
        f"&utm_audience={squad_name}"
        f"&utm_content={ad_name}"
        f"&campaign_id={{{{campaign_id}}}}"
        f"&ad_group_id={{{{ad_squad_id}}}}"
        f"&ad_id={{{{ad_id}}}}"
    )


def create_full_campaign(
    product: str,
    campaign_type: str,
    language: str,
    audience_type: str,
    daily_budget_usd: float,
    creative_id: str,
    bid_strategy: str = "MAX_BID",
    bid_usd: float = 16.0,
    ad_format: str = "INSTANT_FORM",
    landing_url: str | None = None,
    placement: str = "SNAP_ADS",
    targeting: dict | None = None,
    account_id: str | None = None,
    status: str = "PAUSED",
) -> dict:
    """
    Full Snapchat campaign setup in one call.

    Objective is always LEAD_GENERATION.
    Optimization goal is always LEAD_GENERATION.

    bid_strategy : MAX_BID | TARGET_COST
    bid_usd      : target bid amount — Qoyod range $15-$17 (default $16)
    ad_format    : INSTANT_FORM — uses correct lead gen form from config_creatives
                                  (auto-selected by account + product)
                 | WEB_FORM    — uses landing_url + Qoyod Self Service Pixel
                                  (landing_url auto-populated from config_creatives
                                   if not supplied)

    targeting    : If None, pulled automatically from the best-performing
                   Snapchat campaign by CPQL in BQ. Falls back to SA defaults.

    Naming (enforced automatically):
      Campaign : Snapchat_{campaign_type}_{language}_{product}_{audience_type}
      Ad Squad : same name
      Ad       : Snapchat_{product}V1_{language}

    Returns dict with campaign_id, squad_id, ad_id, form/pixel info.
    """
    from config_creatives import web_form_url as _web_form_url

    # Validate inputs
    if bid_strategy not in ("MAX_BID", "TARGET_COST"):
        raise ValueError(f"bid_strategy must be MAX_BID or TARGET_COST, got {bid_strategy!r}")
    if not (15.0 <= bid_usd <= 17.0):
        raise ValueError(f"bid_usd must be $15-$17 (Qoyod range), got ${bid_usd}")
    if ad_format not in ("INSTANT_FORM", "WEB_FORM"):
        raise ValueError(f"ad_format must be INSTANT_FORM or WEB_FORM, got {ad_format!r}")

    result: dict = {}
    acct = account_id or best_account(
        _prefixed(f"{campaign_type}_{language}_{product}_{audience_type}")
    )
    full_name = f"{campaign_type}_{language}_{product}_{audience_type}"

    # ── Resolve form / pixel based on ad_format ───────────────────────────────
    if ad_format == "INSTANT_FORM":
        form_info = snapchat_form(acct, product)
        result["form_id"]   = form_info["id"]
        result["form_name"] = form_info["name"]
        print(f"[snap] Using lead gen form: {form_info['name']} ({form_info['id']})")
    else:
        # WEB_FORM: auto-populate landing URL from config if not provided
        if not landing_url:
            landing_url = _web_form_url(product)
            print(f"[snap] Auto-selected landing URL for '{product}': {landing_url}")
        result["pixel_id"]   = SNAPCHAT_PIXEL_ID
        result["pixel_name"] = "Qoyod Self Service Pixel"
        print(f"[snap] Using pixel: Qoyod Self Service Pixel ({SNAPCHAT_PIXEL_ID})")

    # ── Resolve targeting from best-performing campaign if not supplied ────────
    if targeting is None:
        targeting = best_audience(product=product)

    # 1. Campaign — always LEAD_GENERATION
    camp = create_campaign(
        name=full_name,
        daily_budget_usd=daily_budget_usd,
        objective="LEAD_GENERATION",
        status=status,
        account_id=acct,
    )
    campaign_id = camp.get("id")
    campaign_name = camp.get("name", _prefixed(full_name))
    result["campaign_id"] = campaign_id
    result["campaign_name"] = campaign_name

    # 2. Ad Squad — always LEAD_GENERATION optimization, MAX_BID or TARGET_COST
    squad_payload: dict = {
        "name":               _prefixed(full_name),
        "campaign_id":        campaign_id,
        "status":             status,
        "type":               "SNAP_ADS",
        "placement_v2":       {"config": placement},
        "optimization_goal":  "LEAD_GENERATION",
        "daily_budget_micro": int(daily_budget_usd * 1_000_000),
        "auto_bid":           False,
        "targeting":          targeting,
    }
    # Bidding: MAX_BID sets bid_micro; TARGET_COST sets target_bid_micro
    if bid_strategy == "MAX_BID":
        squad_payload["bid_micro"] = int(bid_usd * 1_000_000)
        squad_payload["bid_strategy"] = "MAX_BID"
    else:
        squad_payload["target_bid_micro"] = int(bid_usd * 1_000_000)
        squad_payload["bid_strategy"] = "TARGET_COST"

    r = _post(f"/campaigns/{campaign_id}/adsquads",
              {"adsquads": [{"adsquad": squad_payload}]})
    squad = r.get("adsquads", [{}])[0].get("adsquad", {})
    squad_id = squad.get("id")
    result["squad_id"] = squad_id
    result["bid_strategy"] = bid_strategy
    result["bid_usd"] = bid_usd
    print(f"[snap] Ad Squad created ({bid_strategy} ${bid_usd}): {squad_payload['name']} -> {squad_id}")

    # 3. Ad — INSTANT_FORM or WEB_FORM
    ad_name_raw = f"{campaign_type}_{language}_{product}V1"
    ad_name = _prefixed(ad_name_raw)

    if ad_format == "WEB_FORM":
        utm_url = _build_utm_url(landing_url, campaign_name, _prefixed(full_name), ad_name)
        print(f"[snap] WEB_FORM URL: {utm_url}")
        result["final_url"] = utm_url
        # Attach pixel to ad squad for WEB_FORM conversion tracking
        try:
            current_squad = _get_one(f"/adsquads/{squad_id}")
            current_squad["pixel_id"] = SNAPCHAT_PIXEL_ID
            _put(f"/adaccounts/{acct}/adsquads",
                 {"adsquads": [{"adsquad": current_squad}]})
            print(f"[snap] Pixel attached to ad squad: {SNAPCHAT_PIXEL_ID}")
        except Exception as e:
            print(f"[snap] Pixel attach failed (non-fatal): {e}")
    else:
        form_id = result.get("form_id")
        print(f"[snap] INSTANT_FORM — form: {result.get('form_name')} ({form_id})")

    ad = create_ad(
        adsquad_id=squad_id,
        name=ad_name_raw,
        creative_id=creative_id,
        status=status,
        account_id=acct,
    )
    result["ad_id"] = ad.get("id")
    result["ad_name"] = ad_name

    result["utm_mapping"] = {
        "utm_source":   "{{site_source_name}}",
        "utm_medium":   "{{placement}}",
        "utm_campaign": campaign_name,
        "utm_audience": _prefixed(full_name),
        "utm_content":  ad_name,
        "campaign_id":  "{{campaign_id}}",
        "ad_group_id":  "{{ad_squad_id}}",
        "ad_id":        "{{ad_id}}",
    }
    result["account_key"] = snapchat_account_key(acct)
    result["account_id"]  = acct

    print(f"\n[snap] Full campaign setup complete:")
    print(f"  Account   : {snapchat_account_key(acct)} ({acct})")
    print(f"  Campaign  : {campaign_name} (id={campaign_id})")
    print(f"  Ad Squad  : {squad_id} | {bid_strategy} ${bid_usd} | LEAD_GENERATION")
    if ad_format == "INSTANT_FORM":
        print(f"  Form      : {result.get('form_name')} ({result.get('form_id')})")
    else:
        print(f"  Landing   : {result.get('final_url')}")
        print(f"  Pixel     : Qoyod Self Service Pixel ({SNAPCHAT_PIXEL_ID})")
    print(f"  Ad        : {ad_name}")
    return result


# ── Creatives / media library ────────────────────────────────────────────────

def list_creatives(limit: int = 20, account_id: str | None = None) -> list[dict]:
    """
    List media assets (images) for a Snapchat ad account.
    Returns list of {id, name, thumbnail_url}.
    """
    acct = account_id or _DEFAULT_ACCOUNT
    if not acct:
        raise ValueError("No SNAPCHAT_AD_ACCOUNT_2025 set in env")

    r = requests.get(
        f"{_BASE}/adaccounts/{acct}/media",
        headers=_headers(),
        params={"media_type": "IMAGE", "limit": limit},
        timeout=15,
    )
    if r.status_code == 401:
        _refresh_token()
        r = requests.get(
            f"{_BASE}/adaccounts/{acct}/media",
            headers=_headers(),
            params={"media_type": "IMAGE", "limit": limit},
            timeout=15,
        )
    if not r.ok:
        raise RuntimeError(f"Snapchat GET /media -> {r.status_code}: {r.text[:300]}")

    items = r.json().get("media", [])
    results = []
    for item in items:
        m = item.get("media", item)
        results.append({
            "id":           m.get("id"),
            "name":         m.get("name"),
            "thumbnail_url": m.get("download_url") or m.get("media_url"),
            "source":       "media",
        })

    print(f"[snap] list_creatives -> {len(results)} assets (account={acct})")
    return results


# ── Segments / audiences ──────────────────────────────────────────────────────

def list_segments(account_id: str = _DEFAULT_ACCOUNT) -> list[dict]:
    r = requests.get(f"{_BASE}/adaccounts/{account_id}/segments",
                     headers=_headers(), timeout=10)
    r.raise_for_status()
    return [s.get("segment", s) for s in r.json().get("segments", [])]
