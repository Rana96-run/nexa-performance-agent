"""
BigQuery writer — shared helper for all collectors.

All channel collectors write daily rows into these tables:
  - campaigns_daily     (one row per campaign per day per channel)
  - ads_daily           (one row per ad per day — optional, heavier)
  - hubspot_leads_daily (HubSpot contacts aggregated by utm_campaign per day)
  - campaign_status     (current status snapshot, overwritten daily)

Idempotent: we MERGE on (date, channel, campaign_id) so re-runs overwrite
the same day's data instead of duplicating.
"""
import os
from datetime import date
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv(override=True)   # always prefer .env over stale system env vars

PROJECT_ID = os.getenv("BQ_PROJECT_ID")
DATASET    = os.getenv("BQ_DATASET", "qoyod_marketing")
LOCATION   = os.getenv("BQ_LOCATION", "me-central1")

# Thresholds pulled from the central config — see config.py
try:
    from config import (
        CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
        CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
    )
except Exception:
    # Hard defaults so this module still works if config import fails
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING = 5.50, 7.50, 8.00
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING = 11.00, 17.00, 21.33

# Resolve the key path: honour absolute paths in .env; fall back to the file
# sitting next to this repo if nothing is set.
_raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if _raw_key and os.path.isabs(_raw_key):
    KEY_PATH = _raw_key
elif _raw_key:
    # Relative path in env — resolve relative to repo root (one level up from collectors/)
    KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), _raw_key.lstrip("./\\"))
else:
    KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bigquery-key.json")


def get_client():
    creds = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(project=PROJECT_ID, credentials=creds, location=LOCATION)


# ---------- SCHEMAS ----------

CAMPAIGNS_DAILY_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("channel", "STRING", mode="REQUIRED"),       # google_ads / meta / snapchat / tiktok
    bigquery.SchemaField("account_id", "STRING"),
    bigquery.SchemaField("campaign_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("campaign_name", "STRING"),
    bigquery.SchemaField("campaign_group_name", "STRING"),             # LinkedIn only: utm_campaign level (group name)
    bigquery.SchemaField("status", "STRING"),                          # ENABLED / PAUSED / LEARNING / REMOVED
    bigquery.SchemaField("objective", "STRING"),
    bigquery.SchemaField("spend", "FLOAT64"),
    bigquery.SchemaField("impressions", "INT64"),
    bigquery.SchemaField("clicks", "INT64"),
    bigquery.SchemaField("ctr", "FLOAT64"),
    bigquery.SchemaField("leads", "INT64"),                            # platform-reported leads
    bigquery.SchemaField("conversions", "FLOAT64"),
    bigquery.SchemaField("cpl", "FLOAT64"),
    bigquery.SchemaField("currency", "STRING"),                        # always "USD" — collectors convert before writing
    bigquery.SchemaField("spend_native", "FLOAT64"),                   # spend in the platform's native currency
    bigquery.SchemaField("currency_native", "STRING"),                 # e.g. "SAR", "USD"
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
]

HUBSPOT_LEADS_DAILY_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("utm_campaign", "STRING"),
    bigquery.SchemaField("utm_source", "STRING"),
    bigquery.SchemaField("utm_medium", "STRING"),
    bigquery.SchemaField("qoyod_source", "STRING"),
    bigquery.SchemaField("leads_count", "INT64"),
    bigquery.SchemaField("mqls_count", "INT64"),
    bigquery.SchemaField("sqls_count", "INT64"),
    bigquery.SchemaField("opportunities_count", "INT64"),
    bigquery.SchemaField("customers_count", "INT64"),
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
]

