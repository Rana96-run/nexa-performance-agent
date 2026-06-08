# CRITICAL KPI RULES — RE-READ BEFORE EVERY ANALYSIS

These are non-negotiables that the agent has historically violated. They
are repeated here in compact form for unmissable re-checking.

## 1. NEVER use `campaigns_daily.leads` as a leads metric

The column exists in the schema because channels (Bing, Meta, etc.) report
their own conversion counts. **These are NOT real leads.** For
WebsiteTraffic-objective campaigns specifically, the channel often counts
page visits as conversions.

**Caught violations (don't repeat these):**

- **2026-05-19 (Rana)** — claimed Bing_WebsiteTraffic_Search_AR_Generic
  was a top performer at $1.48 CPL (1,157 channel-reported "leads" for
  $1,711 spend). Reality on HubSpot side: 31 leads / 9 SQLs → $190 CPQL
  (worst campaign, should pause).

**Correct pattern (mandatory for any analysis touching leads/SQLs):**

```sql
WITH hs AS (
  SELECT
    LOWER(lead_utm_campaign) AS campaign_key,
    SUM(leads_total)     AS leads,
    SUM(leads_qualified) AS sqls
  FROM hubspot_leads_module_daily
  WHERE date BETWEEN ... AND ...
  GROUP BY campaign_key
),
spend AS (
  SELECT campaign_name, SUM(spend) AS spend, SUM(clicks) AS clicks
  FROM campaigns_daily
  WHERE channel = '...' AND date BETWEEN ...
  GROUP BY campaign_name
)
SELECT s.*, hs.leads, hs.sqls,
       SAFE_DIVIDE(s.spend, hs.leads) AS cpl,
       SAFE_DIVIDE(s.spend, hs.sqls)  AS cpql
FROM spend s LEFT JOIN hs ON LOWER(s.campaign_name) = hs.campaign_key
```

## 2. Pre-execution checklist for ANY new analysis script

Before writing a Python/SQL script that touches campaign performance, the
agent MUST mentally verify ALL of these:

1. **Does this script report leads, SQLs, CPL, CPQL, or qualification rate?**
   - If yes → the leads side MUST come from `hubspot_leads_module_daily`
   - If using `campaigns_daily` at all, it can ONLY supply spend/clicks/impressions/IS

2. **Is there a pre-aggregate-then-join step?**
   - Joining campaigns_daily to hubspot_leads_module_daily without pre-agg
     causes spend fan-out (multiplies spend by matching HS rows).
   - Always: `WITH hs AS (SELECT ... GROUP BY ...) ... JOIN hs ON ...`

3. **Is the date window explicit?**
   - Never "last 7 days" in narrative. Always `YYYY-MM-DD to YYYY-MM-DD`
     so HubSpot UI verification is possible.

4. **For ad-level analysis (Meta/Snap/TikTok):**
   - Channel-reported conversions on ads_daily are also unreliable.
   - Join to `hubspot_leads_module_daily` on `lead_utm_content` for the
     leads count, not on the ads_daily `leads` column.

## 3. NEVER invent campaign names — match the existing channel convention

The CLAUDE.md naming convention is `{Channel}_{Type}_{Language}_{Product}_{Audience}`,
but the actual tokens used differ PER CHANNEL. Before creating any new campaign,
**query the existing campaigns on that channel** and match the in-use pattern.

**Caught violations (don't repeat):**

- **2026-05-19 (Rana)** — created TikTok campaign as `Tiktok_WebForm_AR_Qawaem236`.
  The actual TikTok convention is `Tiktok_{Type}_{Audience descriptors}_{Product}_{Format}`
  where Type is `Conversion` or `LeadGen` and Format is `Websiteform` or `Instantform`.
  Real existing campaigns:
    - `Tiktok_Conversion_Prospecting_Interests_Invoice_Sectors_Websiteform`
    - `Tiktok_LeadGen_Broad_Invoice_Websiteform`
    - `Tiktok_Conversion_BOY_Prospecting_Broad_Websiteform`
  Correct name: `Tiktok_Conversion_Prospecting_Interests_FinancialStatemnt_Websiteform`

**Per-channel naming tokens to reference (queried 2026-05-19):**

| Channel | Pattern | Type tokens | Format tokens |
|---|---|---|---|
| Google Ads | `Google_{Type}_{Lang}_{Product}_{Audience}` | Search / PMax / Display | Broad / Interests / Lookalike / Retargeting |
| Microsoft Ads | `Bing_{Type}_{Lang}_{Product}` | Search / WebsiteTraffic | (no audience token in current portfolio) |
| Meta | `Meta_{Type}_{Lang}_{Product}_{Audience}` | LeadGen / Conversion | Interests / Lookalike / Retargeting / Broad |
| Snapchat | `Snapchat_{Type}_{Lang}_{Product}_{Audience}` | LeadGen | Interests / Lookalike / Broad |
| TikTok | `Tiktok_{Type}_{Audience descriptors}_{Product}_{Format}` | Conversion / LeadGen / Awareness | Websiteform / Instantform / Conversion LP |

**Pre-execution check (mandatory before creating ANY new campaign):**

```sql
-- KPI-RULE-BYPASS — just a listing query, not analyzing leads
SELECT DISTINCT campaign_name
FROM campaigns_daily
WHERE channel = '<target_channel>'
  AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
ORDER BY campaign_name
LIMIT 50
```

Then pick the token set that matches >50% of existing campaigns. NEVER invent a new token unless you have user approval.

## 4. UTM tracking is at ACCOUNT level — never override at campaign level without reason

The UTM tracking infrastructure lives at the **customer (account) level**
in Google Ads:
  - `customer.tracking_url_template` — the main template with `{lpurl}`
    and standard UTMs (source, medium, campaign, content, audience, term)
    plus `hsa_*` fields for HubSpot ingestion
  - `customer.final_url_suffix` — IDs: `campaign_id={campaignid}&ad_group_id={adgroupid}&ad_id={creative}`

All campaigns INHERIT both. Campaign-level overrides cause duplicate UTMs
in URLs if they re-state what's already in account-level template.

**Caught violation:**

- **2026-05-20** — my daily audit flagged 3 compliance campaigns as
  "missing UTM suffix" (because campaign-level was empty). I auto-fixed
  by applying STANDARD_UTM_SUFFIX at campaign level — both accounts
  already had full account-level tracking. My fix caused duplicate UTMs
  in click URLs (utm_campaign twice). Reverted by clearing campaign-level
  final_url_suffix + url_custom_parameters on the 4 affected campaigns.

**Rule:**
1. Before flagging "missing UTM" check `customer.final_url_suffix` AND
   `customer.tracking_url_template` FIRST. If either is set at account
   level, campaigns inherit.
2. Only set campaign-level `final_url_suffix` if account-level is unset
   OR a genuinely different tracking is needed.
3. The canonical STANDARD_UTM_SUFFIX in `executors/google_ads.py` is the
   IDEAL. The team's actual setup may differ — match what's deployed.

**Per-channel UTM setup actually deployed (queried 2026-05-20):**

- **Google Ads (both accounts):** UTM tracking at **ACCOUNT level** via
  `customer.tracking_url_template` + `customer.final_url_suffix`. Campaigns
  inherit. NEVER set campaign-level overrides — duplicate UTMs.

- **Microsoft Ads (both accounts):** UTM tracking at **CAMPAIGN level** —
  each campaign has its own `TrackingUrlTemplate` with the canonical pattern:
  ```
  {lpurl}?utm_source=Bing&utm_medium=ppc&utm_audience={_adgroup}
  &utm_content={_adname}&utm_term={keyword}&utm_campaign={_campaign}
  &hsa_acc=1513020554&hsa_cam={campaignid}&hsa_grp={adgroupid}&hsa_ad={creative}
  ```
  Each campaign needs custom params: `campaign`, `adgroup`, `adname` (referenced
  as `{_campaign}` etc. — the underscore is the brace syntax marker, not part
  of the key). `FinalUrlSuffix` stays EMPTY on Bing — the suffix isn't used,
  everything is in the tracking template.

- **TikTok:** UTM not in tracking templates — uses standard `utm_source=tiktok`
  added at ad level via URL params on the LP link.

**Migration consideration:** Bing could be upgraded to account-level matching
Google's pattern, but that touches all 13 active campaigns and risks breaking
any per-campaign customization. Document the decision before doing it.

## 5. No anonymous agents — every action is seat-owned (non-negotiable)

**Rule:** Every task — analysis, code change, review, deploy, Slack post, Asana task — must
be performed by a **named seat agent** (growth-analyst, developer, marketing-ops,
performance-lead, campaign-manager, creative-strategist, cro-specialist, ui-ux-designer)
routed by `ai-orchestrator`. Anonymous agents (workflow task workers with no `agentType`)
are **never** the execution layer for real work.

**Why this matters:** Anonymous workers have no persona, no playbook, no memory, no domain
guardrails. They will invent field names, skip pre-aggregation checks, miss KPI rules, and
produce output the team can't trust. Named seats bring accumulated domain knowledge and are
accountable by role.

**How to apply:**
- In `Workflow()` scripts: always set `agentType` on `agent()` calls that do real work.
  Use anonymous `agent()` only for mechanical transforms (parse a file, build a string).
- In direct `Agent` tool calls: always specify `subagent_type` matching the seat owner.
- `ai-orchestrator` routes first, then seats execute in parallel or in the defined
  handoff chain (`cro-specialist → ui-ux-designer → developer`).
- If a task spans two seats, the orchestrator **sequences** them — never merges into one
  anonymous blob.

**Gate check (pre-workflow):** Before launching any Workflow, confirm:
1. Every `agent()` call that reads/writes/analyses real data has `agentType` set to a named seat.
2. Anonymous `agent()` calls are limited to pure data transforms with no domain judgment.
3. `ai-orchestrator` is the first and last agent — routes in, gates out.

**Caught violation (2026-06-09):** Codebase review was launched with 5 anonymous scan workers
labelled by "dimension" (dead-refs, views-correctness, schedulers, adset-fanout, general-stale).
No seat ownership, no playbook context, no accountability. Rebuilt correctly with
growth-analyst + developer + marketing-ops as named seats, routed by ai-orchestrator.

## 6. Self-check after writing a script — before running

Before executing any new analysis script, scan the SQL for:
- `SELECT .* leads .* FROM .* campaigns_daily` → VIOLATION
- `SELECT .* qualified .* FROM .* campaigns_daily` (column doesn't exist anyway, but flag pattern) → VIOLATION
- `SELECT .* conversions .* FROM .* (campaigns_daily|ads_daily)` and reporting it as "leads" → VIOLATION

If found → rewrite using the WITH-hs-pre-agg pattern above.
