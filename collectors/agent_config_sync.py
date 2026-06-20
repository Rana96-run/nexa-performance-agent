"""
Sync agent config files from repo to BQ table `agent_config`.

Reads specific markdown files from the repo and writes their content
to a BQ lookup table so n8n workflows and dashboard queries can fetch
the latest rules / role prompts without reading the filesystem directly.

Table schema:
  agent_config (
    key         STRING NOT NULL,
    value       STRING,
    updated_at  TIMESTAMP
  )

No partitioning — 6 rows max, tiny table.
MERGE on key: update value+updated_at if key exists, insert if new.

Run standalone:  python collectors/agent_config_sync.py
"""
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

# ── Repo root is one level up from collectors/ ────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent

FILES_TO_SYNC: dict[str, str] = {
    "kpi_rules":                "memory/CRITICAL_KPI_RULES.md",
    "learning_patterns":        "memory/14_learning_patterns.md",
    "growth_analyst_role":      ".claude/agents/growth-analyst.md",
    "performance_lead_role":    ".claude/agents/performance-lead.md",
    "campaign_manager_role":    ".claude/agents/campaign-manager.md",
    "creative_strategist_role": ".claude/agents/creative-strategist.md",
}

_TABLE = "agent_config"

_SCHEMA = [
    # Import here to avoid circular import at module level
]

_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS `{P}.{D}.agent_config` (
  key        STRING NOT NULL,
  value      STRING,
  updated_at TIMESTAMP
)
"""


def _get_bq():
    from collectors.bq_writer import get_client
    return get_client()


def _ensure_table(bq) -> None:
    """Create agent_config table if it doesn't exist."""
    P = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D = os.getenv("BQ_DATASET",    "qoyod_marketing")
    bq.query(_CREATE_DDL.format(P=P, D=D)).result()


def _merge_rows(bq, rows: list[dict]) -> None:
    """
    MERGE agent_config on key.
    Because the table is tiny (6 rows) and we want a true upsert, we:
      1. Write the new rows to a temp table via load_table_from_file (no streaming).
      2. Run a MERGE from the temp table into agent_config.
      3. Drop the temp table.

    No streaming inserts — matches project rule.
    """
    from google.cloud import bigquery

    P = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D = os.getenv("BQ_DATASET",    "qoyod_marketing")
    target_id = f"{P}.{D}.{_TABLE}"
    temp_id   = f"{P}.{D}._agent_config_tmp"

    # ── 1. Write rows to temp table ───────────────────────────────────────────
    ndjson = "\n".join(json.dumps(r, default=str) for r in rows).encode("utf-8")

    schema = [
        bigquery.SchemaField("key",        "STRING"),
        bigquery.SchemaField("value",      "STRING"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema,
    )
    load_job = bq.load_table_from_file(
        BytesIO(ndjson), temp_id, job_config=job_config
    )
    load_job.result()

    # ── 2. MERGE temp → target ────────────────────────────────────────────────
    merge_sql = f"""
    MERGE `{target_id}` AS T
    USING `{temp_id}`  AS S
    ON T.key = S.key
    WHEN MATCHED THEN
      UPDATE SET T.value = S.value, T.updated_at = S.updated_at
    WHEN NOT MATCHED THEN
      INSERT (key, value, updated_at)
      VALUES (S.key, S.value, S.updated_at)
    """
    bq.query(merge_sql).result()

    # ── 3. Drop temp table ────────────────────────────────────────────────────
    bq.delete_table(temp_id, not_found_ok=True)


def sync() -> int:
    """
    Read FILES_TO_SYNC from disk, merge into BQ agent_config.
    Returns number of files successfully synced.
    """
    bq       = _get_bq()
    now_utc  = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    for key, rel_path in FILES_TO_SYNC.items():
        file_path = _REPO_ROOT / rel_path
        if not file_path.exists():
            print(f"[agent_config] WARN: {rel_path} not found on disk — skipping {key!r}")
            continue
        content = file_path.read_text(encoding="utf-8")
        rows.append({
            "key":        key,
            "value":      content,
            "updated_at": now_utc,
        })

    if not rows:
        print("[agent_config] no files found to sync — nothing written")
        return 0

    _ensure_table(bq)
    _merge_rows(bq, rows)

    for r in rows:
        print(f"[agent_config] synced: {r['key']}")

    print(f"[agent_config] done — {len(rows)} keys written to {_TABLE}")
    return len(rows)


if __name__ == "__main__":
    sync()
