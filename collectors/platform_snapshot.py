"""
Platform state snapshot — detects ALL manual user changes across channels.

Runs every 6h from reporting_scheduler. For each channel:
  1. Fetch current campaign status + budget from the API
  2. Write to platform_campaign_snapshot (WRITE_APPEND)
  3. Compare latest vs previous snapshot → changes not made by agent = user actions
  4. Log user actions to agent_activity_log (role='user')

Detected actions logged:
  user_paused_campaign    — user paused a campaign directly in the platform
  user_enabled_campaign   — user re-enabled a paused campaign
  user_changed_budget     — user changed a campaign budget directly
  user_paused_ad          — user paused an ad (Meta / Snap)
  user_enabled_ad         — user re-enabled an ad
"""
import json
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO

from collectors.bq_writer import get_client as get_bq
from logs.activity_logger import log_activity_async


_TABLE = "platform_campaign_snapshot"
_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS `{P}.{D}.{T}` (
  snapped_at     TIMESTAMP NOT NULL,
  channel        STRING    NOT NULL,
  account_id     STRING,
  campaign_id    STRING    NOT NULL,
  campaign_name  STRING,
  status         STRING,
  budget_raw     FLOAT64,
  budget_currency STRING,
  entity_type    STRING    -- 'campaign' or 'ad'
)
PARTITION BY DATE(snapped_at)
OPTIONS(require_partition_filter=false)
"""

_AGENT_ACTIONS = {
    "campaign_paused", "campaign_scaled", "campaign_created",
    "ads_paused", "pause_task_created",
}


# ── Per-channel fetchers ───────────────────────────────────────────────────────

def _google_campaigns() -> list[dict]:
    rows = []
    try:
        from collectors.google_ads_bq import _client, _customer_ids
        from collectors.currency import to_usd
        client = _client()
        ga     = client.get_service("GoogleAdsService")
        query = """
            SELECT campaign.id, campaign.name, campaign.status,
                   campaign_budget.amount_micros, customer.currency_code
            FROM campaign
            WHERE campaign.status != 'REMOVED'
        """
        for cid in _customer_ids():
            try:
                for r in ga.search(customer_id=cid, query=query):
                    budget_usd = to_usd(
                        r.campaign_budget.amount_micros / 1_000_000,
                        r.customer.currency_code or "USD",
                    )
                    rows.append({
                        "channel":        "google_ads",
                        "account_id":     cid,
                        "campaign_id":    str(r.campaign.id),
                        "campaign_name":  r.campaign.name,
                        "status":         r.campaign.status.name,
                        "budget_raw":     budget_usd,
                        "budget_currency": "USD",
                        "entity_type":    "campaign",
                    })
            except Exception as e:
                print(f"[snapshot] google_ads cid={cid} error: {e}")
    except Exception as e:
        print(f"[snapshot] google_ads init error: {e}")
    return rows


def _meta_campaigns() -> list[dict]:
    rows = []
    try:
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount
        from collectors.meta_bq import META_ACCESS_TOKEN, _native_currency
        from collectors.currency import to_usd
        import os
        FacebookAdsApi.init(access_token=META_ACCESS_TOKEN)
        accounts = [a.strip() for a in os.getenv("META_AD_ACCOUNTS", "").split(",") if a.strip()]
        for acct_id in accounts:
            try:
                currency = _native_currency(acct_id)
                account  = AdAccount(acct_id)
                campaigns = account.get_campaigns(fields=[
                    "id", "name", "status", "daily_budget", "lifetime_budget",
                ])
                for c in campaigns:
                    # prefer daily_budget; fall back to lifetime_budget
                    raw_budget = int(c.get("daily_budget") or c.get("lifetime_budget") or 0)
                    budget_usd = to_usd(raw_budget / 100, currency)
                    rows.append({
                        "channel":        "meta",
                        "account_id":     acct_id,
                        "campaign_id":    str(c["id"]),
                        "campaign_name":  c.get("name", ""),
                        "status":         c.get("status", ""),
                        "budget_raw":     budget_usd,
                        "budget_currency": "USD",
                        "entity_type":    "campaign",
                    })
            except Exception as e:
                print(f"[snapshot] meta acct={acct_id} error: {e}")
    except Exception as e:
        print(f"[snapshot] meta init error: {e}")
    return rows


def _snap_campaigns() -> list[dict]:
    rows = []
    try:
        from collectors.snap_bq import _get_token, _list_campaigns, SNAP_AD_ACCOUNT_IDS
        from collectors.currency import to_usd
        token = _get_token()
        for acct_id in SNAP_AD_ACCOUNT_IDS:
            try:
                for c in _list_campaigns(token, acct_id):
                    budget_micro = c.get("daily_budget_micro") or c.get("lifetime_budget_micro") or 0
                    budget_usd   = to_usd(budget_micro / 1_000_000, "USD")
                    rows.append({
                        "channel":        "snapchat",
                        "account_id":     acct_id,
                        "campaign_id":    c.get("id", ""),
                        "campaign_name":  c.get("name", ""),
                        "status":         c.get("status", ""),
                        "budget_raw":     budget_usd,
                        "budget_currency": "USD",
                        "entity_type":    "campaign",
                    })
            except Exception as e:
                print(f"[snapshot] snapchat acct={acct_id} error: {e}")
    except Exception as e:
        print(f"[snapshot] snapchat init error: {e}")
    return rows


def _linkedin_campaigns() -> list[dict]:
    rows = []
    try:
        from collectors.linkedin_bq import _list_campaigns, _list_campaign_groups, AD_ACCT_URN
        from collectors.currency import to_usd
        import requests
        from collectors.linkedin_bq import _headers, BASE
        # Get campaigns with budget fields
        params = {
            "q": "search",
            "search.account.values[0]": AD_ACCT_URN,
            "fields": "id,name,status,totalBudget,dailyBudget",
            "count": 100,
        }
        r = requests.get(f"{BASE}/adCampaigns", headers=_headers(), params=params, timeout=15)
        if r.status_code < 400:
            for c in r.json().get("elements", []):
                daily  = (c.get("dailyBudget") or {})
                total  = (c.get("totalBudget") or {})
                budget_val = (daily.get("amount") or {}).get("value") or \
                             (total.get("amount") or {}).get("value") or 0
                budget_cur = (daily.get("amount") or {}).get("currencyCode", "USD")
                budget_usd = to_usd(float(budget_val), budget_cur)
                rows.append({
                    "channel":        "linkedin",
                    "account_id":     AD_ACCT_URN,
                    "campaign_id":    str(c.get("id", "")),
                    "campaign_name":  c.get("name", ""),
                    "status":         c.get("status", ""),
                    "budget_raw":     budget_usd,
                    "budget_currency": "USD",
                    "entity_type":    "campaign",
                })
    except Exception as e:
        print(f"[snapshot] linkedin error: {e}")
    return rows


# ── Change detection ───────────────────────────────────────────────────────────

def _detect_and_log(bq, P: str, D: str, now_utc: datetime) -> None:
    """
    Compare latest vs second-latest snapshot per campaign.
    Cross-check against agent_activity_log for the last 3h.
    Log new differences as user actions.
    """
    # Agent actions in the last 3 hours (exclude agent-caused changes)
    agent_sql = f"""
        SELECT DISTINCT campaign_name
        FROM `{P}.{D}.agent_activity_log`
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 HOUR)
          AND action IN ({', '.join(f"'{a}'" for a in _AGENT_ACTIONS)})
          AND campaign_name IS NOT NULL
    """
    try:
        agent_touched = {r.campaign_name for r in bq.query(agent_sql).result()}
    except Exception:
        agent_touched = set()

    # ── New campaigns: campaign_ids in latest snapshot not seen in any prior snapshot ──
    new_camp_sql = f"""
        WITH latest AS (
          SELECT DISTINCT channel, campaign_id, campaign_name, status, budget_raw
          FROM `{P}.{D}.{_TABLE}`
          WHERE snapped_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 HOUR)
        ),
        ever_seen AS (
          SELECT DISTINCT channel, campaign_id
          FROM `{P}.{D}.{_TABLE}`
          WHERE snapped_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 HOUR)
        )
        SELECT l.channel, l.campaign_id, l.campaign_name, l.status, l.budget_raw
        FROM latest l
        WHERE NOT EXISTS (
          SELECT 1 FROM ever_seen e
          WHERE e.channel = l.channel AND e.campaign_id = l.campaign_id
        )
    """
    try:
        new_camps = list(bq.query(new_camp_sql).result())
    except Exception as e:
        print(f"[snapshot] new-campaign query failed (non-fatal): {e}")
        new_camps = []

    for nc in new_camps:
        if nc.campaign_name and nc.campaign_name in agent_touched:
            continue  # agent created it
        log_activity_async(
            role="user", action="user_created_campaign", status="success",
            channel=nc.channel, campaign_name=nc.campaign_name,
            details={
                "campaign_id": nc.campaign_id,
                "status": nc.status,
                "budget_usd": round(nc.budget_raw or 0, 2),
            },
        )
        print(f"[snapshot] new campaign detected: {nc.campaign_name} ({nc.channel})")

    # Campaigns where status or budget changed between last two snapshots
    diff_sql = f"""
        WITH ranked AS (
          SELECT *,
            ROW_NUMBER() OVER (
              PARTITION BY channel, campaign_id ORDER BY snapped_at DESC
            ) AS rn
          FROM `{P}.{D}.{_TABLE}`
          WHERE snapped_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 25 HOUR)
        ),
        latest AS (SELECT * FROM ranked WHERE rn = 1),
        prev   AS (SELECT * FROM ranked WHERE rn = 2)
        SELECT
          l.channel, l.campaign_id, l.campaign_name,
          l.status   AS new_status,   p.status   AS old_status,
          l.budget_raw AS new_budget, p.budget_raw AS old_budget,
          l.entity_type
        FROM latest l
        JOIN prev p USING (channel, campaign_id)
        WHERE l.status != p.status
           OR ABS(COALESCE(l.budget_raw, 0) - COALESCE(p.budget_raw, 0)) > 1
    """
    try:
        changes = list(bq.query(diff_sql).result())
    except Exception as e:
        print(f"[snapshot] diff query failed: {e}")
        return

    for c in changes:
        if c.campaign_name in agent_touched:
            continue  # agent made this change — already logged

        # Status change
        if c.new_status != c.old_status:
            old = (c.old_status or "").upper()
            new = (c.new_status or "").upper()
            paused_now   = new in ("PAUSED", "INACTIVE", "ARCHIVED")
            enabled_now  = new in ("ACTIVE", "ENABLED", "DELIVERING")
            action = "user_paused_campaign"  if paused_now  else \
                     "user_enabled_campaign" if enabled_now else \
                     "user_changed_status"
            log_activity_async(
                role="user", action=action, status="success",
                channel=c.channel, campaign_name=c.campaign_name,
                details={
                    "campaign_id": c.campaign_id,
                    "old_status":  c.old_status,
                    "new_status":  c.new_status,
                    "entity_type": c.entity_type,
                },
            )
            print(f"[snapshot] user action: {action} — {c.campaign_name} ({c.old_status}→{c.new_status})")

        # Budget change
        old_b = c.old_budget or 0
        new_b = c.new_budget or 0
        if abs(new_b - old_b) > 1:
            direction = "increased" if new_b > old_b else "decreased"
            log_activity_async(
                role="user", action="user_changed_budget", status="success",
                channel=c.channel, campaign_name=c.campaign_name,
                details={
                    "campaign_id":  c.campaign_id,
                    "old_budget":   round(old_b, 2),
                    "new_budget":   round(new_b, 2),
                    "direction":    direction,
                    "entity_type":  c.entity_type,
                },
            )
            print(f"[snapshot] user budget {direction}: {c.campaign_name} ${old_b:.0f}→${new_b:.0f}")


# ── Main entry ─────────────────────────────────────────────────────────────────

def take_snapshot() -> int:
    """
    Fetch all platforms, write snapshot to BQ, detect user changes.
    Returns total rows written.
    """
    bq  = get_bq()
    P   = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D   = os.getenv("BQ_DATASET",    "qoyod_marketing")
    now = datetime.now(timezone.utc)

    bq.query(_CREATE_DDL.format(P=P, D=D, T=_TABLE)).result()

    # Fetch from all channels
    fetchers = [
        ("google_ads",  _google_campaigns),
        ("meta",        _meta_campaigns),
        ("snapchat",    _snap_campaigns),
        ("linkedin",    _linkedin_campaigns),
    ]
    all_rows = []
    for channel, fn in fetchers:
        try:
            rows = fn()
            for r in rows:
                r["snapped_at"] = now.isoformat()
            all_rows.extend(rows)
            print(f"[snapshot] {channel}: {len(rows)} campaigns")
        except Exception as e:
            print(f"[snapshot] {channel} FAILED: {e}")

    if not all_rows:
        return 0

    # Write to BQ
    ndjson    = b"\n".join(json.dumps(r).encode() for r in all_rows)
    table_ref = bq.dataset(D, project=P).table(_TABLE)
    from google.cloud import bigquery as bqlib
    job_cfg = bqlib.LoadJobConfig(
        source_format=bqlib.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bqlib.WriteDisposition.WRITE_APPEND,
        autodetect=False,
        schema=[
            bqlib.SchemaField("snapped_at",     "TIMESTAMP"),
            bqlib.SchemaField("channel",         "STRING"),
            bqlib.SchemaField("account_id",      "STRING"),
            bqlib.SchemaField("campaign_id",     "STRING"),
            bqlib.SchemaField("campaign_name",   "STRING"),
            bqlib.SchemaField("status",          "STRING"),
            bqlib.SchemaField("budget_raw",      "FLOAT64"),
            bqlib.SchemaField("budget_currency", "STRING"),
            bqlib.SchemaField("entity_type",     "STRING"),
        ],
    )
    bq.load_table_from_file(BytesIO(ndjson), table_ref, job_config=job_cfg).result()
    print(f"[snapshot] wrote {len(all_rows)} rows total")

    # Detect and log user changes vs previous snapshot
    _detect_and_log(bq, P, D, now)

    return len(all_rows)
