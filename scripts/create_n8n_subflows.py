#!/usr/bin/env python3
"""
Creates 7 standalone n8n sub-workflows for the Nexa KPI decision tree:
  A: ROAS & Channel Health (3-factor check → sales escalation or campaign fix)
  B: CPL Fix (channel → campaign → adset drill)
  C: CPQL Fix (channel → campaign → adset drill)
  D: Qual Ratio Fix (LP redirect if <30%, else campaign fix)
  E: Impression Share Fix (budget vs rank root cause)
  F: Creative/CTR Fix (creative fatigue detection)
  QA: QA Auditor (validates all outputs before Orchestrator)

Run: python scripts/create_n8n_subflows.py
IDs saved to: scripts/_subflow_ids.json
Next: run scripts/update_master_routing.py
"""
import json, urllib.request, urllib.error, sys, uuid, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

N8N_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIyYTZlMDMwNC0wN2RhLTRjNzktYTUwNi0zYzkyYjU5ODFiZDEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjA2Yjk1Y2YtNzJiOS00ZGM0LWIxOTAtNTY0Y2QyNzdhMDNiIiwiaWF0IjoxNzgxMTgxODU3fQ"
    ".UvVwQcF0-bW8ipJlgSTPEYe1Zg8tdJE3ZoJ-vJIFi8s"
)
BASE   = "https://qoyod.app.n8n.cloud"
MASTER = "T8icImtZFLYeCa7e"

CRED_BQ     = {"googleApi":     {"id": "kE5RxM61mQkpV21N", "name": "BigQuery (Qoyod)"}}
CRED_CLAUDE = {"anthropicApi":  {"id": "yLwrXNzxReOM4Fgn", "name": "Anthropic account"}}
CRED_ASANA  = {"httpHeaderAuth":{"id": "iUYNax4N4UkcLiQB", "name": "Asana (Qoyod)"}}
CRED_SLACK  = {"httpHeaderAuth":{"id": "YwdlGwXs943DQrfh", "name": "Slack (Qoyod)"}}

ASANA_PROJECT  = "1214135581886045"
ASANA_ASSIGNEE = "1211896896006195"
BQ_PROJECT     = "angular-axle-492812-q4"
BQ_DATASET     = "qoyod_marketing"

SETTINGS = {
    "executionOrder": "v1",
    "timezone": "Asia/Riyadh",
    "saveManualExecutions": True,
    "callerPolicy": "workflowsFromSameOwner"
}

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
def nid(n): return str(uuid.uuid5(_NS, n))

def req(method, path, body=None):
    url  = BASE + "/api/v1" + path
    data = json.dumps(body).encode() if body else None
    r    = urllib.request.Request(
        url, data=data,
        headers={"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
        return None

# ── Node builders ─────────────────────────────────────────────────────────────

def trigger(key, x=0, y=0):
    return {"id": nid(key+"_trig"), "name": "Trigger",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1, "position": [x, y], "parameters": {}}

def code(name, key, js, x=0, y=0):
    return {"id": nid(key+name), "name": name,
            "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [x, y],
            "parameters": {"mode": "runOnceForAllItems", "jsCode": js}}

def bq(name, key, sql, x=0, y=0):
    return {"id": nid(key+name), "name": name,
            "type": "n8n-nodes-base.googleBigQuery", "typeVersion": 2,
            "position": [x, y], "credentials": CRED_BQ,
            "parameters": {"operation": "executeQuery",
                           "projectId": BQ_PROJECT,
                           "sqlQuery": sql,
                           "authentication": "serviceAccount",
                           "options": {}}}

def claude(name, key, x=0, y=0):
    return {"id": nid(key+name), "name": name,
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [x, y], "credentials": CRED_CLAUDE,
            "parameters": {
                "method": "POST", "url": "https://api.anthropic.com/v1/messages",
                "authentication": "genericCredentialType",
                "genericAuthType": "anthropicApi",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "anthropic-version", "value": "2023-06-01"}]},
                "sendBody": True, "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ model:'claude-sonnet-4-6', max_tokens:2000, system:$json.system, messages:$json.messages }) }}",
                "options": {}}}

