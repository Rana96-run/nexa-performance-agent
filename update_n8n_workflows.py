"""
Update all 13 on-demand n8n workflows to query BigQuery FIRST, then pass real data to Claude.
Pattern:
  Webhook -> Respond -> BQ Query -> Code Format -> AI Agent (with real data) -> Slack
"""
import json, sys, time
import urllib.request
import urllib.error

N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyYTZlMDMwNC0wN2RhLTRjNzktYTUwNi0zYzkyYjU5ODFiZDEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjA2Yjk1Y2YtNzJiOS00ZGM0LWIxOTAtNTY0Y2QyNzdhMDNiIiwiaWF0IjoxNzgxMTgxODU3fQ.UvVwQcF0-bW8ipJlgSTPEYe1Zg8tdJE3ZoJ-vJIFi8s"
BQ_CRED_ID = "kE5RxM61mQkpV21N"
BQ_CRED_NAME = "BigQuery (Qoyod)"
BQ_PROJECT = "angular-axle-492812-q4"
BASE_URL = "https://qoyod.app.n8n.cloud/api/v1"

QUERIES = {
    "SCxtvUESOT8rpq46": "SELECT channel, SUM(spend) as spend, SUM(leads_total) as leads, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total),0)) as cpl, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SAFE_DIVIDE(SUM(deal_amount), NULLIF(SUM(spend),0)) as roas FROM `qoyod_marketing.paid_channel_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) GROUP BY channel ORDER BY spend DESC",
    "rx1FDHDJOd16otQz": "SELECT channel, campaign_name, ad_name, SUM(spend) as spend, COUNT(DISTINCT date) as days_running, SUM(leads_total) as hs_leads, SUM(leads_qualified) as hs_sqls, SUM(leads_disqualified) as hs_disq, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total),0)) as cpl, SAFE_DIVIDE(SUM(leads_disqualified), NULLIF(SUM(leads_total),0)) as disq_rate FROM `qoyod_marketing.v_ad_performance` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) GROUP BY channel, campaign_name, ad_name HAVING spend > 20 ORDER BY cpl DESC NULLS LAST LIMIT 50",
    "SrgatDSDwLe0jYsp": "SELECT channel, campaign_name, adgroup_name, keyword_text, SUM(spend) as spend, SUM(impressions) as impressions, AVG(quality_score) as avg_qs, AVG(search_impression_share) as avg_is, SUM(conversions) as conversions FROM `qoyod_marketing.v_keyword_performance` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND status = 'ENABLED' GROUP BY channel, campaign_name, adgroup_name, keyword_text HAVING impressions > 10 ORDER BY avg_qs ASC, spend DESC LIMIT 100",
    "6nFCbFHMjofKPjlO": "SELECT channel, campaign_name, SUM(spend) as spend, SUM(leads_total) as leads, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total),0)) as cpl, SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads_total),0)) as qual_rate FROM `qoyod_marketing.paid_channel_campaign_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) GROUP BY channel, campaign_name HAVING spend > 100 AND sqls >= 3 ORDER BY cpql ASC LIMIT 20",
    "1sda7mo2aM0yyi7J": "SELECT channel, SUM(spend) as spend, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SAFE_DIVIDE(SUM(deal_amount), NULLIF(SUM(spend),0)) as roas FROM `qoyod_marketing.paid_channel_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) GROUP BY channel ORDER BY cpql ASC",
    "lwwVSJPh31wVyCp4": "SELECT channel, SUM(CASE WHEN date >= DATE_TRUNC(CURRENT_DATE(), MONTH) THEN spend ELSE 0 END) as mtd_spend, SUM(CASE WHEN date >= DATE_TRUNC(CURRENT_DATE(), MONTH) THEN leads_qualified ELSE 0 END) as mtd_sqls, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) THEN spend ELSE 0 END) as spend_90d, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) THEN leads_qualified ELSE 0 END) as sqls_90d, SAFE_DIVIDE(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) THEN spend ELSE 0 END), NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) THEN leads_qualified ELSE 0 END),0)) as cpql_30d FROM `qoyod_marketing.paid_channel_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) GROUP BY channel ORDER BY spend_90d DESC",
    "CTn4YSgDaeEJ8gKo": "SELECT channel, FORMAT_DATE('%Y-%m', date) as month, SUM(spend) as spend, SUM(leads_total) as leads, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SAFE_DIVIDE(SUM(deal_amount), NULLIF(SUM(spend),0)) as roas FROM `qoyod_marketing.paid_channel_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY) GROUP BY channel, month ORDER BY channel, month",
    "MV5hPJh69VgeKPa5": "SELECT channel, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend ELSE 0 END) as curr_spend, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend ELSE 0 END) as prev_spend, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN leads_total ELSE 0 END) as curr_leads, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN leads_total ELSE 0 END) as prev_leads, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN leads_qualified ELSE 0 END) as curr_sqls, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN leads_qualified ELSE 0 END) as prev_sqls, SAFE_DIVIDE(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend ELSE 0 END), NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN leads_qualified ELSE 0 END),0)) as curr_cpql, SAFE_DIVIDE(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend ELSE 0 END), NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN leads_qualified ELSE 0 END),0)) as prev_cpql FROM `qoyod_marketing.paid_channel_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) GROUP BY channel ORDER BY curr_spend DESC",
    "IcsYYjYhxawXggqa": "SELECT channel, SUM(CASE WHEN date >= DATE_TRUNC(CURRENT_DATE(), MONTH) THEN spend ELSE 0 END) as mtd_spend, SUM(CASE WHEN date >= DATE_TRUNC(CURRENT_DATE(), MONTH) THEN leads_qualified ELSE 0 END) as mtd_sqls, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) THEN spend ELSE 0 END) as spend_90d, SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) THEN leads_qualified ELSE 0 END) as sqls_90d, SAFE_DIVIDE(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) THEN spend ELSE 0 END), NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) THEN leads_qualified ELSE 0 END),0)) as cpql_30d FROM `qoyod_marketing.paid_channel_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) GROUP BY channel ORDER BY spend_90d DESC",
    "W4ODdu8h77L7Zq2Y": "SELECT channel, campaign_name, ad_name, SUM(spend) as spend, SUM(impressions) as impressions, SUM(clicks) as clicks, SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions),0)) as ctr, SUM(leads_total) as leads, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SUM(video_views) as video_views, SAFE_DIVIDE(SUM(video_views), NULLIF(SUM(impressions),0)) as vtr FROM `qoyod_marketing.v_ad_performance` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) GROUP BY channel, campaign_name, ad_name HAVING spend > 30 ORDER BY cpql ASC NULLS LAST LIMIT 50",
    "QSbff8kzWMfK8L3c": "SELECT lead_utm_campaign, SUM(leads_total) as leads, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads_total),0)) as qual_rate FROM `qoyod_marketing.hubspot_leads_module_daily` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) GROUP BY lead_utm_campaign HAVING leads >= 5 ORDER BY qual_rate ASC",
    "UvkvJRQeKKLC4Sen": "SELECT channel, campaign_name, adset_name, SUM(spend) as spend, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SUM(impressions) as impressions, SUM(clicks) as clicks, SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions),0)) as ctr FROM `qoyod_marketing.v_adset_performance` WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) GROUP BY channel, campaign_name, adset_name HAVING spend > 50 ORDER BY cpql DESC NULLS LAST LIMIT 30",
    "PGNGf4wJfSMNXcST": "SELECT channel, campaign_name, SUM(spend) as spend, SUM(leads_total) as leads, SUM(leads_qualified) as sqls, SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)) as cpql, SAFE_DIVIDE(SUM(deal_amount), NULLIF(SUM(spend),0)) as roas FROM `qoyod_marketing.paid_channel_campaign_daily` WHERE date >= DATE_TRUNC(CURRENT_DATE(), MONTH) GROUP BY channel, campaign_name ORDER BY spend DESC LIMIT 40",
}

