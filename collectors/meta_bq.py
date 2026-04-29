"""
Meta -> BigQuery collector.
Pulls per-day per-campaign metrics from all Meta ad accounts.
"""
from datetime import date, timedelta, datetime, timezone
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from config import META_ACCESS_TOKEN, META_AD_ACCOUNTS
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency


def collect_and_write(days: int = None, incremental: bool = False):
    """
    incremental=True -> last 2 days (12h scheduled runs)
    days=N            -> last N days
    default           -> YTD
    """
    FacebookAdsApi.init(access_token=META_ACCESS_TOKEN)
    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = [a for a in META_AD_ACCOUNTS if a]
    print(f"[meta] Window {start} -> {end} across {len(accounts)} account(s)")

    for account_id in accounts:
        account = AdAccount(account_id)
        count_before = len(rows)
        # Fetch native currency for this ad account so we can convert to USD
        try:
            acct_meta = account.api_get(fields=["currency"])
            native_cur = normalize_currency(acct_meta.get("currency"))
        except Exception as e:
            print(f"[meta]   {account_id} currency lookup failed ({e}) — defaulting to SAR")
            native_cur = "SAR"
        print(f"[meta]   account {account_id} native={native_cur} -> converting to USD")
        try:
            insights = account.get_insights(params={
                "level": "campaign",
                "time_range": {"since": str(start), "until": str(end)},
                "time_increment": 1,  # daily breakdown
                "fields": [
                    "campaign_id", "campaign_name",
                    "spend", "actions", "impressions", "clicks", "ctr",
                ],
                "limit": 500,
            })
            # SDK returns a Cursor that auto-fetches additional pages
            for ins in insights:
                spend_native = float(ins.get("spend", 0) or 0)
                spend        = to_usd(spend_native, native_cur)
                actions = ins.get("actions", []) or []
                leads = next(
                    (int(float(a["value"])) for a in actions if a.get("action_type") == "lead"),
                    0,
                )
                purchases = next(
                    (int(float(a["value"])) for a in actions
                     if a.get("action_type") == "purchase"),
                    0,
                )
                conversions = leads or purchases  # prefer leads; fall back to purchases
                rows.append({
                    "date":           ins.get("date_start"),
                    "channel":        "meta",
                    "account_id":     account_id,
                    "campaign_id":    str(ins.get("campaign_id")),
                    "campaign_name":  ins.get("campaign_name"),
                    "status":         None,
                    "objective":      None,
                    "spend":          round(spend, 2),
                    "impressions":    int(ins.get("impressions", 0) or 0),
                    "clicks":         int(ins.get("clicks", 0) or 0),
                    "ctr":            round(float(ins.get("ctr", 0) or 0), 4),
                    "leads":          conversions,
                    "conversions":    float(conversions),
                    "cpl":            round(spend / conversions, 2) if conversions > 0 else None,
                    "currency":       "USD",
                    "spend_native":   round(spend_native, 2),
                    "currency_native": native_cur,
                    "updated_at":     now,
                })
        except Exception as e:
            print(f"[meta]   account {account_id} error: {e}")
        print(f"[meta]   account {account_id}: {len(rows) - count_before} rows")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"Meta backfill complete: {n} rows")
