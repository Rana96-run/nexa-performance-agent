---
name: wasted-spend-finder
description: Flags every adset with $90+ spend and 0 conversions in the last 7 days. Posts findings to Asana for review. Runs daily before the main loop.
schedule: "0 4 * * *"
timezone: Asia/Riyadh
agent: campaign-manager
connectors: [bigquery, asana]
---

# /wasted-spend-finder — Wasted Spend Detector

You are the **Campaign Manager** scanning for adsets burning budget with zero return.

## What this skill does

Finds every adset where spend ≥ $90 in the last 7 days AND platform conversions = 0. Creates one Asana task per channel with all offenders listed.

## BQ query

```sql
SELECT
  channel,
  campaign_name,
  adset_name,
  SUM(spend)                                                        AS spend_7d,
  SUM(leads_total)                                                  AS leads_7d,
  SUM(qualified)                                                    AS sqls_7d,
  MIN(date)                                                         AS first_seen,
  MAX(date)                                                         AS last_seen
FROM `{PROJECT}.{DATASET}.v_adset_performance`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY channel, campaign_name, adset_name
HAVING SUM(spend) >= 90
   AND SUM(leads_total) = 0
ORDER BY channel, spend_7d DESC
```

## Output

Group results by channel. For each channel with offenders, create one Asana task:

```
WASTED SPEND — {channel} — {date}

{N} adsets with $90+ spend and 0 leads in the last 7 days:

• {adset_name} (Campaign: {campaign_name})
  Spend: ${spend_7d} | Days active: {days} | Leads: 0
  → PAUSE candidate (pending ✅ in #approvals)
  
[repeat for each adset]

Total wasted: ${sum_all_spend}

Created: {date}
Due: {date}
Priority: High
Type: Optimization
Channel: {channel}
Asset level: adset
Action: pause → [Campaign Manager]
```

## Hard rules

- Never auto-pause. Every pause candidate goes through #approvals. This skill only creates the Asana task.
- Threshold is $90 spend over 7 days with **zero leads** (not zero platform conversions — use HubSpot leads from BQ).
- If an adset is in an awareness campaign (`AWARENESS_PATTERNS` — impression-share objective), skip it. Zero leads is expected for awareness.
- Minimum window: 7 days. Don't flag adsets live for fewer than 3 days.

## Done means

One Asana task per channel with offenders, total wasted spend calculated, pause candidates listed with full campaign > adset path.
