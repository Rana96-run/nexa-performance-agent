"""Dry-run all Hex SQL files against BigQuery to verify they parse. Replaces
Hex Jinja vars with sane defaults so the SQL is syntactically complete."""
import os, sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from pathlib import Path
from collectors.bq_writer import get_client

c = get_client()
ROOT = Path(".claude/hex_drilldown")

# Substitute Hex Jinja template tokens with realistic values
SUBS = {
    "{{ start_date }}": "'2026-05-01'",
    "{{ end_date }}":   "'2026-05-13'",
    "{{ channel_filter }}":      "'google_ads'",
    "{{ campaign_filter }}":     "'Search_E-invoice_AR'",
    "{{ selected_campaign }}":   "'Search_E-invoice_AR'",
    "{{ effective_campaign }}":  "'Search_E-invoice_AR'",
    "{{ selected_adset }}":      "'Test_Adset'",
    "{{ selected_pipeline }}":   "'Sales Pipeline'",
    "{{ channel }}":             "'google_ads'",
}

# Strip Jinja {% if %}/{% endif %} blocks — keep inner SQL unconditionally
JINJA_IF = re.compile(r"\{%\s*if [^%]+%\}", re.IGNORECASE)
JINJA_END = re.compile(r"\{%\s*endif\s*%\}", re.IGNORECASE)

def prepare(sql: str) -> str:
    for k, v in SUBS.items():
        sql = sql.replace(k, v)
    sql = JINJA_IF.sub("", sql)
    sql = JINJA_END.sub("", sql)
    return sql

passed, failed = [], []
for path in sorted(ROOT.rglob("*.sql")):
    sql = prepare(path.read_text(encoding="utf-8"))
    job_config = {"dry_run": True, "use_query_cache": False}
    from google.cloud import bigquery
    try:
        c.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)).result
        passed.append(path)
    except Exception as e:
        msg = str(e).split("\n")[0][:140]
        failed.append((path, msg))

print(f"PASSED: {len(passed)}")
print(f"FAILED: {len(failed)}\n")
for path, msg in failed:
    print(f"  ✗ {path}")
    print(f"      {msg}")
