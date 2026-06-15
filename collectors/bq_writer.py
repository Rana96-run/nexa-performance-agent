"""
BigQuery writer — shared helper for all collectors.

All channel collectors write daily rows into these tables:
  - campaigns_daily     (one row per campaign per day per channel)
  - ads_daily           (one row per ad per day — optional, heavier)
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
    # Impression Share metrics — Search + PMax campaigns only; null for
    # social / video / display channels that don't report IS.
    bigquery.SchemaField("impression_share",     "FLOAT64"),           # 0..1, fraction of eligible impressions captured
    bigquery.SchemaField("top_impression_share", "FLOAT64"),           # 0..1, fraction of top-of-page impressions captured
    bigquery.SchemaField("lost_is_budget",       "FLOAT64"),           # 0..1, IS lost due to budget
    bigquery.SchemaField("lost_is_rank",         "FLOAT64"),           # 0..1, IS lost due to ad rank / quality
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
    bigquery.SchemaField("utm_audience",  "STRING"),    # resolved from tracking template; join key vs hubspot_leads_module_daily.lead_utm_audience
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
    bigquery.SchemaField("utm_content",   "STRING"),    # parsed from tracking_url_template; join key vs hubspot_leads_module_daily.lead_utm_content
    bigquery.SchemaField("status",        "STRING"),
    bigquery.SchemaField("spend",         "FLOAT64"),
    bigquery.SchemaField("impressions",   "INT64"),
    bigquery.SchemaField("clicks",        "INT64"),
    bigquery.SchemaField("ctr",           "FLOAT64"),
    bigquery.SchemaField("leads",         "INT64"),
    bigquery.SchemaField("conversions",   "FLOAT64"),
    bigquery.SchemaField("frequency",     "FLOAT64"),
    bigquery.SchemaField("currency",      "STRING"),
    bigquery.SchemaField("final_url",     "STRING"),   # destination LP URL (Google Ads only for now)
    bigquery.SchemaField("updated_at",    "TIMESTAMP"),
    bigquery.SchemaField("cpl",           "FLOAT64"),   # spend / leads (USD); already in live table — added here for explicit-schema validation
    bigquery.SchemaField("creative_type", "STRING"),    # image | video | carousel | collection | story | other (None for Google/Microsoft)
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
    bigquery.SchemaField("role",           "STRING"),   # bq_refresh | performance_audit | keyword_management | daily_digest | ops_scheduler | spike_detector | llm_cadence
                                                          # NB: 'pause_watcher', 'google_ads_audit', 'keyword_approval', 'daily_agent' are the legacy names — renamed 2026-05-06.
    bigquery.SchemaField("action",         "STRING"),   # posted_digest | paused_campaign | created_task | refreshed_views …
    bigquery.SchemaField("status",         "STRING"),   # success | failed | skipped | pending_approval | approved | rejected
    # Context
    bigquery.SchemaField("channel",        "STRING"),   # nullable — google_ads / meta / …
    bigquery.SchemaField("campaign_name",  "STRING"),   # nullable
    bigquery.SchemaField("details",        "STRING"),   # JSON blob — flexible payload
    # Metrics
    bigquery.SchemaField("rows_affected",  "INT64"),    # nullable
    bigquery.SchemaField("duration_s",     "FLOAT64"),  # nullable
    # ── Resource consumption (added 2026-05-08) ──────────────────────────────
    bigquery.SchemaField("tokens_in",        "INT64"),    # Anthropic input tokens
    bigquery.SchemaField("tokens_out",       "INT64"),    # Anthropic output tokens
    bigquery.SchemaField("cost_usd",         "FLOAT64"),  # total $ cost (LLM + BQ + …)
    bigquery.SchemaField("api_calls",        "INT64"),    # outbound HTTP calls to platform APIs
    bigquery.SchemaField("bq_bytes_scanned", "INT64"),    # bytes processed by BQ queries
]

QA_GATE_EVENTS_SCHEMA = [
    bigquery.SchemaField("event_id",     "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("ts",           "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("surface",      "STRING",  mode="REQUIRED"),  # slack | asana | bq | dashboard
    bigquery.SchemaField("passed",       "BOOL",    mode="REQUIRED"),
    bigquery.SchemaField("check_name",   "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("check_passed", "BOOL",    mode="REQUIRED"),
    bigquery.SchemaField("severity",     "STRING"),
    bigquery.SchemaField("detail",       "STRING"),
]

TABLES = {
    "campaigns_daily":     CAMPAIGNS_DAILY_SCHEMA,
    # adsets_daily DROPPED 2026-06-16 — only consumer migrated to wide_ads; 6 collector write calls removed
    "ads_daily":           ADS_DAILY_SCHEMA,
    "keywords_daily":      KEYWORDS_DAILY_SCHEMA,
    "agent_activity_log":  ACTIVITY_LOG_SCHEMA,
    # qa_gate_events DROPPED 2026-06-16 — write-only ops sink, 0 decision-logic reads
}


# ---------- BOOTSTRAP ----------

TABLE_CLUSTERS = {
    "campaigns_daily":     ["channel", "campaign_id"],
    # adsets_daily DROPPED 2026-06-16
    "ads_daily":           ["channel", "campaign_id", "ad_id"],
    "keywords_daily":      ["channel", "campaign_id", "adgroup_id"],
    "agent_activity_log":  ["role", "status"],
    # qa_gate_events DROPPED 2026-06-16
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
    _TS_PARTITIONED = {"agent_activity_log"}  # qa_gate_events dropped 2026-06-16

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

# ─── Pre-write sanity guards (Part A: 2026-05-06) ────────────────────────────
# Single source of truth for "what's a valid row?" — runs before any write hits
# BigQuery. Bad rows are dropped (not raised) so one corrupt record from the
# upstream API doesn't kill the whole batch. Counts are logged.

from datetime import date as _date

_MIN_VALID_DATE = _date(2024, 1, 1)   # nothing earlier than 2024 makes sense
                                       # for our business — sanity floor
_VALID_CURRENCIES = {                 # ISO codes we've ever seen + USD
    "USD", "SAR", "EUR", "GBP", "AED", "EGP", "JOD", "KWD",
    "QAR", "BHD", "OMR", "INR", "TRY", "PKR",
}
# Numeric columns where negative values indicate an upstream parsing/API bug
# (refunds in our world are reflected as conversions=0, not as negative spend).
_NON_NEGATIVE_NUMERICS = {
    "spend", "amount", "amount_total", "amount_won", "amount_lost",
    "amount_open", "cost_micros", "impressions", "clicks", "leads",
    "leads_total", "leads_qualified", "leads_disqualified",
    "deals_total", "deals_won", "deals_lost", "deals_open",
}


def validate_row(row: dict, table_name: str = "") -> tuple[bool, str]:
    """
    Returns (is_valid, reason). Bad rows are dropped at write time, with the
    reason logged. This catches:

      • date in the future (anything > today)
      • date before the sanity floor (2024-01-01)
      • negative spend / amount / count
      • currency code outside the known allowlist
      • required `date` field missing or unparseable
    """
    # Tables partitioned on TIMESTAMP `ts` have no `date` field — skip the
    # date-specific checks. Validate-row is per-row so we get the table name
    # via the closure context; keep it via a sentinel.
    if table_name in {"agent_activity_log"}:  # ts-partitioned, no date field
        return True, "ok"

    # 1. Date must exist and be parseable
    d = row.get("date")
    if not d:
        return False, "missing date"
    if isinstance(d, str):
        try:
            d_obj = _date.fromisoformat(d[:10])
        except Exception:
            return False, f"unparseable date: {d!r}"
    elif isinstance(d, _date):
        d_obj = d
    else:
        return False, f"date wrong type: {type(d).__name__}"

    # 2. Date bounds
    today = _date.today()
    if d_obj > today:
        return False, f"future date: {d_obj}"
    if d_obj < _MIN_VALID_DATE:
        return False, f"pre-2024 date: {d_obj}"

    # 3. Non-negative numerics
    for col in _NON_NEGATIVE_NUMERICS:
        if col in row and row[col] is not None:
            try:
                v = float(row[col])
            except Exception:
                continue
            if v < 0:
                return False, f"{col} negative: {v}"

    # 4. Currency allowlist (only if a currency field is present)
    for cur_field in ("currency", "currency_native"):
        cur = row.get(cur_field)
        if cur and cur not in _VALID_CURRENCIES:
            return False, f"{cur_field} not in allowlist: {cur!r}"

    return True, ""


def filter_valid_rows(rows: list[dict], table_name: str
                      ) -> tuple[list[dict], dict[str, int]]:
    """Returns (valid_rows, drop_counts_by_reason). Logs a summary if any
    rows were dropped — so the operator sees it, but doesn't crash."""
    valid: list[dict] = []
    dropped: dict[str, int] = {}
    examples: dict[str, dict] = {}
    for r in rows:
        ok, reason = validate_row(r, table_name)
        if ok:
            valid.append(r)
        else:
            # Bucket reasons (strip the value off, just keep the type)
            bucket = reason.split(":")[0]
            dropped[bucket] = dropped.get(bucket, 0) + 1
            if bucket not in examples:
                examples[bucket] = {"row": r, "reason": reason}

    if dropped:
        total = sum(dropped.values())
        print(f"[validate] {table_name}: dropped {total}/{len(rows)} rows — {dict(dropped)}")
        for bucket, info in examples.items():
            ex = info["row"]
            ex_brief = {k: ex.get(k) for k in ("date","channel","account_id","campaign_id","spend","currency") if k in ex}
            print(f"  -> example [{bucket}]: {info['reason']} | {ex_brief}")
    return valid, dropped


