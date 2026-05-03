"""
collectors/airbyte_normalize.py
================================
Reads Airbyte's raw BigQuery tables (written by Airbyte Cloud sync) and
MERGEs them into our canonical campaigns_daily table.

Airbyte destination dataset:  airbyte_raw  (set in Airbyte UI)
Our destination dataset:       qoyod_marketing  (BQ_DATASET env var)

Run after each Airbyte sync — called from reporting_scheduler.py.
Can also be run manually:  python collectors/airbyte_normalize.py

Channels handled:
  google_ads   → airbyte_raw.google_ads_campaign_performance_report
  meta         → airbyte_raw.facebook_ads_insights
  snapchat     → airbyte_raw.snapchat_campaign_stats
  tiktok       → airbyte_raw.tiktok_ads_reports_daily
  linkedin     → airbyte_raw.linkedin_ad_campaign_analytics
  microsoft    → airbyte_raw.microsoft_ads_campaign_performance_report
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv(override=True)

PROJECT    = os.getenv("BQ_PROJECT_ID")
DATASET    = os.getenv("BQ_DATASET", "qoyod_marketing")
RAW        = os.getenv("AIRBYTE_RAW_DATASET", "airbyte_raw")
KEY_PATH   = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")

# Resolve relative key path
if KEY_PATH and not os.path.isabs(KEY_PATH):
    KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), KEY_PATH.lstrip("./\\"))


def _client() -> bigquery.Client:
    creds = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(project=PROJECT, credentials=creds)


def _table_exists(client: bigquery.Client, dataset: str, table: str) -> bool:
    try:
        client.get_table(f"{PROJECT}.{dataset}.{table}")
        return True
    except Exception:
        return False


def _run(client: bigquery.Client, sql: str, label: str) -> int:
    """Run a query and return rows affected."""
    try:
        job = client.query(sql)
        job.result()
        print(f"  [airbyte-norm] {label}: done ({job.num_dml_affected_rows or 0} rows)")
        return job.num_dml_affected_rows or 0
    except Exception as e:
        print(f"  [airbyte-norm] {label}: FAILED — {e}")
        return 0


# ── Shared MERGE template ─────────────────────────────────────────────────────

MERGE_SQL = """
MERGE `{project}.{dataset}.campaigns_daily` T
USING (
  {select_sql}
) S
ON  T.date = S.date
AND T.channel = S.channel
AND T.campaign_id = S.campaign_id
WHEN MATCHED THEN UPDATE SET
  campaign_name       = S.campaign_name,
  account_id          = S.account_id,
  status              = S.status,
  objective           = S.objective,
  spend               = S.spend,
  impressions         = S.impressions,
  clicks              = S.clicks,
  ctr                 = S.ctr,
  leads               = S.leads,
  conversions         = S.conversions,
  cpl                 = S.cpl,
  currency            = S.currency,
  spend_native        = S.spend_native,
  currency_native     = S.currency_native,
  updated_at          = S.updated_at
