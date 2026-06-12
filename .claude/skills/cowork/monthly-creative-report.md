---
name: monthly-creative-report
description: Run the 1st-of-month winning creative analysis per channel. Pulls 30-day ad performance from BQ, identifies winning creatives (qual ratio > 50% AND CPL ≤ $25), writes one Google Sheet tab per channel, and posts the Sheet link to Asana for the design team.
schedule: "0 5 1 * *"
timezone: Asia/Riyadh
agent: creative-strategist
connectors: [bigquery, google-drive, asana]
---

# /monthly-creative-report — Monthly Winning Creative Analysis

You are the **Creative Strategist** running the monthly creative performance report. Your output is a Google Sheet that the design team reads to know what's working and what to replicate.

## What this skill does

1. Pulls last 30 days of ad performance from BQ (`v_ad_performance`)
2. Identifies winners: qual ratio > 50% AND CPL ≤ $30 (from `AD_CPL_SCALE`)
3. Creates a Google Sheet with one tab per channel
4. Posts the Sheet link to Asana for the design team

## BQ query

```sql
SELECT
  channel,
  ad_name,
  ad_id,
  SUM(clicks)                                                       AS clicks,
  SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0))            AS ctr,
  SUM(leads_total)                                                  AS leads,
  SUM(qualified)                                                    AS qualified_leads,
  SAFE_DIVIDE(SUM(qualified), NULLIF(SUM(leads_total), 0))         AS qual_ratio,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0))             AS cpl,
  SUM(spend)                                                        AS spend
FROM `{PROJECT}.{DATASET}.v_ad_performance`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND leads_total > 0
GROUP BY channel, ad_name, ad_id
HAVING SUM(leads_total) >= 3
ORDER BY channel, qual_ratio DESC, cpl ASC
```

Minimum 3 leads threshold to avoid statistical noise.

## Winning criteria

Both conditions must be met:
- `qual_ratio > 0.50` (more than half of leads qualify)
- `cpl ≤ 25.00` (spend per lead at or below $25)

Rows meeting both criteria = **winners** (highlight green in Sheet).
Rows with qual_ratio > 0.50 but CPL > $25 = **optimise** (highlight yellow — creative works, fix bid/budget).
Rows with qual_ratio ≤ 0.50 regardless of CPL = **underperformer** (highlight red).

## Google Sheet structure

Sheet name: `Winning Creatives — {month_name} {year}` (e.g. "Winning Creatives — June 2026")

One tab per channel with data (skip channels with zero rows):
- Tab names: Meta, Google, Snapchat, TikTok, LinkedIn, Microsoft
- Columns: Rank | Ad Name | Ad ID | Clicks | CTR | Leads | Qualified | Qual% | CPL | Spend | Status
- Sort: winners first, then optimise, then underperformers
- Freeze row 1 (header), bold it

Summary tab (first tab, called "Summary"):
```
Channel       | Winners | Optimise | Total Ads | Best Ad Name      | Best Qual%
Meta          | N       | N        | N         | {name}            | XX%
Google        | N       | N        | N         | {name}            | XX%
...
```

## Asana task

```
WINNING CREATIVES — {month_name} {year}

Google Sheet: {sheet_url}

TOP WINNERS THIS MONTH:
{for each channel: "• {channel}: {best_ad_name} — {qual%} qual, ${cpl} CPL"}

DESIGN TEAM ACTION:
• Replicate the winning creative format for each channel listed above
• Prioritise: duplicate into a new variant with a fresh hook, same format and CTA
• For "optimise" rows: the creative works — review bid/budget before replacing

UNDERPERFORMERS TO REPLACE:
{for each channel: worst ad with 0% qual or CPL > $50}

Created: {date}
Due: {date + 7 days}
Priority: Medium
Type: Recommendation
Channel: all
Asset level: ad
Action: optimize → [Creative Strategist]
```

## Hard rules

- Never post individual ad names to Slack — Asana + Sheet only.
- Qual ratio is the primary sort. CPL is secondary. Never sort by spend alone.
- CPL winner threshold = $25 (fixed — not derived from AD_CPL_SCALE).
- Report covers only channels with ≥ 1 ad with ≥ 3 leads. Skip silent channels entirely.
- The existing weekly creative audit (Sunday) is separate — this report is monthly, higher fidelity, Sheet-first.

## Done means

Google Sheet created in Drive, one tab per channel with winning/optimise/underperform rows, Asana task created with Sheet link and top winners listed.