def upsert_rows(table_name: str, rows: list[dict], key_fields: list[str]):
    """
    Idempotent write: for each distinct DATE in `rows`, DELETE that partition's
    rows, then INSERT fresh. Replaces the whole day rather than per-key DELETE,
    which stays well under BQ's 1 MB query limit even for large backfills.
    """
    if not rows:
        print(f"[SKIP] {table_name}: no rows to write.")
        return 0

    # Sanity guard: drop future-dated, negative-spend, bad-currency rows BEFORE
    # they hit BigQuery. Single source of truth lives in validate_row().
    rows, _drop_counts = filter_valid_rows(rows, table_name)
    if not rows:
        print(f"[SKIP] {table_name}: all rows dropped by validator.")
        return 0

    # QA gate — sanity-check the batch (internal dupes, multi-account presence)
    # before any DELETE fires. Auto-retry-then-block per qa/gate.py policy.
    try:
        from qa.gate import gate, QAGateError
        try:
            gate.verify_bq_write(table_name, rows, key_fields)
        except QAGateError as e:
            print(f"[bq] QA gate BLOCKED upsert to {table_name}: {e}")
            raise
    except ImportError:
        pass  # qa module not present — degrade gracefully

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
--
-- SOURCE FILTER (added 2026-06-09): only keep qoyod_source values that map to a
-- known channel in channel_name_map (item 5). Leads from NON-mapped sources
-- (Offline / Direct Traffic / Organic Social / Email Marketing / Other /
-- Direct In-app Purchase / Referrals / Twitter Ads / 'youtube') carry a paid UTM
-- on the contact (last-touch HubSpot attribution kept a stale UTM) but their
-- qoyod_source is non-paid, so COALESCE(cnm_exact, cnm_slug) returned NULL channel.
-- Those rows never satisfied `p.channel = h.channel` in v_adset_performance and
-- surfaced as leads-only orphan rows (38 rows / 40 leads on 2026-06-09).
-- They are genuinely non-paid touches that do not belong in the paid attribution
-- view, so we drop them at the source grain. Sources kept = the display names in
-- channel_name_map; matched with the SAME exact-then-slug logic the channel join
-- uses, so the filter and the channel resolution stay perfectly in lock-step.
hs_full AS (
  SELECT
    date,
    qoyod_source,
    lead_utm_campaign,
    lead_utm_audience,
    lead_utm_content,
    lead_utm_term,
    lead_utm_source,
    SUM(leads_total)        AS leads,
    SUM(leads_qualified)    AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
  WHERE lead_utm_campaign IS NOT NULL
    AND TRIM(lead_utm_campaign) != ''
    AND LOWER(TRIM(lead_utm_campaign)) != '__none__'
    -- keep only sources that resolve to a known channel (paid + organic_search)
    AND (
      LOWER(TRIM(qoyod_source)) IN (
        'google ads','meta ads','snapchat ads','tiktok ads',
        'linkedin ads','microsoft ads','youtube ads','organic search'
      )
      OR REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(qoyod_source)), r'[^a-z0-9]+', '_'), r'^_+|_+$', '') IN (
        'google_ads','meta_ads','snapchat_ads','tiktok_ads',
        'linkedin_ads','microsoft_ads','youtube_ads','organic_search'
      )
    )
  GROUP BY 1, 2, 3, 4, 5, 6, 7
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
    AND LOWER(TRIM(lead_utm_campaign)) != '__none__'
  GROUP BY 1, 2, 3
),

