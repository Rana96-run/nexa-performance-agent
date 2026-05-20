"""Add a strong column description to campaigns_daily.leads so the BQ
schema itself warns any reader that this column is channel-reported,
not real leads. Updates the BigQuery table schema metadata (description
only — no data change, no breaking change).

This complements the .claude/hooks/kpi_rule_guard.py local enforcement
by adding documentation at the BQ layer that everyone (Hex dashboard,
DataGrip users, future engineers) sees automatically.
"""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField

PROJECT  = "angular-axle-492812-q4"
DATASET  = "qoyod_marketing"
TABLES   = ["campaigns_daily", "ads_daily", "adsets_daily"]

WARNING = (
    "⚠ CHANNEL-REPORTED, NOT REAL LEADS. This counts pixel/postback events "
    "from the channel (e.g. WebsiteTraffic objective on Bing counts page "
    "views as conversions). For real lead counts use "
    "`hubspot_leads_module_daily.leads_total`. See "
    "memory/CRITICAL_KPI_RULES.md."
)

c = bigquery.Client(project=PROJECT, location="me-central1")

for tname in TABLES:
    try:
        table = c.get_table(f"{PROJECT}.{DATASET}.{tname}")
    except Exception as e:
        print(f"⚠ {tname}: cannot fetch ({type(e).__name__}: {str(e)[:120]})")
        continue

    print(f"\n{tname} — fields with 'leads' or 'conversions':")
    new_schema = []
    changed = 0
    for f in table.schema:
        if f.name.lower() in ("leads", "conversions"):
            # Update description if not already set to our warning
            existing = f.description or ""
            if WARNING.split(".")[0] in existing:
                print(f"  ⏭ {f.name}: already warned")
                new_schema.append(f)
            else:
                new_field = SchemaField(
                    name=f.name,
                    field_type=f.field_type,
                    mode=f.mode,
                    description=WARNING,
                )
                new_schema.append(new_field)
                changed += 1
                print(f"  ✅ {f.name}: warning added")
        else:
            new_schema.append(f)

    if changed:
        table.schema = new_schema
        c.update_table(table, ["schema"])
        print(f"  → updated {changed} field(s) on {tname}")
    else:
        print(f"  (no changes)")
