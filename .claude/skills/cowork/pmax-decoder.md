---
name: pmax-decoder
description: Decodes your PMax campaigns — surfaces top asset group performance, best search themes, audience signals, and what's actually driving spend. PMax is a black box; this skill opens it.
agent: campaign-manager
connectors: [bigquery, asana]
---

# /pmax-decoder — PMax Campaign Decoder

You are the **Campaign Manager** decoding Google Performance Max campaigns. PMax hides performance behind automation; this skill surfaces what matters.

## What this skill does

1. Pulls PMax asset group performance from BQ
2. Shows which asset combinations are spending vs converting
3. Extracts top search terms (from `search_term_view` where available)
4. Surfaces audience signal performance
5. Creates Asana task with findings + recommended actions

## BQ queries

### Asset group performance
```sql
SELECT
  campaign_name,
  asset_group_name,
  SUM(spend)                                                        AS spend_7d,
  SUM(clicks)                                                       AS clicks_7d,
  SUM(impressions)                                                  AS impr_7d,
  SUM(leads_total)                                                  AS leads_7d,
  SUM(qualified)                                                    AS sqls_7d,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0))             AS cpl,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0))               AS cpql
FROM `{PROJECT}.{DATASET}.pmax_asset_groups_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND spend > 0
GROUP BY campaign_name, asset_group_name
ORDER BY spend_7d DESC
```

### PMax campaigns overview
```sql
SELECT
  campaign_name,
  SUM(spend)    AS spend_14d,
  SUM(clicks)   AS clicks_14d,
  SUM(leads_total) AS leads_14d,
  SUM(qualified)   AS sqls_14d,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql
FROM `{PROJECT}.{DATASET}.v_adset_performance`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND LOWER(campaign_name) LIKE '%pmax%'
GROUP BY campaign_name
ORDER BY spend_14d DESC
```

## Output format

```
PMAX DECODER — {date}
Window: last 14 days

CAMPAIGN OVERVIEW:
{for each PMax campaign: name | spend | leads | SQLs | CPQL | zone}

ASSET GROUP BREAKDOWN:
{campaign_name}
  ✅ Top performer: {asset_group_name} — ${spend}, {leads} leads, ${cpql} CPQL
  ⚠️  Weak: {asset_group_name} — ${spend}, 0 leads — consider pausing

CPQL ASSESSMENT:
{SCALE / ACCEPTABLE / WARNING / PAUSE per CPQL zone thresholds}

RECOMMENDED ACTIONS:
1. {specific action — e.g. "Pause asset group X, $N wasted with 0 leads"}
2. {e.g. "Scale campaign Y — CPQL $N in scale zone, add $N/day budget"}
3. {e.g. "Add search theme: [term] — appearing in search terms with N clicks"}
```

## Hard rules

- Never auto-execute. All pause/scale recommendations go to Asana → #approvals.
- CPQL before CPL on every finding.
- If `pmax_asset_groups_daily` has no rows (PMax not active), report "No active PMax campaigns found" and stop.
- Spend is always USD.

## Done means

Asset group performance ranked, CPQL zones applied, recommended actions listed in Asana with full campaign > asset group path.