def asana(name, key, x=0, y=0):
    return {"id": nid(key+name), "name": name,
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [x, y], "credentials": CRED_ASANA,
            "parameters": {
                "method": "POST", "url": "https://app.asana.com/api/1.0/tasks",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendBody": True, "specifyBody": "json",
                "jsonBody": f"={{{{ JSON.stringify({{ data: {{ name: $json.task_name, notes: $json.task_notes, projects: ['{ASANA_PROJECT}'], assignee: '{ASANA_ASSIGNEE}', due_on: $json.due_on }} }}) }}}}",
                "options": {}}}

def ifnode(name, key, left, op, right, x=0, y=0):
    return {"id": nid(key+name), "name": name,
            "type": "n8n-nodes-base.if", "typeVersion": 2,
            "position": [x, y],
            "parameters": {"conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{"id": nid(key+name+"c"),
                                "leftValue": left, "rightValue": str(right),
                                "operator": {"type": "number", "operation": op}}],
                "combinator": "and"}}}

def ret(name, key, vals, x=0, y=0):
    return {"id": nid(key+name), "name": name,
            "type": "n8n-nodes-base.set", "typeVersion": 3.4,
            "position": [x, y],
            "parameters": {"mode": "manual",
                           "fields": {"values": [{"name": k, "stringValue": v}
                                                  for k,v in vals.items()]}}}

def build_conns(pairs):
    c = {}
    for src, dst, si, di in pairs:
        c.setdefault(src, {"main": []})
        while len(c[src]["main"]) <= si: c[src]["main"].append([])
        c[src]["main"][si].append({"node": dst, "type": "main", "index": di})
    return c

def create_wf(name, nodes, conns):
    r = req("POST", "/workflows",
            {"name": name, "nodes": nodes, "connections": conns,
             "settings": SETTINGS})
    if r and "id" in r:
        print(f"  ✓ '{name}'  id={r['id']}")
        return r["id"]
    print(f"  ✗ FAILED '{name}'")
    return None

# ── SUB-FLOW A ────────────────────────────────────────────────────────────────
def sf_a():
    k = "sfa_"
    nodes = [
        trigger(k, 0, 0),
        code("Evaluate 3 Factors", k, r"""
const d = $input.first().json;
const qual_ok   = (d.qual_rate_pct || 0) >= 45;
const cpql_ok   = (d.cpql || 999)        <= 60;
const volume_ok = (d.leads_total || 0)   >= (d.prior_leads_total || 0);
return [{json:{...d, qual_ok, cpql_ok, volume_ok, all_green: qual_ok&&cpql_ok&&volume_ok,
               today: new Date().toISOString().slice(0,10)}}];
""", 250, 0),
        ifnode("All Green?", k, "={{ $json.all_green === true ? 1 : 0 }}", "equal", 1, 500, 0),
        code("Build — Sales Escalation", k, f"""
const d=$json, t=new Date().toISOString().slice(0,10);
return [{{json:{{
  task_name:`[SALES ESCALATION] ${{d.channel}} — Qualified leads not closing (ROAS ${{d.roas}}x)`,
  task_notes:`Channel: ${{d.channel}}\\nROAS: ${{d.roas}}x (below 1x)\\n\\n3-Factor Check — ALL GREEN:\\n• Qual Rate: ${{d.qual_rate_pct}}% ≥ 45% ✅\\n• CPQL: $${{d.cpql}} ≤ $60 ✅\\n• Lead Volume: ${{d.leads_total}} vs prior ${{d.prior_leads_total}} ✅\\n\\nChannel is generating qualified leads at good cost. Deals NOT closing = sales process issue.\\n\\nAction Required:\\n→ Route specific deals to sales team for review\\n→ Do NOT reduce budget or reallocate channel\\n→ Check deal stage in HubSpot for this channel\\n\\nCreated: ${{t}} | Due: +2d | Priority: P1 | Type: Sales Escalation | Channel: ${{d.channel}} | Asset level: Channel | Action: sales-review → [performance-lead]`,
  due_on: new Date(Date.now()+2*86400000).toISOString().slice(0,10)
}}}}];
""", 750, -200),
        code("Build — Campaign Fix", k, f"""
const d=$json, t=new Date().toISOString().slice(0,10);
const issues=[];
if(!d.qual_ok)   issues.push(`Qual ${{d.qual_rate_pct}}% < 45%`);
if(!d.cpql_ok)   issues.push(`CPQL $${{d.cpql}} > $60`);
if(!d.volume_ok) issues.push(`Volume ${{d.leads_total}} < prior ${{d.prior_leads_total}}`);
return [{{json:{{
  task_name:`[ROAS FIX] ${{d.channel}} — ROAS ${{d.roas}}x, channel issues: ${{issues.join(', ')}}`,
  task_notes:`Channel: ${{d.channel}}\\nROAS: ${{d.roas}}x (below 1x)\\n\\n3-Factor Check FAILED:\\n${{issues.map(i=>'• '+i).join('\\n')}}\\n\\nAction Required:\\n→ Drill to campaign/adset level for root cause\\n→ Run CPQL/Qual sub-flows for detailed analysis\\n→ Do NOT reallocate budget until confirmed\\n\\nCreated: ${{t}} | Due: +1d | Priority: P1 | Type: ROAS Fix | Channel: ${{d.channel}} | Asset level: Channel | Action: investigate → [campaign-manager]`,
  due_on: new Date(Date.now()+1*86400000).toISOString().slice(0,10)
}}}}];
""", 750, 200),
        asana("Create Asana Task", k, 1000, 0),
        ret("Return Result", k, {
            "sub_flow": "A_ROAS",
            "status":   "={{ $json.data ? 'created' : 'error' }}",
            "channel":  "={{ $('Evaluate 3 Factors').first().json.channel }}",
            "action":   "={{ $('Evaluate 3 Factors').first().json.all_green ? 'sales_escalation' : 'campaign_fix' }}"
        }, 1250, 0)
    ]
    conns = build_conns([
        ("Trigger","Evaluate 3 Factors",0,0),
        ("Evaluate 3 Factors","All Green?",0,0),
        ("All Green?","Build — Sales Escalation",0,0),
        ("All Green?","Build — Campaign Fix",1,0),
        ("Build — Sales Escalation","Create Asana Task",0,0),
        ("Build — Campaign Fix","Create Asana Task",0,0),
        ("Create Asana Task","Return Result",0,0)
    ])
    return create_wf("Nexa · Sub-Flow A — ROAS & Channel Health", nodes, conns)

