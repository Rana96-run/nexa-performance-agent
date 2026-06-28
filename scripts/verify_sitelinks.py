"""
Verify that QFlavours sitelinks were created and attached to both Google Ads accounts.

Accounts:
  - 1513020554  (Qoyod New)
  - 5753494964  (Auto Cloud)

Queries customer_asset for SITELINK field type where final_urls contains 'know-qflavours'.
"""

import io
import os
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 output on Windows so Arabic + symbols don't crash
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CUSTOMER_IDS = [
    "1513020554",  # Qoyod New
    "5753494964",  # Auto Cloud
]

GAQL = """
SELECT
  customer_asset.asset,
  customer_asset.field_type,
  customer_asset.status,
  asset.name,
  asset.sitelink_asset.link_text,
  asset.sitelink_asset.description1,
  asset.sitelink_asset.description2,
  asset.final_urls
FROM customer_asset
WHERE customer_asset.field_type = 'SITELINK'
"""

URL_FILTER = "know-qflavours"


def build_client() -> GoogleAdsClient:
    return GoogleAdsClient.load_from_dict(
        {
            "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
            "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
            "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
            "login_customer_id": "5789762982",  # MCC — no dashes
            "use_proto_plus": True,
        }
    )


def verify_account(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")

    print(f"\n{'='*60}")
    print(f"Account: {customer_id}")
    print(f"{'='*60}")

    try:
        response = ga_service.search(customer_id=customer_id, query=GAQL)
        all_rows = list(response)
        # Filter in Python: keep only rows whose final_urls contain the LP slug
        rows = [
            r for r in all_rows
            if any(URL_FILTER in url for url in r.asset.final_urls)
        ]

        print(f"  Total sitelinks on account: {len(all_rows)}")
        if not rows:
            print(f"  0 results — no sitelinks with '{URL_FILTER}' in final_urls.")
            return

        print(f"  Found {len(rows)} sitelink(s):\n")
        for i, row in enumerate(rows, start=1):
            asset = row.asset
            ca = row.customer_asset
            sl = asset.sitelink_asset
            final_urls = list(asset.final_urls) if asset.final_urls else []
            print(f"  [{i}]")
            print(f"       link_text   : {sl.link_text}")
            print(f"       description1: {sl.description1}")
            print(f"       description2: {sl.description2}")
            print(f"       final_url   : {final_urls[0] if final_urls else '(none)'}")
            print(f"       status      : {ca.status.name}")
            print(f"       asset_name  : {asset.name}")
            print(f"       resource    : {ca.asset}")
            print()

    except GoogleAdsException as ex:
        print(f"  Google Ads API error:")
        for error in ex.failure.errors:
            print(f"    {error.message}")
    except Exception as ex:
        print(f"  Unexpected error: {ex}")


def main() -> None:
    client = build_client()
    for customer_id in CUSTOMER_IDS:
        verify_account(client, customer_id)
    print("\nVerification complete.")


if __name__ == "__main__":
    main()
