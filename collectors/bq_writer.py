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
    "adsets_daily":        ADSETS_DAILY_SCHEMA,
    "ads_daily":           ADS_DAILY_SCHEMA,
    "keywords_daily":      KEYWORDS_DAILY_SCHEMA,
    "agent_activity_log":  ACTIVITY_LOG_SCHEMA,
    "qa_gate_events":      QA_GATE_EVENTS_SCHEMA,
}


# ---------- BOOTSTRAP ----------

TABLE_CLUSTERS = {
    "campaigns_daily":     ["channel", "campaign_id"],
    "adsets_daily":        ["channel", "campaign_id", "adset_id"],
    "ads_daily":           ["channel", "campaign_id", "ad_id"],
    "keywords_daily":      ["channel", "campaign_id", "adgroup_id"],
    "agent_activity_log":  ["role", "status"],
    "qa_gate_events":      ["surface", "check_name"],
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
    _TS_PARTITIONED = {"agent_activity_log", "qa_gate_events"}

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
    if table_name in {"agent_activity_log", "qa_gate_events"}:
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
    # Skipped for the gate's own logging table to avoid recursion.
    if table_name != "qa_gate_events":
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
-- Adset/AdGroup level: spend + impressions + clicks from adsets_daily (platform),
-- leads/SQLs/disqual from HubSpot, deals/closed-won/ROAS from hubspot_deals_daily.
-- Falls back to UTM-proxy spend when adsets_daily has no rows yet.
-- Ad set / Ad group level performance.
-- Spend/impressions/clicks come from adsets_daily (real platform data via Airbyte).
-- Leads/SQLs come from utm_paid_attribution_daily (HubSpot utm_audience match).
-- Falls back to UTM-proxy spend when adsets_daily has no row for that adset.
WITH platform AS (
  -- One row per DISTINCT adset_id (not per name). Same-name different-ID adsets
  -- stay separate so each keeps its own adset_id + spend. Grouping by adset_id
  -- was added 2026-06-09 alongside the v_ad_performance fix — ANY_VALUE(adset_id)
  -- on a name grain silently dropped one ID and merged spend across distinct
  -- adsets (63 spend-bearing groups, $4.8k/30d).
  SELECT date, channel, campaign_name,
    -- utm_audience column holds the resolved custom-param value (e.g. _adgroup for
    -- Microsoft, adset_name for Meta/TikTok/Snap). Fall back to adset_name so
    -- channels that don't populate utm_audience still show up.
    ANY_VALUE(COALESCE(utm_audience, adset_name)) AS utm_audience,
    ANY_VALUE(adset_name) AS adset_name,
    ANY_VALUE(status) AS status,
    adset_id              AS platform_adset_id,
    ANY_VALUE(campaign_id) AS platform_campaign_id,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM `{PROJECT_ID}.{DATASET}.adsets_daily`
  GROUP BY date, channel, campaign_name, adset_id
),
-- LEADS source — AUTHORITATIVE at (date, channel, utm_campaign, utm_audience)
-- grain from utm_paid_attribution_daily. 2026-06-09: removed the adset-ID and
-- campaign-ID re-joins to hubspot_leads_module_daily (Strategy C/D). They
-- double-counted by spraying campaign-level leads across adsets ON TOP OF the
-- audience-grain leads. The upstream view is the single source of truth.
hubspot AS (
  SELECT date, channel, utm_campaign, utm_audience,
    ANY_VALUE(utm_source) AS utm_source,
    SUM(leads) AS leads,
    SUM(leads_qualified) AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_audience IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
-- Deals: ID-matched bucket (Snap/Meta/TikTok Instantform — survives adset renames)
deals_by_id AS (
  SELECT date, qoyod_source AS channel,
    deal_adgroup_id_sync AS adset_id,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_lost  ELSE 0 END) AS new_biz_deals_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_open  ELSE 0 END) AS new_biz_deals_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_total ELSE 0 END) AS new_biz_deals_total,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_open ELSE 0 END) AS new_biz_amount_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_total ELSE 0 END) AS new_biz_amount_total,
    -- All pipelines
    SUM(deals_won)    AS all_deals_won,
    SUM(amount_won)   AS all_revenue_won,
    SUM(amount_lost)  AS all_amount_lost,
    SUM(amount_open)  AS all_amount_open,
    SUM(amount_total) AS all_amount_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_adgroup_id_sync IS NOT NULL
  GROUP BY 1, 2, 3
),
-- Deals: name-matched bucket (Google/Bing/LinkedIn website forms — no sync ID)
deals_by_name AS (
  SELECT date, qoyod_source AS channel, deal_utm_campaign AS utm_campaign,
    deal_utm_audience AS utm_audience,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_lost  ELSE 0 END) AS new_biz_deals_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_open  ELSE 0 END) AS new_biz_deals_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_total ELSE 0 END) AS new_biz_deals_total,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_open ELSE 0 END) AS new_biz_amount_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_total ELSE 0 END) AS new_biz_amount_total,
    -- All pipelines
    SUM(deals_won)    AS all_deals_won,
    SUM(amount_won)   AS all_revenue_won,
    SUM(amount_lost)  AS all_amount_lost,
    SUM(amount_open)  AS all_amount_open,
    SUM(amount_total) AS all_amount_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_adgroup_id_sync IS NULL
    AND deal_utm_audience IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
