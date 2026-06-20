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
be performed by a **named seat agent** (growth-analyst, developer, project-coordinator,
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
growth-analyst + developer + project-coordinator as named seats, routed by ai-orchestrator.

## 6. Self-check after writing a script — before running

Before executing any new analysis script, scan the SQL for:
- `SELECT .* leads .* FROM .* campaigns_daily` → VIOLATION
- `SELECT .* qualified .* FROM .* campaigns_daily` (column doesn't exist anyway, but flag pattern) → VIOLATION
- `SELECT .* conversions .* FROM .* (campaigns_daily|ads_daily)` and reporting it as "leads" → VIOLATION

If found → rewrite using the WITH-hs-pre-agg pattern above.

Also check these three before writing any recommendation or query:

**Campaign type check (before applying CPQL/CPA targets):**
- Does the campaign name match `config.py::AWARENESS_PATTERNS`?
  (`impressionshare`, `impression_share`, `websitetraffic`, `reach`)
- If yes → **STOP. Do NOT compute CPQL, do NOT recommend tCPA, do NOT flag as "drain".**
  KPI = IS% (target ≥ 25%). Zero leads is acceptable. Budget control only.
- If no → proceed with CPQL zones.

**LOWER/TRIM GROUP BY check (before writing any CTE that feeds a case-insensitive join):**
- Is this CTE the RIGHT side of a `LOWER(TRIM(...))` join predicate?
- If yes → the CTE MUST also GROUP BY `LOWER(TRIM(the_key_column))`, not the raw column.
  Grouping by raw casing while joining on normalized casing fans the left side.
  Rule: `LOWER(TRIM())` join demands a `LOWER(TRIM())`-grouped right side.

**Per-channel reconciliation reminder (after any view or CTE change touching leads):**
- An org-wide total reconciliation is NOT sufficient. Run per-channel ratio:
  `v_ad/adset_performance leads` vs `hubspot_leads_module_daily` by channel.
  Bar: ratio ≤ 1.05 on EVERY paid channel (google_ads, meta, snapchat, tiktok, microsoft_ads).
  A clean Google Ads total can mask 2× over-count on smaller channels.
  Use `scripts/reconcile_views.py` for the automated check.

---

## n8n SQL rules (non-negotiable — enforced by kpi_rule_guard.py)

These apply to every BigQuery node in every n8n workflow. Violations here
caused 11 bugs across 6 workflows (discovered 2026-06-18).

### NEVER use `wide_ads` for campaign-level or channel-level KPIs

`wide_ads` attributes leads per ad via `utm_content` on exact date match —
~39% of leads are dropped. It is an ad-grain table for creative performance
only. Never query it for CPQL, CPL, qual rate, or lead counts at campaign
or channel level.

**Wrong:**
```sql
SELECT channel, SUM(leads_total) FROM wide_ads GROUP BY channel
```

**Correct — always use campaigns_daily + pre-aggregated HS CTE:**
```sql
WITH hs AS (
  SELECT date, lead_utm_campaign,
         SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM hubspot_leads_module_daily
  GROUP BY date, lead_utm_campaign
),
spend AS (
  SELECT channel, campaign_name, LOWER(campaign_name) AS k,
         SUM(spend) AS spend
  FROM campaigns_daily
  GROUP BY channel, campaign_name
)
SELECT s.channel, s.campaign_name, s.spend,
       SUM(hs.leads) AS leads, SUM(hs.sqls) AS sqls,
       SAFE_DIVIDE(s.spend, SUM(hs.sqls)) AS cpql
FROM spend s
LEFT JOIN hs ON LOWER(hs.lead_utm_campaign) = s.k
GROUP BY s.channel, s.campaign_name, s.spend
```

### NEVER use MAX() or MIN() on a rate after a JOIN

`MAX(qual_rate)` after joining picks an arbitrary row from the wrong campaign.
Always compute rates from summed numerator / summed denominator.

**Wrong:** `MAX(hs.qual_rate)` in outer GROUP BY
**Correct:** `SAFE_DIVIDE(SUM(hs.sqls), SUM(hs.leads)) AS qual_rate`

### NEVER group by date+campaign and ORDER BY metric LIMIT N

This picks the single worst/best day, not the true 14-day average.

**Wrong:** `GROUP BY date, channel, campaign_name ORDER BY cpql DESC LIMIT 8`
**Correct:** `GROUP BY channel, campaign_name` — aggregate the full window first

### NEVER join hubspot_leads_module_daily without pre-aggregating first

Direct JOIN multiplies spend rows by the number of matching HubSpot rows
(fan-out bug). Always wrap HubSpot in a CTE that GROUPs before joining.

### ALWAYS use LOWER() on both sides of the campaign name join

`ON c.campaign_name = hs.lead_utm_campaign` silently drops leads when case
differs. Always: `ON LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)`

### Claude node prompt rule

Every Claude node that receives BQ data must include:
> "The following table contains pre-computed KPIs from BigQuery. Do not
> recalculate any numbers. Interpret the data as-is. All figures are
> final — cite them exactly as shown in the table."

### n8n workflow edit discipline

Workflows are ONLY edited via local JSON files in `n8n/workflows/`, then
pushed via the n8n API. Never edit directly in the n8n Cloud UI — Cloud UI
edits are not reflected in git and will be overwritten on the next push.

---

## Campaign Status Filter (non-negotiable)

Before ANY pause recommendation, CPQL flag, or "worst performer" label:

- Filter out campaigns (or ads) with `spend = 0` for all rows in the last 2 days of `campaigns_daily` / `ads_daily`
- SQL subquery to exclude already-paused campaigns:
  ```sql
  AND campaign_name NOT IN (
    SELECT campaign_name
    FROM `{{ $vars.BQ_PROJECT }}.{{ $vars.BQ_DATASET }}.campaigns_daily`
    WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 2 DAY)
    GROUP BY campaign_name
    HAVING SUM(spend) = 0 AND SUM(impressions) = 0
  )
  ```
- A paused campaign will always look like a bad performer — never flag it
- This applies to: daily Slack summaries, ZATCA re-evals, bulk_ads audit, n8n KPI nodes, period comparisons, any "top/worst" channel ranking
- In `bulk_ads.py`: the `_fetch_already_paused_ads()` function pre-fetches inactive ad names and filters them before the flagging loop
- Established 2026-06-19 after ZATCA pause recommendations were sent for ZATCAVendorShop and ZATCAPhase2 — both already paused

---

## HubSpot Lead Object: ALWAYS `0-136`, NEVER contacts (non-negotiable)

Any HubSpot API call involving leads MUST use the Lead Module object `0-136`:

```
/crm/v3/objects/0-136/search
```

NEVER use `/crm/v3/objects/contacts/search` to count or fetch leads.
Contacts and Leads are separate HubSpot objects. A contacts count compared
to a BQ leads count is a meaningless comparison and will always produce
a false gap.

Applies to: reconciliation scripts, ad-hoc queries, any new HubSpot API call.
Collector reference: `collectors/hubspot_leads_bq.py` → `LEAD_OBJ = "0-136"`
