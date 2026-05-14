"""
Google Ads `click_view` → BigQuery — resolves gclids to campaign/adgroup/ad IDs.

Solves: when a HubSpot contact has `hs_google_click_id` but no `campaign_id`
(e.g., they landed on a page without the Final URL Suffix, or converted on
app.qoyod.com directly), we can still ID-attribute them by looking up the
gclid in Google Ads' `click_view` resource.

Constraints:
- Google Ads retains `click_view` for the LAST 90 DAYS only
- Per user direction: we use a 30-day window (matches monthly reporting cycle)
- `click_view` queries MUST include `segments.date` filter

Daily run:
  railway run python -m collectors.gclid_clickview            # incremental last 30d
  railway run python -m collectors.gclid_clickview --days 90  # full window

Output table: `gclid_attribution`
  Columns: gclid, date, campaign_id, campaign_name, ad_group_id,
           ad_group_name, ad_id, customer_id, updated_at
"""
import os
import sys
from datetime import date, timedelta, datetime, timezone
from google.cloud import bigquery
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from io import BytesIO
import json as _json
from collectors.bq_writer import get_client as get_bq_client
from config import GOOGLE_ADS_CONFIG


def _ads_client() -> GoogleAdsClient:
    return GoogleAdsClient.load_from_dict({
        "developer_token": GOOGLE_ADS_CONFIG["developer_token"],
        "client_id":       GOOGLE_ADS_CONFIG["client_id"],
        "client_secret":   GOOGLE_ADS_CONFIG["client_secret"],
        "refresh_token":   GOOGLE_ADS_CONFIG["refresh_token"],
        "login_customer_id": GOOGLE_ADS_CONFIG["login_customer_id"],
        "use_proto_plus":  True,
    })


