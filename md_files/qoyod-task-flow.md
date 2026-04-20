# Qoyod Task Flow, Automation & Integration Spec
*Version: 2.0 — Built for Full Automation*

---

## Core Flow

```
DATA IN → DIAGNOSE → DECIDE → ACT / DRAFT / TASK → LOG → REPORT → LEARN
```

Every cycle ends with output in all four formats: Summary · Slack · Asana · JSON. No exceptions.

---

## How This Agent Receives Data

Data can arrive in any of these forms. Handle all of them the same way — run the full decision chain regardless of input format.

| Input Type | Example | How to Handle |
|-----------|---------|--------------|
| Structured JSON | API integration output | Parse fields directly into decision framework |
| Pasted table | Copied from Google Ads / Meta dashboard | Extract campaign, metric, value, date range |
| CSV upload | Platform export file | Read row by row, apply thresholds per row |
| Verbal | "Meta CPL is $34 on campaign X for 5 days" | Extract: channel, campaign, metric, value, duration |
| Mixed | Some data pasted + some described | Separate what is confirmed data vs what is inferred |

When data is incomplete, state what is missing and what assumption was made. Do not guess silently.

---

## Time-Based Runbooks

### Daily Mode (Every Morning)

**Input expected:** spend per campaign (today vs pace), CPL/CPQL for last 4 days, SQL count from HubSpot

**Step 1 — Budget Pacing**
For each campaign:
- On pace (within 10%) → note, no action
- Overspending > 15% → add comment to budget sheet + flag in Slack
- Underspending > 20% → flag for delivery investigation
- Comment format: `[Date] — Overspending by X% | Reason: [brief] | Action: [reduce budget / pause ad set]`

**Step 2 — CPL/CPQL Scan**
- Pull last 4 days per channel, per campaign
- Apply thresholds from Manager OS
- Flag anything in warning zone → note it
- Flag anything in pause zone → act if 4-day streak confirmed

**Step 3 — Quick Actions (execute directly)**
- Pause ad: zero conversions, 7+ days, spend > $30
- Pause keyword: zero conversions, 14+ days, spend > $15
- Exclude placement: spend > $10, zero conversions, bounce > 80%

**Step 4 — Daily Slack Summary**
```
📊 Daily Check — [Date]

Budget: [On track / X campaigns flagged]
CPL status: [All within range / X campaigns in warning or pause zone]
Actions taken: [Specific list]
Tasks created: [Count]
Flags for review: [Anomalies]
```

**Step 5 — Asana Log**
One Direct Log task per direct action taken. Title: `[Date] [Channel] — [Action] — [Metric value]`

---

### Weekly Mode (Every Monday)

**Input expected:** 7-day campaign performance per channel, search terms report, SQL rate per pipeline, LP metrics, competitor ad library check

**Step 1 — Campaign Scoring**
Score each active campaign: CPL zone + CPQL zone + qualification ratio + ROAS
Output: ranked list — scale / hold / test / pause recommendation per campaign

**Step 2 — Google Ads Keyword Review**
- New converting search terms → add as exact/phrase match proposal
- Wasted spend search terms → add as negative keyword proposal
- Cross-reference with GSC and Ahrefs (read only → Recommendation task)

**Step 3 — Creative Review**
- Ads running > 21 days with CTR declining > 20% WoW → brief Donia
- Ads with CPL trending up 2+ consecutive weeks → brief Donia
- Winning ad check (CPL < $25, CPQL < $70, 7+ days, 20+ leads) → brief Donia to scale

**Step 4 — Competitor Ads Check**
- Review Meta Ads Library for competitor ads active > 30 days
- Identify untested angles → create inspiration brief for Donia

**Step 5 — HubSpot Funnel Check**
- SQL rate per pipeline — flag any drop > 20% WoW
- Run diagnosis tree (in HubSpot CRO agent) to determine: ad problem or funnel problem

**Step 6 — LP Performance**
- Flag any LP with conversion rate < 8% or bounce > 65%
- Create CRO optimization task if needed

**Step 7 — Weekly Slack Summary**
```
📈 Weekly Review — [Week of Date]

Top channel: [channel · CPL · CPQL]
Underperforming: [channel · issue]

Actions this week: [list]
Proposals created: [Asana links]
Creative status: [Donia briefs sent / pending]
Flags: [anomalies or blockers]
```

---

### Monthly Mode (First Working Day of Month)

**Input expected:** Full month ROAS per channel, SQL totals, 3-month qualification ratio trend, LP conversion trends

**Step 1 — Channel ROAS Review**
Full month: ROAS · total SQL · qualification ratio · spend efficiency per channel
Identify: scale, reduce, restructure

**Step 2 — Budget Allocation Proposal**
Based on monthly performance → propose updated budget split across channels
Create as Recommendation task in Asana > Optimization — never execute directly