# ── SUB-FLOW B ────────────────────────────────────────────────────────────────
def sf_b():
    k = "sfb_"
    sql = f"""
SELECT channel, campaign_name, adset_name,
  ROUND(SUM(spend),2) AS spend, SUM(leads_total) AS leads,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_total),0)),2) AS cpl,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),NULLIF(SUM(leads_total),0))*100,1) AS qual_pct
FROM `{BQ_PROJECT}.{BQ_DATASET}.wide_ads`
WHERE date = DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 DAY)
  AND channel = '={{{{$input.first().json.channel}}}}'  AND leads_total > 0
GROUP BY channel,campaign_name,adset_name ORDER BY cpl DESC LIMIT 20"""
    nodes = [
        trigger(k, 0, 0),
        bq("BQ — CPL Drill", k, sql, 250, 0),
        code("Build Claude Prompt", k, r"""
const rows=$input.all().map(i=>i.json);
const ch=$('Trigger').first().json.channel, cpl=$('Trigger').first().json.cpl;
const worst=rows.filter(r=>(r.cpl||0)>25).slice(0,8);
return [{json:{
  system:`You are a paid media analyst. Analyze CPL data for ${ch}. Current CPL: $${cpl}. Scale target ≤$25, warning >$40, pause >$50. Find root cause and recommend fixes. Output JSON: {"root_cause":str,"worst_adsets":[{"adset_name":str,"cpl":num,"recommendation":str}],"channel_recommendation":str,"asana_title":str}`,
  messages:[{role:'user',content:`Channel: ${ch}\nCurrent CPL: $${cpl}\n\nAdset breakdown:\n${JSON.stringify(worst,null,2)}`}]
}}];
""", 500, 0),
        claude("Claude — CPL Analyst", k, 750, 0),
        code("Parse Claude", k, r"""
const raw=$json.content?.find(b=>b.type==='text')?.text||'{}';
const ch=$('Trigger').first().json.channel, t=new Date().toISOString().slice(0,10);
try{
  const r=JSON.parse(raw);
  return [{json:{
    task_name: r.asana_title||`[CPL FIX] ${ch} — CPL above threshold`,
    task_notes:`Channel: ${ch}\n\nRoot Cause:\n${r.root_cause||'See data'}\n\nWorst Adsets:\n${(r.worst_adsets||[]).map(a=>`• ${a.adset_name}: $${a.cpl} — ${a.recommendation}`).join('\n')}\n\nRecommendation:\n${r.channel_recommendation||'—'}\n\nCreated: ${t} | Due: +2d | Priority: P1 | Type: CPL Fix | Channel: ${ch} | Asset level: Ad Set | Action: optimize → [campaign-manager]`,
    due_on: new Date(Date.now()+2*86400000).toISOString().slice(0,10)
  }}];
}catch(e){return [{json:{task_name:`CPL Fix parse error`,task_notes:raw,due_on:t}}];}
""", 1000, 0),
        asana("Create Asana Task", k, 1250, 0),
        ret("Return Result", k, {"sub_flow":"B_CPL","status":"={{ $json.data?'created':'error' }}","channel":"={{ $('Trigger').first().json.channel }}"}, 1500, 0)
    ]
    conns = build_conns([
        ("Trigger","BQ — CPL Drill",0,0),("BQ — CPL Drill","Build Claude Prompt",0,0),
        ("Build Claude Prompt","Claude — CPL Analyst",0,0),("Claude — CPL Analyst","Parse Claude",0,0),
        ("Parse Claude","Create Asana Task",0,0),("Create Asana Task","Return Result",0,0)
    ])
    return create_wf("Nexa · Sub-Flow B — CPL Fix", nodes, conns)

