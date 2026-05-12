"""
Meta -> BigQuery collector.
Pulls per-day metrics at campaign / adset / ad grain.

  collect_and_write()        -> campaigns_daily
  collect_adsets_and_write() -> adsets_daily
  collect_ads_and_write()    -> ads_daily
"""
from datetime import date, timedelta, datetime, timezone
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from config import META_ACCESS_TOKEN, META_AD_ACCOUNTS
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency


def _init():
    FacebookAdsApi.init(access_token=META_ACCESS_TOKEN)


def _date_window(days, incremental):
    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)
    return start, end


def _native_currency(account_id):
    try:
        acct = AdAccount(account_id).api_get(fields=["currency"])
        return normalize_currency(acct.get("currency"))
    except Exception as e:
        print(f"[meta]   {account_id} currency lookup failed ({e}) — defaulting to SAR")
        return "SAR"


def _leads_from_actions(actions):
    actions = actions or []
    leads = next((int(float(a["value"])) for a in actions if a.get("action_type") == "lead"), 0)
    if leads:
        return leads
    return next((int(float(a["value"])) for a in actions if a.get("action_type") == "purchase"), 0)


# ── Campaign level → campaigns_daily ─────────────────────────────────────────

def collect_and_write(days: int = None, incremental: bool = False):
    """Campaign grain → campaigns_daily."""
    _init()
    start, end = _date_window(days, incremental)
    now        = datetime.now(timezone.utc).isoformat()
    rows       = []
    accounts   = [a for a in META_AD_ACCOUNTS if a]
    print(f"[meta] campaigns {start} -> {end} | {len(accounts)} account(s)")

    for account_id in accounts:
        account    = AdAccount(account_id)
        native_cur = _native_currency(account_id)
        count_before = len(rows)
        try:
            for ins in account.get_insights(params={
                "level": "campaign",
                "time_range": {"since": str(start), "until": str(end)},
                "time_increment": 1,
                "fields": ["campaign_id", "campaign_name",
                           "spend", "actions", "impressions", "clicks", "ctr"],
                "limit": 500,
            }):
                spend_native = float(ins.get("spend", 0) or 0)
                spend        = to_usd(spend_native, native_cur)
                conversions  = _leads_from_actions(ins.get("actions"))
                rows.append({
                    "date":            ins.get("date_start"),
                    "channel":         "meta",
                    "account_id":      account_id,
                    "campaign_id":     str(ins.get("campaign_id")),
                    "campaign_name":   ins.get("campaign_name"),
                    "status":          None,
                    "objective":       None,
                    "spend":           round(spend, 2),
                    "impressions":     int(ins.get("impressions", 0) or 0),
                    "clicks":          int(ins.get("clicks", 0) or 0),
                    "ctr":             round(float(ins.get("ctr", 0) or 0), 4),
                    "leads":           conversions,
                    "conversions":     float(conversions),
                    "cpl":             round(spend / conversions, 2) if conversions > 0 else None,
                    "currency":        "USD",
                    "spend_native":    round(spend_native, 2),
                    "currency_native": native_cur,
                    "updated_at":      now,
                })
        except Exception as e:
            print(f"[meta]   account {account_id} error: {e}")
        print(f"[meta]   account {account_id}: {len(rows) - count_before} rows")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


# ── Ad Set level → adsets_daily ──────────────────────────────────────────────