-- 4. Spend: sum to campaign grain. CRITICAL: group by the NORMALISED
-- LOWER(TRIM()) campaign key, NOT the raw campaign_name. The downstream spend
-- joins (sp_exact / sp_slug) match on LOWER(TRIM(...)); if this CTE keeps two
-- casing variants of the same campaign as separate rows (e.g. Snapchat's
-- 'Snapchat_LeadGen_Retargeting_Instantform' vs '..._Leadgen_...'), a single
-- HubSpot lead bucket matches BOTH spend rows and its leads are DOUBLED. This
-- fan propagated into v_ad/v_adset_performance (snapchat 148 truth -> 172).
-- Fixed 2026-06-09: collapse casing variants to one spend row per normalised key.
spend_campaign AS (
  SELECT
    date,
    channel,
    -- normalised join key — one row per (date, channel, lowercased campaign)
    LOWER(TRIM(
      CASE WHEN channel = 'linkedin'
           THEN COALESCE(campaign_group_name, campaign_name)
           ELSE campaign_name
      END
    )) AS campaign_name,
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
    -- Microsoft: map qoyod_source 'Microsoft Ads' to the SINGLE canonical slug
    -- 'microsoft_ads' (matches campaigns_daily.channel). The legacy 'microsoft'
    -- slug row was REMOVED 2026-06-09 — having both rows made the cnm_exact /
    -- cnm_slug joins fan one HubSpot Microsoft row across two slugs, so the view
    -- emitted the SAME leads under both channel='microsoft' and 'microsoft_ads'
    -- (per-channel recon double-counted Microsoft). One row = one slug.
    STRUCT('microsoft_ads' AS channel_slug, 'Microsoft Ads'  AS qoyod_source_name),
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
    hf.lead_utm_source                                       AS utm_source,
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
    utm_source,
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
    AND LOWER(TRIM(lead_utm_campaign)) != '__none__'
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
    CAST(NULL AS STRING)                                     AS utm_source,
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
    utm_source,
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
    utm_source,
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
  utm_source,
  COALESCE(spend, 0.0)                                     AS spend,
  COALESCE(leads, 0)                                       AS leads,
  COALESCE(leads_qualified, 0)                             AS leads_qualified,
  COALESCE(leads_disqualified, 0)                          AS leads_disqualified,
  SAFE_DIVIDE(COALESCE(spend, 0.0), NULLIF(leads, 0))      AS CPL,
  SAFE_DIVIDE(COALESCE(spend, 0.0), NULLIF(leads_qualified, 0)) AS CPQL,
  SAFE_DIVIDE(leads_qualified, NULLIF(leads_qualified + leads_disqualified, 0)) AS qual_rate,
  match_method
FROM combined
"""


V_ADSET_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_adset_performance` AS
SELECT
  date,
  channel,
  ANY_VALUE(channel_name)                                                      AS channel_name,
  ANY_VALUE(campaign_name)                                                     AS utm_campaign,
  ANY_VALUE(adset_name)                                                        AS utm_audience,
  ANY_VALUE(adset_name)                                                        AS adset_name,
  CAST(NULL AS STRING)                                                         AS utm_source,
  ANY_VALUE(status)                                                            AS status,
  campaign_id,
  adset_id,
  ROUND(SUM(spend), 2)                                                        AS spend,
  SUM(impressions)                                                             AS impressions,
  SUM(clicks)                                                                  AS clicks,
  SUM(leads_total)                                                             AS leads,
  SUM(leads_qualified)                                                         AS leads_qualified,
  SUM(leads_disqualified)                                                      AS leads_disqualified,
  SUM(new_biz_deals_won)                                                       AS new_biz_deals_won,
  SUM(new_biz_deals_lost)                                                      AS new_biz_deals_lost,
  SUM(new_biz_deals_open)                                                      AS new_biz_deals_open,
  SUM(new_biz_deals_total)                                                     AS new_biz_deals_total,
  ROUND(SUM(new_biz_revenue_won), 2)                                          AS new_biz_revenue_won,
  ROUND(SUM(new_biz_amount_lost), 2)                                          AS new_biz_amount_lost,
  ROUND(SUM(new_biz_amount_open), 2)                                          AS new_biz_amount_open,
  ROUND(SUM(new_biz_revenue_won)+SUM(new_biz_amount_lost)+SUM(new_biz_amount_open), 2) AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),
    NULLIF(SUM(leads_qualified)+SUM(leads_disqualified), 0)), 4)              AS qual_rate,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified),
    NULLIF(SUM(leads_qualified)+SUM(leads_disqualified), 0)), 4)              AS disq_rate,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)), 2)             AS CPL,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)         AS CPQL,
  ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)     AS new_biz_roas,
  ROUND(SUM(all_revenue_won), 2)                                             AS revenue_won,
  ROUND(SUM(all_amount_lost), 2)                                             AS amount_lost,
  ROUND(SUM(all_amount_open), 2)                                             AS amount_open,
  ROUND(SUM(all_revenue_won)+SUM(all_amount_lost)+SUM(all_amount_open), 2)   AS amount_total,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won), NULLIF(SUM(spend), 0)), 2)         AS roas,
  'wide_ads'                                                                  AS data_source
FROM `{PROJECT_ID}.{DATASET}.wide_ads`
GROUP BY date, channel, campaign_id, adset_id
"""


V_AD_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_ad_performance` AS
SELECT
  date,
  channel,
  ANY_VALUE(channel_name)                                                      AS channel_name,
  ANY_VALUE(campaign_name)                                                     AS utm_campaign,
  ANY_VALUE(adset_name)                                                        AS utm_audience,
  ANY_VALUE(utm_content)                                                       AS utm_content,
  ANY_VALUE(ad_name)                                                           AS ad_name,
  CAST(NULL AS STRING)                                                         AS utm_source,
  campaign_id,
  adset_id,
  ad_id,
  ROUND(SUM(spend), 2)                                                        AS spend,
  SUM(impressions)                                                             AS impressions,
  SUM(clicks)                                                                  AS clicks,
  SUM(leads_total)                                                             AS leads_total,
  SUM(leads_total)                                                             AS leads,
  SUM(leads_qualified)                                                         AS leads_qualified,
  SUM(leads_qualified)                                                         AS qualified,
  SUM(leads_disqualified)                                                      AS leads_disqualified,
  SUM(new_biz_deals_won)                                                       AS new_biz_deals_won,
  SUM(new_biz_deals_lost)                                                      AS new_biz_deals_lost,
  SUM(new_biz_deals_open)                                                      AS new_biz_deals_open,
  SUM(new_biz_deals_total)                                                     AS new_biz_deals_total,
  ROUND(SUM(new_biz_revenue_won), 2)                                          AS new_biz_revenue_won,
  ROUND(SUM(new_biz_amount_lost), 2)                                          AS new_biz_amount_lost,
  ROUND(SUM(new_biz_amount_open), 2)                                          AS new_biz_amount_open,
  ROUND(SUM(new_biz_revenue_won)+SUM(new_biz_amount_lost)+SUM(new_biz_amount_open), 2) AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),
    NULLIF(SUM(leads_qualified)+SUM(leads_disqualified), 0)), 4)              AS qual_rate,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified),
    NULLIF(SUM(leads_qualified)+SUM(leads_disqualified), 0)), 4)              AS disq_rate,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)), 2)             AS CPL,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)         AS CPQL,
  ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)     AS new_biz_roas,
  ROUND(SUM(all_revenue_won), 2)                                             AS revenue_won,
  ROUND(SUM(all_amount_lost), 2)                                             AS amount_lost,
  ROUND(SUM(all_amount_open), 2)                                             AS amount_open,
  ROUND(SUM(all_revenue_won)+SUM(all_amount_lost)+SUM(all_amount_open), 2)   AS amount_total,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won), NULLIF(SUM(spend), 0)), 2)         AS roas,
  ANY_VALUE(creative_type)                                                    AS creative_type,
  ANY_VALUE(status)                                                           AS status,
  'wide_ads'                                                                  AS data_source
FROM `{PROJECT_ID}.{DATASET}.wide_ads`
GROUP BY date, channel, campaign_id, adset_id, ad_id
"""


V_KEYWORD_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_keyword_performance` AS
-- Keyword level: Google Ads + Microsoft Ads.
-- Spend/impressions/clicks/QS from wide_keywords (already joined at materialisation).
-- Rebuilt 2026-06-15: utm_paid_attribution_daily was dropped; sources are now
-- wide_keywords (spend + leads via hubspot_leads_individual) and
-- hubspot_deals_individual for deal aggregates.
WITH platform AS (
  -- wide_keywords already joins keywords_daily + hubspot_leads_individual + hubspot_deals_individual.
  -- We GROUP BY date×channel×campaign_name×adgroup_name×keyword_text to collapse
  -- any multi-day window into the daily grain we expose.
  SELECT
    date,
    channel,
    channel_name,
    campaign_name,
    adgroup_name,
    keyword_text                              AS utm_term,
    match_type,
    ANY_VALUE(status)                         AS status,
    AVG(quality_score)                        AS quality_score,
    SUM(spend)                               AS spend,
    SUM(impressions)                         AS impressions,
    SUM(clicks)                              AS clicks,
    SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) AS ctr,
    SUM(leads_total)                         AS leads,
    SUM(leads_qualified)                     AS leads_qualified,
    SUM(leads_disqualified)                  AS leads_disqualified,
    SUM(new_biz_deals_won)                   AS new_biz_deals_won,
    SUM(new_biz_deals_total)                 AS new_biz_deals_total,
    SUM(new_biz_revenue_won)                 AS new_biz_revenue_won,
    SUM(all_deals_won)                       AS deals_won,
    SUM(all_revenue_won)                     AS revenue_won
  FROM `{PROJECT_ID}.{DATASET}.wide_keywords`
  GROUP BY 1, 2, 3, 4, 5, 6, 7
),
deals AS (
  -- All-pipeline deal aggregates by keyword term (for richer deal columns).
  SELECT
    createdate                               AS date,
    CASE
      WHEN LOWER(TRIM(qoyod_source)) = 'google ads'    THEN 'google_ads'
      WHEN LOWER(TRIM(qoyod_source)) = 'microsoft ads' THEN 'microsoft_ads'
      ELSE LOWER(REPLACE(TRIM(qoyod_source), ' ', '_'))
    END                                      AS channel,
    LOWER(TRIM(deal_utm_campaign))           AS utm_campaign,
    LOWER(TRIM(deal_utm_term))               AS utm_term,
    SUM(deals_total)                         AS deals_total,
    SUM(deals_won)                           AS deals,
    SUM(amount_won)                          AS amount_won,
    SUM(amount_lost)                         AS amount_lost,
    SUM(amount_open)                         AS amount_open,
    SUM(amount_total)                        AS amount_total,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_won  ELSE 0 END)    AS new_biz_amount_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_lost ELSE 0 END)    AS new_biz_amount_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_open ELSE 0 END)    AS new_biz_amount_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_total ELSE 0 END)   AS new_biz_amount_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_utm_term IS NOT NULL AND deal_utm_term != ''
  GROUP BY 1, 2, 3, 4
)
SELECT
  p.date,
  p.channel,
  p.channel_name,
  p.campaign_name                            AS utm_campaign,
  p.adgroup_name                             AS utm_audience,
  p.adgroup_name                             AS adgroup_name,
  p.utm_term,
  CAST(NULL AS STRING)                       AS utm_source,
  p.status,
  p.match_type,
  p.quality_score,
  COALESCE(p.spend, 0)                       AS spend,
  COALESCE(p.impressions, 0)                 AS impressions,
  COALESCE(p.clicks, 0)                      AS clicks,
  COALESCE(p.ctr, 0)                         AS ctr,
  COALESCE(p.leads, 0)                       AS leads,
  COALESCE(p.leads_qualified, 0)             AS leads_qualified,
  COALESCE(p.leads_disqualified, 0)          AS leads_disqualified,
  -- All-pipeline deal columns (sourced from hubspot_deals_daily compat view)
  COALESCE(d.deals, 0)                       AS deals,
  COALESCE(d.deals, 0)                       AS deals_won,
  COALESCE(p.revenue_won, d.amount_won, 0)   AS revenue_won,
  COALESCE(d.amount_lost, 0)                 AS amount_lost,
  COALESCE(d.amount_open, 0)                 AS amount_open,
  COALESCE(d.amount_total, 0)                AS amount_total,
  SAFE_DIVIDE(COALESCE(p.revenue_won, d.amount_won), NULLIF(p.spend, 0)) AS roas,
  -- New business deal amounts (Sales Pipeline + Bookkeeping + Qflavours)
  COALESCE(p.new_biz_deals_won, 0)           AS new_biz_deals_won,
  COALESCE(p.new_biz_revenue_won, d.new_biz_amount_won, 0) AS new_biz_revenue_won,
  COALESCE(d.new_biz_amount_lost, 0)         AS new_biz_amount_lost,
  COALESCE(d.new_biz_amount_open, 0)         AS new_biz_amount_open,
  COALESCE(d.new_biz_amount_total, 0)        AS new_biz_amount_total,
  SAFE_DIVIDE(COALESCE(p.new_biz_revenue_won, d.new_biz_amount_won), NULLIF(p.spend, 0)) AS new_biz_roas,
  SAFE_DIVIDE(p.leads_qualified, NULLIF(p.leads_qualified + p.leads_disqualified, 0))    AS qual_rate,
  SAFE_DIVIDE(p.leads_disqualified, NULLIF(p.leads_qualified + p.leads_disqualified, 0)) AS disq_rate,
  SAFE_DIVIDE(p.spend, NULLIF(p.leads, 0))           AS CPL,
  SAFE_DIVIDE(p.spend, NULLIF(p.leads_qualified, 0)) AS CPQL,
  'wide_keywords'                            AS match_method,
  'wide_keywords'                            AS data_source
FROM platform p
LEFT JOIN deals d
  ON p.date = d.date
  AND p.channel = d.channel
  AND LOWER(TRIM(p.utm_campaign)) = d.utm_campaign
  AND LOWER(TRIM(p.utm_term))     = d.utm_term
"""


def create_views():
    # v_adset_performance and v_ad_performance are now in materialize_heavy_views()
    # (collectors/views.py). utm_paid_attribution_daily was dropped 2026-06-15.
    client = get_client()
    for sql, name in [
        (V_KEYWORD_PERFORMANCE_SQL,           "v_keyword_performance"),
    ]:
        table_id = f"{PROJECT_ID}.{DATASET}.{name}"
        try:
            t = client.get_table(table_id)
            if t.table_type == "TABLE":
                # Previously materialized as a TABLE — drop first so
                # CREATE OR REPLACE VIEW can proceed cleanly.
                client.delete_table(table_id)
                print(f"[INFO] Dropped materialised table {name} before recreating as view.")
        except Exception:
            pass  # table doesn't exist yet — fine
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
