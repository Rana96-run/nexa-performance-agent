"""
Create 6 account-level sitelinks for Qflavours LP on both Google Ads accounts.
URL: https://lp.qoyod.com/know-qflavours/

Accounts:
  - 1513020554  (Qoyod New)
  - 5753494964  (Auto Cloud)

Library note: google-ads v30 ships the v23 proto set.
SitelinkAsset fields: link_text, description1, description2 (NO final_urls).
final_urls is set on the parent Asset object instead.
"""

import io
import os
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# Force UTF-8 output on Windows so Arabic + symbols don't crash
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CUSTOMER_IDS = [
    "1513020554",  # Qoyod New
    "5753494964",  # Auto Cloud
]

LP_URL = "https://lp.qoyod.com/know-qflavours/"

SITELINKS = [
    {
        "link_text": "نظام KDS للمطبخ",
        "description1": "طلبات تصل للمطبخ فوراً",
        "description2": "بدون ورق وبدون تأخير",
    },
    {
        "link_text": "الطلب عبر QR",
        "description1": "طلب مباشر من الطاولة",
        "description2": "وفّر 40% وقت الانتظار",
    },
    {
        "link_text": "تقارير متعددة الفروع",
        "description1": "تابع مبيعاتك لحظة بلحظة",
        "description2": "جميع الفروع في مكان واحد",
    },
    {
        "link_text": "فواتير ZATCA تلقائية",
        "description1": "فواتير إلكترونية معتمدة",
        "description2": "قيود محاسبية آلية",
    },
    {
        "link_text": "يعمل بدون إنترنت",
        "description1": "استمر في البيع بدون نت",
        "description2": "تزامن تلقائي عند الاتصال",
    },
    {
        "link_text": "جرّب مجاناً 14 يوم",
        "description1": "ابدأ تجربة فليفرز الآن",
        "description2": "إعداد فوري بدون بطاقة",
    },
]


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


def create_sitelinks_for_account(client: GoogleAdsClient, customer_id: str) -> None:
    asset_service = client.get_service("AssetService")
    customer_asset_service = client.get_service("CustomerAssetService")

    print(f"\n{'='*60}")
    print(f"Account: {customer_id}")
    print(f"{'='*60}")

    for i, sl in enumerate(SITELINKS, start=1):
        link_text = sl["link_text"]
        try:
            # ── Step 1: create the Asset ──────────────────────────────────────
            asset_op = client.get_type("AssetOperation")
            asset = asset_op.create
            asset.name = f"Qflavours_Sitelink_{i}_{link_text}"
            # final_urls is on the parent Asset, NOT on sitelink_asset (v23 proto)
            asset.final_urls.append(LP_URL)
            asset.sitelink_asset.link_text = link_text
            asset.sitelink_asset.description1 = sl["description1"]
            asset.sitelink_asset.description2 = sl["description2"]

            asset_resp = asset_service.mutate_assets(
                customer_id=customer_id, operations=[asset_op]
            )
            asset_resource = asset_resp.results[0].resource_name

            # ── Step 2: attach to account (CustomerAsset) ─────────────────────
            ca_op = client.get_type("CustomerAssetOperation")
            ca = ca_op.create
            ca.asset = asset_resource
            ca.field_type = client.enums.AssetFieldTypeEnum.SITELINK

            customer_asset_service.mutate_customer_assets(
                customer_id=customer_id, operations=[ca_op]
            )

            print(f"  [{i}] ✓  '{link_text}'  →  {asset_resource}")

        except GoogleAdsException as ex:
            print(f"  [{i}] ✗  '{link_text}'")
            for error in ex.failure.errors:
                print(f"       ERROR: {error.message}")
                if error.location:
                    for fv in error.location.field_value_errors:
                        print(f"       field: {fv.field_name}")
        except Exception as ex:
            print(f"  [{i}] ✗  '{link_text}'  →  unexpected: {ex}")


def main() -> None:
    client = build_client()
    for customer_id in CUSTOMER_IDS:
        create_sitelinks_for_account(client, customer_id)
    print("\nDone.")


if __name__ == "__main__":
    main()