# ── SUB-FLOW C ────────────────────────────────────────────────────────────────
def sf_c():
    k = "sfc_"
    sql = f"""
SELECT channel, campaign_name, adset_name,
  ROUND(SUM(spend),2) AS spend, SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(leads_qualified),0)),2) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),NULLIF(SUM(leads_total),0))*100,1) AS qual_pct
FROM `{BQ_PROJECT}.{BQ_DATASET}.wide_ads`
WHERE date = DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 1 DAY)
  AND channel = '={{{{$input.first().json.channel}}}}'  AND leads_qualified > 0
GROUP BY channel,campaign_name,adset_name ORDER BY cpql DESC LIMIT 20"""
    nodes = [
        trigger(k, 0, 0),
        bq("BQ — CPQL Drill", k, sql, 250, 0),
        code("Build Claude Prompt", k, r"""
const rows=$input.all().map(i=>i.json);
const ch=$('Trigger').first().json.channel, cpql=$('Trigger').first().json.cpql;
const worst=rows.filter(r=>(r.cpql||0)>60).slice(0,8);
return [{json:{
  system:`You are a paid media analyst. Analyze CPQL data for ${ch}. Current CPQL: $${cpql}. Scale target ≤$60, acceptable $60–$85, investigate >$85. Is this an audience, creative, LP qual, or bid issue? Output JSON: {"root_cause":str,"worst_adsets":[{"adset_name":str,"cpql":num,"qual_pct":num,"recommendation":str}],"channel_recommendation":str,"asana_title":str}`,
  messages:[{role:'user',content:`Channel: ${ch}\nCurrent CPQL: $${cpql}\n\nAdset breakdown:\n${JSON.stringify(worst,null,2)}`}]
}}];
""", 500, 0),
        claude("Claude — CPQL Analyst", k, 750, 0),
        code("Parse Claude", k, r"""
const raw=$json.content?.find(b=>b.type==='text')?.text||'{}';
const ch=$('Trigger').first().json.channel, t=new Date().toISOString().slice(0,10);
try{
  const r=JSON.parse(raw);
  return [{json:{
    task_name: r.asana_title||`[CPQL FIX] ${ch} — CPQL above $60 scale target`,
    task_notes:`Channel: ${ch}\n\nRoot Cause:\n${r.root_cause}\n\nWorst Adsets:\n${(r.worst_adsets||[]).map(a=>`• ${a.adset_name}: CPQL $${a.cpql} | Qual ${a.qual_pct}% — ${a.recommendation}`).join('\n')}\n\nRecommendation:\n${r.channel_recommendation}\n\nCreated: ${t} | Due: +2d | Priority: P1 | Type: CPQL Fix | Channel: ${ch} | Asset level: Ad Set | Action: optimize → [campaign-manager]`,
    due_on: new Date(Date.now()+2*86400000).toISOString().slice(0,10)
  }}];
}catch(e){return [{json:{task_name:`CPQL Fix parse error`,task_notes:raw,due_on:t}}];}
""", 1000, 0),
        asana("Create Asana Task", k, 1250, 0),
        ret("Return Result", k, {"sub_flow":"C_CPQL","status":"={{ $json.data?'created':'error' }}","channel":"={{ $('Trigger').first().json.channel }}"}, 1500, 0)
    ]
    conns = build_conns([
        ("Trigger","BQ — CPQL Drill",0,0),("BQ — CPQL Drill","Build Claude Prompt",0,0),
        ("Build Claude Prompt","Claude — CPQL Analyst",0,0),("Claude — CPQL Analyst","Parse Claude",0,0),
        ("Parse Claude","Create Asana Task",0,0),("Create Asana Task","Return Result",0,0)
    ])
    return create_wf("Nexa · Sub-Flow C — CPQL Fix", nodes, conns)

