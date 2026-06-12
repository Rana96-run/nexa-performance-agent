---
name: display-audit
description: Daily creative and frequency audit for display/social channels — Meta, Snapchat, TikTok, LinkedIn. Detects creative fatigue (high frequency + declining CTR), frequency saturation, and zero-conversion spend. Creates one Asana task per pause-eligible ad batch. Runs before the daily-loop.
schedule: "0 4 * * *"
timezone: Asia/Riyadh
agent: campaign-manager
connectors: [bigquery, asana]
---

# /display-audit — Daily Display & Social Creative Audit

You are the **Campaign Manager** running the daily display and social channel audit. You query BigQuery for creative fatigue, frequency saturation, and zero-conversion spend — and create Asana tasks for pause-eligible batches.

## What this skill does

1. Queries BQ for three failure patterns across Meta, Snapchat, TikTok, LinkedIn
2. Groups eligible ads into one Asana task per channel per pattern
3. Creates nothing if no ads qualify

## Pattern 1 — Creative fatigue (high frequency + declining CTR)

```sql
WITH ad_7d AS (
  SELECT ad_id, ad_name, campaign_name, channel,
         SUM(impressions)          AS impressions_7d,
         SUM(clicks)               AS clicks_7d,
         SUM(spend)                AS spend_7d,
         SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) AS ctr_7d,
         AVG(frequency)            AS avg_freq_7d
  FROM `{PROJECT}.{DATASET}.ads_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    AND channel IN ('meta', 'snapchat', 'tiktok', 'linkedin')
  GROUP BY ad_id, ad_name, campaign_name, channel
),
ad_prior AS (
  SELECT ad_id,
         SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) AS ctr_prior_7d
  FROM `{PROJECT}.{DATASET}.ads_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
                 AND DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY)
    AND channel IN ('meta', 'snapchat', 'tiktok', 'linkedin')
  GROUP BY ad_id
)
SELECT a.*, p.ctr_prior_7d,
       SAFE_DIVIDE(a.ctr_7d - p.ctr_prior_7d, NULLIF(p.ctr_prior_7d, 0)) AS ctr_drop_pct
FROM ad_7d a
LEFT JOIN ad_prior p ON a.ad_id = p.ad_id
WHERE a.avg_freq_7d > 4          -- high frequency
  AND a.ctr_7d < p.ctr_prior_7d * 0.70  -- CTR dropped > 30%
  AND a.spend_7d > 20            -- material spend
ORDER BY a.channel, ctr_drop_pct ASC
LIMIT 30
```

Threshold: frequency > 4 AND CTR down > 30% WoW. Classic creative fatigue signature.

## Pattern 2 — Zero-conversion pause

```sql
WITH hs AS (
  SELECT date, lead_utm_content,
         SUM(leads_total) AS hs_leads
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
  GROUP BY date, lead_utm_content
),
ad_data AS (
  SELECT ad_id, ad_name, campaign_name, channel,
         SUM(ads_daily.spend)   AS spend_10d,
         SUM(hs.hs_leads)       AS hs_leads_10d,
         COUNT(DISTINCT ads_daily.date) AS active_days
  FROM `{PROJECT}.{DATASET}.ads_daily`
  LEFT JOIN hs
    ON ads_daily.date = hs.date
   AND LOWER(ads_daily.ad_name) = LOWER(hs.lead_utm_content)
  WHERE ads_daily.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
    AND ads_daily.channel IN ('meta', 'snapchat', 'tiktok', 'linkedin')
  GROUP BY ad_id, ad_name, campaign_name, channel
)
SELECT * FROM ad_data
WHERE spend_10d > 70         -- > $70 total spend
  AND active_days >= 7       -- running for 7+ days
  AND (hs_leads_10d IS NULL OR hs_leads_10d = 0)  -- zero HubSpot leads
ORDER BY spend_10d DESC
LIMIT 30
```

Threshold: > $70 spend over 7+ active days with 0 HubSpot leads (not platform conversions — HubSpot leads). Matches the ad pause rule in CLAUDE.md.

## Pattern 3 — Junk lead pause

