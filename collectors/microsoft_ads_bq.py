"""
Microsoft Advertising (Bing Ads) -> BigQuery collector.
Pulls campaign-level performance reports -> campaigns_daily.

Supports multiple accounts via env vars:
  Primary:   MS_ACCOUNT_ID / MS_CUSTOMER_ID / MS_REFRESH_TOKEN
             (confidential client — obtained via authorization_code, sends client_secret)
  Secondary: MS_ACCOUNT_ID_2 / MS_CUSTOMER_ID_2 / MS_REFRESH_TOKEN_2
             (public client — obtained via device_code, NO client_secret)

Run `python collectors/microsoft_ads.py auth` once per account to get tokens.
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

_MS_TENANT    = os.getenv("MS_TENANT_ID", "common")
TOKEN_URL     = f"https://login.microsoftonline.com/{_MS_TENANT}/oauth2/v2.0/token"
SCOPE         = "https://ads.microsoft.com/msads.manage offline_access"
REPORTING_URL = "https://reporting.api.bingads.microsoft.com/Reporting/v13"

# ---------------------------------------------------------------------------
# Legacy single-account vars kept for backward compat (used below in _accounts)
# ---------------------------------------------------------------------------
CUSTOMER_ID     = os.getenv("MS_CUSTOMER_ID", "")
ACCOUNT_ID      = os.getenv("MS_ACCOUNT_ID", "")
REFRESH_TOKEN   = os.getenv("MS_REFRESH_TOKEN", "")


def _accounts() -> list[dict]:
    """Return all configured MS Ads accounts.

    Each entry: {account_id, customer_id, refresh_token, public_client}
    public_client=True  → device_code token, do NOT send client_secret on refresh
    public_client=False → authorization_code token, send client_secret on refresh
    """
    accs = []
    if os.getenv("MS_ACCOUNT_ID") and os.getenv("MS_REFRESH_TOKEN"):
        accs.append({
            "account_id":    os.getenv("MS_ACCOUNT_ID", ""),
            "customer_id":   os.getenv("MS_CUSTOMER_ID", ""),
            "refresh_token": os.getenv("MS_REFRESH_TOKEN", ""),
            "public_client": False,  # confidential client (authorization_code)
        })
    if os.getenv("MS_ACCOUNT_ID_2") and os.getenv("MS_REFRESH_TOKEN_2"):
        accs.append({
            "account_id":    os.getenv("MS_ACCOUNT_ID_2", ""),
            "customer_id":   os.getenv("MS_CUSTOMER_ID_2", ""),
            "refresh_token": os.getenv("MS_REFRESH_TOKEN_2", ""),
            "public_client": True,   # public client (device_code — no client_secret)
        })
    return accs


def _get_access_token_for(refresh_token: str, public_client: bool = False) -> str:
    """Exchange refresh token for access token.
    public_client=True omits client_secret (device_code tokens reject it).
    """
    data = {
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "refresh_token": refresh_token,
        "scope":         SCOPE,
    }
    if not public_client:
        data["client_secret"] = CLIENT_SECRET
    r = requests.post(TOKEN_URL, data=data, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def _get_access_token() -> str:
    """Legacy single-account helper (used by existing callers)."""
    if not REFRESH_TOKEN:
        raise RuntimeError("MS_REFRESH_TOKEN is empty — run auth flow first")
    return _get_access_token_for(REFRESH_TOKEN, public_client=False)


def _headers_for(access_token: str, account_id: str, customer_id: str) -> dict:
    return {
        "Authorization":     f"Bearer {access_token}",
        "DeveloperToken":    DEVELOPER_TOKEN,
        "CustomerId":        customer_id,
        "CustomerAccountId": account_id,
        "Content-Type":      "application/json",
    }


def _headers(access_token: str) -> dict:
    """Legacy single-account headers (backward compat)."""
    return _headers_for(access_token, ACCOUNT_ID, CUSTOMER_ID)


def _submit_report_generic(access_token: str, start: date, end: date,
                           report_type: str, columns: list[str],
                           report_name: str = "NexaReport",
                           account_id: str = "",
                           customer_id: str = "") -> str | None:
    """Generic async report submission. Returns report request ID or None."""
    act_id  = account_id  or ACCOUNT_ID
    cust_id = customer_id or CUSTOMER_ID
    body = {
        "ReportRequest": {
            "Type":                   report_type,   # REST discriminator — required
            "Format":                 "Csv",
            "Language":               "English",
            "ReportName":             report_name,
            "ReturnOnlyCompleteData": False,
            "Aggregation":            "Daily",
            "ExcludeColumnHeaders":   False,
            "ExcludeReportFooter":    True,
            "ExcludeReportHeader":    True,
            "Columns":                columns,
            "Scope":                  {"AccountIds": [int(act_id)]},
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
        f"{REPORTING_URL}/GenerateReport/Submit",
        json=body, headers=_headers_for(access_token, act_id, cust_id), timeout=20,
    )
    if r.status_code >= 400:
        print(f"[ms-bq] submit {report_type} acct={act_id} {r.status_code}: {r.text[:200]}")
        return None
    return r.json().get("ReportRequestId")


def _submit_report(access_token: str, start: date, end: date,
                   account_id: str = "", customer_id: str = "") -> str | None:
    """Submit campaign-level async performance report. Returns request ID."""
    return _submit_report_generic(
        access_token, start, end,
        report_type="CampaignPerformanceReportRequest",
        report_name="NexaDailyPerformance",
        columns=[
            "TimePeriod", "AccountId", "CurrencyCode",
            "CampaignId", "CampaignName",
            "CampaignStatus", "Impressions", "Clicks", "Spend",
            "Conversions", "CostPerConversion", "Ctr",
        ],
        account_id=account_id,
        customer_id=customer_id,
    )


def _poll_report(access_token: str, request_id: str,
                 max_wait: int = 300,
                 account_id: str = "", customer_id: str = "") -> str | None:
    """Poll until report is ready. Returns download URL or None."""
    hdrs = _headers_for(access_token, account_id or ACCOUNT_ID, customer_id or CUSTOMER_ID)
    for _ in range(max_wait // 5):
        r = requests.post(
            f"{REPORTING_URL}/GenerateReport/Poll",
            json={"ReportRequestId": request_id},
            headers=hdrs, timeout=15,
        )
        if r.status_code >= 400:
            print(f"[ms-bq] poll {r.status_code}: {r.text[:100]}")
            return None
        data   = r.json()
        status = data.get("ReportRequestStatus", {})
        state  = status.get("Status", "")
        if state == "Success":
            url = status.get("ReportDownloadUrl")
            if not url:
                # Microsoft returns Success + null URL when the account has
                # ZERO activity in the queried window. NOT a bug — the
                # platform legitimately has nothing to report. Most common
                # cause: campaigns paused on the Bing Ads side. Verify in UI:
                # https://ui.ads.microsoft.com
                print("[ms-bq] WARNING: report Success but ReportDownloadUrl=null "
                      "-> no spend/activity in window. Likely campaigns paused.")
            return url
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
    accs = _accounts()
    if not accs:
        print("[ms-bq] No MS Ads accounts configured — skipping")
        return 0

    def _f(val, default=0.0):
        """Parse a CSV numeric string that may have commas, % signs, or be blank."""
        try:
            return float(str(val or "").replace(",", "").replace("%", "").strip() or default)
        except (TypeError, ValueError):
            return float(default)

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    # IMPORTANT — collect all accounts' rows into ONE buffer before upserting.
    # upsert_rows() DELETE scope is (date, channel) — if we upsert each account
    # separately, the second account's DELETE wipes the first account's rows
    # for any shared date. Found 2026-05-15: account 188176729's spend was being
    # erased every refresh by account 187231519's subsequent run.
    all_rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for acc in accs:
        act_id  = acc["account_id"]
        cust_id = acc["customer_id"]
        try:
            access_token = _get_access_token_for(acc["refresh_token"], acc["public_client"])
        except Exception as e:
            print(f"[ms-bq] auth failed for account {act_id}: {e}")
            continue

        print(f"[ms-bq] campaigns window {start} -> {end} (account {act_id})")
        request_id = _submit_report(access_token, start, end,
                                    account_id=act_id, customer_id=cust_id)
        if not request_id:
            continue
        download_url = _poll_report(access_token, request_id,
                                    account_id=act_id, customer_id=cust_id)
        if not download_url:
            continue

        csv_rows = _download_and_parse(download_url)
        bq_rows = []
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
            ctr          = _f(row.get("Ctr")) / 100
            bq_rows.append({
                "date":            day,
                "channel":         "microsoft_ads",
                "account_id":      act_id,
                "campaign_id":     str(row.get("CampaignId", "")),
                "campaign_name":   row.get("CampaignName", ""),
                "status":          row.get("CampaignStatus", ""),
                "objective":       None,
                "spend":           round(spend, 2),
                "impressions":     impr,
                "clicks":          clicks,
                "ctr":             round(ctr, 6),
                "leads":           leads,
                "conversions":     float(leads),
                "cpl":             round(cpl_usd, 2) if cpl_usd else None,
                "currency":        "USD",
                "spend_native":    round(spend_native, 2),
                "currency_native": native_cur,
                "updated_at":      now,
            })
        print(f"[ms-bq] campaigns parsed {len(bq_rows)} rows (account {act_id})")
        all_rows.extend(bq_rows)

    if not all_rows:
        return 0
    # Single upsert with combined rows from all accounts. DELETE wipes the
    # (date, channel) partition once — both accounts' rows then re-inserted.
    return upsert_rows("campaigns_daily", all_rows,
                       key_fields=["date", "channel", "campaign_id"])


# ── Ad Group level → adsets_daily ────────────────────────────────────────────

def collect_adsets_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad group grain → adsets_daily. utm_audience maps to AdGroupName."""
    accs = _accounts()
    if not accs:
        print("[ms-bq] No MS Ads accounts configured — skipping adgroups")
        return 0

    def _f(val, default=0.0):
        try:
            return float(str(val or "").replace(",", "").replace("%", "").strip() or default)
        except (TypeError, ValueError):
            return float(default)

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    # Multi-account aggregation — same bug as collect_and_write (see comments
    # there). Pool all accounts' rows then upsert once.
    all_rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for acc in accs:
        act_id  = acc["account_id"]
        cust_id = acc["customer_id"]
        try:
            access_token = _get_access_token_for(acc["refresh_token"], acc["public_client"])
        except Exception as e:
            print(f"[ms-bq] adgroups auth failed for account {act_id}: {e}")
            continue

        print(f"[ms-bq] adgroups window {start} -> {end} (account {act_id})")
        request_id = _submit_report_generic(
            access_token, start, end,
            report_type="AdGroupPerformanceReportRequest",
            report_name="NexaAdGroupPerformance",
            columns=[
                "TimePeriod", "AccountId", "CurrencyCode",
                "CampaignId", "CampaignName",
                "AdGroupId", "AdGroupName", "Status",
                "TrackingTemplate", "CustomParameters",
                "Impressions", "Clicks", "Spend",
                "Conversions", "CostPerConversion", "Ctr",
            ],
            account_id=act_id, customer_id=cust_id,
        )
        if not request_id:
            continue
        download_url = _poll_report(access_token, request_id,
                                    account_id=act_id, customer_id=cust_id)
        if not download_url:
            continue

        csv_rows = _download_and_parse(download_url)
        bq_rows = []
        for row in csv_rows:
            day = (row.get("TimePeriod") or "")[:10]
            if not day:
                continue
            native_cur   = normalize_currency(row.get("CurrencyCode"))
            spend_native = _f(row.get("Spend"))
            spend        = to_usd(spend_native, native_cur)
            leads        = int(_f(row.get("Conversions")))
            impr         = int(_f(row.get("Impressions")))
            clicks       = int(_f(row.get("Clicks")))
            ctr          = _f(row.get("Ctr")) / 100
            # utm_audience: Microsoft tracking templates use {_audience}=SomeValue
            # as a custom parameter at ad group level — same pattern as {_adname}
            # at ad level. HubSpot captures the _audience VALUE (e.g.
            # 'Bing_AR_Brand_Keywords'), NOT the raw AdGroupName from the API.
            # Parse custom params first; fall back to utm_audience= in template;
            # last resort is AdGroupName (won't join to HubSpot but at least shows spend).
            import re as _re
            adgroup_name = row.get("AdGroupName", "")
            _cust_params_str = row.get("CustomParameters") or ""
            _track_tmpl      = row.get("TrackingTemplate") or ""
            _cust_params = {}
            for m in _re.finditer(r"\{_([A-Za-z0-9_]+)\}\s*=\s*([^;]+)", _cust_params_str):
                _cust_params[m.group(1)] = m.group(2).strip()
            # Tracking template: utm_audience={_adgroup} → custom param key = "adgroup"
            # (same pattern as utm_content={_adname} → key = "adname" for ads)
            _utm_audience = _cust_params.get("adgroup")
            if not _utm_audience:
                # Try resolving utm_audience= from the tracking template using custom params
                mm = _re.search(r"utm_audience=([^&\s\"']+)", _track_tmpl, _re.IGNORECASE)
                if mm:
                    _raw = mm.group(1)
                    _resolved = _re.sub(
                        r"\{_([A-Za-z0-9_]+)\}",
                        lambda x: _cust_params.get(x.group(1), x.group(0)),
                        _raw,
                    )
                    if "{" not in _resolved:
                        _utm_audience = _resolved
            if not _utm_audience:
                _utm_audience = adgroup_name or None   # fallback — won't join HubSpot
            bq_rows.append({
                "date":          day,
                "channel":       "microsoft_ads",
                "account_id":    act_id,
                "campaign_id":   str(row.get("CampaignId", "")),
                "campaign_name": row.get("CampaignName", ""),
                "adset_id":      str(row.get("AdGroupId", "")),
                "adset_name":    adgroup_name,
                "utm_audience":  _utm_audience,
                "status":        row.get("Status", ""),
                "spend":         round(spend, 2),
                "impressions":   impr,
                "clicks":        clicks,
                "ctr":           round(ctr, 6),
                "leads":         leads,
                "conversions":   float(leads),
                "currency":      "USD",
                "updated_at":    now,
            })
        print(f"[ms-bq] adgroups parsed {len(bq_rows)} rows (account {act_id})")
        all_rows.extend(bq_rows)

    if not all_rows:
        return 0
    return upsert_rows("adsets_daily", all_rows,
                       key_fields=["date", "channel", "adset_id"])