# ── SUB-FLOW D ────────────────────────────────────────────────────────────────
def sf_d():
    k = "sfd_"
    sql = f"""
SELECT channel, campaign_name, adset_name, destination_url,
  SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),NULLIF(SUM(leads_total),0))*100,1) AS qual_pct
FROM `{BQ_PROJECT}.{BQ_DATASET}.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY)
  AND channel = '={{{{$input.first().json.channel}}}}'  AND leads_total > 0
GROUP BY channel,campaign_name,adset_name,destination_url ORDER BY qual_pct ASC LIMIT 20"""
    nodes = [
        trigger(k, 0, 0),
        bq("BQ — Qual Drill", k, sql, 250, 0),
        ifnode("Qual < 30%?", k, "={{ $('Trigger').first().json.qual_rate_pct }}", "smallerEqual", 30, 500, 0),
        code("Build — LP Redirect Urgent", k, f"""
const rows=$input.all().map(i=>i.json);
const ch=$('Trigger').first().json.channel, q=$('Trigger').first().json.qual_rate_pct;
const t=new Date().toISOString().slice(0,10);
const worst=rows.filter(r=>(r.qual_pct||0)<30).slice(0,5);
return [{{json:{{
  task_name:`[URGENT LP REDIRECT] ${{ch}} — Qual ${{q}}% critical (< 30% threshold)`,
  task_notes:`Channel: ${{ch}}\\nQual Rate: ${{q}}% — CRITICAL\\n\\nAction (IMMEDIATE):\\n→ Redirect traffic to best same-category LP NOW\\n→ Do NOT wait for a new LP\\n\\nWorst LPs (< 30% qual):\\n${{worst.map(r=>`• ${{r.destination_url||'unknown'}} — ${{r.qual_pct}}% (${{r.leads}} leads)`).join('\\n')}}\\n\\nHandoff → CRO Specialist:\\n→ Create LP brief\\n→ Identify redirect target URL\\n→ Max 2 variable changes per test\\n\\nCreated: ${{t}} | Due: TODAY | Priority: P0 | Type: LP Redirect | Channel: ${{ch}} | Asset level: Landing Page | Action: redirect → [cro-specialist]`,
  due_on: t
}}}}];
""", 750, -200),
        code("Build — Qual Improvement", k, f"""
const rows=$input.all().map(i=>i.json);
const ch=$('Trigger').first().json.channel, q=$('Trigger').first().json.qual_rate_pct;
const t=new Date().toISOString().slice(0,10);
const low=rows.filter(r=>(r.qual_pct||0)<45).slice(0,5);
return [{{json:{{
  task_name:`[QUAL FIX] ${{ch}} — Qual rate ${{q}}% below 45% target`,
  task_notes:`Channel: ${{ch}}\\nQual Rate: ${{q}}% — Below 45% target\\n\\nLow-performing adsets/LPs:\\n${{low.map(r=>`• ${{r.adset_name}} → ${{r.destination_url||'?'}}: ${{r.qual_pct}}%`).join('\\n')}}\\n\\nPossible causes:\\n1. Audience mismatch\\n2. LP messaging vs ad promise disconnect\\n3. Wrong LP routing\\n\\nCreated: ${{t}} | Due: +2d | Priority: P1 | Type: Qual Fix | Channel: ${{ch}} | Asset level: Ad Set | Action: investigate → [campaign-manager]`,
  due_on: new Date(Date.now()+2*86400000).toISOString().slice(0,10)
}}}}];
""", 750, 200),
        asana("Create Asana Task", k, 1000, 0),
        ret("Return Result", k, {
            "sub_flow": "D_QUAL",
            "status":   "={{ $json.data?'created':'error' }}",
            "channel":  "={{ $('Trigger').first().json.channel }}",
            "action":   "={{ $('Trigger').first().json.qual_rate_pct <= 30 ? 'lp_redirect' : 'qual_fix' }}"
        }, 1250, 0)
    ]
    conns = build_conns([
        ("Trigger","BQ — Qual Drill",0,0),("BQ — Qual Drill","Qual < 30%?",0,0),
        ("Qual < 30%?","Build — LP Redirect Urgent",0,0),("Qual < 30%?","Build — Qual Improvement",1,0),
        ("Build — LP Redirect Urgent","Create Asana Task",0,0),
        ("Build — Qual Improvement","Create Asana Task",0,0),
        ("Create Asana Task","Return Result",0,0)
    ])
    return create_wf("Nexa · Sub-Flow D — Qual Ratio Fix", nodes, conns)

