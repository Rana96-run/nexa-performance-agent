"""
LinkedIn Ads -> BigQuery collector.
Pulls per-day per-campaign stats -> campaigns_daily.

Auth: LI_ACCESS_TOKEN rotated automatically — reads from BQ platform_tokens
      (written by scripts/linkedin_refresh.py, called nightly by operational_scheduler).
      Falls back to env var LI_ACCESS_TOKEN if BQ has no valid token.
      LI_AD_ACCOUNT_URN e.g. urn:li:sponsoredAccount:506171805
"""
import os
import requests
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

_RIYADH = timezone(timedelta(hours=3))

load_dotenv(override=True)

BASE        = "https://api.linkedin.com/rest"
AD_ACCT_URN = os.getenv("LI_AD_ACCOUNT_URN", "")

# Read token from BQ (auto-refreshed nightly) or fall back to env
def _get_token() -> str:
    try:
        from scripts.linkedin_refresh import get_active_token
        t = get_active_token()
        if t:
            return t
    except Exception:
        pass
    return os.getenv("LI_ACCESS_TOKEN", "")

TOKEN = _get_token()


def _headers() -> dict:
    return {
        "Authorization":  f"Bearer {TOKEN}",
        # LinkedIn rolls API versions monthly; their N-12 retirement window
        # means we need to bump this roughly twice a year.  Bumped May 2026
        # because 202502 returned NONEXISTENT_VERSION; verified 202602 works.
        "LinkedIn-Version": "202602",
        # NOTE: X-Restli-Protocol-Version: 2.0.0 intentionally REMOVED.
        # With v202502 it causes 400 "Projected field not present in schema"
        # errors on every field-projection call.  Without it all endpoints
        # return 200 correctly.
    }


def _account_currency() -> str:
    """Fetch the ad account's native currency. Defaults to SAR on error."""
    if not AD_ACCT_URN:
        return "SAR"
    # Extract numeric ID from URN: "urn:li:sponsoredAccount:506171805" -> "506171805"
    acct_id = AD_ACCT_URN.rsplit(":", 1)[-1]
    try:
        r = requests.get(f"{BASE}/adAccounts/{acct_id}",
                         headers=_headers(), timeout=15)
        if r.status_code < 400:
            return normalize_currency(r.json().get("currency"))
    except Exception as e:
        print(f"[li-bq] currency lookup failed: {e}")
    return "SAR"


def _list_campaign_groups() -> dict:
    """Return {group_urn: group_name} for all campaign groups on the account."""
    if not AD_ACCT_URN:
        return {}
    acct_id = AD_ACCT_URN.rsplit(":", 1)[-1]
    r = requests.get(f"{BASE}/adAccounts/{acct_id}/adCampaignGroups",
                     headers=_headers(),
                     params={"q": "search"},
                     timeout=15)
    if r.status_code >= 400:
        print(f"[li-bq] campaign groups {r.status_code}: {r.text[:200]}")
        return {}
    out = {}
    for g in r.json().get("elements", []):
        urn = f"urn:li:sponsoredCampaignGroup:{g.get('id', '')}"
        out[urn] = g.get("name", urn)
    return out


def _list_campaigns(group_names: dict) -> dict:
    """Return {campaign_urn: {name, group_name, status, objective}} for all campaigns.

    LinkedIn UTM mapping:
      campaign group name -> utm_campaign
      campaign name       -> utm_audience
    """
    if not AD_ACCT_URN:
        return {}
    acct_id = AD_ACCT_URN.rsplit(":", 1)[-1]
    params = {
        "q": "search",
    }
    r = requests.get(f"{BASE}/adAccounts/{acct_id}/adCampaigns",
                     headers=_headers(), params=params, timeout=15)
    if r.status_code >= 400:
        print(f"[li-bq] campaigns {r.status_code}: {r.text[:200]}")
        return {}
    out = {}
    for c in r.json().get("elements", []):
        urn        = f"urn:li:sponsoredCampaign:{c.get('id', '')}"
        group_urn  = c.get("campaignGroup", "")
        out[urn] = {
            "name":       c.get("name", urn),
            "group_name": group_names.get(group_urn, ""),  # utm_campaign
            "status":     c.get("status", ""),
            "objective":  c.get("objectiveType", ""),
        }
    return out


