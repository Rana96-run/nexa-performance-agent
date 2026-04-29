"""
Microsoft Advertising (Bing Ads) -> BigQuery collector.
Pulls campaign-level performance reports -> campaigns_daily.

Requires MS_REFRESH_TOKEN in .env.
Run `python collectors/microsoft_ads.py auth` once to get the token.
"""
import os
import csv
import io
import time
import zipfile
import requests
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency

load_dotenv()

CLIENT_ID       = os.getenv("MS_CLIENT_ID", "")
CLIENT_SECRET   = os.getenv("MS_CLIENT_SECRET", "")
TENANT_ID       = os.getenv("MS_TENANT_ID", "")
DEVELOPER_TOKEN = os.getenv("MS_DEVELOPER_TOKEN", "")
CUSTOMER_ID     = os.getenv("MS_CUSTOMER_ID", "")
ACCOUNT_ID      = os.getenv("MS_ACCOUNT_ID", "")
REFRESH_TOKEN   = os.getenv("MS_REFRESH_TOKEN", "")

TOKEN_URL     = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE         = "https://ads.microsoft.com/msads.manage offline_access"
REPORTING_URL = "https://reporting.api.bingads.microsoft.com/api/advertiser/reporting/v13"


def _get_access_token() -> str:
    if not REFRESH_TOKEN:
        raise RuntimeError("MS_REFRESH_TOKEN is empty — run auth flow first")
    r = requests.post(TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "scope":         SCOPE,
    }, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(access_token: str) -> dict:
    return {
        "Authorization":      f"Bearer {access_token}",
        "DeveloperToken":     DEVELOPER_TOKEN,
        "CustomerId":         CUSTOMER_ID,
        "CustomerAccountId":  ACCOUNT_ID,
        "Content-Type":       "application/json",
    }


def _submit_report(access_token: str, start: date, end: date) -> str | None:
    """Submit async performance report. Returns request ID."""
    body = {
        "ReportRequest": {
            "Format":                 "Csv",
            "Language":               "English",
            "ReportName":             "NexaDailyPerformance",
            "ReturnOnlyCompleteData": False,
            "Aggregation":            "Daily",
            "ExcludeColumnHeaders":   False,
            "ExcludeReportFooter":    True,
            "ExcludeReportHeader":    True,
            "Columns": [
                "TimePeriod", "AccountId", "CurrencyCode",
                "CampaignId", "CampaignName",
                "CampaignStatus", "Impressions", "Clicks", "Spend",
                "Conversions", "CostPerConversion", "Ctr",
            ],
            "Scope": {"AccountIds": {"long": [ACCOUNT_ID]}},
            "Time": {
                "CustomDateRangeStart": {
                    "Day": start.day, "Month": start.month, "Year": start.year
                },
                "CustomDateRangeEnd": {
                    "Day": end.day, "Month": end.month, "Year": end.year
                },
            },
        }
    }
    r = requests.post(
        f"{REPORTING_URL}/SubmitGenerateReport",
        json=body, headers=_headers(access_token), timeout=20,
    )
    if r.status_code >= 400:
        print(f"[ms-bq] submit report {r.status_code}: {r.text[:200]}")
        return None
    return r.json().get("ReportRequestId")


def _poll_report(access_token: str, request_id: str,
                 max_wait: int = 300) -> str | None:
    """Poll until report is ready. Returns download URL or None."""
    for _ in range(max_wait // 5):
        r = requests.post(
            f"{REPORTING_URL}/PollGenerateReport",
            json={"ReportRequestId": request_id},
            headers=_headers(access_token), timeout=15,
        )
        if r.status_code >= 400:
            print(f"[ms-bq] poll {r.status_code}: {r.text[:100]}")
            return None
        data   = r.json()
        status = data.get("ReportRequestStatus", {})
        state  = status.get("Status", "")
        if state == "Success":
            return status.get("ReportDownloadUrl")
        if state in ("Error", "Failed"):
            print(f"[ms-bq] report failed: {status}")
            return None
        time.sleep(5)
    print("[ms-bq] report timed out")
    return None


def _download_and_parse(url: str) -> list[dict]:
    """Download ZIP -> extract CSV -> parse rows."""
    r = requests.get(url, timeout=60)
    rows = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            with z.open(name) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
                for row in reader:
                    rows.append(row)
    return rows


def collect_and_write(days: int = None, incremental: bool = False) -> int:
    if not REFRESH_TOKEN:
        print("[ms-bq] MS_REFRESH_TOKEN not set — skipping Microsoft Ads")
        return 0

    try:
        access_token = _get_access_token()
    except Exception as e:
        print(f"[ms-bq] auth failed: {e}")
        return 0

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    print(f"[ms-bq] Window {start} -> {end}")

    request_id = _submit_report(access_token, start, end)
    if not request_id:
        return 0

    download_url = _poll_report(access_token, request_id)
    if not download_url:
        return 0

    csv_rows = _download_and_parse(download_url)
    now = datetime.now(timezone.utc).isoformat()
    bq_rows = []

    def _f(val, default=0.0):
        """Parse a CSV numeric string that may have commas, % signs, or be blank."""
        try:
            return float(str(val or "").replace(",", "").replace("%", "").strip() or default)
        except (TypeError, ValueError):
            return float(default)

    for row in csv_rows:
        day  = (row.get("TimePeriod") or "")[:10]
        if not day:
            continue
        native_cur   = normalize_currency(row.get("CurrencyCode"))
        spend_native = _f(row.get("Spend"))
        spend        = to_usd(spend_native, native_cur)
        leads        = int(_f(row.get("Conversions")))
        impr         = int(_f(row.get("Impressions")))
        clicks       = int(_f(row.get("Clicks")))
        cpl_native   = _f(row.get("CostPerConversion"))
        cpl_usd      = to_usd(cpl_native, native_cur) if cpl_native > 0 else None
        # Ctr field is "N %" (e.g. "1.23 %") — strip % then divide by 100
        ctr = _f(row.get("Ctr")) / 100

        bq_rows.append({
            "date":           day,
            "channel":        "microsoft_ads",
            "account_id":     ACCOUNT_ID,
            "campaign_id":    str(row.get("CampaignId", "")),
            "campaign_name":  row.get("CampaignName", ""),
            "status":         row.get("CampaignStatus", ""),
            "objective":      None,
            "spend":          round(spend, 2),
            "impressions":    impr,
            "clicks":         clicks,
            "ctr":            round(ctr, 6),
            "leads":          leads,
            "conversions":    float(leads),
            "cpl":            round(cpl_usd, 2) if cpl_usd else None,
            "currency":       "USD",
            "spend_native":   round(spend_native, 2),
            "currency_native": native_cur,
            "updated_at":     now,
        })

    print(f"[ms-bq] parsed {len(bq_rows)} rows")
    return upsert_rows("campaigns_daily", bq_rows,
                       key_fields=["date", "channel", "campaign_id"])


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"Microsoft Ads BQ complete: {n} rows")
