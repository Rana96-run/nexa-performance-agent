"""
patch_n8n_sql.py — Apply corrected wide_ads SQL to 11 broken BQ nodes
across 3 n8n workflows (Monthly, Master, Weekly).

Run via: railway run python scripts/patch_n8n_sql.py
N8N_API_KEY is injected by Railway.
"""

import os
import sys
import io
import json
import copy
import requests

# Force UTF-8 output on Windows so node names with special chars don't crash
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_URL = "https://qoyod.app.n8n.cloud/api/v1"
API_KEY = os.environ.get("N8N_API_KEY", "")

if not API_KEY:
    print("ERROR: N8N_API_KEY not found in environment. Run via: railway run python scripts/patch_n8n_sql.py")
    sys.exit(1)

HEADERS = {
    "X-N8N-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

# ── Corrected SQL per node ────────────────────────────────────────────────────

SQL = {}

# Monthly
SQL["Query Period Compare (Monthly)"] = """SELECT channel, period,
  ROUND(SUM(spend),2) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_total),0)),2) AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql,
  'compare' AS _query
FROM (
  SELECT channel,
    CASE
      WHEN DATE_TRUNC(date,MONTH)=DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 MONTH),MONTH) THEN 'prior_month'
      WHEN DATE_TRUNC(date,MONTH)=DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH) THEN 'this_month'
    END AS period,
    spend, leads_total, leads_qualified
  FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
  WHERE date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 MONTH),MONTH)
)
WHERE period IS NOT NULL
GROUP BY channel, period ORDER BY channel, period"""

SQL["Query Forecast (Monthly)"] = """SELECT channel,
  ROUND(SUM(spend),2) AS mtd_spend,
  SUM(leads_total) AS mtd_leads,
  SUM(leads_qualified) AS mtd_sqls,
  DATE_DIFF(LAST_DAY(CURRENT_DATE('Asia/Riyadh')),DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH),DAY)+1 AS days_in_month,
  DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH),DAY)+1 AS days_elapsed,
  ROUND(SUM(spend)/(DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH),DAY)+1)
    *(DATE_DIFF(LAST_DAY(CURRENT_DATE('Asia/Riyadh')),DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH),DAY)+1),0) AS proj_spend_eom,
  ROUND(SUM(leads_total)/(DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH),DAY)+1)
    *(DATE_DIFF(LAST_DAY(CURRENT_DATE('Asia/Riyadh')),DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH),DAY)+1),0) AS proj_leads_eom,
  'forecast' AS _query
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH)
GROUP BY channel ORDER BY mtd_spend DESC"""

SQL["Query CRO"] = """SELECT channel, campaign_name,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  SUM(leads_disqualified) AS disq,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),NULLIF(SUM(leads_total),0))*100,1) AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified),NULLIF(SUM(leads_total),0))*100,1) AS disq_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql,
  'cro' AS _query
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH)
GROUP BY channel, campaign_name HAVING SUM(leads_total) >= 5
ORDER BY qual_rate_pct ASC LIMIT 20"""

SQL["Query ROAS"] = """SELECT channel,
  ROUND(SUM(spend),2) AS spend,
  ROUND(SUM(all_revenue_won),2) AS revenue_won,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won),NULLIF(SUM(spend),0)),2) AS roas,
  SUM(leads_total) AS leads,
  SUM(new_biz_deals_won) AS deals_won,
  'roas' AS _query
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'),MONTH)
GROUP BY channel ORDER BY roas DESC"""

# Master
SQL["Query KPIs"] = """SELECT channel,
  ROUND(SUM(spend),2) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_total),0)),2) AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),NULLIF(SUM(leads_total),0))*100,1) AS qual_pct,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won),NULLIF(SUM(spend),0)),2) AS roas,
  SUM(new_biz_deals_won) AS deals_won,
  ROUND(SUM(new_biz_revenue_won),2) AS revenue_won
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date = DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 DAY)
GROUP BY channel ORDER BY spend DESC"""

SQL["Query Period Compare (Master)"] = """WITH base AS (
  SELECT channel,
    CASE
      WHEN date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY) AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 8 DAY) THEN 'A_prior'
      WHEN date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 7 DAY) AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 DAY) THEN 'B_this'
    END AS period,
    spend, leads_total, leads_qualified, leads_open, all_revenue_won, new_biz_deals_won
  FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY)
)
SELECT channel, period,
  ROUND(SUM(spend),0) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won),NULLIF(SUM(spend),0)),2) AS roas,
  SUM(new_biz_deals_won) AS deals_won
FROM base WHERE period IS NOT NULL
GROUP BY channel, period ORDER BY channel, period"""

SQL["Query Ad Audit (Master)"] = """SELECT channel, campaign_name, ad_name,
  ROUND(SUM(spend),0) AS spend_14d,
  SUM(leads_total) AS hs_leads,
  SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified),NULLIF(SUM(leads_total),0))*100,1) AS disq_pct,
  DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),MIN(date),DAY) AS days_active,
  CASE
    WHEN SUM(spend) > 70 AND SUM(leads_total) = 0 AND DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),MIN(date),DAY) >= 7 THEN 'PAUSE_ZERO_CONV'
    WHEN SAFE_DIVIDE(SUM(leads_disqualified),NULLIF(SUM(leads_total),0)) >= 0.60 AND SUM(leads_total) >= 5 AND DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),MIN(date),DAY) >= 10 THEN 'PAUSE_JUNK'
    WHEN SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_total),0)) > 50 AND DATE_DIFF(CURRENT_DATE('Asia/Riyadh'),MIN(date),DAY) >= 10 THEN 'PAUSE_HIGH_CPL'
    WHEN ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) < 85 AND SUM(leads_qualified) >= 2 THEN 'SCALE'
    ELSE 'WATCH'
  END AS recommendation
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY)
GROUP BY channel, campaign_name, ad_name
HAVING SUM(spend) > 5
ORDER BY spend_14d DESC LIMIT 60"""

SQL["Query Forecast (Master)"] = """SELECT channel,
  ROUND(SUM(spend)/7*30,0) AS proj_spend,
  ROUND(SUM(leads_total)/7*30,0) AS proj_leads,
  ROUND(SUM(leads_qualified)/7*30,0) AS proj_sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql_7d,
  SUM(new_biz_deals_won) AS deals_won_7d,
  ROUND(SUM(new_biz_revenue_won),2) AS revenue_won_7d
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 7 DAY)
GROUP BY channel ORDER BY proj_spend DESC"""

# Weekly
SQL["Query Period Compare (Weekly)"] = """SELECT channel, period,
  ROUND(SUM(spend),2) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_total),0)),2) AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql,
  SUM(new_biz_deals_won) AS deals_won,
  'compare' AS _query
FROM (
  SELECT channel,
    CASE
      WHEN date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY) AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 8 DAY) THEN 'prior_7d'
      WHEN date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 7 DAY) AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 DAY) THEN 'last_7d'
    END AS period,
    spend, leads_total, leads_qualified, new_biz_deals_won
  FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY)
)
WHERE period IS NOT NULL
GROUP BY channel, period ORDER BY channel, period"""

SQL["Query Forecast (Weekly)"] = """SELECT channel,
  ROUND(SUM(spend)/7*30,0) AS proj_spend,
  ROUND(SUM(leads_total)/7*30,0) AS proj_leads,
  ROUND(SUM(leads_qualified)/7*30,0) AS proj_sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified)/7*30,0)),0) AS proj_cpql,
  ROUND(SUM(new_biz_deals_won)/7*30,0) AS proj_deals,
  'forecast' AS _query
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 7 DAY)
GROUP BY channel ORDER BY proj_spend DESC"""

SQL["Query Ad Audit (Weekly)"] = """SELECT channel, campaign_name, ad_name,
  ROUND(SUM(spend),0) AS spend_14d,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  SUM(new_biz_deals_won) AS deals_won,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_total),0)),0) AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),0) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified),NULLIF(SUM(leads_total),0))*100,0) AS disq_pct,
  'ad_audit' AS _query
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY)
GROUP BY channel, campaign_name, ad_name
HAVING SUM(spend) >= 20
ORDER BY cpql ASC NULLS LAST LIMIT 30"""


# ── Node-name → SQL key mapping per workflow ─────────────────────────────────

WORKFLOW_NODE_MAP = {
    "0Zh45UoTtjjhRn8U": {  # Monthly
        "Query Period Compare": SQL["Query Period Compare (Monthly)"],
        "Query Forecast":       SQL["Query Forecast (Monthly)"],
        "Query CRO":            SQL["Query CRO"],
        "Query ROAS":           SQL["Query ROAS"],
    },
    "T8icImtZFLYeCa7e": {  # Master
        "Query KPIs":           SQL["Query KPIs"],
        "Query Period Compare": SQL["Query Period Compare (Master)"],
        "Query Ad Audit":       SQL["Query Ad Audit (Master)"],
        "Query Forecast":       SQL["Query Forecast (Master)"],
    },
    "iNSdpXH7Rc9Lb8h8": {  # Weekly
        "Query Period Compare": SQL["Query Period Compare (Weekly)"],
        "Query Forecast":       SQL["Query Forecast (Weekly)"],
        "Query Ad Audit":       SQL["Query Ad Audit (Weekly)"],
    },
}

WORKFLOW_NAMES = {
    "0Zh45UoTtjjhRn8U": "Monthly",
    "T8icImtZFLYeCa7e": "Master",
    "iNSdpXH7Rc9Lb8h8": "Weekly",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_workflow(wf_id: str) -> dict:
    url = f"{BASE_URL}/workflows/{wf_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def put_workflow(wf_id: str, payload: dict) -> dict:
    url = f"{BASE_URL}/workflows/{wf_id}"
    r = requests.put(url, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def set_query_in_node(node: dict, new_sql: str) -> bool:
    """
    Mutate node in-place to set the SQL string.
    Handles known parameter layouts for n8n BigQuery nodes:
      1. node.parameters.sqlQuery   (most common in n8n BQ node)
      2. node.parameters.query      (older layout)
      3. node.parameters.operation.query
      4. node.parameters.sql
    Returns True if the field was found and updated.
    """
    params = node.get("parameters", {})

    # Layout 1: parameters.sqlQuery (n8n BigQuery node)
    if "sqlQuery" in params:
        params["sqlQuery"] = new_sql
        return True

    # Layout 2: parameters.query
    if "query" in params:
        params["query"] = new_sql
        return True

    # Layout 3: parameters.operation (object or string)
    if "operation" in params:
        op = params["operation"]
        if isinstance(op, dict) and "query" in op:
            op["query"] = new_sql
            return True

    # Layout 4: parameters.sql (some community nodes)
    if "sql" in params:
        params["sql"] = new_sql
        return True

    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    total_patched = 0
    total_errors = 0

    for wf_id, node_map in WORKFLOW_NODE_MAP.items():
        wf_name = WORKFLOW_NAMES[wf_id]
        print(f"\n{'='*60}")
        print(f"Workflow: {wf_name}  ({wf_id})")
        print(f"{'='*60}")

        # 1. Fetch full workflow JSON
        print("  GET workflow...", end=" ")
        try:
            wf = get_workflow(wf_id)
            print(f"OK  ({len(wf.get('nodes', []))} nodes)")
        except Exception as exc:
            print(f"FAILED: {exc}")
            total_errors += 1
            continue

        # Print all node names for reference (encode safely for Windows console)
        node_names = [n.get("name", "<unnamed>") for n in wf.get("nodes", [])]
        safe_names = [nm.encode("ascii", "replace").decode("ascii") for nm in node_names]
        print(f"  Node names in workflow: {safe_names}")

        # 2. Walk nodes and patch matches
        patched_nodes = []
        not_found = []
        wf_updated = copy.deepcopy(wf)

        for target_name, new_sql in node_map.items():
            matched = False
            for node in wf_updated.get("nodes", []):
                if node.get("name") == target_name:
                    matched = True
                    updated = set_query_in_node(node, new_sql)
                    if updated:
                        patched_nodes.append(target_name)
                        print(f"  [PATCHED] {target_name}")
                    else:
                        print(f"  [WARNING] {target_name} found but query field location unknown — node parameters: {list(node.get('parameters', {}).keys())}")
                        not_found.append(target_name)
                    break
            if not matched:
                print(f"  [NOT FOUND] Node '{target_name}' not found in workflow")
                not_found.append(target_name)

        if not patched_nodes:
            print(f"  No nodes patched — skipping PUT to avoid no-op overwrite")
            total_errors += 1
            continue

        # 3. PUT the updated workflow — only send writable fields
        # n8n v1 PUT /workflows/{id} rejects read-only fields (createdAt, updatedAt, etc.)
        # n8n v1 PUT requires: name, nodes, connections, settings
        # Exclude read-only top-level fields (meta, versionId, activeVersionId, etc.)
        # settings.availableInMCP is an internal key that fails validation — strip it
        PUT_FIELDS = {"name", "nodes", "connections", "staticData", "pinData", "settings"}
        put_body = {k: v for k, v in wf_updated.items() if k in PUT_FIELDS}

        # n8n PUT /workflows/{id} only accepts these settings keys (from API schema):
        # executionOrder, saveManualExecutions, saveExecutionProgress,
        # saveDataSuccessExecution, saveDataErrorExecution, callerPolicy,
        # executionTimeout, timezone, errorWorkflow, callerIds
        # Everything else (availableInMCP, binaryMode, etc.) is rejected.
        SETTINGS_ALLOWED = {
            "executionOrder", "saveManualExecutions", "saveExecutionProgress",
            "saveDataSuccessExecution", "saveDataErrorExecution", "callerPolicy",
            "executionTimeout", "timezone", "errorWorkflow", "callerIds",
        }
        if "settings" in put_body and isinstance(put_body["settings"], dict):
            put_body["settings"] = {
                k: v for k, v in put_body["settings"].items()
                if k in SETTINGS_ALLOWED
            }

        print(f"  PUT workflow ({len(patched_nodes)} nodes patched)...", end=" ")
        try:
            result = put_workflow(wf_id, put_body)
            # n8n returns the updated workflow; check it has the same id
            returned_id = result.get("id", "")
            if returned_id == wf_id or str(returned_id) == wf_id:
                print(f"200 OK")
                total_patched += len(patched_nodes)
            else:
                print(f"Unexpected response id={returned_id!r}")
                total_errors += 1
        except requests.HTTPError as exc:
            print(f"FAILED: {exc.response.status_code} — {exc.response.text[:500]}")
            total_errors += 1
        except Exception as exc:
            print(f"FAILED: {exc}")
            total_errors += 1

        if not_found:
            print(f"  [SKIPPED] Nodes not matched: {not_found}")

    print(f"\n{'='*60}")
    print(f"DONE — {total_patched} nodes patched, {total_errors} workflow errors")
    print(f"{'='*60}")
    if total_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