def _fetch_analytics(start: date, end: date) -> list[dict]:
    """
    Fetch DAILY analytics for all campaigns in the account.
    LinkedIn returns one element per (campaign, day).

    IMPORTANT: LinkedIn REST API only returns fields explicitly listed in the
    'fields' param.  Without it costInLocalCurrency is silently omitted and
    every row appears as $0 spend even when real spend exists.
    """
    if not AD_ACCT_URN:
        return []
    params = {
        "q":                     "analytics",
        "pivot":                 "CAMPAIGN",
        "timeGranularity":       "DAILY",
        "accounts[0]":           AD_ACCT_URN,
        "dateRange.start.day":   start.day,
        "dateRange.start.month": start.month,
        "dateRange.start.year":  start.year,
        "dateRange.end.day":     end.day,
        "dateRange.end.month":   end.month,
        "dateRange.end.year":    end.year,
        # Must explicitly request cost — LinkedIn omits it otherwise
        "fields": "costInLocalCurrency,impressions,clicks,externalWebsiteConversions,dateRange,pivotValues",
        "count":  1000,
    }
    elements = []
    start_idx = 0
    while True:
        params["start"] = start_idx
        r = requests.get(f"{BASE}/adAnalytics", headers=_headers(),
                         params=params, timeout=30)
        if r.status_code >= 400:
            print(f"[li-bq] analytics {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        page = data.get("elements", [])
        elements.extend(page)
        # Stop if we got fewer than requested (last page)
        if len(page) < params["count"]:
            break
        start_idx += len(page)
    return elements


def collect_and_write(days: int = None, incremental: bool = False) -> int:
    if not TOKEN or not AD_ACCT_URN:
        print("[li-bq] LI_ACCESS_TOKEN or LI_AD_ACCOUNT_URN missing — skipping")
        return 0

    end = datetime.now(_RIYADH).date()
    if incremental:
        start = end - timedelta(days=29)   # 30-day window covers all platform restatement windows
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(2025, 1, 1)   # full history from campaign launch

    print(f"[li-bq] Window {start} -> {end}")

    native_cur = _account_currency()
    print(f"[li-bq] account {AD_ACCT_URN} native={native_cur} -> converting to USD")

    try:
        group_names = _list_campaign_groups()
        campaigns   = _list_campaigns(group_names)
        analytics   = _fetch_analytics(start, end)
    except Exception as e:
        print(f"[li-bq] API error: {e}")
        return 0

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for el in analytics:
        pivot_vals = el.get("pivotValues", [])
        camp_urn   = pivot_vals[0] if pivot_vals else ""
        meta       = campaigns.get(camp_urn, {})

        # dateRange.start gives the specific day for DAILY granularity
        dr = el.get("dateRange", {}).get("start", {})
        if not dr:
            continue
        try:
            day = date(dr["year"], dr["month"], dr["day"]).isoformat()
        except (KeyError, ValueError):
            continue

        try:
            spend_native = float(el.get("costInLocalCurrency") or 0)
        except (TypeError, ValueError):
            spend_native = 0.0
        spend  = to_usd(spend_native, native_cur)
        clicks = int(el.get("clicks") or 0)
        impr   = int(el.get("impressions") or 0)
        try:
            leads = int(float(el.get("externalWebsiteConversions") or 0))
        except (TypeError, ValueError):
            leads = 0
        ctr = round(clicks / impr * 100, 4) if impr else 0.0
        cpl = round(spend / leads, 2) if leads > 0 else None

        rows.append({
            "date":                day,
            "channel":             "linkedin",
            "account_id":          AD_ACCT_URN,
            "campaign_id":         camp_urn,
            "campaign_name":       meta.get("name", camp_urn),
            "campaign_group_name": meta.get("group_name", ""),  # utm_campaign for LinkedIn
            "status":              meta.get("status", ""),
            "objective":           meta.get("objective", ""),
            "spend":          round(spend, 2),
            "impressions":    impr,
            "clicks":         clicks,
            "ctr":            ctr,
            "leads":          leads,
            "conversions":    float(leads),
            "cpl":            cpl,
            "currency":       "USD",
            "spend_native":   round(spend_native, 2),
            "currency_native": native_cur,
            "updated_at":     now,
        })

    print(f"[li-bq] {len(rows)} rows across {len(campaigns)} campaigns")
    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


# ── Ad Set level → adsets_daily ──────────────────────────────────────────────

def collect_adsets_and_write(days: int = None, incremental: bool = False) -> int:
    """
    LinkedIn Campaign grain → adsets_daily.

    LinkedIn UTM hierarchy:
      Campaign Group  = utm_campaign  → stored as campaign_id
      Campaign        = utm_audience  → stored as adset_id
    """
    if not TOKEN or not AD_ACCT_URN:
        print("[li-bq] LI_ACCESS_TOKEN or LI_AD_ACCOUNT_URN missing — skipping adsets")
        return 0

    end = datetime.now(_RIYADH).date()
    if incremental:
        start = end - timedelta(days=29)   # 30-day window covers all platform restatement windows
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(2025, 1, 1)   # full history from campaign launch

    print(f"[li-bq] adsets window {start} -> {end}")

    native_cur = _account_currency()

    try:
        group_names = _list_campaign_groups()
        campaigns   = _list_campaigns(group_names)
        analytics   = _fetch_analytics(start, end)  # pivot=CAMPAIGN — same data
    except Exception as e:
        print(f"[li-bq] adsets API error: {e}")
        return 0

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for el in analytics:
        pivot_vals = el.get("pivotValues", [])
        camp_urn   = pivot_vals[0] if pivot_vals else ""
        meta       = campaigns.get(camp_urn, {})

        dr = el.get("dateRange", {}).get("start", {})
        if not dr:
            continue
        try:
            day = date(dr["year"], dr["month"], dr["day"]).isoformat()
        except (KeyError, ValueError):
            continue

        try:
            spend_native = float(el.get("costInLocalCurrency") or 0)
        except (TypeError, ValueError):
            spend_native = 0.0
        spend  = to_usd(spend_native, native_cur)
        clicks = int(el.get("clicks") or 0)
        impr   = int(el.get("impressions") or 0)
        try:
            leads = int(float(el.get("externalWebsiteConversions") or 0))
        except (TypeError, ValueError):
            leads = 0
        ctr = round(clicks / impr * 100, 4) if impr else 0.0

        # Campaign Group URN: derive from campaign meta
        group_urn  = ""
        group_name = meta.get("group_name", "")
        # Reconstruct group URN by reversing the group_names dict
        for urn, name in group_names.items():
            if name == group_name:
                group_urn = urn
                break

        _adset_name = meta.get("name", camp_urn)
        rows.append({
            "date":          day,
            "channel":       "linkedin",
            "account_id":    AD_ACCT_URN,
            "campaign_id":   group_urn or camp_urn,   # Campaign Group = utm_campaign
            "campaign_name": group_name,
            "adset_id":      camp_urn,                # Campaign = utm_audience
            "adset_name":    _adset_name,
            "utm_audience":  _adset_name,             # LinkedIn Campaign name = utm_audience
            "status":        meta.get("status", ""),
            "spend":         round(spend, 2),
            "impressions":   impr,
            "clicks":        clicks,
            "ctr":           ctr,
            "leads":         leads,
            "conversions":   float(leads),
            "currency":      "USD",
            "updated_at":    now,
        })

    print(f"[li-bq] adsets: {len(rows)} rows across {len(campaigns)} campaigns")
    # adsets_daily DROPPED 2026-06-16 — only consumer migrated to wide_ads.
    return 0  # was: upsert_rows("adsets_daily", rows, ...)


def _list_creatives() -> dict:
    """Return {creative_urn: {campaign_urn, name, status}} for all creatives on the account."""
    if not AD_ACCT_URN:
        return {}
    acct_id = AD_ACCT_URN.rsplit(":", 1)[-1]
    out = {}
    start_idx = 0
    while True:
        r = requests.get(
            f"{BASE}/adCreatives",
            headers=_headers(),
            params={
                "q": "search",
                "search.account.values[0]": AD_ACCT_URN,
                "count": 100,
                "start": start_idx,
            },
            timeout=15,
        )
        if r.status_code >= 400:
            print(f"[li-bq] adCreatives {r.status_code}: {r.text[:200]}")
            break
        items = r.json().get("elements", [])
        for c in items:
            urn = f"urn:li:sponsoredCreative:{c.get('id', '')}"
            out[urn] = {
                "campaign_urn": c.get("campaign", ""),
                "name":         c.get("name", urn),
                "status":       c.get("status", ""),
            }
        if len(items) < 100:
            break
        start_idx += len(items)
    return out


def _fetch_ad_analytics(start: date, end: date) -> list:
    """Fetch DAILY analytics pivoted by CREATIVE (ad level)."""
    if not AD_ACCT_URN:
        return []
    params = {
        "q":                     "analytics",
        "pivot":                 "CREATIVE",
        "timeGranularity":       "DAILY",
        "accounts[0]":           AD_ACCT_URN,
        "dateRange.start.day":   start.day,
        "dateRange.start.month": start.month,
        "dateRange.start.year":  start.year,
        "dateRange.end.day":     end.day,
        "dateRange.end.month":   end.month,
        "dateRange.end.year":    end.year,
        "fields": "costInLocalCurrency,impressions,clicks,externalWebsiteConversions,dateRange,pivotValues",
        "count":  1000,
    }
    elements = []
    start_idx = 0
    while True:
        params["start"] = start_idx
        r = requests.get(f"{BASE}/adAnalytics", headers=_headers(),
                         params=params, timeout=30)
        if r.status_code >= 400:
            print(f"[li-bq] ad analytics {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        page = data.get("elements", [])
        elements.extend(page)
        if len(page) < params["count"]:
            break
        start_idx += len(page)
    return elements


def collect_ads_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad (creative) grain -> ads_daily. Uses pivot=CREATIVE on adAnalytics."""
    if not TOKEN or not AD_ACCT_URN:
        print("[li-bq] LI_ACCESS_TOKEN or LI_AD_ACCOUNT_URN missing — skipping ads")
        return 0

    end = datetime.now(_RIYADH).date()
    if incremental:
        start = end - timedelta(days=29)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(2025, 1, 1)

    print(f"[li-bq] ads window {start} -> {end}")

    native_cur = _account_currency()

    try:
        group_names = _list_campaign_groups()
        campaigns   = _list_campaigns(group_names)
        creatives   = _list_creatives()
        analytics   = _fetch_ad_analytics(start, end)
    except Exception as e:
        print(f"[li-bq] ads API error: {e}")
        return 0

    now  = datetime.now(timezone.utc).isoformat()
    rows = []

    for el in analytics:
        pivot_vals   = el.get("pivotValues", [])
        creative_urn = pivot_vals[0] if pivot_vals else ""
        creative     = creatives.get(creative_urn, {})
        camp_urn     = creative.get("campaign_urn", "")
        camp_meta    = campaigns.get(camp_urn, {})

        # Reconstruct campaign group URN
        group_name = camp_meta.get("group_name", "")
        group_urn  = ""
        for urn, name in group_names.items():
            if name == group_name:
                group_urn = urn
                break

        dr = el.get("dateRange", {}).get("start", {})
        if not dr:
            continue
        try:
            day = date(dr["year"], dr["month"], dr["day"]).isoformat()
        except (KeyError, ValueError):
            continue

        try:
            spend_native = float(el.get("costInLocalCurrency") or 0)
        except (TypeError, ValueError):
            spend_native = 0.0
        spend  = to_usd(spend_native, native_cur)
        clicks = int(el.get("clicks") or 0)
        impr   = int(el.get("impressions") or 0)
        try:
            leads = int(float(el.get("externalWebsiteConversions") or 0))
        except (TypeError, ValueError):
            leads = 0
        ctr = round(clicks / impr * 100, 4) if impr else 0.0

        # Derive numeric creative ID from URN for ad_id
        creative_id = creative_urn.rsplit(":", 1)[-1] if creative_urn else creative_urn

        rows.append({
            "date":          day,
            "channel":       "linkedin",
            "account_id":    AD_ACCT_URN,
            "campaign_id":   group_urn or camp_urn,   # Campaign Group = utm_campaign
            "campaign_name": group_name,
            "adset_id":      camp_urn,                # LinkedIn Campaign = adset
            "adset_name":    camp_meta.get("name", camp_urn),
            "ad_id":         creative_urn,
            "ad_name":       creative.get("name", creative_urn),
            "utm_content":   creative.get("name", creative_urn),
            "status":        creative.get("status", ""),
            "spend":         round(spend, 2),
            "impressions":   impr,
            "clicks":        clicks,
            "ctr":           ctr,
            "leads":         leads,
            "conversions":   float(leads),
            "currency":      "USD",
            "spend_native":  round(spend_native, 2),
            "currency_native": native_cur,
            "updated_at":    now,
        })

    print(f"[li-bq] ads: {len(rows)} rows across {len(creatives)} creatives")
    return upsert_rows("ads_daily", rows,
                       key_fields=["date", "channel", "ad_id"])


if __name__ == "__main__":
    import sys
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "all"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in ("all", "campaigns"):
        print(f"campaigns: {collect_and_write(days=days)} rows")
    if cmd in ("all", "adsets"):
        print(f"adsets:    {collect_adsets_and_write(days=days)} rows")
    if cmd in ("all", "ads"):
        print(f"ads:       {collect_ads_and_write(days=days)} rows")