# ── Keyword level → keywords_daily ───────────────────────────────────────────

def collect_keywords_and_write(days: int = None, incremental: bool = False) -> int:
    """Keyword grain → keywords_daily. utm_term maps to Keyword text."""
    accs = _accounts()
    if not accs:
        print("[ms-bq] No MS Ads accounts configured — skipping keywords")
        return 0

    def _f(val, default=0.0):
        try:
            return float(str(val or "").replace(",", "").replace("%", "").strip() or default)
        except (TypeError, ValueError):
            return float(default)

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    # Multi-account aggregation — same bug as collect_and_write.
    all_rows: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for acc in accs:
        act_id  = acc["account_id"]
        cust_id = acc["customer_id"]
        try:
            access_token = _get_access_token_for(acc["refresh_token"], acc["public_client"])
        except Exception as e:
            print(f"[ms-bq] keywords auth failed for account {act_id}: {e}")
            continue

        print(f"[ms-bq] keywords window {start} -> {end} (account {act_id})")
        request_id = _submit_report_generic(
            access_token, start, end,
            report_type="KeywordPerformanceReportRequest",
            report_name="NexaKeywordPerformance",
            columns=[
                "TimePeriod", "AccountId", "CurrencyCode",
                "CampaignId", "CampaignName",
                "AdGroupId", "AdGroupName",
                "KeywordId", "Keyword", "BidMatchType", "QualityScore",
                "Impressions", "Clicks", "Spend",
                "Conversions", "CostPerConversion", "Ctr", "AverageCpc",
            ],
            account_id=act_id, customer_id=cust_id,
        )
        if not request_id:
            continue
        download_url = _poll_report(access_token, request_id,
                                    account_id=act_id, customer_id=cust_id)
        if not download_url:
            continue

        csv_rows = _download_and_parse(download_url)
        bq_rows = []
        for row in csv_rows:
            day = (row.get("TimePeriod") or "")[:10]
            if not day:
                continue
            native_cur     = normalize_currency(row.get("CurrencyCode"))
            spend_native   = _f(row.get("Spend"))
            spend          = to_usd(spend_native, native_cur)
            avg_cpc_native = _f(row.get("AverageCpc"))
            avg_cpc        = to_usd(avg_cpc_native, native_cur)
            conv           = _f(row.get("Conversions"))
            ctr            = _f(row.get("Ctr")) / 100
            qs_raw         = row.get("QualityScore", "")
            try:
                qs = int(float(qs_raw)) if qs_raw and qs_raw not in ("--", "") else None
            except (ValueError, TypeError):
                qs = None
            bq_rows.append({
                "date":          day,
                "channel":       "microsoft_ads",
                "account_id":    act_id,
                "campaign_id":   str(row.get("CampaignId", "")),
                "campaign_name": row.get("CampaignName", ""),
                "adgroup_id":    str(row.get("AdGroupId", "")),
                "adgroup_name":  row.get("AdGroupName", ""),
                "keyword_id":    str(row.get("KeywordId", "")),
                "keyword_text":  row.get("Keyword", ""),
                "match_type":    row.get("BidMatchType", ""),
                "status":        None,
                "quality_score": qs,
                "spend":         round(spend, 2),
                "impressions":   int(_f(row.get("Impressions"))),
                "clicks":        int(_f(row.get("Clicks"))),
                "ctr":           round(ctr, 6),
                "avg_cpc":       round(avg_cpc, 4),
                "conversions":   float(conv),
                "currency":      "USD",
                "updated_at":    now,
            })
        print(f"[ms-bq] keywords parsed {len(bq_rows)} rows (account {act_id})")
        all_rows.extend(bq_rows)

    if not all_rows:
        return 0
    return upsert_rows("keywords_daily", all_rows,
                       key_fields=["date", "channel", "adgroup_id", "keyword_id"])