def _ensure_table_exists():
    """Create gclid_attribution table if missing."""
    client = get_bq_client()
    table_id = f"{os.getenv('BQ_PROJECT_ID')}.{os.getenv('BQ_DATASET')}.gclid_attribution"
    schema = [
        bigquery.SchemaField("gclid", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("campaign_id", "STRING"),
        bigquery.SchemaField("campaign_name", "STRING"),
        bigquery.SchemaField("ad_group_id", "STRING"),
        bigquery.SchemaField("ad_group_name", "STRING"),
        bigquery.SchemaField("ad_id", "STRING"),
        bigquery.SchemaField("customer_id", "STRING"),
        bigquery.SchemaField("click_type", "STRING"),  # e.g., HEADLINE, SITELINK
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="date")
    table.clustering_fields = ["campaign_id", "ad_group_id"]
    client.create_table(table, exists_ok=True)
    return table_id


def _list_customer_ids(ads) -> list[str]:
    """Returns the 2 active sub-accounts we report on:
    - 5753494964 = Auto Cloud
    - 1513020554 = Qoyod New
    (Other sub-accounts under the MCC are manager / test / unused — skipped
    per user direction 2026-05-14.)
    """
    return ["5753494964", "1513020554"]


def collect_clickview(days: int = 30) -> int:
    """Pull `click_view` for the last N days from Google Ads, upsert to BQ.

    Queries EVERY sub-account under the MCC (Qoyod has multiple).
    Returns: number of rows written.
    """
    ads = _ads_client()
    service = ads.get_service("GoogleAdsService")
    customer_ids = _list_customer_ids(ads)
    print(f"[gclid] Querying {len(customer_ids)} sub-accounts: {customer_ids}")

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    print(f"[gclid] Window: {start_date} → {end_date} ({days} days)")

    # click_view restrictions discovered:
    #  - Cannot select fields from ad_group_ad resource (incompatible with FROM)
    #    → use click_view.ad_group_ad (string resource path) and parse ad_id
    #    from the suffix: 'customers/X/adGroupAds/<adgroup_id>~<ad_id>'
    #  - Queries must filter to a SINGLE day (segments.date = 'YYYY-MM-DD')
    #    → loop per day. Each query takes <3s.

    import re as _re

    def _extract_ad_id(resource_name: str) -> str | None:
        if not resource_name:
            return None
        m = _re.search(r"adGroupAds/\d+~(\d+)$", resource_name)
        return m.group(1) if m else None

    rows = []
    now = datetime.now(timezone.utc).isoformat()

    for cust_id in customer_ids:
        print(f"\n[gclid] === customer {cust_id} ===")
        cust_total = 0
        day_cursor = start_date
        while day_cursor <= end_date:
            day_str = day_cursor.isoformat()
            query = f"""
                SELECT
                    click_view.gclid,
                    click_view.ad_group_ad,
                    segments.date,
                    segments.click_type,
                    campaign.id,
                    campaign.name,
                    ad_group.id,
                    ad_group.name
                FROM click_view
                WHERE segments.date = '{day_str}'
            """
            day_rows = 0
            try:
                response = service.search_stream(customer_id=cust_id, query=query)
                for batch in response:
                    for r in batch.results:
                        rows.append({
                            "gclid":        r.click_view.gclid or None,
                            "date":         r.segments.date,
                            "campaign_id":  str(r.campaign.id) if r.campaign.id else None,
                            "campaign_name": r.campaign.name or None,
                            "ad_group_id":  str(r.ad_group.id) if r.ad_group.id else None,
                            "ad_group_name": r.ad_group.name or None,
                            "ad_id":        _extract_ad_id(r.click_view.ad_group_ad),
                            "customer_id":  cust_id,
                            "click_type":   r.segments.click_type.name if r.segments.click_type else None,
                            "updated_at":   now,
                        })
                        day_rows += 1
                cust_total += day_rows
            except GoogleAdsException as e:
                # Sub-account may not have click_view permissions or click data.
                # Log once per customer at first error and skip the rest of that account's days.
                first_err = e.failure.errors[0] if e.failure.errors else None
                msg = first_err.message[:80] if first_err else e.error.code().name
                print(f"  {day_str} cust={cust_id}: ERR — {msg}")
                break  # Skip rest of date range for this account
            day_cursor += timedelta(days=1)
        print(f"  → customer {cust_id} total: {cust_total} clicks")

    # Filter out rows with empty gclid (rare but possible — non-tagged clicks)
    rows = [r for r in rows if r["gclid"]]
    print(f"[gclid] Fetched {len(rows)} click_view rows")

    if not rows:
        return 0

    table_id = _ensure_table_exists()
    bq = get_bq_client()

    # Rolling-window cache: clear the date range we just collected,
    # then bulk-load the fresh rows. Skipping upsert_rows because its
    # DELETE-IN-UNNEST pattern hits parameter-size limits at 500K+ rows.
    dates_in_batch = sorted({r["date"] for r in rows})
    min_d, max_d = dates_in_batch[0], dates_in_batch[-1]
    print(f"[gclid] Clearing existing rows {min_d} → {max_d}")
    bq.query(
        f"DELETE FROM `{table_id}` WHERE `date` BETWEEN @s AND @e",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("s", "DATE", min_d),
            bigquery.ScalarQueryParameter("e", "DATE", max_d),
        ]),
    ).result()

    # Bulk-load via NDJSON. Load jobs handle multi-million rows easily and
    # land directly in partitions (not the streaming buffer) so they're
    # immediately queryable.
    ndjson = "\n".join(_json.dumps(r, default=str) for r in rows).encode("utf-8")
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    load_job = bq.load_table_from_file(BytesIO(ndjson), table_id, job_config=job_config)
    load_job.result()
    print(f"[gclid] Loaded {len(rows)} rows into {table_id}")
    return len(rows)


if __name__ == "__main__":
    import argparse
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30,
                        help="Lookback window (default: 30 days)")
    args = parser.parse_args()

    n = collect_clickview(days=args.days)
    print(f"\n[gclid] Done — wrote {n} rows to gclid_attribution")