utmproxy AS (
  SELECT date, channel, utm_campaign, utm_audience, SUM(spend) AS spend
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_audience IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
joined AS (
  SELECT
    COALESCE(p.date, h.date)                AS date,
    COALESCE(p.channel, h.channel)          AS channel,
    COALESCE(p.campaign_name, h.utm_campaign) AS utm_campaign,
    COALESCE(p.utm_audience, h.utm_audience)  AS utm_audience,
    p.adset_name                              AS adset_name,
    p.status                                  AS status,
    p.platform_campaign_id                    AS campaign_id,
    p.platform_adset_id                       AS adset_id,
    COALESCE(p.spend, u.spend) AS spend, p.impressions, p.clicks,
    p.date AS p_date,
    h.utm_campaign AS h_utm_campaign,
    h.utm_source,
    h.leads              AS leads_raw,
    h.leads_qualified    AS leads_qualified_raw,
    h.leads_disqualified AS leads_disqualified_raw,
    -- dedup key = the upstream bucket's OWN identity (date, channel, utm_campaign,
    -- utm_audience). Constant per upstream row → counted exactly once even when a
    -- bucket fans across multiple platform adset_id rows. No ID fallbacks.
    CASE
      WHEN h.leads IS NOT NULL THEN CONCAT('AB|', CAST(IFNULL(h.date, DATE '1900-01-01') AS STRING), '|', IFNULL(h.channel,''),
                                                '|', IFNULL(h.utm_campaign,''), '|', IFNULL(h.utm_audience,''))
      ELSE NULL
    END                                        AS lead_src_key,
    di.new_biz_deals_won  AS di_deals_won,  di.new_biz_deals_lost  AS di_deals_lost,
    di.new_biz_deals_open AS di_deals_open, di.new_biz_deals_total AS di_deals_total,
    di.new_biz_revenue_won AS di_rev_won,   di.new_biz_amount_lost AS di_amt_lost,
    di.new_biz_amount_open AS di_amt_open,  di.new_biz_amount_total AS di_amt_total,
    di.all_revenue_won AS di_all_rev_won,   di.all_amount_lost AS di_all_amt_lost,
    di.all_amount_open AS di_all_amt_open,  di.all_amount_total AS di_all_amt_total,
    di.adset_id AS di_adset_id,
    dn.new_biz_deals_won  AS dn_deals_won,  dn.new_biz_deals_lost  AS dn_deals_lost,
    dn.new_biz_deals_open AS dn_deals_open, dn.new_biz_deals_total AS dn_deals_total,
    dn.new_biz_revenue_won AS dn_rev_won,   dn.new_biz_amount_lost AS dn_amt_lost,
    dn.new_biz_amount_open AS dn_amt_open,  dn.new_biz_amount_total AS dn_amt_total,
    dn.all_revenue_won AS dn_all_rev_won,   dn.all_amount_lost AS dn_all_amt_lost,
    dn.all_amount_open AS dn_all_amt_open,  dn.all_amount_total AS dn_all_amt_total,
    dn.utm_campaign AS dn_utm_campaign, dn.utm_audience AS dn_utm_audience
  FROM platform p
  FULL OUTER JOIN hubspot h
    ON p.date = h.date AND p.channel = h.channel
    AND LOWER(TRIM(p.utm_audience)) = LOWER(TRIM(h.utm_audience))
  LEFT JOIN utmproxy u
    ON h.date = u.date AND h.channel = u.channel AND h.utm_audience = u.utm_audience
  -- Deals: ID-match (Snap/Meta/TikTok Instantform — survives adset renames)
  LEFT JOIN deals_by_id di
    ON p.date = di.date AND p.channel = di.channel
    AND p.platform_adset_id = di.adset_id
  -- Deals: name-match (Google/Bing/LinkedIn website forms — no sync ID)
  LEFT JOIN deals_by_name dn
    ON COALESCE(p.date, h.date) = dn.date
    AND COALESCE(p.channel, h.channel) = dn.channel
    AND LOWER(TRIM(COALESCE(p.campaign_name, h.utm_campaign))) = LOWER(TRIM(dn.utm_campaign))
    AND LOWER(TRIM(COALESCE(p.utm_audience, h.utm_audience))) = LOWER(TRIM(dn.utm_audience))
)
SELECT
  date, channel,
  CASE channel
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'meta'          THEN 'Meta Ads'
    WHEN 'snapchat'      THEN 'Snapchat Ads'
    WHEN 'tiktok'        THEN 'TikTok Ads'
    WHEN 'linkedin'      THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    ELSE channel
  END                                      AS channel_name,
  utm_campaign, utm_audience,
  COALESCE(adset_name, utm_audience) AS adset_name,
  utm_source,
  status,
  campaign_id, adset_id,
  -- Fan-out guard: each platform row already carries its own adset_id's spend.
  -- The utm_audience->hubspot join still fans a platform row across multiple
  -- hubspot rows, so count platform metrics ONCE per adset_id (per day/channel).
  IF(ROW_NUMBER() OVER (PARTITION BY date, channel,
       COALESCE(CAST(adset_id AS STRING), LOWER(TRIM(utm_audience)))
     ORDER BY COALESCE(h_utm_campaign,'')) = 1, COALESCE(spend, 0), 0)  AS spend,
  IF(ROW_NUMBER() OVER (PARTITION BY date, channel,
       COALESCE(CAST(adset_id AS STRING), LOWER(TRIM(utm_audience)))
     ORDER BY COALESCE(h_utm_campaign,'')) = 1, COALESCE(impressions, 0), 0)     AS impressions,
  IF(ROW_NUMBER() OVER (PARTITION BY date, channel,
       COALESCE(CAST(adset_id AS STRING), LOWER(TRIM(utm_audience)))
     ORDER BY COALESCE(h_utm_campaign,'')) = 1, COALESCE(clicks, 0), 0)          AS clicks,
  -- LEADS fan-out guard: count each HubSpot source row's leads exactly ONCE.
  IF(lead_src_key IS NULL OR
     ROW_NUMBER() OVER (PARTITION BY lead_src_key ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1,
     COALESCE(leads_raw, 0), 0)                AS leads,
  IF(lead_src_key IS NULL OR
     ROW_NUMBER() OVER (PARTITION BY lead_src_key ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1,
     COALESCE(leads_qualified_raw, 0), 0)      AS leads_qualified,
  IF(lead_src_key IS NULL OR
     ROW_NUMBER() OVER (PARTITION BY lead_src_key ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1,
     COALESCE(leads_disqualified_raw, 0), 0)   AS leads_disqualified,
  -- DEALS fan-out guard: each deal bucket counted once per its own grain.
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_deals_won,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_deals_won,0), 0) AS new_biz_deals_won,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_deals_lost,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_deals_lost,0), 0) AS new_biz_deals_lost,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_deals_open,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_deals_open,0), 0) AS new_biz_deals_open,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_deals_total,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_deals_total,0), 0) AS new_biz_deals_total,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_rev_won,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_rev_won,0), 0) AS new_biz_revenue_won,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_amt_lost,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_amt_lost,0), 0) AS new_biz_amount_lost,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_amt_open,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_amt_open,0), 0) AS new_biz_amount_open,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_amt_total,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_amt_total,0), 0) AS new_biz_amount_total,
  -- Ratios + cost: use RAW lead values so per-row metrics stay correct
  SAFE_DIVIDE(leads_qualified_raw, NULLIF(COALESCE(leads_qualified_raw,0) + COALESCE(leads_disqualified_raw,0), 0)) AS qual_rate,
  SAFE_DIVIDE(leads_disqualified_raw, NULLIF(COALESCE(leads_qualified_raw,0) + COALESCE(leads_disqualified_raw,0), 0)) AS disq_rate,
  SAFE_DIVIDE(spend, NULLIF(leads_raw, 0))           AS CPL,
  SAFE_DIVIDE(spend, NULLIF(leads_qualified_raw, 0)) AS CPQL,
  SAFE_DIVIDE(IFNULL(di_rev_won,0) + IFNULL(dn_rev_won,0), NULLIF(spend, 0)) AS new_biz_roas,
  -- All-pipeline amounts (fan-out guard identical to new_biz pattern above)
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_all_rev_won,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_all_rev_won,0), 0) AS revenue_won,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_all_amt_lost,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_all_amt_lost,0), 0) AS amount_lost,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_all_amt_open,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_all_amt_open,0), 0) AS amount_open,
  IF(di_adset_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_adset_id ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(di_all_amt_total,0), 0)
    + IF(dn_utm_audience IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_audience ORDER BY COALESCE(CAST(adset_id AS STRING),'')) = 1, IFNULL(dn_all_amt_total,0), 0) AS amount_total,
  SAFE_DIVIDE(IFNULL(di_all_rev_won,0) + IFNULL(dn_all_rev_won,0), NULLIF(spend, 0)) AS roas,
  IF(p_date IS NOT NULL, 'platform', 'utm_proxy')                         AS data_source