# ── SUB-FLOW E ────────────────────────────────────────────────────────────────
def sf_e():
    k = "sfe_"
    sql = f"""
SELECT channel, campaign_name,
  ROUND(SUM(spend),2) AS spend, SUM(impressions) AS impressions, SUM(leads_total) AS leads,
  ROUND(SAFE_DIVIDE(SUM(spend),NULLIF(SUM(impressions),0))*1000,4) AS cpm
FROM `{BQ_PROJECT}.{BQ_DATASET}.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 7 DAY)
  AND channel = '={{{{$input.first().json.channel}}}}'  AND spend > 0
GROUP BY channel,campaign_name ORDER BY spend DESC LIMIT 15"""
    nodes = [
        trigger(k, 0, 0),
        bq("BQ — IS Campaign Drill", k, sql, 250, 0),
        code("Build Claude Prompt", k, r"""
const rows=$input.all().map(i=>i.json);
const ch=$('Trigger').first().json.channel, t=new Date().toISOString().slice(0,10);
return [{json:{
  system:`You are a paid media analyst. ${ch} channel has low impression share. Analyze campaign spend and CPM to determine if IS is lost to budget or rank/quality. Output JSON: {"is_lost_to":"budget"|"rank"|"both","root_cause":str,"campaigns_to_fix":[{"campaign_name":str,"recommendation":str}],"channel_recommendation":str,"asana_title":str}`,
  messages:[{role:'user',content:`Channel: ${ch}\nDate: ${t}\n\nCampaign breakdown (last 7d):\n${JSON.stringify(rows,null,2)}`}]
}}];
""", 500, 0),
        claude("Claude — IS Analyst", k, 750, 0),
        code("Parse Claude", k, r"""
const raw=$json.content?.find(b=>b.type==='text')?.text||'{}';
const ch=$('Trigger').first().json.channel, t=new Date().toISOString().slice(0,10);
try{
  const r=JSON.parse(raw);
  return [{json:{
    task_name: r.asana_title||`[IS FIX] ${ch} — Impression Share at floor`,
    task_notes:`Channel: ${ch}\n\nIS Lost To: ${r.is_lost_to}\nRoot Cause: ${r.root_cause}\n\nCampaigns:\n${(r.campaigns_to_fix||[]).map(c=>`• ${c.campaign_name}: ${c.recommendation}`).join('\n')}\n\nRecommendation:\n${r.channel_recommendation}\n\nCreated: ${t} | Due: +2d | Priority: P2 | Type: IS Fix | Channel: ${ch} | Asset level: Campaign | Action: optimize → [campaign-manager]`,
    due_on: new Date(Date.now()+2*86400000).toISOString().slice(0,10)
  }}];
}catch(e){return [{json:{task_name:`IS Fix parse error`,task_notes:raw,due_on:t}}];}
""", 1000, 0),
        asana("Create Asana Task", k, 1250, 0),
        ret("Return Result", k, {"sub_flow":"E_IS","status":"={{ $json.data?'created':'error' }}","channel":"={{ $('Trigger').first().json.channel }}"}, 1500, 0)
    ]
    conns = build_conns([
        ("Trigger","BQ — IS Campaign Drill",0,0),("BQ — IS Campaign Drill","Build Claude Prompt",0,0),
        ("Build Claude Prompt","Claude — IS Analyst",0,0),("Claude — IS Analyst","Parse Claude",0,0),
        ("Parse Claude","Create Asana Task",0,0),("Create Asana Task","Return Result",0,0)
    ])
    return create_wf("Nexa · Sub-Flow E — Impression Share Fix", nodes, conns)