# ── Ad level → ads_daily ───────────────────────────────────────────────────────

def collect_ads_and_write(days: int = None, incremental: bool = False) -> int:
    """Ad grain → ads_daily. utm_content maps to AdId.

    Note Microsoft Ads naming inconsistency vs other report types:
      AdGroupPerformanceReport uses 'Status' (not AdGroupStatus)
      KeywordPerformanceReport uses 'KeywordStatus'
      AdPerformanceReport      uses 'AdStatus' (NOT Status — would 400)
    """
    accs = _accounts()
    if not accs:
        print("[ms-bq] No MS Ads accounts configured — skipping ads")
        return 0

    def _f(val, default=0.0):
        try:
            return float(str(val or "").replace(",", "").replace("%", "").strip() or default)
        except (TypeError, ValueError):
            return float(default)

    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    all_rows: list[dict] = []
    for acc in accs:
        act_id  = acc["account_id"]
        cust_id = acc["customer_id"]
        try:
            access_token = _get_access_token_for(acc["refresh_token"], acc["public_client"])
        except Exception as e:
            print(f"[ms-bq] ads auth failed for account {act_id}: {e}")
            continue

        print(f"[ms-bq] ads window {start} -> {end} (account {act_id})")
        request_id = _submit_report_generic(
            access_token, start, end,
            report_type="AdPerformanceReportRequest",
            report_name="NexaAdPerformance",
            columns=[
                "TimePeriod", "AccountId", "CurrencyCode",
                "CampaignId", "CampaignName",
                "AdGroupId", "AdGroupName",
                "AdId", "AdTitle", "AdDescription", "AdType", "AdStatus",
                "FinalUrl", "TrackingTemplate", "CustomParameters",
                "Impressions", "Clicks", "Spend",
                "Conversions", "CostPerConversion", "Ctr",
            ],
            account_id=act_id, customer_id=cust_id,
        )
        if not request_id:
            continue
        download_url = _poll_report(access_token, request_id,
                                    account_id=act_id, customer_id=cust_id)
        if not download_url:
            continue

        csv_rows = _download_and_parse(download_url)
        now = datetime.now(timezone.utc).isoformat()
        bq_rows = []
        for row in csv_rows:
            day = (row.get("TimePeriod") or "")[:10]
            if not day:
                continue
            native_cur   = normalize_currency(row.get("CurrencyCode"))
            spend_native = _f(row.get("Spend"))
            spend        = to_usd(spend_native, native_cur)
            leads        = int(_f(row.get("Conversions")))
            ctr          = _f(row.get("Ctr")) / 100
            cpl_native   = _f(row.get("CostPerConversion"))
            cpl_usd      = to_usd(cpl_native, native_cur) if cpl_native > 0 else None
            # Microsoft Ads stores per-ad URL config in CustomParameters:
            #   "{_adname}=Bing_AR_Feature_Competitros_HubSpot"
            # The campaign/ad_group-level TrackingTemplate uses
            # `utm_content={_adname}`, so the resolved value at click time
            # equals the `_adname` value here. We take it directly as
            # utm_content (no need to read the template).
            #
            # Fallback chain:
            #   1. _adname value from CustomParameters     (primary, matches HubSpot)
            #   2. utm_content= in TrackingTemplate         (literal template, rare at ad level)
            #   3. utm_content= in FinalUrl                 (last resort)
            _final_url   = row.get("FinalUrl") or ""
            _track_tmpl  = row.get("TrackingTemplate") or ""
            _cust_params_str = row.get("CustomParameters") or ""
            import re as _re
            _cust_params = {}
            for m in _re.finditer(r"\{_([A-Za-z0-9_]+)\}\s*=\s*([^;]+)", _cust_params_str):
                _cust_params[m.group(1)] = m.group(2).strip()
            _utm_content = _cust_params.get("adname")
            if not _utm_content:
                # Fall back to parsing utm_content from templates/URLs
                for _candidate in (_track_tmpl, _final_url):
                    if not _candidate:
                        continue
                    mm = _re.search(r"utm_content=([^&\s\"']+)", _candidate, _re.IGNORECASE)
                    if mm:
                        _raw = mm.group(1)
                        _resolved = _re.sub(
                            r"\{_([A-Za-z0-9_]+)\}",
                            lambda x: _cust_params.get(x.group(1), x.group(0)),
                            _raw,
                        )
                        if "{" not in _resolved:
                            _utm_content = _resolved
                            break
            ad_name = (row.get("AdTitle") or row.get("AdDescription") or row.get("AdId") or "").strip()
            bq_rows.append({
                "date":          day,
                "channel":       "microsoft_ads",
                "account_id":    act_id,
                "campaign_id":   str(row.get("CampaignId", "")),
                "campaign_name": row.get("CampaignName", ""),
                "adset_id":      str(row.get("AdGroupId", "")),
                "adset_name":    row.get("AdGroupName", ""),
                "ad_id":         str(row.get("AdId", "")),
                "ad_name":       ad_name,
                "utm_content":   _utm_content,
                "status":        row.get("AdStatus", ""),
                "spend":         round(spend, 2),
                "impressions":   int(_f(row.get("Impressions"))),
                "clicks":        int(_f(row.get("Clicks"))),
                "ctr":           round(ctr, 6),
                "leads":         leads,
                "conversions":   float(leads),
                "cpl":           round(cpl_usd, 2) if cpl_usd else None,
                "frequency":     None,
                "currency":      "USD",
                "final_url":     row.get("FinalUrl", ""),
                "updated_at":    now,
            })
        print(f"[ms-bq] ads parsed {len(bq_rows)} rows (account {act_id})")
        all_rows.extend(bq_rows)

    if not all_rows:
        return 0
    return upsert_rows("ads_daily", all_rows,
                       key_fields=["date", "channel", "ad_id"])


if __name__ == "__main__":
    import sys
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "all"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in ("all", "campaigns"):
        print(f"campaigns: {collect_and_write(days=days)} rows")
    if cmd in ("all", "adgroups"):
        print(f"adgroups:  {collect_adsets_and_write(days=days)} rows")
    if cmd in ("all", "keywords"):
        print(f"keywords:  {collect_keywords_and_write(days=days)} rows")
    if cmd in ("all", "ads"):
        print(f"ads:       {collect_ads_and_write(days=days)} rows")
