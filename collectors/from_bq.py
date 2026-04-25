"""
BigQuery reader — single source of truth for the agent's analysis loop.

The `*_bq.py` writers populate `campaigns_daily` 4×/day. The agent's
decision loop reads from here instead of re-hitting each ad API. Benefits:

  - One source of truth (agent + dashboard see the same numbers).
  - Removes ~600 lines of duplicate fetch code across 4 channels.
  - Cheaper (no extra API calls per cadence run).

Latency trade: data is up to 6h stale (the BQ refresh cadence), which is
acceptable for daily/weekly cadences making multi-day-trend decisions.
For ad-level (Meta) and keyword-level (Google) decisions where BQ has
no grain, the agent still hits the live API via the executor modules.

Each `read_*` function returns a list of dicts in the same shape the old
direct collectors emitted, so `main.py`'s downstream code (Asana task
builders, Claude prompts) is unchanged.
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Optional

from collectors.bq_writer import get_client, PROJECT_ID, DATASET


def _table(name: str) -> str:
    return f"`{PROJECT_ID}.{DATASET}.{name}`"


def read_campaigns(channel: str, days: int = 7) -> list[dict]:
    """
    Read the last `days` of campaign-level rows for a single channel from
    `campaigns_daily`. Returns a list of dicts shaped like the legacy
    direct-collector outputs.

    Channel keys (must match what `*_bq.py` writes):
        google_ads · meta · snapchat · linkedin · microsoft_ads · tiktok
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)

    sql = f"""
        SELECT
            date,
            campaign_id,
            campaign_name,
            spend,
            currency,
            spend_native,
            currency_native,
            impressions,
            clicks,
            ctr,
            leads,
            conversions,
            cpl,
            account_id
        FROM {_table('campaigns_daily')}
        WHERE channel = @channel
          AND date BETWEEN @start AND @end
        ORDER BY date, campaign_id
    """
    from google.cloud import bigquery
    client = get_client()
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("channel", "STRING", channel),
                bigquery.ScalarQueryParameter("start",   "DATE",   start),
                bigquery.ScalarQueryParameter("end",     "DATE",   end),
            ]
        ),
    )
    rows = []
    for r in job.result():
        rows.append({
            "campaign_id":      r["campaign_id"],
            "campaign_name":    r["campaign_name"],
            "date":             str(r["date"]) if r["date"] else None,
            "spend":            float(r["spend"] or 0),
            "currency":         r["currency"] or "USD",
            "spend_native":     float(r["spend_native"] or 0),
            "currency_native":  r["currency_native"],
            "impressions":      int(r["impressions"] or 0),
            "clicks":           int(r["clicks"] or 0),
            "ctr":              float(r["ctr"] or 0),
            "conversions":      float(r["conversions"] or 0),
            "leads":            int(r["leads"] or 0),
            "cpl":              float(r["cpl"]) if r["cpl"] is not None else None,
            "account_id":       r["account_id"],
        })
    return rows