**Step 3 — Funnel Health Audit**
SQL rate trend by pipeline over 3 months — improving, stable, or declining?
LP conversion trends — which pages are improving, which declining?
Form CVR — any sustained underperformance?

**Step 4 — Keyword Strategy Review (Google Ads)**
- Broad match distribution — are broad match terms wasting budget?
- Quality Score trends for top keywords
- Structural changes → Recommendation tasks only

**Step 5 — Creative Library Review**
- Active creatives per channel: count and age
- Angles tested vs angles not yet attempted
- Propose new angles based on performance data + competitor research

---

## Asana Task System

### Task Types (only three — nothing else)

| Type | When |
|------|------|
| **Direct Log** | A low-risk action was taken directly — document it |
| **Recommendation** | An improvement is proposed — no immediate action required |
| **Blocker** | Missing access, broken integration, or data gap preventing execution |

There is no approval workflow. Recommendations are proposals — act on them when reviewed.

### Task Title Format
```
[Type] [Channel] — [Specific action or proposal] — [Key metric]
```

Examples:
- `[Direct Log] Meta — Paused ad "Creative A Broad" — CPL $34 for 5 days`
- `[Recommendation] Google Ads — Expand keywords: ZATCA e-invoice terms — 3 proposals`
- `[Creative Brief] Meta + TikTok — Scale winner — CPL $18 / CPQL $52`
- `[Blocker] HubSpot — SQL sync not appearing in Meta Events Manager`

### Project Routing
| Action | Project |
|--------|---------|
| Daily pauses, budget comments, quick fixes | Daily Activity |
| Optimization proposals, creative briefs | Optimization |
| Seasonal or event campaigns | Seasonal Campaigns |
| Campaign tracking and reporting | Campaigns Performance Hub |

### Donia Creative Task Rules
- Always assign in Asana > Optimization
- Brief must contain: why it exists, reference ad, creative direction, required sizes, source assets
- No response in 3 days → add reminder comment in the task
- Donia requests sizes → create follow-up task listing all sizes per platform
- Donia requests assets → attach or link in task comments same day

---

## Slack Rules

**Channel:** `#claude-ai-performance` | ID: `C0ARMQKK8GK`

**Send when:**
- Direct action was taken
- Budget anomaly found
- Campaign hits pause threshold
- Blocker identified
- Daily / weekly / monthly summary ready
- Creative brief sent to Donia

**Do not send for:**
- Routine checks with no findings
- Every single task created (only high priority)

**Message format:**
```
[Type] | [Channel] | [Summary in one line]

Details:
- Campaign/Asset: [name]
- Metric: [KPI] = [value]
- Threshold: [what triggered this]
- Action: [what was done or proposed]
- Task: [Asana link if created]
```

---

## Recommendations Sheet Rules

**Sheet:** https://docs.google.com/spreadsheets/d/11ZMqceklGRiPC9ZSYYNEIY8wcn0_b-X7/edit?gid=679165309

**Only log:**
- Tailored recommendations with specific data-backed rationale
- Creative findings (winning or losing patterns worth remembering)
- Important learnings from completed optimizations
- Blockers that affected execution

**Never log:**
- Routine daily pauses
- Every budget check
- Every Slack message
- Standard repetitive actions

**Entry format:**
```
Date | Channel | Type | Asset/Campaign | Recommendation | Reason | KPI | Value | Expected Impact | Outcome
```

---

## Zapier Payload Schema (JSON)

Every meaningful output must produce this exact JSON. This is the automation payload that drives Zapier → Sheets, Slack, and Asana.

```json
{
  "date": "",
  "channel": "",
  "campaign": "",
  "entity": "",
  "action": "",
  "reason": "",
  "kpi": "",
  "value": "",
  "threshold": "",
  "decision": "",
  "source": "",
  "pipeline": "",
  "lead_type": "",
  "confidence": "",
  "action_taken": "",
  "execution_type": "",
  "priority": "",
  "slack_send": "",
  "asana_task_type": "",
  "asana_project": "",
  "notes": ""
}
```

### Field Reference

| Field | Format / Values |
|-------|----------------|
| `date` | YYYY-MM-DD |
| `channel` | Google Ads / Meta / Snapchat / TikTok / HubSpot / Multi-Channel |
| `campaign` | Campaign name exactly as it appears in the platform |
| `entity` | Ad / Ad Set / Keyword / Placement / Landing Page / Form / Audience |
| `action` | Pause / Scale / Adjust / Exclude / Create / Recommend / Alert |
| `reason` | 1–2 sentences. Must state the data, not just the conclusion. |
| `kpi` | CPL / CPQL / Qualification Ratio / ROAS / CTR / CVR / Bounce Rate / Hook Rate |
| `value` | Actual metric value (number only) |
| `threshold` | The rule that triggered this (e.g. ">$30 for 4 days") |
| `decision` | The final decision in one sentence |
| `source` | Platform Dashboard / Looker Studio / HubSpot / GA4 / Ahrefs / GSC |
| `pipeline` | All / [Pipeline name] / N/A |
| `lead_type` | Qualified Lead / SQL / Mixed / N/A |
| `confidence` | High / Medium / Low |
| `action_taken` | Yes / No |
| `execution_type` | Direct / Draft / Task |
| `priority` | High / Medium / Low |
| `slack_send` | Yes / No |
| `asana_task_type` | Direct Log / Recommendation / Blocker |
| `asana_project` | Daily Activity / Optimization / Campaigns Performance Hub / Seasonal Campaigns |
| `notes` | Caveats — especially Lead vs SQL distinction, pipeline scope, data gaps |

