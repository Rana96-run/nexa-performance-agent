"""
LinkedIn Ads → BigQuery collector.
Pulls per-day per-campaign stats → campaigns_daily.

Auth: LI_ACCESS_TOKEN in .env (expires every 60 days — refresh manually).
      LI_AD_ACCOUNT_URN e.g. urn:li:sponsoredAccount:506171805
"""
import os
import requests
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

load_dotenv(override=True)

BASE        = "https://api.linkedin.com/rest"
TOKEN       = os.getenv("LI_ACCESS_TOKEN", "")
AD_ACCT_URN = os.getenv("LI_AD_ACCOUNT_URN", "")


def _headers() -> dict:
    return {
        "Authorization":             f"Bearer {TOKEN}",
        # LinkedIn rolls API versions monthly; their N-12 retirement window
        # means we need to bump this roughly twice a year.  Current Apr 2026.
        "LinkedIn-Version":          "202502",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _account_currency() -> str:
    """Fetch the ad account's native currency. Defaults to SAR on error."""
    if not AD_ACCT_URN:
        return "SAR"
    # Extract numeric ID from URN: "urn:li:sponsoredAccount:506171805" → "506171805"
    acct_id = AD_ACCT_URN.rsplit(":", 1)[-1]
    try:
        r = requests.get(f"{BASE}/adAccounts/{acct_id}",
                         headers=_headers(), timeout=15)
        if r.status_code < 400:
            return normalize_currency(r.json().get("currency"))
    except Exception as e:
        print(f"[li-bq] currency lookup failed: {e}")
    return "SAR"


def _list_campaigns() -> dict:
    """Return {campaign_urn: {name, status, objective}} for all campaigns."""
    if not AD_ACCT_URN:
        return {}
    params = {
        "q":                         "search",
        "search.account.values[0]":  AD_ACCT_URN,
        "fields":                    "id,name,status,objectiveType",
    }
    r = requests.get(f"{BASE}/adCampaigns", headers=_headers(),
                     params=params, timeout=15)
    if r.status_code >= 400:
        print(f"[li-bq] campaigns {r.status_code}: {r.text[:200]}")
        return {}
    out = {}
    for c in r.json().get("elements", []):
        urn = f"urn:li:sponsoredCampaign:{c.get('id', '')}"
        out[urn] = {
            "name":      c.get("name", urn),
            "status":    c.get("status", ""),
            "objective": c.get("objectiveType", ""),
        }
    return out


def _fetch_analytics(start: date, end: date) -> list[dict]:
    """
    Fetch DAILY analytics for all campaigns in the account.
    LinkedIn returns one element per (campaign, day).
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
        "fields": (
            "dateRange,impressions,clicks,"
            "costInLocalCurrency,externalWebsiteConversions,"
            "pivotValues"
        ),
    }
    r = requests.get(f"{BASE}/adAnalytics", headers=_headers(),
                     params=params, timeout=30)
    if r.status_code >= 400:
        print(f"[li-bq] analytics {r.status_code}: {r.text[:200]}")
        return []
    return r.json().get("elements", [])


def collect_and_write(days: int = None, incremental: bool = False) -> int:
    if not TOKEN or not AD_ACCT_URN:
        print("[li-bq] LI_ACCESS_TOKEN or LI_AD_ACCOUNT_URN missing — skipping")
        return 0

    end = date.today()
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    print(f"[li-bq] Window {start} → {end}")

    native_cur = _account_currency()
    print(f"[li-bq] account {AD_ACCT_URN} native={native_cur} → converting to USD")

    try:
        campaigns = _list_campaigns()
        analytics = _fetch_analytics(start, end)
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
            "date":           day,
            "channel":        "linkedin",
            "account_id":     AD_ACCT_URN,
            "campaign_id":    camp_urn,
            "campaign_name":  meta.get("name", camp_urn),
            "status":         meta.get("status", ""),
            "objective":      meta.get("objective", ""),
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


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"LinkedIn BQ complete: {n} rows")