def collect_adsets_and_write(days: int = None, incremental: bool = False):
    """Ad set grain → adsets_daily. Same token, level='adset'."""
    _init()
    start, end = _date_window(days, incremental)
    now        = datetime.now(timezone.utc).isoformat()
    rows       = []
    accounts   = [a for a in META_AD_ACCOUNTS if a]
    print(f"[meta] adsets {start} -> {end} | {len(accounts)} account(s)")

    for account_id in accounts:
        account    = AdAccount(account_id)
        native_cur = _native_currency(account_id)
        count_before = len(rows)
        try:
            for ins in account.get_insights(params={
                "level": "adset",
                "time_range": {"since": str(start), "until": str(end)},
                "time_increment": 1,
                "fields": [
                    "campaign_id", "campaign_name",
                    "adset_id", "adset_name",
                    "spend", "actions", "impressions", "clicks", "ctr", "frequency",
                ],
                "limit": 500,
            }):
                spend_native = float(ins.get("spend", 0) or 0)
                spend        = to_usd(spend_native, native_cur)
                conversions  = _leads_from_actions(ins.get("actions"))
                rows.append({
                    "date":          ins.get("date_start"),
                    "channel":       "meta",
                    "account_id":    account_id,
                    "campaign_id":   str(ins.get("campaign_id")),
                    "campaign_name": ins.get("campaign_name"),
                    "adset_id":      str(ins.get("adset_id")),
                    "adset_name":    ins.get("adset_name"),
                    "utm_audience":  ins.get("adset_name"),  # Meta {{adset.name}} resolves to this
                    "status":        None,
                    "spend":         round(spend, 2),
                    "impressions":   int(ins.get("impressions", 0) or 0),
                    "clicks":        int(ins.get("clicks", 0) or 0),
                    "ctr":           round(float(ins.get("ctr", 0) or 0), 4),
                    "leads":         conversions,
                    "conversions":   float(conversions),
                    "frequency":     round(float(ins.get("frequency", 0) or 0), 4),
                    "currency":      "USD",
                    "updated_at":    now,
                })
        except Exception as e:
            print(f"[meta]   adsets account {account_id} error: {e}")
        print(f"[meta]   adsets account {account_id}: {len(rows) - count_before} rows")

    return upsert_rows("adsets_daily", rows,
                       key_fields=["date", "channel", "adset_id"])


# ── Ad level → ads_daily ─────────────────────────────────────────────────────

def collect_ads_and_write(days: int = None, incremental: bool = False):
    """Ad grain → ads_daily. Same token, level='ad'."""
    _init()
    start, end = _date_window(days, incremental)
    now        = datetime.now(timezone.utc).isoformat()
    rows       = []
    accounts   = [a for a in META_AD_ACCOUNTS if a]
    print(f"[meta] ads {start} -> {end} | {len(accounts)} account(s)")

    for account_id in accounts:
        account    = AdAccount(account_id)
        native_cur = _native_currency(account_id)
        count_before = len(rows)
        try:
            for ins in account.get_insights(params={
                "level": "ad",
                "time_range": {"since": str(start), "until": str(end)},
                "time_increment": 1,
                "fields": [
                    "campaign_id", "campaign_name",
                    "adset_id", "adset_name",
                    "ad_id", "ad_name",
                    "spend", "actions", "impressions", "clicks", "ctr", "frequency",
                ],
                "limit": 500,
            }):
                spend_native = float(ins.get("spend", 0) or 0)
                spend        = to_usd(spend_native, native_cur)
                conversions  = _leads_from_actions(ins.get("actions"))
                rows.append({
                    "date":          ins.get("date_start"),
                    "channel":       "meta",
                    "account_id":    account_id,
                    "campaign_id":   str(ins.get("campaign_id")),
                    "campaign_name": ins.get("campaign_name"),
                    "adset_id":      str(ins.get("adset_id")),
                    "adset_name":    ins.get("adset_name"),
                    "ad_id":         str(ins.get("ad_id")),
                    "ad_name":       ins.get("ad_name"),
                    "utm_content":   ins.get("ad_name"),  # Meta {{ad.name}} resolves to this
                    "status":        None,
                    "spend":         round(spend, 2),
                    "impressions":   int(ins.get("impressions", 0) or 0),
                    "clicks":        int(ins.get("clicks", 0) or 0),
                    "ctr":           round(float(ins.get("ctr", 0) or 0), 4),
                    "leads":         conversions,
                    "conversions":   float(conversions),
                    "frequency":     round(float(ins.get("frequency", 0) or 0), 4),
                    "currency":      "USD",
                    "updated_at":    now,
                })
        except Exception as e:
            print(f"[meta]   ads account {account_id} error: {e}")
        print(f"[meta]   ads account {account_id}: {len(rows) - count_before} rows")

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