# ── SUB-FLOW F ────────────────────────────────────────────────────────────────
def sf_f():
    k = "sff_"
    sql = f"""
WITH cur AS (
  SELECT channel, utm_content, adset_name,
    ROUND(SAFE_DIVIDE(SUM(clicks),NULLIF(SUM(impressions),0))*100,3) AS ctr,
    SUM(impressions) AS imps, SUM(leads_total) AS leads,
    ROUND(SAFE_DIVIDE(SUM(leads_qualified),NULLIF(SUM(leads_total),0))*100,1) AS qual_pct
  FROM `{BQ_PROJECT}.{BQ_DATASET}.wide_ads`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 7 DAY)
    AND channel = '={{{{$input.first().json.channel}}}}'
  GROUP BY channel,utm_content,adset_name
),
pri AS (
  SELECT channel, utm_content,
    ROUND(SAFE_DIVIDE(SUM(clicks),NULLIF(SUM(impressions),0))*100,3) AS ctr
  FROM `{BQ_PROJECT}.{BQ_DATASET}.wide_ads`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 14 DAY)
                 AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'),INTERVAL 8 DAY)
    AND channel = '={{{{$input.first().json.channel}}}}'
  GROUP BY channel,utm_content
)
SELECT c.channel,c.utm_content,c.adset_name,
  c.ctr AS ctr_current, p.ctr AS ctr_prior,
  ROUND(SAFE_DIVIDE(c.ctr-p.ctr,NULLIF(p.ctr,0))*100,1) AS ctr_change_pct,
  c.imps,c.leads,c.qual_pct
FROM cur c LEFT JOIN pri p USING(channel,utm_content)
WHERE c.imps>500 ORDER BY ctr_change_pct ASC LIMIT 15"""
    nodes = [
        trigger(k, 0, 0),
        bq("BQ — CTR Creative Drill", k, sql, 250, 0),
        code("Build Claude Prompt", k, r"""
const rows=$input.all().map(i=>i.json);
const ch=$('Trigger').first().json.channel, t=new Date().toISOString().slice(0,10);
const fatigued=rows.filter(r=>(r.ctr_change_pct||0)<-20).slice(0,8);
return [{json:{
  system:`You are a creative strategist analyst. ${ch} channel shows CTR decay (creative fatigue). Identify fatigued creatives and recommend rotation. Output JSON: {"fatigued_creatives":[{"utm_content":str,"ctr_drop":num,"adset_name":str,"action":"pause"|"refresh"}],"channel_recommendation":str,"new_creative_brief":str,"asana_title":str}`,
  messages:[{role:'user',content:`Channel: ${ch}\nDate: ${t}\n\nCreatives with CTR decline:\n${JSON.stringify(fatigued,null,2)}`}]
}}];
""", 500, 0),
        claude("Claude — Creative Analyst", k, 750, 0),
        code("Parse Claude", k, r"""
const raw=$json.content?.find(b=>b.type==='text')?.text||'{}';
const ch=$('Trigger').first().json.channel, t=new Date().toISOString().slice(0,10);
try{
  const r=JSON.parse(raw);
  return [{json:{
    task_name: r.asana_title||`[CREATIVE REFRESH] ${ch} — CTR decay detected`,
    task_notes:`Channel: ${ch}\n\nFatigued Creatives:\n${(r.fatigued_creatives||[]).map(c=>`• ${c.utm_content} (${c.adset_name}): CTR -${c.ctr_drop}% → ${c.action}`).join('\n')}\n\nNew Creative Brief:\n${r.new_creative_brief||'—'}\n\nRecommendation:\n${r.channel_recommendation}\n\nCreated: ${t} | Due: +3d | Priority: P2 | Type: Creative Refresh | Channel: ${ch} | Asset level: Ad | Action: brief → [creative-strategist]`,
    due_on: new Date(Date.now()+3*86400000).toISOString().slice(0,10)
  }}];
}catch(e){return [{json:{task_name:`Creative Fix parse error`,task_notes:raw,due_on:t}}];}
""", 1000, 0),
        asana("Create Asana Task", k, 1250, 0),
        ret("Return Result", k, {"sub_flow":"F_CREATIVE","status":"={{ $json.data?'created':'error' }}","channel":"={{ $('Trigger').first().json.channel }}"}, 1500, 0)
    ]
    conns = build_conns([
        ("Trigger","BQ — CTR Creative Drill",0,0),("BQ — CTR Creative Drill","Build Claude Prompt",0,0),
        ("Build Claude Prompt","Claude — Creative Analyst",0,0),("Claude — Creative Analyst","Parse Claude",0,0),
        ("Parse Claude","Create Asana Task",0,0),("Create Asana Task","Return Result",0,0)
    ])
    return create_wf("Nexa · Sub-Flow F — Creative & CTR Fix", nodes, conns)

