"""
Google Ads -> BigQuery collector.
Pulls per-day per-campaign metrics for ALL ad accounts under the MCC
(list in GOOGLE_ADS_CUSTOMER_IDS), writes to campaigns_daily.
"""
import os
from datetime import date, timedelta, datetime, timezone
from google.ads.googleads.client import GoogleAdsClient
from config import GOOGLE_ADS_CONFIG
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency


def _client():
    return GoogleAdsClient.load_from_dict({
        "developer_token": GOOGLE_ADS_CONFIG["developer_token"],
        "client_id": GOOGLE_ADS_CONFIG["client_id"],
        "client_secret": GOOGLE_ADS_CONFIG["client_secret"],
        "refresh_token": GOOGLE_ADS_CONFIG["refresh_token"],
        "login_customer_id": GOOGLE_ADS_CONFIG["login_customer_id"],
        "use_proto_plus": True,
    })


def _customer_ids():
    raw = os.getenv("GOOGLE_ADS_CUSTOMER_IDS") or GOOGLE_ADS_CONFIG.get("customer_id", "")
    return [c.strip().replace("-", "") for c in raw.split(",") if c.strip()]


def collect_and_write(days: int = None, incremental: bool = False):
    """
    incremental=True -> last 2 days (scheduled 12h runs)
    days=N            -> last N days
    default           -> YTD
    """
    client = _client()
    ga = client.get_service("GoogleAdsService")

    end = date.today() - timedelta(days=1)  # Google Ads data is T-1
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)

    query = f"""
        SELECT
            customer.id,
            customer.descriptive_name,
            customer.currency_code,
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            metrics.cost_micros,
            metrics.conversions,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            segments.date
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
    """

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _customer_ids()
    print(f"[google_ads] Window {start} -> {end} across {len(accounts)} account(s)")
    for cid in accounts:
        count = 0
        try:
            search_results = ga.search(customer_id=cid, query=query)
            for r in search_results:
                spend_native = r.metrics.cost_micros / 1_000_000
                native_cur   = normalize_currency(r.customer.currency_code)
                spend        = to_usd(spend_native, native_cur)
                conv         = r.metrics.conversions
                rows.append({
                    "date":           str(r.segments.date),
                    "channel":        "google_ads",
                    "account_id":     cid,
                    "campaign_id":    str(r.campaign.id),
                    "campaign_name":  r.campaign.name,
                    "status":         r.campaign.status.name,
                    "objective":      r.campaign.advertising_channel_type.name,
                    "spend":          round(spend, 2),
                    "impressions":    int(r.metrics.impressions),
                    "clicks":         int(r.metrics.clicks),
                    "ctr":            round(r.metrics.ctr * 100, 4),
                    "leads":          int(conv),
                    "conversions":    float(conv),
                    "cpl":            round(spend / conv, 2) if conv > 0 else None,
                    "currency":       "USD",
                    "spend_native":   round(spend_native, 2),
                    "currency_native": native_cur,
                    "updated_at":     now,
                })
                count += 1
        except Exception as e:
            print(f"[google_ads]   account {cid} error: {e}")
        print(f"[google_ads]   account {cid}: {count} rows")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"Google Ads backfill complete: {n} rows")
