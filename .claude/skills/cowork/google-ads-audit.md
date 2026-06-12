---
name: google-ads-audit
description: Daily Google Ads and Microsoft Ads quality audit — impression share losses, Quality Score issues, and search term expansion candidates. Queries BQ for IS/QS metrics and creates one Asana task per finding bucket. Runs before the daily-loop so findings are ready for the morning digest.
schedule: "0 4 * * *"
timezone: Asia/Riyadh
agent: campaign-manager
connectors: [bigquery, asana]
---

# /google-ads-audit — Daily Search Ads Quality Audit

You are the **Campaign Manager** running the daily Google Ads and Microsoft Ads audit. You query BigQuery (which stores IS, QS, and search term data from the collectors) and create Asana tasks for the finding buckets below.

## What this skill does

1. Queries BQ for IS losses, QS issues, and search term candidates
2. Groups findings into buckets
3. Creates one Asana task per non-empty bucket
4. Creates nothing if a bucket is empty

## Bucket 1 — Impression Share lost to Budget

```sql
SELECT
  campaign_name, channel,
  AVG(search_budget_lost_is)   AS avg_budget_lost_is,
  AVG(search_rank_lost_is)     AS avg_rank_lost_is,
  SUM(impressions)             AS impressions,
  SUM(spend)                   AS spend
FROM `{PROJECT}.{DATASET}.keyword_view`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND channel IN ('google_ads', 'microsoft_ads')
  AND search_budget_lost_is > 0.30
GROUP BY campaign_name, channel
HAVING SUM(spend) > 10
ORDER BY avg_budget_lost_is DESC
LIMIT 20
```

Threshold: budget IS loss > 30%. These campaigns are constrained by budget, not quality.

## Bucket 2 — Low Quality Score keywords

```sql
SELECT
  campaign_name, ad_group_name, keyword_text, channel,
  quality_score, search_rank_lost_is,
  SUM(spend) AS spend_7d,
  SUM(conversions) AS conv_7d
FROM `{PROJECT}.{DATASET}.keyword_view`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND channel IN ('google_ads', 'microsoft_ads')
  AND quality_score > 0
  AND quality_score < 5
  AND search_rank_lost_is > 0.80
GROUP BY campaign_name, ad_group_name, keyword_text, channel, quality_score, search_rank_lost_is
HAVING SUM(spend) > 5
ORDER BY quality_score ASC, spend_7d DESC
LIMIT 30
```

Apply the converting keyword exception: if conv_7d > 4 AND spend_7d/conv_7d BETWEEN 10 AND 70 → leave enabled (do not include in pause list). Only include keywords that fail the exception.

## Bucket 3 — Search term expansion candidates

```sql
SELECT
  campaign_name, channel,
  search_term,
  SUM(conversions) AS conv_7d,
  SUM(spend)       AS spend_7d,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(conversions), 0)) AS cpa
FROM `{PROJECT}.{DATASET}.search_term_view`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND channel IN ('google_ads', 'microsoft_ads')
  AND conversions > 2
  AND matched_keyword IS NULL  -- not yet an exact keyword
ORDER BY conv_7d DESC
LIMIT 20
```

Filter out: any term in the ALWAYS_NEGATIVE list (login, free, course, download, loan, job + Arabic equivalents). Filter out brand terms (قيود/qoyod) unless the campaign name contains "Brand".

## Asana task format

### Task 1 — IS Budget Losses (if bucket non-empty)
```
GOOGLE ADS AUDIT — IS Budget Loss — {date}

CAMPAIGNS LOSING IMPRESSION SHARE TO BUDGET (7-day avg):
{for each row: • {campaign_name} ({channel}): {avg_budget_lost_is}% IS lost — ${spend} spent, ${avg_budget_lost_is * daily_budget:.0f} potential IS if uncapped}

RECOMMENDED ACTION:
For each campaign above: consider increasing daily budget OR consolidating into fewer ad groups to reduce IS waste.

Date range: {date_from} to {date_to}
Created: {date}
Due: {date + 3 days}
Priority: Medium
Type: Recommendation
Channel: google / microsoft
Asset level: campaign
Action: review → [Campaign Manager]
```

### Task 2 — Low QS Keywords (if bucket non-empty, after converting exception applied)
```
GOOGLE ADS AUDIT — Low Quality Score — {date}

LOW QS KEYWORDS (QS < 5, IS lost > 80%, age ≥ 10 days):
{for each keyword: • [{ad_group}] "{keyword_text}" — QS {qs}, IS lost {is_lost}%, ${spend_7d} spent, {conv_7d} conv}

NOTE: Keywords with conv > 4 AND CPA $10–$70 are excluded (converting despite low QS).
NOTE: Never pause the last keyword in an ad group — zero-active-keyword guard applies.

RECOMMENDED ACTION: Pause keywords listed above (not delete — only pause). Submit via scripts/bulk_keywords.py after approval.

Created: {date}
Due: {date + 3 days}
Priority: Medium
Type: Recommendation
Channel: google / microsoft
Asset level: keyword
Action: pause → [Campaign Manager]
```

### Task 3 — Expansion Candidates (if bucket non-empty)
```
GOOGLE ADS AUDIT — Keyword Expansion — {date}

TOP SEARCH TERM CANDIDATES (converting but not yet a keyword):
{for each term: • "{search_term}" ({campaign_name}): {conv_7d} conv, ${cpa:.0f} CPA}

NOTE: All policy-filtered (always-negative + brand terms removed). Max 30 per ad group cap applies — check existing count before adding.

RECOMMENDED ACTION: Review each candidate and add as exact or phrase match keyword in the relevant ad group.

Created: {date}
Due: {date + 3 days}
Priority: Medium
Type: Recommendation
Channel: google / microsoft
Asset level: keyword
Action: add → [Campaign Manager]
```

## Hard rules

- Never post keyword names to Slack — Asana only.
- Apply the converting keyword exception before flagging low QS keywords.
- Apply the zero-active-keyword guard: never include a keyword that is the last enabled keyword in its ad group.
- Apply the 30-keyword cap: if an ad group already has 30 enabled keywords, do not include expansion candidates for that ad group.
- Quality score 0 (not set / PMax keywords) → skip entirely.
- Minimum keyword age: 10 days before flagging for QS+IS-lost rule.

## Done means

One Asana task per non-empty bucket. Empty buckets produce no task.