# ── QA AUDITOR ────────────────────────────────────────────────────────────────
def qa_auditor():
    k = "qa_"
    nodes = [
        trigger(k, 0, 0),
        code("Validate Output", k, r"""
const inp=$input.first().json;
const errors=[];
if(!inp.sub_flow)       errors.push('Missing sub_flow identifier');
if(!inp.channel)        errors.push('Missing channel field');
if(inp.status!=='created'&&inp.status!=='ok'&&inp.status!=='QA_PASSED')
                        errors.push(`Upstream status: ${inp.status||'unknown'}`);
const notes=(inp.task_notes||'').toLowerCase();
if(notes.includes(' sar')&&!notes.includes('usd'))
                        errors.push('Spend figures may be in SAR — must be USD');
if(notes.includes('auto-executed')||notes.includes('auto-applied'))
                        errors.push('Output claims auto-execution — requires ✅ approval');
const passed=errors.length===0;
return [{json:{
  qa_status: passed?'QA_PASSED':'QA_FAILED',
  errors, validated_at: new Date().toISOString(),
  agent: inp.sub_flow||'unknown', channel: inp.channel||'unknown',
  original_input: inp
}}];
""", 250, 0),
        ifnode("All Checks Passed?", k, "={{ $json.errors.length }}", "equal", 0, 500, 0),
        ret("QA_PASSED", k, {
            "qa_result":     "QA_PASSED",
            "sub_flow":      "={{ $('Validate Output').first().json.agent }}",
            "channel":       "={{ $('Validate Output').first().json.channel }}",
            "validated_at":  "={{ $('Validate Output').first().json.validated_at }}"
        }, 750, -100),
        ret("QA_FAILED", k, {
            "qa_result":     "QA_FAILED",
            "sub_flow":      "={{ $('Validate Output').first().json.agent }}",
            "channel":       "={{ $('Validate Output').first().json.channel }}",
            "errors":        "={{ JSON.stringify($('Validate Output').first().json.errors) }}",
            "validated_at":  "={{ $('Validate Output').first().json.validated_at }}"
        }, 750, 100)
    ]
    conns = build_conns([
        ("Trigger","Validate Output",0,0),
        ("Validate Output","All Checks Passed?",0,0),
        ("All Checks Passed?","QA_PASSED",0,0),
        ("All Checks Passed?","QA_FAILED",1,0)
    ])
    return create_wf("Nexa · QA Auditor", nodes, conns)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Creating Nexa KPI Sub-Workflows ===\n")
    ids = {}
    print("--- Sub-Flow A: ROAS & Channel Health ---")
    ids["A"] = sf_a()
    print("--- Sub-Flow B: CPL Fix ---")
    ids["B"] = sf_b()
    print("--- Sub-Flow C: CPQL Fix ---")
    ids["C"] = sf_c()
    print("--- Sub-Flow D: Qual Ratio Fix ---")
    ids["D"] = sf_d()
    print("--- Sub-Flow E: Impression Share Fix ---")
    ids["E"] = sf_e()
    print("--- Sub-Flow F: Creative & CTR Fix ---")
    ids["F"] = sf_f()
    print("--- QA Auditor ---")
    ids["QA"] = qa_auditor()

    print("\n=== Summary ===")
    for k,v in ids.items():
        status = "✓" if v else "✗"
        print(f"  {status} {k}: {v}")

    out = os.path.join(os.path.dirname(__file__), "_subflow_ids.json")
    with open(out, "w") as f:
        json.dump(ids, f, indent=2)
    print(f"\nIDs saved to: {out}")
    print("Next step: run scripts/update_master_routing.py")