FROM joined
"""


V_AD_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_ad_performance` AS
-- Ad/Creative level: spend+impressions+clicks from ads_daily,
-- leads/SQLs/disqual from HubSpot, deals/closed-won/ROAS from deals.
WITH platform AS (
  -- One row per DISTINCT ad_id (not per name). Same-name different-ID ads stay
  -- separate so each keeps its own ad_id + spend. Grouping by ad_id was added
  -- 2026-06-09 after we found 370 spend-bearing groups ($7.8k/30d) where two
  -- ads shared a utm_content/ad_name and ANY_VALUE(ad_id) silently dropped one
  -- ID and merged the spend. utm_content is still carried (for the HubSpot join)
  -- but it is no longer part of the grain — ad_id is.
  SELECT date, channel, campaign_name, adset_name,
    -- utm_content column holds the resolved _adname custom-param value.
    -- Fall back to ad_name for channels without custom params.
    ANY_VALUE(COALESCE(utm_content, ad_name)) AS utm_content,
    ANY_VALUE(ad_name) AS ad_name,
    ad_id                  AS platform_ad_id,
    ANY_VALUE(adset_id)    AS platform_adset_id,
    ANY_VALUE(campaign_id) AS platform_campaign_id,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
    -- creative_type + status: one value per ad; MAX picks the non-null value across days
    MAX(creative_type) AS creative_type,
    MAX(status)        AS status
  FROM `{PROJECT_ID}.{DATASET}.ads_daily`
  GROUP BY date, channel, campaign_name, adset_name, ad_id
),
-- LEADS source — AUTHORITATIVE at (date, channel, utm_campaign, utm_audience,
-- utm_content) grain. utm_paid_attribution_daily already resolves HubSpot leads
-- to this exact grain (one row per bucket, no fan-out). 2026-06-09: this view no
-- longer re-joins hubspot_leads_module_daily by ad_id / campaign_id sync. Those
-- fallback (Strategy C/D) re-joins double-counted — they sprayed campaign-level
-- leads across every ad in the campaign ON TOP OF the content-grain leads
-- (snapchat 172 truth -> 316 in the view). The upstream view is the single source.
hubspot AS (
  SELECT date, channel, utm_campaign, utm_audience, utm_content,
    ANY_VALUE(utm_source) AS utm_source,
    SUM(leads) AS leads,
    SUM(leads_qualified) AS leads_qualified,
    SUM(leads_disqualified) AS leads_disqualified
  FROM `{PROJECT_ID}.{DATASET}.utm_paid_attribution_daily`
  WHERE utm_campaign != '__no_utm__' AND utm_content IS NOT NULL
  GROUP BY 1, 2, 3, 4, 5
),
-- Deals: ID-matched bucket (survives ad renames)
deals_by_id AS (
  SELECT date, qoyod_source AS channel,
    deal_ad_id_sync AS ad_id,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_lost  ELSE 0 END) AS new_biz_deals_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_open  ELSE 0 END) AS new_biz_deals_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_total ELSE 0 END) AS new_biz_deals_total,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_open ELSE 0 END) AS new_biz_amount_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_total ELSE 0 END) AS new_biz_amount_total,
    -- All pipelines
    SUM(deals_won)    AS all_deals_won,
    SUM(amount_won)   AS all_revenue_won,
    SUM(amount_lost)  AS all_amount_lost,
    SUM(amount_open)  AS all_amount_open,
    SUM(amount_total) AS all_amount_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_ad_id_sync IS NOT NULL
  GROUP BY 1, 2, 3
),
-- Deals: name-matched bucket (no sync ID)
deals_by_name AS (
  SELECT date, qoyod_source AS channel,
    deal_utm_campaign AS utm_campaign,
    deal_utm_content AS utm_content,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_lost  ELSE 0 END) AS new_biz_deals_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_open  ELSE 0 END) AS new_biz_deals_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_total ELSE 0 END) AS new_biz_deals_total,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_open ELSE 0 END) AS new_biz_amount_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_total ELSE 0 END) AS new_biz_amount_total,
    -- All pipelines
    SUM(deals_won)    AS all_deals_won,
    SUM(amount_won)   AS all_revenue_won,
    SUM(amount_lost)  AS all_amount_lost,
    SUM(amount_open)  AS all_amount_open,
    SUM(amount_total) AS all_amount_total
  FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
  WHERE deal_ad_id_sync IS NULL
    AND deal_utm_content IS NOT NULL
  GROUP BY 1, 2, 3, 4
),
joined AS (
  SELECT
    COALESCE(p.date, h.date)                  AS date,
    COALESCE(p.channel, h.channel)            AS channel,
    COALESCE(p.campaign_name, h.utm_campaign) AS utm_campaign,
    COALESCE(p.adset_name, h.utm_audience)    AS utm_audience,
    COALESCE(p.utm_content, h.utm_content)    AS utm_content,
    p.ad_name                                 AS ad_name,
    p.platform_campaign_id                    AS campaign_id,
    p.platform_adset_id                       AS adset_id,
    p.platform_ad_id                          AS ad_id,
    p.spend, p.impressions, p.clicks, p.creative_type, p.status,
    p.date AS p_date,
    h.utm_campaign AS h_utm_campaign,
    h.utm_source,
    -- raw leads come straight from the authoritative upstream content-grain bucket
    h.leads              AS leads_raw,
    h.leads_qualified    AS leads_qualified_raw,
    h.leads_disqualified AS leads_disqualified_raw,
    -- dedup key = the upstream bucket's OWN identity (date, channel, utm_campaign,
    -- utm_audience, utm_content). Constant per upstream row, so a bucket that fans
    -- across multiple platform ad_id rows (same utm_content, different campaign/
    -- audience) is counted EXACTLY ONCE. No ID-based fallbacks anymore.
    CASE
      WHEN h.leads IS NOT NULL THEN CONCAT('AB|', CAST(IFNULL(h.date, DATE '1900-01-01') AS STRING), '|', IFNULL(h.channel,''),
                                                '|', IFNULL(h.utm_campaign,''), '|', IFNULL(h.utm_audience,''), '|', IFNULL(h.utm_content,''))
      ELSE NULL
    END                                        AS lead_src_key,
    -- deals: ID + name buckets
    di.new_biz_deals_won  AS di_deals_won,  di.new_biz_deals_lost  AS di_deals_lost,
    di.new_biz_deals_open AS di_deals_open, di.new_biz_deals_total AS di_deals_total,
    di.new_biz_revenue_won AS di_rev_won,   di.new_biz_amount_lost AS di_amt_lost,
    di.new_biz_amount_open AS di_amt_open,  di.new_biz_amount_total AS di_amt_total,
    di.all_revenue_won AS di_all_rev_won,   di.all_amount_lost AS di_all_amt_lost,
    di.all_amount_open AS di_all_amt_open,  di.all_amount_total AS di_all_amt_total,
    di.ad_id AS di_ad_id,
    dn.new_biz_deals_won  AS dn_deals_won,  dn.new_biz_deals_lost  AS dn_deals_lost,
    dn.new_biz_deals_open AS dn_deals_open, dn.new_biz_deals_total AS dn_deals_total,
    dn.new_biz_revenue_won AS dn_rev_won,   dn.new_biz_amount_lost AS dn_amt_lost,
    dn.new_biz_amount_open AS dn_amt_open,  dn.new_biz_amount_total AS dn_amt_total,
    dn.all_revenue_won AS dn_all_rev_won,   dn.all_amount_lost AS dn_all_amt_lost,
    dn.all_amount_open AS dn_all_amt_open,  dn.all_amount_total AS dn_all_amt_total,
    dn.utm_campaign AS dn_utm_campaign, dn.utm_content AS dn_utm_content
  FROM platform p
  FULL OUTER JOIN hubspot h
    ON p.date = h.date AND p.channel = h.channel
    AND LOWER(TRIM(p.utm_content)) = LOWER(TRIM(h.utm_content))
  -- Deals: ID-match (survives ad renames)
  LEFT JOIN deals_by_id di
    ON p.date = di.date AND p.channel = di.channel
    AND p.platform_ad_id = di.ad_id
  -- Deals: name-match (no sync ID)
  LEFT JOIN deals_by_name dn
    ON COALESCE(p.date, h.date) = dn.date
    AND COALESCE(p.channel, h.channel) = dn.channel
    AND LOWER(TRIM(COALESCE(p.campaign_name, h.utm_campaign))) = LOWER(TRIM(dn.utm_campaign))
    AND LOWER(TRIM(COALESCE(p.utm_content, h.utm_content))) = LOWER(TRIM(dn.utm_content))
)
SELECT
  date, channel,
  CASE channel
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'meta'          THEN 'Meta Ads'
    WHEN 'snapchat'      THEN 'Snapchat Ads'
    WHEN 'tiktok'        THEN 'TikTok Ads'
    WHEN 'linkedin'      THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    ELSE channel
  END                                        AS channel_name,
  utm_campaign, utm_audience, utm_content,
  COALESCE(ad_name, utm_content) AS ad_name,
  utm_source,
  campaign_id, adset_id, ad_id,
  -- spend/impr/clicks: each platform row already carries its own ad_id's spend.
  -- The utm_content->hubspot join still fans a platform row across multiple
  -- hubspot rows, so count platform metrics ONCE per ad_id (per day/channel).
  IF(ROW_NUMBER() OVER (PARTITION BY date, channel,
       COALESCE(CAST(ad_id AS STRING), LOWER(TRIM(utm_content)))
     ORDER BY COALESCE(h_utm_campaign,'')) = 1, spend, 0)               AS spend,
  IF(ROW_NUMBER() OVER (PARTITION BY date, channel,
       COALESCE(CAST(ad_id AS STRING), LOWER(TRIM(utm_content)))
     ORDER BY COALESCE(h_utm_campaign,'')) = 1, COALESCE(impressions,0), 0) AS impressions,
  IF(ROW_NUMBER() OVER (PARTITION BY date, channel,
       COALESCE(CAST(ad_id AS STRING), LOWER(TRIM(utm_content)))
     ORDER BY COALESCE(h_utm_campaign,'')) = 1, COALESCE(clicks,0), 0)      AS clicks,
  -- LEADS fan-out guard: a single HubSpot source row (lead_src_key) can now match
  -- MULTIPLE platform ad_id rows sharing the same utm_content. Count each HubSpot
  -- source row's leads exactly ONCE, on the first platform row it lands on.
  IF(lead_src_key IS NULL OR
     ROW_NUMBER() OVER (PARTITION BY lead_src_key ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1,
     COALESCE(leads_raw, 0), 0)                AS leads,
  IF(lead_src_key IS NULL OR
     ROW_NUMBER() OVER (PARTITION BY lead_src_key ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1,
     COALESCE(leads_qualified_raw, 0), 0)      AS leads_qualified,
  IF(lead_src_key IS NULL OR
     ROW_NUMBER() OVER (PARTITION BY lead_src_key ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1,
     COALESCE(leads_disqualified_raw, 0), 0)   AS leads_disqualified,
  -- DEALS fan-out guard: each deal source bucket counted once per its own grain.
  -- ID bucket grain = (date, channel, ad_id); name bucket grain = (date, channel, utm_campaign, utm_content).
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_deals_won,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_deals_won,0), 0) AS new_biz_deals_won,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_deals_lost,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_deals_lost,0), 0) AS new_biz_deals_lost,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_deals_open,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_deals_open,0), 0) AS new_biz_deals_open,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_deals_total,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_deals_total,0), 0) AS new_biz_deals_total,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_rev_won,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_rev_won,0), 0) AS new_biz_revenue_won,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_amt_lost,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_amt_lost,0), 0) AS new_biz_amount_lost,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_amt_open,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_amt_open,0), 0) AS new_biz_amount_open,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_amt_total,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_amt_total,0), 0) AS new_biz_amount_total,
  -- Ratios + cost: use the RAW (un-zeroed) lead values so per-row CPL/CPQL stay
  -- correct on every ad row; only the SUM-able lead columns above are deduped.
  SAFE_DIVIDE(leads_qualified_raw, NULLIF(COALESCE(leads_qualified_raw,0) + COALESCE(leads_disqualified_raw,0), 0)) AS qual_rate,
  SAFE_DIVIDE(leads_disqualified_raw, NULLIF(COALESCE(leads_qualified_raw,0) + COALESCE(leads_disqualified_raw,0), 0)) AS disq_rate,
  SAFE_DIVIDE(spend, NULLIF(leads_raw, 0))           AS CPL,
  SAFE_DIVIDE(spend, NULLIF(leads_qualified_raw, 0)) AS CPQL,
  SAFE_DIVIDE(IFNULL(di_rev_won,0) + IFNULL(dn_rev_won,0), NULLIF(spend, 0)) AS new_biz_roas,
  -- All-pipeline amounts (fan-out guard identical to new_biz pattern above)
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_all_rev_won,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_all_rev_won,0), 0) AS revenue_won,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_all_amt_lost,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_all_amt_lost,0), 0) AS amount_lost,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_all_amt_open,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_all_amt_open,0), 0) AS amount_open,
  IF(di_ad_id IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, di_ad_id ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(di_all_amt_total,0), 0)
    + IF(dn_utm_content IS NULL OR ROW_NUMBER() OVER (PARTITION BY date, channel, dn_utm_campaign, dn_utm_content ORDER BY COALESCE(CAST(ad_id AS STRING),'')) = 1, IFNULL(dn_all_amt_total,0), 0) AS amount_total,
  SAFE_DIVIDE(IFNULL(di_all_rev_won,0) + IFNULL(dn_all_rev_won,0), NULLIF(spend, 0)) AS roas,
  creative_type, status,
  IF(p_date IS NOT NULL, 'platform', 'utm_proxy')            AS data_source
FROM joined
"""