ADSETS_DAILY_SCHEMA = [
    bigquery.SchemaField("date",          "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("channel",       "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("account_id",    "STRING"),
    bigquery.SchemaField("campaign_id",   "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("campaign_name", "STRING"),
    bigquery.SchemaField("adset_id",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("adset_name",    "STRING"),
    bigquery.SchemaField("status",        "STRING"),
    bigquery.SchemaField("spend",         "FLOAT64"),
    bigquery.SchemaField("impressions",   "INT64"),
    bigquery.SchemaField("clicks",        "INT64"),
    bigquery.SchemaField("ctr",           "FLOAT64"),
    bigquery.SchemaField("leads",         "INT64"),     # platform-reported
    bigquery.SchemaField("conversions",   "FLOAT64"),
    bigquery.SchemaField("frequency",     "FLOAT64"),   # Meta/Snap only
    bigquery.SchemaField("currency",      "STRING"),
    bigquery.SchemaField("updated_at",    "TIMESTAMP"),
]

ADS_DAILY_SCHEMA = [
    bigquery.SchemaField("date",          "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("channel",       "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("account_id",    "STRING"),
    bigquery.SchemaField("campaign_id",   "STRING"),
    bigquery.SchemaField("campaign_name", "STRING"),
    bigquery.SchemaField("adset_id",      "STRING"),
    bigquery.SchemaField("adset_name",    "STRING"),
    bigquery.SchemaField("ad_id",         "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("ad_name",       "STRING"),
    bigquery.SchemaField("status",        "STRING"),
    bigquery.SchemaField("spend",         "FLOAT64"),
    bigquery.SchemaField("impressions",   "INT64"),
    bigquery.SchemaField("clicks",        "INT64"),
    bigquery.SchemaField("ctr",           "FLOAT64"),
    bigquery.SchemaField("leads",         "INT64"),
    bigquery.SchemaField("conversions",   "FLOAT64"),
    bigquery.SchemaField("frequency",     "FLOAT64"),
    bigquery.SchemaField("currency",      "STRING"),
    bigquery.SchemaField("updated_at",    "TIMESTAMP"),
]

KEYWORDS_DAILY_SCHEMA = [
    # Google Ads + Microsoft Ads only
    bigquery.SchemaField("date",            "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("channel",         "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("account_id",      "STRING"),
    bigquery.SchemaField("campaign_id",     "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("campaign_name",   "STRING"),
    bigquery.SchemaField("adgroup_id",      "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("adgroup_name",    "STRING"),
    bigquery.SchemaField("keyword_id",      "STRING"),
    bigquery.SchemaField("keyword_text",    "STRING"),  # the actual keyword
    bigquery.SchemaField("match_type",      "STRING"),  # EXACT / PHRASE / BROAD
    bigquery.SchemaField("status",          "STRING"),
    bigquery.SchemaField("spend",           "FLOAT64"),
    bigquery.SchemaField("impressions",     "INT64"),
    bigquery.SchemaField("clicks",          "INT64"),
    bigquery.SchemaField("ctr",             "FLOAT64"),
    bigquery.SchemaField("avg_cpc",         "FLOAT64"),
    bigquery.SchemaField("conversions",     "FLOAT64"),
    bigquery.SchemaField("quality_score",   "INT64"),   # Google Ads only (1-10)
    bigquery.SchemaField("currency",        "STRING"),
    bigquery.SchemaField("updated_at",      "TIMESTAMP"),
]

ACTIVITY_LOG_SCHEMA = [
    # Core identity
    bigquery.SchemaField("activity_id",    "STRING",    mode="REQUIRED"),  # UUID
    bigquery.SchemaField("ts",             "TIMESTAMP", mode="REQUIRED"),  # when it ran
    bigquery.SchemaField("session_id",     "STRING"),                      # groups one agent run
    # What ran
    bigquery.SchemaField("role",           "STRING"),   # daily_digest | bq_refresh | pause_watcher | junk_leads | slack_poster | asana_creator | airbyte_normalizer
    bigquery.SchemaField("action",         "STRING"),   # posted_digest | paused_campaign | created_task | refreshed_views …
    bigquery.SchemaField("status",         "STRING"),   # success | failed | skipped | pending_approval | approved | rejected
    # Context
    bigquery.SchemaField("channel",        "STRING"),   # nullable — google_ads / meta / …
    bigquery.SchemaField("campaign_name",  "STRING"),   # nullable
    bigquery.SchemaField("details",        "STRING"),   # JSON blob — flexible payload
    # Metrics
    bigquery.SchemaField("rows_affected",  "INT64"),    # nullable
    bigquery.SchemaField("duration_s",     "FLOAT64"),  # nullable
]

TABLES = {
    "campaigns_daily":     CAMPAIGNS_DAILY_SCHEMA,
    "adsets_daily":        ADSETS_DAILY_SCHEMA,
    "ads_daily":           ADS_DAILY_SCHEMA,
    "keywords_daily":      KEYWORDS_DAILY_SCHEMA,
    "hubspot_leads_daily": HUBSPOT_LEADS_DAILY_SCHEMA,
    "agent_activity_log":  ACTIVITY_LOG_SCHEMA,
}


# ---------- BOOTSTRAP ----------

TABLE_CLUSTERS = {
    "campaigns_daily":     ["channel", "campaign_id"],
    "adsets_daily":        ["channel", "campaign_id", "adset_id"],
    "ads_daily":           ["channel", "campaign_id", "ad_id"],
    "keywords_daily":      ["channel", "campaign_id", "adgroup_id"],
    "hubspot_leads_daily":  ["qoyod_source"],
    "agent_activity_log":  ["role", "status"],
}


def ensure_dataset_and_tables():
    """Create dataset + all tables with partitioning + clustering."""
    client = get_client()
    dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET}")
    dataset_ref.location = LOCATION
    try:
        client.create_dataset(dataset_ref, exists_ok=True)
        print(f"[OK] Dataset {PROJECT_ID}.{DATASET} ready.")
    except Exception as e:
        print(f"[ERROR] Could not create dataset: {e}")
        raise

    # Tables that partition on TIMESTAMP field "ts" instead of DATE "date"
    _TS_PARTITIONED = {"agent_activity_log"}

    for table_name, schema in TABLES.items():
        table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"
        table = bigquery.Table(table_id, schema=schema)
        partition_field = "ts" if table_name in _TS_PARTITIONED else "date"
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=partition_field,
        )
        if table_name in TABLE_CLUSTERS:
            table.clustering_fields = TABLE_CLUSTERS[table_name]
        try:
            client.create_table(table, exists_ok=True)
            print(f"[OK] Table {table_name} ready.")
        except Exception as e:
            print(f"[ERROR] Could not create table {table_name}: {e}")
            raise


# ---------- WRITE ----------

def upsert_rows(table_name: str, rows: list[dict], key_fields: list[str]):
    """
    Idempotent write: for each distinct DATE in `rows`, DELETE that partition's
    rows, then INSERT fresh. Replaces the whole day rather than per-key DELETE,
    which stays well under BQ's 1 MB query limit even for large backfills.
    """
    if not rows:
        print(f"[SKIP] {table_name}: no rows to write.")
        return 0

    client = get_client()
    table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"

    # Idempotent delete:
    #   - Always scope by date (cheap, uses partition pruning).
    #   - Also scope by the second key-field if present (e.g. "channel", "qoyod_source")
    #     so we don't wipe sibling data in shared tables like campaigns_daily.
    #   - Use IN (...) on the scoping value, one DELETE per date.
    from collections import defaultdict
    scope_field = key_fields[1] if len(key_fields) > 1 else None
    by_date = defaultdict(set)
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        if scope_field:
            by_date[d].add(str(r.get(scope_field, "")))
        else:
            by_date[d].add(None)

    for d, scope_vals in by_date.items():
        params = [bigquery.ScalarQueryParameter("d", "DATE", d)]
        if scope_field:
            sv_list = sorted(scope_vals)
            params.append(bigquery.ArrayQueryParameter("sv", "STRING", sv_list))
            delete_sql = (
                f"DELETE FROM `{table_id}` "
                f"WHERE date = @d AND {scope_field} IN UNNEST(@sv)"
            )
        else:
            delete_sql = f"DELETE FROM `{table_id}` WHERE date = @d"
        client.query(
            delete_sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()

    # Use a LOAD job (not streaming inserts) — load jobs land immediately in the
    # partition (not the streaming buffer) so subsequent DELETEs work, and they're
    # free. We upload NDJSON.
    import json as _json
    ndjson = "\n".join(_json.dumps(r, default=str) for r in rows).encode("utf-8")

    # Pass the explicit schema so ALLOW_FIELD_ADDITION can add new columns
    # (e.g. 'currency') to an existing table that was created before the field
    # was added to CAMPAIGNS_DAILY_SCHEMA.  Without an explicit schema the load
    # job validates against only the existing table schema and rejects extras.
    schema = TABLES.get(table_name)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        schema=schema,  # None -> autodetect disabled but ALLOW_FIELD_ADDITION still triggers
    )
    from io import BytesIO
    load_job = client.load_table_from_file(
        BytesIO(ndjson), table_id, job_config=job_config
    )
    load_job.result()
    print(f"[OK] Wrote {len(rows)} rows to {table_name} ({len(by_date)} partitions, load job)")
    return len(rows)


# ---------- VIEWS ----------

CAMPAIGN_PERFORMANCE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.campaign_performance` AS
WITH hs AS (
  SELECT
    date,
    lead_utm_campaign,
    qoyod_source,
    SUM(leads_total)        AS leads,
    SUM(leads_open)         AS leads_open,
    SUM(leads_qualified)    AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
  GROUP BY date, lead_utm_campaign, qoyod_source
)
SELECT
  c.date,
  c.channel,
  c.campaign_name,
  c.status,
  c.spend,
  c.leads           AS platform_leads,
  c.conversions,
  c.cpl             AS platform_cpl,
  h.leads           AS hs_leads,
  h.leads_open      AS hs_leads_open,
  h.leads_qualified AS hs_sqls,
  h.leads_disqualified AS hs_disqualified,
  SAFE_DIVIDE(c.spend, NULLIF(h.leads, 0))                      AS cpl,
  SAFE_DIVIDE(c.spend, NULLIF(h.leads_qualified, 0))            AS cpql,
  SAFE_DIVIDE(h.leads_qualified, NULLIF(h.leads, 0))            AS qual_rate,
  CASE
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads, 0)) < {CPL_SCALE} THEN 'scale'
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads, 0)) <= {CPL_ACCEPTABLE} THEN 'acceptable'
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads, 0)) <= {CPL_WARNING} THEN 'warning'
    ELSE 'pause_zone'
  END AS cpl_zone,
  CASE
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads_qualified, 0)) IS NULL THEN 'no_data'
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads_qualified, 0)) < {CPQL_SCALE} THEN 'scale'
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads_qualified, 0)) <= {CPQL_ACCEPTABLE} THEN 'acceptable'
    WHEN SAFE_DIVIDE(c.spend, NULLIF(h.leads_qualified, 0)) <= {CPQL_WARNING} THEN 'warning'
    ELSE 'pause_zone'
  END AS cpql_zone
FROM `{PROJECT_ID}.{DATASET}.campaigns_daily` c
LEFT JOIN hs h
  ON  c.date = h.date
  -- LinkedIn: utm_campaign maps to campaign group name, not campaign name
 AND  LOWER(CASE WHEN c.channel = 'linkedin'
                 THEN c.campaign_group_name
                 ELSE c.campaign_name END) = LOWER(h.lead_utm_campaign)
"""

# All-dimension lead performance: per channel + campaign + adset + ad + keyword
LEAD_UTM_PERFORMANCE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.lead_utm_performance` AS
SELECT
  date,
  qoyod_source                              AS channel,
  lead_utm_campaign                         AS utm_campaign,
  IFNULL(lead_utm_audience, '(none)')       AS utm_audience,
  IFNULL(lead_utm_content,  '(none)')       AS utm_content,
  IFNULL(lead_utm_term,     '(none)')       AS utm_term,
  SUM(leads_total)                          AS leads,
  SUM(leads_open)                           AS leads_open,
  SUM(leads_qualified)                      AS leads_qualified,
  SUM(leads_disqualified)                   AS leads_disqualified,
  SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads_total), 0)) AS qual_rate
FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
GROUP BY 1, 2, 3, 4, 5, 6
"""

# Pipeline breakdown: per channel + campaign + adset + ad + keyword + pipeline + stage
LEAD_FUNNEL_BY_PIPELINE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.lead_funnel_by_pipeline` AS
SELECT
  date,
  qoyod_source                              AS channel,
  pipeline,
  stage,
  lead_utm_campaign                         AS utm_campaign,
  IFNULL(lead_utm_audience, '(none)')       AS utm_audience,
  IFNULL(lead_utm_content,  '(none)')       AS utm_content,
  IFNULL(lead_utm_term,     '(none)')       AS utm_term,
  SUM(leads_total)                          AS leads,
  SUM(leads_open)                           AS leads_open,
  SUM(leads_qualified)                      AS leads_qualified,
  SUM(leads_disqualified)                   AS leads_disqualified,
  SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads_total), 0)) AS qual_rate,
  ANY_VALUE(top_disq_reason)                AS top_disq_reason
FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
"""


UTM_PAID_ATTRIBUTION_VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily` AS
-- ─────────────────────────────────────────────────────────────────────────────
-- utm_paid_attribution_daily
-- Joins paid spend (campaign grain from campaigns_daily) to HubSpot leads
-- at the campaign / adset / ad / keyword grain.
--
-- Dual-match strategy (07_attribution.md):
--   A. exact: LOWER(TRIM(utm_campaign)) = LOWER(TRIM(campaign_name))
--   B. slug:  slugify both sides and compare
-- Spend is proportionally distributed from campaign to adset/ad grain.
-- Unattributed leads (click-ID attributed but no UTM) appear as __no_utm__.
-- ─────────────────────────────────────────────────────────────────────────────

-- Helper: slugify a string
-- (lowercase → collapse non-alphanum runs → strip leading/trailing _)
WITH

-- 1. HubSpot: aggregate at full UTM grain (all 4 levels)
hs_full AS (
  SELECT
    date,
    qoyod_source,
    lead_utm_campaign,
    lead_utm_audience,
    lead_utm_content,
    lead_utm_term,
    SUM(leads_total)        AS leads,
    SUM(leads_qualified)    AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
  WHERE lead_utm_campaign IS NOT NULL
    AND TRIM(lead_utm_campaign) != ''
  GROUP BY 1, 2, 3, 4, 5, 6
),

-- 2. HubSpot: channel totals (authoritative, from qoyod_source)
hs_channel_total AS (
  SELECT
    date,
    qoyod_source,
    SUM(leads_total) AS channel_leads_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
  GROUP BY 1, 2
),

-- 3. HubSpot: campaign-level totals (to calculate proportional spend distribution)
hs_campaign_total AS (
  SELECT
    date,
    qoyod_source,
    lead_utm_campaign,
    SUM(leads_total) AS campaign_leads_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
  WHERE lead_utm_campaign IS NOT NULL
    AND TRIM(lead_utm_campaign) != ''
  GROUP BY 1, 2, 3
),

-- 4. Spend: sum to campaign grain (one row per date + channel + campaign_name)
spend_campaign AS (
  SELECT
    date,
    channel,
    -- LinkedIn: campaign_group_name is the utm_campaign level
    CASE WHEN channel = 'linkedin'
         THEN COALESCE(campaign_group_name, campaign_name)
         ELSE campaign_name
    END AS campaign_name,
    SUM(spend) AS spend
  FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
  GROUP BY 1, 2, 3
),

-- 5. Map channel slug → qoyod_source display name (matches HubSpot)
channel_name_map AS (
  SELECT channel_slug, qoyod_source_name FROM UNNEST([
    STRUCT('google_ads'    AS channel_slug, 'Google Ads'     AS qoyod_source_name),
    STRUCT('meta'          AS channel_slug, 'Meta Ads'       AS qoyod_source_name),
    STRUCT('snapchat'      AS channel_slug, 'Snapchat Ads'   AS qoyod_source_name),
    STRUCT('tiktok'        AS channel_slug, 'TikTok Ads'     AS qoyod_source_name),
    STRUCT('linkedin'      AS channel_slug, 'LinkedIn Ads'   AS qoyod_source_name),
    STRUCT('microsoft_ads' AS channel_slug, 'Microsoft Ads'  AS qoyod_source_name),
    STRUCT('microsoft'     AS channel_slug, 'Microsoft Ads'  AS qoyod_source_name),
    STRUCT('youtube'       AS channel_slug, 'YouTube Ads'    AS qoyod_source_name),
    STRUCT('organic_search'AS channel_slug, 'Organic Search' AS qoyod_source_name)
  ])
),

-- 6. HubSpot full grain + join to spend via dual-strategy matcher
attributed AS (
  SELECT
    hf.date,
    hf.qoyod_source,
    COALESCE(cnm_exact.channel_slug, cnm_slug.channel_slug) AS channel,
    hf.lead_utm_campaign                                     AS utm_campaign,
    hf.lead_utm_audience                                     AS utm_audience,
    hf.lead_utm_content                                      AS utm_content,
    hf.lead_utm_term                                         AS utm_term,
    hf.leads,
    hf.leads_qualified,
    hf.leads_disqualified,
    -- Campaign total leads for proportional spend calc
    hct.campaign_leads_total,
    -- Spend: try exact match first, then slug match
    COALESCE(sp_exact.spend, sp_slug.spend)                  AS spend_campaign,
    CASE
      WHEN sp_exact.spend IS NOT NULL THEN 'exact'
      WHEN sp_slug.spend  IS NOT NULL THEN 'slug'
      ELSE 'unattributed'
    END AS match_method
  FROM hs_full hf

  -- Campaign-level totals for proportional distribution
  LEFT JOIN hs_campaign_total hct
    ON  hf.date                = hct.date
    AND hf.qoyod_source        = hct.qoyod_source
    AND hf.lead_utm_campaign   = hct.lead_utm_campaign

  -- Reverse-map qoyod_source → channel slug for spend join
  LEFT JOIN channel_name_map cnm_exact
    ON LOWER(TRIM(hf.qoyod_source)) = LOWER(TRIM(cnm_exact.qoyod_source_name))
  LEFT JOIN channel_name_map cnm_slug
    ON REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(hf.qoyod_source)), r'[^a-z0-9]+', '_'), r'^_+|_+$', '')
     = REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(cnm_slug.qoyod_source_name)), r'[^a-z0-9]+', '_'), r'^_+|_+$', '')

  -- Strategy A: exact spend match
  LEFT JOIN spend_campaign sp_exact
    ON  hf.date = sp_exact.date
    AND COALESCE(cnm_exact.channel_slug, cnm_slug.channel_slug) = sp_exact.channel
    AND LOWER(TRIM(hf.lead_utm_campaign)) = LOWER(TRIM(sp_exact.campaign_name))

  -- Strategy B: slug spend match (only used when exact fails)
  LEFT JOIN spend_campaign sp_slug
    ON  sp_exact.spend IS NULL
    AND hf.date = sp_slug.date
    AND COALESCE(cnm_exact.channel_slug, cnm_slug.channel_slug) = sp_slug.channel
    AND REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(hf.lead_utm_campaign)), r'[^a-z0-9]+', '_'), r'^_+|_+$', '')
      = REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(sp_slug.campaign_name)),  r'[^a-z0-9]+', '_'), r'^_+|_+$', '')
),

-- 7. Compute proportionally distributed spend
attributed_with_spend AS (
  SELECT
    date,
    qoyod_source,
    channel,
    utm_campaign,
    utm_audience,
    utm_content,
    utm_term,
    leads,
    leads_qualified,
    leads_disqualified,
    match_method,
    -- Distribute campaign spend proportionally by leads at this grain
    SAFE_DIVIDE(
      spend_campaign * leads,
      NULLIF(campaign_leads_total, 0)
    ) AS spend
  FROM attributed
),

-- 8. UTM-attributed leads per channel+date (to compute unattributed gap)
hs_utm_channel_total AS (
  SELECT
    date,
    qoyod_source,
    SUM(leads_total) AS utm_leads_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
  WHERE lead_utm_campaign IS NOT NULL
    AND TRIM(lead_utm_campaign) != ''
  GROUP BY 1, 2
),

-- 9. Unattributed bucket: channel_total - utm_total per date+channel
unattributed AS (
  SELECT
    hct.date,
    hct.qoyod_source,
    cnm.channel_slug                                         AS channel,
    '__no_utm__'                                             AS utm_campaign,
    CAST(NULL AS STRING)                                     AS utm_audience,
    CAST(NULL AS STRING)                                     AS utm_content,
    CAST(NULL AS STRING)                                     AS utm_term,
    GREATEST(0, hct.channel_leads_total - COALESCE(uct.utm_leads_total, 0)) AS leads,
    CAST(0 AS INT64)                                         AS leads_qualified,
    CAST(0 AS INT64)                                         AS leads_disqualified,
    CAST(NULL AS FLOAT64)                                    AS spend,
    'unattributed'                                           AS match_method
  FROM hs_channel_total hct
  LEFT JOIN hs_utm_channel_total uct
    ON  hct.date          = uct.date
    AND hct.qoyod_source  = uct.qoyod_source
  LEFT JOIN channel_name_map cnm
    ON LOWER(TRIM(hct.qoyod_source)) = LOWER(TRIM(cnm.qoyod_source_name))
  -- Only emit if there's an actual gap
  WHERE (hct.channel_leads_total - COALESCE(uct.utm_leads_total, 0)) > 0
),

-- 10. Final union of attributed + unattributed
combined AS (
  SELECT
    date,
    qoyod_source,
    channel,
    utm_campaign,
    utm_audience,
    utm_content,
    utm_term,
    leads,
    leads_qualified,
    leads_disqualified,
    spend,
    match_method
  FROM attributed_with_spend

  UNION ALL

  SELECT
    date,
    qoyod_source,
    channel,
    utm_campaign,
    utm_audience,
    utm_content,
    utm_term,
    leads,
    leads_qualified,
    leads_disqualified,
    spend,
    match_method
  FROM unattributed
)

-- Final output with derived metrics
SELECT
  date,
  channel,
  -- Display name
  CASE channel
    WHEN 'google_ads'     THEN 'Google Ads'
    WHEN 'meta'           THEN 'Meta Ads'
    WHEN 'snapchat'       THEN 'Snapchat Ads'
    WHEN 'tiktok'         THEN 'TikTok Ads'
    WHEN 'linkedin'       THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads'  THEN 'Microsoft Ads'
    WHEN 'microsoft'      THEN 'Microsoft Ads'
    WHEN 'youtube'        THEN 'YouTube Ads'
    WHEN 'organic_search' THEN 'Organic Search'
    ELSE INITCAP(REPLACE(COALESCE(channel, qoyod_source, 'unknown'), '_', ' '))
  END AS channel_name,
  utm_campaign,
  utm_audience,
  utm_content,
  utm_term,
  COALESCE(spend, 0.0)                                     AS spend,
  COALESCE(leads, 0)                                       AS leads,
  COALESCE(leads_qualified, 0)                             AS leads_qualified,
  COALESCE(leads_disqualified, 0)                          AS leads_disqualified,
  SAFE_DIVIDE(COALESCE(spend, 0.0), NULLIF(leads, 0))      AS CPL,
  SAFE_DIVIDE(COALESCE(spend, 0.0), NULLIF(leads_qualified, 0)) AS CPQL,
  SAFE_DIVIDE(leads_qualified, NULLIF(leads, 0))           AS qual_rate,
  match_method
FROM combined
"""


V_ADSET_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_adset_performance` AS
-- Adset/AdGroup level: spend + impressions + clicks from adsets_daily (platform),
-- leads/SQLs/disqual from HubSpot, deals/closed-won/ROAS from hubspot_deals_daily.
-- Falls back to UTM-proxy spend when adsets_daily has no rows yet.
-- Ad set / Ad group level performance.
-- Spend/impressions/clicks come from adsets_daily (real platform data via Airbyte).
-- Leads/SQLs come from utm_paid_attribution_daily (HubSpot utm_audience match).
-- Falls back to UTM-proxy spend when adsets_daily has no row for that adset.
WITH platform AS (
  SELECT date, channel, campaign_name,
    adset_name AS utm_audience,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM `{PROJECT_ID}.{DATASET}.adsets_daily`
  GROUP BY 1, 2, 3, 4
),
hubspot AS (
  SELECT date, channel, utm_campaign, utm_audience,
    SUM(leads) AS leads,
    SUM(leads_qualified) AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_audience IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
deals AS (
  SELECT date, qoyod_source AS channel, deal_utm_campaign AS utm_campaign,
    deal_utm_audience AS utm_audience,
    SUM(deals_total) AS deals,
    SUM(deals_won) AS deals_won,
    SUM(amount_won) AS revenue_won
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_utm_audience IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
utmproxy AS (
  SELECT date, channel, utm_campaign, utm_audience, SUM(spend) AS spend
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_audience IS NOT NULL
  GROUP BY 1, 2, 3, 4
)
SELECT
  COALESCE(p.date, h.date)                AS date,
  COALESCE(p.channel, h.channel)          AS channel,
  CASE COALESCE(p.channel, h.channel)
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'meta'          THEN 'Meta Ads'
    WHEN 'snapchat'      THEN 'Snapchat Ads'
    WHEN 'tiktok'        THEN 'TikTok Ads'
    WHEN 'linkedin'      THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    ELSE COALESCE(p.channel, h.channel)
  END                                      AS channel_name,
  COALESCE(p.campaign_name, h.utm_campaign) AS utm_campaign,
  COALESCE(p.utm_audience, h.utm_audience)  AS utm_audience,
  COALESCE(p.spend, u.spend, 0)             AS spend,
  COALESCE(p.impressions, 0)                AS impressions,
  COALESCE(p.clicks, 0)                     AS clicks,
  COALESCE(h.leads, 0)                      AS leads,
  COALESCE(h.leads_qualified, 0)            AS leads_qualified,
  COALESCE(h.leads_disqualified, 0)         AS leads_disqualified,
  COALESCE(d.deals, 0)                      AS deals,
  COALESCE(d.deals_won, 0)                  AS deals_won,
  COALESCE(d.revenue_won, 0)                AS revenue_won,
  -- Ratios
  SAFE_DIVIDE(h.leads_qualified, NULLIF(h.leads, 0))                     AS qual_rate,
  SAFE_DIVIDE(h.leads_disqualified, NULLIF(h.leads, 0))                  AS disq_rate,
  -- Cost metrics
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads, 0))            AS CPL,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads_qualified, 0))  AS CPQL,
  -- ROAS = revenue_won / spend
  SAFE_DIVIDE(d.revenue_won, NULLIF(COALESCE(p.spend, u.spend), 0))      AS ROAS,
  IF(p.date IS NOT NULL, 'platform', 'utm_proxy')                         AS data_source
FROM platform p
FULL OUTER JOIN hubspot h
  ON p.date = h.date AND p.channel = h.channel
  AND LOWER(TRIM(p.utm_audience)) = LOWER(TRIM(h.utm_audience))
LEFT JOIN utmproxy u
  ON h.date = u.date AND h.channel = u.channel AND h.utm_audience = u.utm_audience
LEFT JOIN deals d
  ON COALESCE(p.date, h.date) = d.date
  AND COALESCE(p.channel, h.channel) = d.channel
  AND LOWER(TRIM(COALESCE(p.utm_audience, h.utm_audience))) = LOWER(TRIM(d.utm_audience))
"""


V_AD_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_ad_performance` AS
-- Ad/Creative level: spend+impressions+clicks from ads_daily,
-- leads/SQLs/disqual from HubSpot, deals/closed-won/ROAS from deals.
WITH platform AS (
  SELECT date, channel, campaign_name, adset_name, ad_name AS utm_content,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM `{PROJECT_ID}.{DATASET}.ads_daily`
  GROUP BY 1, 2, 3, 4, 5
),
hubspot AS (
  SELECT date, channel, utm_campaign, utm_audience, utm_content,
    SUM(leads) AS leads,
    SUM(leads_qualified) AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_content IS NOT NULL
  GROUP BY 1, 2, 3, 4, 5
),
deals AS (
  SELECT date, qoyod_source AS channel,
    deal_utm_campaign AS utm_campaign,
    deal_utm_content AS utm_content,
    SUM(deals_total) AS deals,
    SUM(deals_won) AS deals_won,
    SUM(amount_won) AS revenue_won
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_utm_content IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
utmproxy AS (
  SELECT date, channel, utm_campaign, utm_audience, utm_content, SUM(spend) AS spend
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_content IS NOT NULL
  GROUP BY 1, 2, 3, 4, 5
)
SELECT
  COALESCE(p.date, h.date)                  AS date,
  COALESCE(p.channel, h.channel)            AS channel,
  CASE COALESCE(p.channel, h.channel)
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'meta'          THEN 'Meta Ads'
    WHEN 'snapchat'      THEN 'Snapchat Ads'
    WHEN 'tiktok'        THEN 'TikTok Ads'
    WHEN 'linkedin'      THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    ELSE COALESCE(p.channel, h.channel)
  END                                        AS channel_name,
  COALESCE(p.campaign_name, h.utm_campaign)  AS utm_campaign,
  COALESCE(p.adset_name, h.utm_audience)     AS utm_audience,
  COALESCE(p.utm_content, h.utm_content)     AS utm_content,
  COALESCE(p.spend, u.spend, 0)              AS spend,
  COALESCE(p.impressions, 0)                 AS impressions,
  COALESCE(p.clicks, 0)                      AS clicks,
  COALESCE(h.leads, 0)                       AS leads,
  COALESCE(h.leads_qualified, 0)             AS leads_qualified,
  COALESCE(h.leads_disqualified, 0)          AS leads_disqualified,
  COALESCE(d.deals, 0)                       AS deals,
  COALESCE(d.deals_won, 0)                   AS deals_won,
  COALESCE(d.revenue_won, 0)                 AS revenue_won,
  SAFE_DIVIDE(h.leads_qualified, NULLIF(h.leads, 0))                    AS qual_rate,
  SAFE_DIVIDE(h.leads_disqualified, NULLIF(h.leads, 0))                 AS disq_rate,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads, 0))           AS CPL,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads_qualified, 0)) AS CPQL,
  SAFE_DIVIDE(d.revenue_won, NULLIF(COALESCE(p.spend, u.spend), 0))     AS ROAS,
  IF(p.date IS NOT NULL, 'platform', 'utm_proxy')                        AS data_source
FROM platform p
FULL OUTER JOIN hubspot h
  ON p.date = h.date AND p.channel = h.channel
  AND LOWER(TRIM(p.utm_content)) = LOWER(TRIM(h.utm_content))
LEFT JOIN utmproxy u
  ON h.date = u.date AND h.channel = u.channel AND h.utm_content = u.utm_content
LEFT JOIN deals d
  ON COALESCE(p.date, h.date) = d.date
  AND COALESCE(p.channel, h.channel) = d.channel
  AND LOWER(TRIM(COALESCE(p.utm_content, h.utm_content))) = LOWER(TRIM(d.utm_content))
"""


V_KEYWORD_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_keyword_performance` AS
-- Keyword level: Google Ads + Microsoft Ads.
-- Spend/impressions/clicks/QS from keywords_daily; leads/deals from HubSpot.
WITH platform AS (
  SELECT date, channel, campaign_name, adgroup_name, keyword_text AS utm_term,
    match_type,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
    SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions),0)) AS ctr,
    AVG(quality_score) AS quality_score
  FROM `{PROJECT_ID}.{DATASET}.keywords_daily`
  GROUP BY 1, 2, 3, 4, 5, 6
),
hubspot AS (
  SELECT date, channel, utm_campaign, utm_audience, utm_term,
    SUM(leads) AS leads,
    SUM(leads_qualified) AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified,
    ANY_VALUE(match_method) AS match_method
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE channel IN ('google_ads', 'microsoft_ads')
    AND utm_term IS NOT NULL AND utm_campaign != '__no_utm__'
  GROUP BY 1, 2, 3, 4, 5
),
deals AS (
  SELECT date, qoyod_source AS channel,
    deal_utm_campaign AS utm_campaign,
    deal_utm_term AS utm_term,
    SUM(deals_total) AS deals,
    SUM(deals_won) AS deals_won,
    SUM(amount_won) AS revenue_won
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_utm_term IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
utmproxy AS (
  SELECT date, channel, utm_campaign, utm_term, SUM(spend) AS spend
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_term IS NOT NULL AND utm_campaign != '__no_utm__'
  GROUP BY 1, 2, 3, 4
)
SELECT
  COALESCE(p.date, h.date)                  AS date,
  COALESCE(p.channel, h.channel)            AS channel,
  CASE COALESCE(p.channel, h.channel)
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    ELSE COALESCE(p.channel, h.channel)
  END                                        AS channel_name,
  COALESCE(p.campaign_name, h.utm_campaign)  AS utm_campaign,
  COALESCE(p.adgroup_name, h.utm_audience)   AS utm_audience,
  COALESCE(p.utm_term, h.utm_term)           AS utm_term,
  p.match_type,
  p.quality_score,
  COALESCE(p.spend, u.spend, 0)              AS spend,
  COALESCE(p.impressions, 0)                 AS impressions,
  COALESCE(p.clicks, 0)                      AS clicks,
  COALESCE(p.ctr, 0)                         AS ctr,
  COALESCE(h.leads, 0)                       AS leads,
  COALESCE(h.leads_qualified, 0)             AS leads_qualified,
  COALESCE(h.leads_disqualified, 0)          AS leads_disqualified,
  COALESCE(d.deals, 0)                       AS deals,
  COALESCE(d.deals_won, 0)                   AS deals_won,
  COALESCE(d.revenue_won, 0)                 AS revenue_won,
  SAFE_DIVIDE(h.leads_qualified, NULLIF(h.leads, 0))                    AS qual_rate,
  SAFE_DIVIDE(h.leads_disqualified, NULLIF(h.leads, 0))                 AS disq_rate,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads, 0))           AS CPL,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads_qualified, 0)) AS CPQL,
  SAFE_DIVIDE(d.revenue_won, NULLIF(COALESCE(p.spend, u.spend), 0))     AS ROAS,
  COALESCE(h.match_method, 'utm_proxy')      AS match_method,
  IF(p.date IS NOT NULL, 'platform', 'utm_proxy')                        AS data_source
FROM platform p
FULL OUTER JOIN hubspot h
  ON p.date = h.date AND p.channel = h.channel
  AND LOWER(TRIM(p.utm_term)) = LOWER(TRIM(h.utm_term))
LEFT JOIN utmproxy u
  ON h.date = u.date AND h.channel = u.channel AND h.utm_term = u.utm_term
LEFT JOIN deals d
  ON COALESCE(p.date, h.date) = d.date
  AND COALESCE(p.channel, h.channel) = d.channel
  AND LOWER(TRIM(COALESCE(p.utm_term, h.utm_term))) = LOWER(TRIM(d.utm_term))
"""


def create_views():
    client = get_client()
    for sql, name in [
        (CAMPAIGN_PERFORMANCE_VIEW_SQL,       "campaign_performance"),
        (LEAD_UTM_PERFORMANCE_VIEW_SQL,       "lead_utm_performance"),
        (LEAD_FUNNEL_BY_PIPELINE_VIEW_SQL,    "lead_funnel_by_pipeline"),
        (UTM_PAID_ATTRIBUTION_VIEW_SQL,       "utm_paid_attribution_daily"),
        (V_ADSET_PERFORMANCE_SQL,             "v_adset_performance"),
        (V_AD_PERFORMANCE_SQL,                "v_ad_performance"),
        (V_KEYWORD_PERFORMANCE_SQL,           "v_keyword_performance"),
    ]:
        client.query(sql).result()
        print(f"[OK] View {name} created.")


# ---------- TEST ----------

def test_connection():
    client = get_client()
    query = "SELECT 1 AS ok, CURRENT_TIMESTAMP() AS now"
    rows = list(client.query(query).result())
    print(f"[OK] Connected to {PROJECT_ID}. Test query returned: {rows[0].ok} at {rows[0].now}")
    return True


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "test":
        test_connection()
    elif cmd == "bootstrap":
        test_connection()
        ensure_dataset_and_tables()
        create_views()
    elif cmd == "views":
        create_views()
    else:
        print("Usage: python collectors/bq_writer.py [test|bootstrap|views]")