WHEN NOT MATCHED THEN INSERT (
  date, channel, account_id, campaign_id, campaign_name, campaign_group_name,
  status, objective, spend, impressions, clicks, ctr,
  leads, conversions, cpl, currency, spend_native, currency_native, updated_at
) VALUES (
  S.date, S.channel, S.account_id, S.campaign_id, S.campaign_name, S.campaign_group_name,
  S.status, S.objective, S.spend, S.impressions, S.clicks, S.ctr,
  S.leads, S.conversions, S.cpl, S.currency, S.spend_native, S.currency_native, S.updated_at
)
"""


# ── Google Ads ────────────────────────────────────────────────────────────────

def normalize_google_ads(client: bigquery.Client) -> int:
    table = "google_ads_campaign_performance_report"
    if not _table_exists(client, RAW, table):
        print(f"  [airbyte-norm] google_ads: raw table {table} not found — skipping")
        return 0

    # Google Ads: cost in micros → USD; customer_id may have dashes
    select = f"""
    SELECT
      PARSE_DATE('%Y-%m-%d', segments_date)                           AS date,
      'google_ads'                                                    AS channel,
      CAST(customer_id AS STRING)                                     AS account_id,
      CAST(campaign_id AS STRING)                                     AS campaign_id,
      campaign_name                                                   AS campaign_name,
      NULL                                                            AS campaign_group_name,
      UPPER(campaign_status)                                          AS status,
      campaign_advertising_channel_type                               AS objective,
      ROUND(COALESCE(metrics_cost_micros, 0) / 1000000.0, 4)         AS spend,
      COALESCE(metrics_impressions, 0)                                AS impressions,
      COALESCE(metrics_clicks, 0)                                     AS clicks,
      SAFE_DIVIDE(COALESCE(metrics_clicks, 0),
                  NULLIF(metrics_impressions, 0))                    AS ctr,
      COALESCE(CAST(metrics_conversions AS INT64), 0)                 AS leads,
      COALESCE(metrics_conversions, 0)                                AS conversions,
      SAFE_DIVIDE(COALESCE(metrics_cost_micros, 0) / 1000000.0,
                  NULLIF(CAST(metrics_conversions AS FLOAT64), 0))   AS cpl,
      'USD'                                                           AS currency,
      ROUND(COALESCE(metrics_cost_micros, 0) / 1000000.0, 4)         AS spend_native,
      'USD'                                                           AS currency_native,
      CURRENT_TIMESTAMP()                                             AS updated_at
    FROM `{PROJECT}.{RAW}.{table}`
    WHERE segments_date IS NOT NULL
      AND campaign_id IS NOT NULL
    """

    sql = MERGE_SQL.format(
        project=PROJECT, dataset=DATASET, select_sql=select
    )
    return _run(client, sql, "google_ads")


# ── Meta Ads ──────────────────────────────────────────────────────────────────

def normalize_meta(client: bigquery.Client) -> int:
    table = "facebook_ads_insights"
    if not _table_exists(client, RAW, table):
        print(f"  [airbyte-norm] meta: raw table {table} not found — skipping")
        return 0

    # Meta: spend is a string "12.34" in USD; leads in actions JSON array
    select = f"""
    SELECT
      PARSE_DATE('%Y-%m-%d', date_start)                             AS date,
      'meta'                                                         AS channel,
      CAST(account_id AS STRING)                                     AS account_id,
      CAST(campaign_id AS STRING)                                    AS campaign_id,
      campaign_name                                                  AS campaign_name,
      NULL                                                           AS campaign_group_name,
      'ACTIVE'                                                       AS status,
      objective                                                      AS objective,
      ROUND(CAST(spend AS FLOAT64), 4)                               AS spend,
      CAST(impressions AS INT64)                                     AS impressions,
      CAST(clicks AS INT64)                                          AS clicks,
      SAFE_DIVIDE(CAST(clicks AS FLOAT64),
                  NULLIF(CAST(impressions AS FLOAT64), 0))           AS ctr,
      -- Extract lead count from actions array
      COALESCE((
        SELECT CAST(a.value AS INT64)
        FROM UNNEST(JSON_QUERY_ARRAY(actions, '$')) a
        WHERE JSON_VALUE(a, '$.action_type') IN ('lead', 'onsite_conversion.lead_grouped')
        LIMIT 1
      ), 0)                                                          AS leads,
      CAST(COALESCE(
        (SELECT a.value FROM UNNEST(JSON_QUERY_ARRAY(actions, '$')) a
         WHERE JSON_VALUE(a, '$.action_type') = 'lead' LIMIT 1), '0'
      ) AS FLOAT64)                                                  AS conversions,
      SAFE_DIVIDE(CAST(spend AS FLOAT64),
                  NULLIF(CAST(clicks AS FLOAT64), 0))               AS cpl,
      'USD'                                                          AS currency,
      ROUND(CAST(spend AS FLOAT64), 4)                               AS spend_native,
      'USD'                                                          AS currency_native,
      CURRENT_TIMESTAMP()                                            AS updated_at
    FROM `{PROJECT}.{RAW}.{table}`
    WHERE date_start IS NOT NULL
      AND campaign_id IS NOT NULL
    """

    sql = MERGE_SQL.format(
        project=PROJECT, dataset=DATASET, select_sql=select
    )
    return _run(client, sql, "meta")


# ── Snapchat ──────────────────────────────────────────────────────────────────

def normalize_snapchat(client: bigquery.Client) -> int:
    table = "snapchat_campaign_stats"
    if not _table_exists(client, RAW, table):
        print(f"  [airbyte-norm] snapchat: raw table {table} not found — skipping")
        return 0

    # Snapchat: spend in micro-cents (divide by 1,000,000); currency SAR → USD
    select = f"""
    SELECT
      DATE(TIMESTAMP(start_time))                                    AS date,
      'snapchat'                                                     AS channel,
      account_id                                                     AS account_id,
      id                                                             AS campaign_id,
      name                                                           AS campaign_name,
      NULL                                                           AS campaign_group_name,
      status                                                         AS status,
      objective                                                      AS objective,
      -- Snap spend is in micro-currency (SAR micros) → convert to USD at 3.75
      ROUND(COALESCE(spend, 0) / 1000000.0 / 3.75, 4)               AS spend,
      COALESCE(impressions, 0)                                       AS impressions,
      COALESCE(swipes, 0)                                            AS clicks,
      SAFE_DIVIDE(COALESCE(swipes, 0),
                  NULLIF(impressions, 0))                            AS ctr,
      0                                                              AS leads,
      0                                                              AS conversions,
      NULL                                                           AS cpl,
      'USD'                                                          AS currency,
      ROUND(COALESCE(spend, 0) / 1000000.0, 4)                       AS spend_native,
      'SAR'                                                          AS currency_native,
      CURRENT_TIMESTAMP()                                            AS updated_at
    FROM `{PROJECT}.{RAW}.{table}`
    WHERE start_time IS NOT NULL
      AND id IS NOT NULL
    """

    sql = MERGE_SQL.format(
        project=PROJECT, dataset=DATASET, select_sql=select
    )
    return _run(client, sql, "snapchat")


# ── TikTok ────────────────────────────────────────────────────────────────────

def normalize_tiktok(client: bigquery.Client) -> int:
    # TikTok Airbyte connector can produce two possible stream names
    table = "tiktok_ads_reports_daily"
    if not _table_exists(client, RAW, table):
        table = "tiktok_basic_reports"
    if not _table_exists(client, RAW, table):
        print(f"  [airbyte-norm] tiktok: raw table not found — skipping")
        return 0

    select = f"""
    SELECT
      PARSE_DATE('%Y-%m-%d', stat_time_day)                          AS date,
      'tiktok'                                                       AS channel,
      CAST(advertiser_id AS STRING)                                  AS account_id,
      CAST(campaign_id AS STRING)                                    AS campaign_id,
      campaign_name                                                  AS campaign_name,
      NULL                                                           AS campaign_group_name,
      UPPER(campaign_status)                                         AS status,
      objective_type                                                 AS objective,
      ROUND(COALESCE(CAST(spend AS FLOAT64), 0), 4)                  AS spend,
      COALESCE(CAST(show_cnt AS INT64), 0)                           AS impressions,
      COALESCE(CAST(click_cnt AS INT64), 0)                          AS clicks,
      SAFE_DIVIDE(COALESCE(CAST(click_cnt AS FLOAT64), 0),
                  NULLIF(CAST(show_cnt AS FLOAT64), 0))              AS ctr,
      COALESCE(CAST(conversion AS INT64), 0)                         AS leads,
      COALESCE(CAST(conversion AS FLOAT64), 0)                       AS conversions,
      SAFE_DIVIDE(COALESCE(CAST(spend AS FLOAT64), 0),
                  NULLIF(CAST(conversion AS FLOAT64), 0))            AS cpl,
      'USD'                                                          AS currency,
      ROUND(COALESCE(CAST(spend AS FLOAT64), 0), 4)                  AS spend_native,
      'USD'                                                          AS currency_native,
      CURRENT_TIMESTAMP()                                            AS updated_at
    FROM `{PROJECT}.{RAW}.{table}`
    WHERE stat_time_day IS NOT NULL
      AND campaign_id IS NOT NULL
    """

    sql = MERGE_SQL.format(
        project=PROJECT, dataset=DATASET, select_sql=select
    )
    return _run(client, sql, "tiktok")


# ── LinkedIn ──────────────────────────────────────────────────────────────────

def normalize_linkedin(client: bigquery.Client) -> int:
    table = "linkedin_ad_campaign_analytics"
    if not _table_exists(client, RAW, table):
        print(f"  [airbyte-norm] linkedin: raw table {table} not found — skipping")
        return 0

    # LinkedIn: pivotValues contains campaign URN; extract numeric ID
    select = f"""
    SELECT
      DATE(
        dateRange_start_year,
        dateRange_start_month,
        dateRange_start_day
      )                                                              AS date,
      'linkedin'                                                     AS channel,
      '{os.getenv("LI_AD_ACCOUNT_URN", "").split(":")[-1]}'         AS account_id,
      -- Extract numeric campaign ID from URN
      REGEXP_EXTRACT(
        COALESCE(pivotValues_0,
                 JSON_VALUE(TO_JSON_STRING(pivotValues), '$[0]')),
        r'[0-9]+'
      )                                                              AS campaign_id,
      COALESCE(pivotValues_0,
               JSON_VALUE(TO_JSON_STRING(pivotValues), '$[0]'))      AS campaign_name,
      NULL                                                           AS campaign_group_name,
      'ACTIVE'                                                       AS status,
      NULL                                                           AS objective,
      ROUND(COALESCE(costInUsd, 0), 4)                               AS spend,
      COALESCE(impressions, 0)                                       AS impressions,
      COALESCE(clicks, 0)                                            AS clicks,
      SAFE_DIVIDE(COALESCE(clicks, 0),
                  NULLIF(impressions, 0))                            AS ctr,
      COALESCE(leadGenerationMailContactInfoShares, 0)               AS leads,
      COALESCE(leadGenerationMailContactInfoShares, 0)               AS conversions,
      SAFE_DIVIDE(COALESCE(costInUsd, 0),
                  NULLIF(leadGenerationMailContactInfoShares, 0))    AS cpl,
      'USD'                                                          AS currency,
      ROUND(COALESCE(costInUsd, 0), 4)                               AS spend_native,
      'USD'                                                          AS currency_native,
      CURRENT_TIMESTAMP()                                            AS updated_at
    FROM `{PROJECT}.{RAW}.{table}`
    WHERE dateRange_start_year IS NOT NULL
    """

    sql = MERGE_SQL.format(
        project=PROJECT, dataset=DATASET, select_sql=select
    )
    return _run(client, sql, "linkedin")


# ── Microsoft Ads ─────────────────────────────────────────────────────────────

def normalize_microsoft(client: bigquery.Client) -> int:
    table = "microsoft_ads_campaign_performance_report"
    if not _table_exists(client, RAW, table):
        print(f"  [airbyte-norm] microsoft: raw table {table} not found — skipping")
        return 0

    # Microsoft: spend in account currency (USD for Qoyod)
    select = f"""
    SELECT
      PARSE_DATE('%Y-%m-%d', TimePeriod)                             AS date,
      'microsoft_ads'                                                AS channel,
      CAST(AccountId AS STRING)                                      AS account_id,
      CAST(CampaignId AS STRING)                                     AS campaign_id,
      CampaignName                                                   AS campaign_name,
      NULL                                                           AS campaign_group_name,
      UPPER(CampaignStatus)                                          AS status,
      NULL                                                           AS objective,
      ROUND(COALESCE(CAST(Spend AS FLOAT64), 0), 4)                  AS spend,
      COALESCE(CAST(Impressions AS INT64), 0)                        AS impressions,
      COALESCE(CAST(Clicks AS INT64), 0)                             AS clicks,
      SAFE_DIVIDE(COALESCE(CAST(Clicks AS FLOAT64), 0),
                  NULLIF(CAST(Impressions AS FLOAT64), 0))           AS ctr,
      COALESCE(CAST(Conversions AS INT64), 0)                        AS leads,
      COALESCE(CAST(Conversions AS FLOAT64), 0)                      AS conversions,
      SAFE_DIVIDE(COALESCE(CAST(Spend AS FLOAT64), 0),
                  NULLIF(CAST(Conversions AS FLOAT64), 0))           AS cpl,
      'USD'                                                          AS currency,
      ROUND(COALESCE(CAST(Spend AS FLOAT64), 0), 4)                  AS spend_native,
      'USD'                                                          AS currency_native,
      CURRENT_TIMESTAMP()                                            AS updated_at
    FROM `{PROJECT}.{RAW}.{table}`
    WHERE TimePeriod IS NOT NULL
      AND CampaignId IS NOT NULL
    """

    sql = MERGE_SQL.format(
        project=PROJECT, dataset=DATASET, select_sql=select
    )
    return _run(client, sql, "microsoft_ads")


# ── Entry point ───────────────────────────────────────────────────────────────

def run_all_normalizations() -> dict[str, int]:
    """
    Run all channel normalizations. Called from reporting_scheduler.py
    after Airbyte sync completes (or on a schedule matching Airbyte's sync).
    Returns dict of channel → rows merged.
    """
    print(f"[airbyte-norm] Starting normalization → {PROJECT}.{DATASET}.campaigns_daily")
    client = _client()

    results = {
        "google_ads":    normalize_google_ads(client),
        "meta":          normalize_meta(client),
        "snapchat":      normalize_snapchat(client),
        "tiktok":        normalize_tiktok(client),
        "linkedin":      normalize_linkedin(client),
        "microsoft_ads": normalize_microsoft(client),
    }

    total = sum(results.values())
    print(f"[airbyte-norm] Done — {total} total rows merged across {len(results)} channels")
    return results


if __name__ == "__main__":
    run_all_normalizations()