V_KEYWORD_PERFORMANCE_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.v_keyword_performance` AS
-- Keyword level: Google Ads + Microsoft Ads.
-- Spend/impressions/clicks/QS from keywords_daily; leads/deals from HubSpot.
WITH platform AS (
  SELECT date, channel, campaign_name, adgroup_name, keyword_text AS utm_term,
    match_type,
    ANY_VALUE(status) AS status,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
    SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions),0)) AS ctr,
    AVG(quality_score) AS quality_score
  FROM `{PROJECT_ID}.{DATASET}.keywords_daily`
  GROUP BY 1, 2, 3, 4, 5, 6
),
hubspot AS (
  SELECT date, channel, utm_campaign, utm_audience, utm_term,
    ANY_VALUE(utm_source) AS utm_source,
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
    -- All pipelines
    SUM(deals_total) AS deals,
    SUM(deals_won)   AS deals_won,
    SUM(amount_won)  AS revenue_won,
    SUM(amount_lost) AS amount_lost,
    SUM(amount_open) AS amount_open,
    SUM(amount_total) AS amount_total,
    -- New business pipelines (Sales Pipeline, Bookkeeping, Qflavours)
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_open ELSE 0 END) AS new_biz_amount_open,
    SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
             THEN amount_total ELSE 0 END) AS new_biz_amount_total
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
  COALESCE(p.adgroup_name, h.utm_audience)   AS adgroup_name,
  COALESCE(p.utm_term, h.utm_term)           AS utm_term,
  h.utm_source,
  p.status,
  p.match_type,
  p.quality_score,
  COALESCE(p.spend, u.spend, 0)              AS spend,
  COALESCE(p.impressions, 0)                 AS impressions,
  COALESCE(p.clicks, 0)                      AS clicks,
  COALESCE(p.ctr, 0)                         AS ctr,
  COALESCE(h.leads, 0)                       AS leads,
  COALESCE(h.leads_qualified, 0)             AS leads_qualified,
  COALESCE(h.leads_disqualified, 0)          AS leads_disqualified,
  -- All-pipeline deal amounts
  COALESCE(d.deals, 0)                       AS deals,
  COALESCE(d.deals_won, 0)                   AS deals_won,
  COALESCE(d.revenue_won, 0)                 AS revenue_won,
  COALESCE(d.amount_lost, 0)                 AS amount_lost,
  COALESCE(d.amount_open, 0)                 AS amount_open,
  COALESCE(d.amount_total, 0)                AS amount_total,
  SAFE_DIVIDE(d.revenue_won, NULLIF(COALESCE(p.spend, u.spend), 0))     AS roas,
  -- New business deal amounts (Sales Pipeline + Bookkeeping + Qflavours)
  COALESCE(d.new_biz_deals_won, 0)           AS new_biz_deals_won,
  COALESCE(d.new_biz_revenue_won, 0)         AS new_biz_revenue_won,
  COALESCE(d.new_biz_amount_lost, 0)         AS new_biz_amount_lost,
  COALESCE(d.new_biz_amount_open, 0)         AS new_biz_amount_open,
  COALESCE(d.new_biz_amount_total, 0)        AS new_biz_amount_total,
  SAFE_DIVIDE(d.new_biz_revenue_won, NULLIF(COALESCE(p.spend, u.spend), 0)) AS new_biz_roas,
  SAFE_DIVIDE(h.leads_qualified, NULLIF(h.leads_qualified + h.leads_disqualified, 0))    AS qual_rate,
  SAFE_DIVIDE(h.leads_disqualified, NULLIF(h.leads_qualified + h.leads_disqualified, 0)) AS disq_rate,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads, 0))           AS CPL,
  SAFE_DIVIDE(COALESCE(p.spend, u.spend), NULLIF(h.leads_qualified, 0)) AS CPQL,
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
    # NOTE: heavy views (utm_paid_attribution_daily, paid_channel_campaign_daily,
    # channel_roas_daily, paid_channel_daily, v_adset_performance, v_ad_performance)
    # are materialized via materialize_heavy_views() in collectors/views.py — not here.
    # This function handles lightweight views only. Dropped views removed 2026-06-09.
    client = get_client()
    for sql, name in [
        (UTM_PAID_ATTRIBUTION_VIEW_SQL,       "utm_paid_attribution_daily"),
        (V_ADSET_PERFORMANCE_SQL,             "v_adset_performance"),
        (V_AD_PERFORMANCE_SQL,                "v_ad_performance"),
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