CODE_FORMAT_JS = """const items = $input.all();
const rows = items.map(i => i.json);
if (!rows || rows.length === 0) {
  return [{ json: { bq_data: 'NO DATA RETURNED FROM BIGQUERY', row_count: 0 } }];
}
const formatted = JSON.stringify(rows, null, 2);
return [{ json: { bq_data: formatted, row_count: rows.length } }];"""


def n8n_request(method, path, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", N8N_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()[:500]}


BQ_NODE_NAME = "BQ Query"
CODE_NODE_NAME = "Code Format"


def build_updated_workflow(wf, sql):
    nodes = wf["nodes"]
    connections = wf["connections"]

    webhook_node = next(n for n in nodes if n["type"] == "n8n-nodes-base.webhook")
    agent_node = next(n for n in nodes if n["type"] == "@n8n/n8n-nodes-langchain.agent")
    claude_node = next(n for n in nodes if n["type"] == "@n8n/n8n-nodes-langchain.lmChatAnthropic")

    wf_slug = webhook_node["parameters"].get("path", "od-unknown")
    bq_node_id = f"bq-{wf_slug}"
    code_node_id = f"code-{wf_slug}"

    # Remove any previously injected BQ/Code nodes (idempotent)
    existing_bq = [n for n in nodes if n["type"] == "n8n-nodes-base.googleBigQuery"]
    existing_code = [n for n in nodes if n["type"] == "n8n-nodes-base.code"]
    removed_names = set(n["name"] for n in existing_bq + existing_code)
    nodes[:] = [n for n in nodes if n["type"] not in (
        "n8n-nodes-base.googleBigQuery",
        "n8n-nodes-base.code"
    )]
    # Remove all stale connections: keys and values referencing removed node names
    for name in list(connections.keys()):
        connections.pop(name) if name in removed_names else None
    # Also purge any outgoing references to removed nodes from remaining connections
    for src in list(connections.keys()):
        main = connections[src].get("main", [])
        new_main = []
        for output_list in main:
            new_output = [c for c in output_list if c["node"] not in removed_names]
            new_main.append(new_output)
        connections[src]["main"] = new_main

    # Reposition existing nodes to make room
    agent_node["position"] = [1050, 300]
    claude_node["position"] = [1050, 520]
    for n in nodes:
        if n["id"].startswith("slack-"):
            n["position"] = [1300, 300]

    # BQ node — must match exactly the format used in Master workflow (typeVersion 2.1, serviceAccount auth, __rl projectId)
    bq_node = {
        "id": bq_node_id,
        "name": BQ_NODE_NAME,
        "type": "n8n-nodes-base.googleBigQuery",
        "typeVersion": 2.1,
        "position": [500, 300],
        "credentials": {
            "googleApi": {
                "id": BQ_CRED_ID,
                "name": BQ_CRED_NAME
            }
        },
        "parameters": {
            "projectId": {
                "__rl": True,
                "value": BQ_PROJECT,
                "mode": "id"
            },
            "sqlQuery": sql,
            "options": {},
            "authentication": "serviceAccount"
        }
    }

    # Code format node
    code_node = {
        "id": code_node_id,
        "name": CODE_NODE_NAME,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [750, 300],
        "parameters": {
            "jsCode": CODE_FORMAT_JS
        }
    }

    # Update agent system message to inject BQ data — idempotent (strip old injection first)
    existing_sys = agent_node["parameters"].get("options", {}).get("systemMessage", "")
    # Strip any previously injected BQ data block
    injection_marker = "\n\n⚠️ REAL BIGQUERY DATA IS PROVIDED BELOW"
    if injection_marker in existing_sys:
        existing_sys = existing_sys[:existing_sys.index(injection_marker)]
    new_sys = (
        existing_sys.rstrip()
        + "\n\n⚠️ REAL BIGQUERY DATA IS PROVIDED BELOW — DO NOT INVENT NUMBERS. "
        + "Analyse ONLY the real data shown here:\n\n"
        + "{{ $('" + CODE_NODE_NAME + "').item.json.bq_data }}\n\n"
        + "Row count: {{ $('" + CODE_NODE_NAME + "').item.json.row_count }}"
    )
    agent_node["parameters"]["options"]["systemMessage"] = new_sys

    nodes.append(bq_node)
    nodes.append(code_node)

    # Rebuild connections
    webhook_name = webhook_node["name"]
    agent_name = agent_node["name"]
    bq_name = bq_node["name"]
    code_name = code_node["name"]

    # Rebuild Webhook connections cleanly:
    # main[0] = [Respond to Webhook, BQ Query]  (single output carrying both)
    respond_node_name = next(
        n["name"] for n in nodes if n["type"] == "n8n-nodes-base.respondToWebhook"
    )
    connections[webhook_name] = {
        "main": [
            [
                {"node": respond_node_name, "type": "main", "index": 0},
                {"node": bq_name, "type": "main", "index": 0},
            ]
        ]
    }

    # BQ -> Code -> Agent
    connections[bq_name] = {
        "main": [[{"node": code_name, "type": "main", "index": 0}]]
    }
    connections[code_name] = {
        "main": [[{"node": agent_name, "type": "main", "index": 0}]]
    }

    return wf


def update_workflow(wf_id):
    print(f"\n{'='*60}")
    print(f"Processing: {wf_id}")

    wf = n8n_request("GET", f"/workflows/{wf_id}")
    if "error" in wf:
        print(f"  ERROR fetching: {wf}")
        return False

    name = wf.get("name", "?")
    print(f"  Name: {name}")

    sql = QUERIES[wf_id]

    updated = build_updated_workflow(wf, sql)

    payload = {
        "name": updated["name"],
        "nodes": updated["nodes"],
        "connections": updated["connections"],
        "settings": updated.get("settings", {}),
        "staticData": updated.get("staticData"),
    }

    result = n8n_request("PUT", f"/workflows/{wf_id}", payload)

    if "error" in result:
        print(f"  ERROR updating: {result}")
        return False

    node_types = [n["type"] for n in result.get("nodes", [])]
    has_bq = "n8n-nodes-base.googleBigQuery" in node_types
    has_code = "n8n-nodes-base.code" in node_types
    node_count = len(result.get("nodes", []))

    print(f"  OK -- {node_count} nodes | BQ={has_bq} | Code={has_code}")
    return True


results = {}
for wf_id in QUERIES.keys():
    ok = update_workflow(wf_id)
    results[wf_id] = ok
    time.sleep(0.5)

print(f"\n{'='*60}")
print("SUMMARY:")
ok_count = sum(1 for v in results.values() if v)
print(f"  {ok_count}/13 workflows updated successfully")
for wf_id, ok in results.items():
    status = "OK" if ok else "FAILED"
    print(f"  [{status}] {wf_id}")