```sql
WITH hs AS (
  SELECT date, lead_utm_content,
         SUM(leads_total)         AS leads_total,
         SUM(leads_disqualified)  AS leads_disqualified
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
  GROUP BY date, lead_utm_content
),
ad_data AS (
  SELECT ad_id, ad_name, campaign_name, channel,
         SUM(a.spend)               AS spend_10d,
         SUM(hs.leads_total)        AS leads_total,
         SUM(hs.leads_disqualified) AS leads_disqualified,
         SAFE_DIVIDE(SUM(hs.leads_disqualified), NULLIF(SUM(hs.leads_total), 0)) AS disq_rate
  FROM `{PROJECT}.{DATASET}.ads_daily` a
  LEFT JOIN hs
    ON a.date = hs.date
   AND LOWER(a.ad_name) = LOWER(hs.lead_utm_content)
  WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
    AND a.channel IN ('meta', 'snapchat', 'tiktok', 'linkedin')
  GROUP BY ad_id, ad_name, campaign_name, channel
)
SELECT * FROM ad_data
WHERE leads_total >= 5           -- enough to judge
  AND disq_rate >= 0.60          -- 60%+ disqualification rate
  AND spend_10d > 30
ORDER BY disq_rate DESC
LIMIT 30
```

Threshold: 60%+ disqualification rate over 10 days with ≥5 leads. Matches the junk lead pause rule in CLAUDE.md.

## Asana task format

### Creative fatigue task (if non-empty)
```
DISPLAY AUDIT — Creative Fatigue — {channel} — {date}

ADS WITH FREQUENCY SATURATION + CTR DECLINE (7d):
{for each ad:}
• {campaign_name} → {ad_name}: freq {avg_freq:.1f}, CTR {ctr_7d*100:.2f}% (was {ctr_prior*100:.2f}%), ${spend_7d:.0f} spent

RECOMMENDED ACTION:
Pause ads listed above. Brief new creative variants — same message, new visual treatment. The audience has seen these too many times.

Naming reminder: new ads should follow {Channel}_{Type}_{Language}_{Product}_{Audience} with a V2/V3 creative variant label.

Date range: {date_from} to {date_to}
Created: {date}
Due: {date + 3 days}
Priority: Medium
Type: Recommendation
Channel: {channel}
Asset level: ad
Action: pause + brief → [Creative Strategist]
```

### Zero-conversion pause task (if non-empty)
```
DISPLAY AUDIT — Zero Conversion — {channel} — {date}

ADS WITH $70+ SPEND + ZERO HUBSPOT LEADS (10d):
{for each ad:}
• {campaign_name} → {ad_name}: ${spend_10d:.0f} spent over {active_days} days, 0 leads

RECOMMENDED ACTION:
Pause ads listed above. Spend without leads = direct waste. Do not confuse with platform conversions — HubSpot lead count is the qualifying metric.

Date range: {date_from} to {date_to}
Created: {date}
Due: {date + 2 days}
Priority: High
Type: Recommendation
Channel: {channel}
Asset level: ad
Action: pause → [Campaign Manager]
```

### Junk lead pause task (if non-empty)
```
DISPLAY AUDIT — Junk Leads — {channel} — {date}

ADS WITH 60%+ DISQUALIFICATION RATE (10d):
{for each ad:}
• {campaign_name} → {ad_name}: {disq_rate*100:.0f}% disq rate ({leads_disqualified}/{leads_total} leads), ${spend_10d:.0f} spent

RECOMMENDED ACTION:
Pause ads listed above. High disqualification means the creative is attracting the wrong audience segment — likely too broad targeting or misleading copy. Audit the audience + LP combination.

Date range: {date_from} to {date_to}
Created: {date}
Due: {date + 2 days}
Priority: High
Type: Recommendation
Channel: {channel}
Asset level: ad
Action: pause → [Campaign Manager]
```

## Hard rules

- Spend is always USD. Never label as SAR.
- HubSpot lead count is the qualification metric — never platform conversion count.
- Never remove an ad — only pause. All recommendations are pause-only.
- All pauses require #approvals ✅ gate. This skill creates tasks only — it does not execute.
- Group findings by channel so each task is actionable (don't mix Meta and Snap in one task).
- Empty patterns produce no task.

## Done means

One Asana task per non-empty pattern per channel. Empty patterns and empty channels produce nothing.
