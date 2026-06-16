#!/usr/bin/env python3
"""
BigQuery MCP Server for Nexa Performance Agent.

Exposes Google BigQuery as MCP tools so Claude / Cowork agents can run
SQL queries, list tables, and inspect schemas — without needing the
google-cloud-bigquery library pre-installed in the sandbox.

Transport : stdio (local Cowork plugin)
Auth      : Service-account key file pointed to by GOOGLE_APPLICATION_CREDENTIALS
            (same key already used by all collectors in this project)
"""

from __future__ import annotations

import json
import os
from typing import Optional

from google.cloud import bigquery
from google.oauth2 import service_account
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
mcp = FastMCP("bigquery_mcp")

# ---------------------------------------------------------------------------
# BQ client — built once, reused across all tool calls
# ---------------------------------------------------------------------------
_PROJECT = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
_DATASET  = os.getenv("BQ_DATASET",     "nexa_performance")
_LOCATION = os.getenv("BQ_LOCATION",    "me-central1")
_KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

def _get_client() -> bigquery.Client:
    """Return an authenticated BigQuery client."""
    if _KEY_FILE and os.path.exists(_KEY_FILE):
        creds = service_account.Credentials.from_service_account_file(
            _KEY_FILE,
            scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
        )
        return bigquery.Client(project=_PROJECT, credentials=creds, location=_LOCATION)
    # Fallback: Application Default Credentials (works on Railway / GCE)
    return bigquery.Client(project=_PROJECT, location=_LOCATION)


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------
class RunQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sql: str = Field(
        ...,
        description=(
            "StandardSQL query to run against BigQuery. "
            "Must be a SELECT statement. Use fully-qualified table names: "
            "`angular-axle-492812-q4.nexa_performance.table_name`. "
            "Example: SELECT channel, SUM(spend) FROM `...campaigns_daily` "
            "WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY) "
            "GROUP BY channel ORDER BY 2 DESC"
        ),
        min_length=10,
    )
    max_rows: Optional[int] = Field(
        default=500,
        description="Maximum rows to return (1–2000). Default 500.",
        ge=1,
        le=2000,
    )
    response_format: Optional[str] = Field(
        default="json",
        description="'json' (default) for machine-readable, 'markdown' for a text table.",
    )
    timeout_seconds: Optional[int] = Field(
        default=60,
        description="Query timeout in seconds (1–120). Default 60.",
        ge=1,
        le=120,
    )


class ListTablesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    dataset_id: Optional[str] = Field(
        default=None,
        description=(
            "Dataset ID to list tables from. Defaults to the project default "
            f"('{_DATASET}'). Format: 'dataset_id' or 'project.dataset_id'."
        ),
    )


class GetSchemaInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    table: str = Field(
        ...,
        description=(
            "Fully-qualified table name, e.g. 'campaigns_daily' (uses default dataset) "
            "or 'nexa_performance.campaigns_daily' or the full "
            "'angular-axle-492812-q4.nexa_performance.campaigns_daily'."
        ),
        min_length=1,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rows_to_json(rows: list[dict]) -> str:
    return json.dumps(rows, indent=2, default=str)


def _rows_to_markdown(rows: list[dict]) -> str:
    if not rows:
        return "_No rows returned._"
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    sep_line    = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines  = [
        "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |"
        for row in rows
    ]
    return "\n".join([header_line, sep_line] + body_lines)


def _resolve_table_ref(table: str) -> str:
    """
    Accept bare table name, dataset.table, or project.dataset.table.
    Always return a fully-qualified backtick-quoted reference.
    """
    parts = table.strip().strip("`").split(".")
    if len(parts) == 1:
        return f"`{_PROJECT}.{_DATASET}.{parts[0]}`"
    if len(parts) == 2:
        return f"`{_PROJECT}.{parts[0]}.{parts[1]}`"
    return f"`{'`.`'.join(parts)}`"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="bq_run_query",
    annotations={
        "title": "Run BigQuery SQL Query",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def bq_run_query(params: RunQueryInput) -> str:
    """
    Execute a read-only SQL query against the Nexa Performance BigQuery project
    and return the results.

    Use this tool whenever you need to pull live data: spend, leads, CPQL,
    channel performance, LP metrics, forecasts, ad-level analysis, etc.
    Always prefer this over cached recollections.

    Args:
        params (RunQueryInput):
            - sql (str): StandardSQL SELECT statement. Use fully-qualified table
              names: `angular-axle-492812-q4.nexa_performance.<table>`.
            - max_rows (int): Cap on rows returned (default 500, max 2000).
            - response_format (str): 'json' (default) or 'markdown'.
            - timeout_seconds (int): Query timeout, default 60s.

    Returns:
        str: JSON array of row objects, or a Markdown table. On error,
             returns an "Error: ..." string with the BigQuery error message.

    Schema reference:
        Key tables in nexa_performance dataset:
        - campaigns_daily          — daily spend/clicks/impressions by campaign
        - wide_ads                 — ad-grain KPIs incl. leads/sqls (replaces paid_channel_daily)
        - wide_keywords            — keyword-grain KPIs
        - hubspot_leads_module_daily — HubSpot lead module (source of truth for leads)
        - hubspot_deals_daily       — deal amounts (USD, already converted)
        - ads_daily                 — ad-level performance
        - keyword_view              — Google Ads keyword performance
        Use bq_list_tables() to discover all available tables.
        Use bq_get_schema() to inspect column names and types before querying.

    Examples:
        - "Channel performance last 7 days" →
          SELECT channel, SUM(spend) AS spend, SUM(leads_total) AS leads
          FROM `angular-axle-492812-q4.nexa_performance.wide_ads`
          WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
          GROUP BY channel ORDER BY spend DESC
    """
    try:
        client = _get_client()
        job_config = bigquery.QueryJobConfig(
            use_query_cache=True,
            use_legacy_sql=False,
        )
        job = client.query(
            params.sql,
            job_config=job_config,
            timeout=params.timeout_seconds,
        )
        result = job.result(timeout=params.timeout_seconds)

        rows = [dict(row) for row in result]
        if len(rows) > params.max_rows:
            rows = rows[: params.max_rows]
            truncated = True
        else:
            truncated = False

        if params.response_format == "markdown":
            table_str = _rows_to_markdown(rows)
            note = f"\n\n_Showing {len(rows)} rows" + (" (truncated)." if truncated else ".")  + "_"
            return table_str + note

        # JSON (default)
        payload = {
            "row_count": len(rows),
            "truncated": truncated,
            "rows": rows,
        }
        return json.dumps(payload, indent=2, default=str)

    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(
    name="bq_list_tables",
    annotations={
        "title": "List BigQuery Tables",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def bq_list_tables(params: ListTablesInput) -> str:
    """
    List all tables in a BigQuery dataset.

    Use before running a query if you're unsure of available table names,
    or when you need to discover what data sources exist.

    Args:
        params (ListTablesInput):
            - dataset_id (str, optional): Dataset to list. Defaults to
              the project default ('nexa_performance').

    Returns:
        str: JSON array of table summaries with name, type, and row count.
             On error returns "Error: ...".
    """
    try:
        client  = _get_client()
        dataset = params.dataset_id or _DATASET
        # Handle project-qualified dataset IDs
        if "." not in dataset:
            dataset_ref = bigquery.DatasetReference(_PROJECT, dataset)
        else:
            parts = dataset.split(".", 1)
            dataset_ref = bigquery.DatasetReference(parts[0], parts[1])

        tables = list(client.list_tables(dataset_ref))
        result = [
            {
                "table_id":  t.table_id,
                "table_type": t.table_type,
                "dataset":    t.dataset_id,
                "project":    t.project,
            }
            for t in tables
        ]
        return json.dumps({"dataset": dataset, "table_count": len(result), "tables": result}, indent=2)

    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(
    name="bq_get_schema",
    annotations={
        "title": "Get BigQuery Table Schema",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def bq_get_schema(params: GetSchemaInput) -> str:
    """
    Return the schema (column names, types, descriptions) for a BigQuery table.

    Use this before writing a complex query to confirm exact column names and
    types — schemas evolve and cached knowledge may be stale.

    Args:
        params (GetSchemaInput):
            - table (str): Table name. Accepts bare name ('campaigns_daily'),
              dataset-qualified ('nexa_performance.campaigns_daily'), or
              fully-qualified ('angular-axle-492812-q4.nexa_performance.campaigns_daily').

    Returns:
        str: JSON object with table metadata and a 'fields' array, each entry
             containing name, field_type, mode, and description.
             On error returns "Error: ...".
    """
    try:
        client = _get_client()
        # Parse table reference
        ref_str = params.table.strip().strip("`")
        parts   = ref_str.split(".")
        if len(parts) == 1:
            tbl_ref = bigquery.TableReference(
                bigquery.DatasetReference(_PROJECT, _DATASET), parts[0]
            )
        elif len(parts) == 2:
            tbl_ref = bigquery.TableReference(
                bigquery.DatasetReference(_PROJECT, parts[0]), parts[1]
            )
        else:
            tbl_ref = bigquery.TableReference(
                bigquery.DatasetReference(parts[0], parts[1]), parts[2]
            )

        table = client.get_table(tbl_ref)
        fields = [
            {
                "name":        f.name,
                "field_type":  f.field_type,
                "mode":        f.mode,
                "description": f.description or "",
            }
            for f in table.schema
        ]
        return json.dumps(
            {
                "table":       f"{table.project}.{table.dataset_id}.{table.table_id}",
                "num_rows":    table.num_rows,
                "num_bytes":   table.num_bytes,
                "modified":    str(table.modified),
                "field_count": len(fields),
                "fields":      fields,
            },
            indent=2,
            default=str,
        )

    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()  # stdio transport
