"""
Google Ads — keyword-grain reader + executors.

Campaign-level data has moved to BigQuery (read via
`collectors.from_bq.read_campaigns("google_ads", days=N)`). BQ does not
yet store per-keyword rows, so `get_keyword_performance()` still hits the
live API. Pause executors stay here too — they need a live API client.
"""
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException  # noqa: F401 — re-exported for callers
from config import GOOGLE_ADS_CONFIG
from datetime import date, timedelta
from collectors.currency import to_usd, normalize_currency


def get_client():
    return GoogleAdsClient.load_from_dict({
        "developer_token": GOOGLE_ADS_CONFIG["developer_token"],
        "client_id": GOOGLE_ADS_CONFIG["client_id"],
        "client_secret": GOOGLE_ADS_CONFIG["client_secret"],
        "refresh_token": GOOGLE_ADS_CONFIG["refresh_token"],
        "login_customer_id": GOOGLE_ADS_CONFIG["login_customer_id"],
        "use_proto_plus": True,
    })


def get_keyword_performance(days=14):
    """Pull keyword-level performance for waste detection."""
    client = get_client()
    ga_service = client.get_service("GoogleAdsService")
    customer_id = GOOGLE_ADS_CONFIG["customer_id"]

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    query = f"""
        SELECT
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.resource_name,
            ad_group.name,
            campaign.name,
            customer.currency_code,
            metrics.cost_micros,
            metrics.conversions,
            metrics.clicks
        FROM keyword_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            AND ad_group_criterion.status = 'ENABLED'
        ORDER BY metrics.cost_micros DESC
    """

    results = []
    response = ga_service.search(customer_id=customer_id, query=query)
    for row in response:
        native_cur   = normalize_currency(getattr(row.customer, "currency_code", None))
        spend_native = row.metrics.cost_micros / 1_000_000
        spend        = to_usd(spend_native, native_cur)
        results.append({
            "keyword": row.ad_group_criterion.keyword.text,
            "match_type": row.ad_group_criterion.keyword.match_type.name,
            "resource_name": row.ad_group_criterion.resource_name,
            "ad_group": row.ad_group.name,
            "campaign": row.campaign.name,
            "spend": round(spend, 2),
            "conversions": row.metrics.conversions,
            "clicks": row.metrics.clicks,
            "currency": "USD",
            "spend_native": round(spend_native, 2),
            "currency_native": native_cur,
        })
    return results


def pause_keyword(resource_name: str):
    """Pause a keyword by resource name. Only call after approval."""
    client = get_client()
    customer_id = GOOGLE_ADS_CONFIG["customer_id"]
    agc_service = client.get_service("AdGroupCriterionService")
    agc_operation = client.get_type("AdGroupCriterionOperation")

    agc = agc_operation.update
    agc.resource_name = resource_name
    agc.status = client.enums.AdGroupCriterionStatusEnum.PAUSED

    field_mask = client.get_type("FieldMask")
    field_mask.paths.append("status")
    agc_operation.update_mask.CopyFrom(field_mask)

    response = agc_service.mutate_ad_group_criteria(
        customer_id=customer_id,
        operations=[agc_operation]
    )
    return response


def pause_ad(ad_resource_name: str):
    """Pause an ad by resource name. Only call after approval."""
    client = get_client()
    customer_id = GOOGLE_ADS_CONFIG["customer_id"]
    ad_service = client.get_service("AdGroupAdService")
    operation = client.get_type("AdGroupAdOperation")

    ad = operation.update
    ad.resource_name = ad_resource_name
    ad.status = client.enums.AdGroupAdStatusEnum.PAUSED

    field_mask = client.get_type("FieldMask")
    field_mask.paths.append("status")
    operation.update_mask.CopyFrom(field_mask)

    response = ad_service.mutate_ad_group_ads(
        customer_id=customer_id,
        operations=[operation]
    )
    return response