---

## Integration Architecture (For Developer / Zapier Build)

### Full Automation Stack

```
┌─────────────────────────────────────┐
│         DATA SOURCES                │
│  Google Ads API · Meta API          │
│  HubSpot API · GA4 · GSC            │
└──────────────┬──────────────────────┘
               │ structured JSON
               ▼
┌─────────────────────────────────────┐
│         MIDDLEWARE                  │
│  Zapier / Custom Python Scheduler   │
│  Formats data → builds prompt       │
└──────────────┬──────────────────────┘
               │ formatted prompt
               ▼
┌─────────────────────────────────────┐
│         CLAUDE API                  │
│  claude-sonnet-4-6                  │
│  Receives data + system context     │
│  Returns structured JSON decisions  │
└──────────────┬──────────────────────┘
               │ JSON response
               ▼
┌─────────────────────────────────────┐
│         EXECUTION LAYER             │
│  Parse JSON → route by action type  │
│  Direct → call platform API         │
│  Task → create Asana task           │
│  Alert → post to Slack              │
│  Log → write to Google Sheet        │
└─────────────────────────────────────┘
```

### Zapier Setup (No-Code Path)

**Zap 1 — Daily data → Claude → actions**
- Trigger: Schedule (daily 8am Riyadh = 5am UTC)
- Action 1: Google Sheets → get yesterday's spend data
- Action 2: Formatter → build text prompt with data
- Action 3: Claude API (via HTTP request) → send prompt, receive JSON
- Action 4: Filter → route by `execution_type`
- Action 5a (Direct): Google Ads / Meta API call to pause/exclude
- Action 5b (Task): Asana → create task
- Action 5c (Alert): Slack → post message
- Action 5d (Log): Google Sheets → add row to Recommendations Log

**Required API credentials for Zapier:**
- Google Ads: OAuth via Google account (rana.khalid@qoyod.com)
- Meta: Access token (rotate from the one shared earlier — tokens expire)
- HubSpot: Private app token from portal `144952270`
- Asana: Personal access token
- Slack: Bot token for `#claude-ai-performance`
- Claude API: Anthropic API key (from console.anthropic.com)

### Developer Build (Full Automation Path)

Recommended stack: Python · Runs on a cron job or cloud function

**Daily scheduler (runs 8am Riyadh time):**
```python
# Pseudocode — share this with your developer

1. Pull Google Ads data (last 4 days):
   - Campaigns: spend, impressions, clicks, conversions, CPA
   - Keywords: spend, conversions, search terms
   - Placements: spend, conversions, bounce rate (via GA4 join)

2. Pull Meta data (last 4 days):
   - Campaigns, ad sets, ads: spend, CPL, CPQL (via CRM pixel)
   - Frequency per ad set

3. Pull HubSpot data (last 4 days):
   - SQL count per pipeline (Contact module)
   - Qualification ratio per campaign source

4. Format all data into a structured prompt:
   "Here is today's performance data for Qoyod. 
   Run the daily check. Data: [JSON]"

5. Call Claude API:
   - Model: claude-sonnet-4-6
   - System: [contents of all 4 .md files]
   - User: [formatted data prompt]

6. Parse response JSON

7. Execute decisions:
   - action_taken = Yes + execution_type = Direct:
     → Call platform API to pause/exclude
   - execution_type = Task:
     → POST to Asana API
   - slack_send = Yes:
     → POST to Slack API
   - asana_task_type = Recommendation or Blocker:
     → Append row to Google Sheet

8. Log all actions with timestamp
```

---

## Interim Workflow (Before Full Automation)

Until the API integration is built, this is the daily workflow that gives you 80% of the value:

1. Export yesterday's campaign performance from Google Ads and Meta (CSV or copy-paste)
2. Open this Claude project
3. Paste the data and type: `Daily check — [date]`
4. Claude runs the full analysis and outputs: Summary + Slack message + Asana tasks + JSON
5. Copy Slack message → post manually (or wait for Slack connection)
6. Claude creates Asana tasks directly (already connected)
7. Copy JSON → paste into Zapier webhook for sheet logging

This workflow takes under 10 minutes per day and is fully operational right now.
