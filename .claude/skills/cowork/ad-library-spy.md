---
name: ad-library-spy
description: Pulls active competitor ads from the Meta Ad Library, groups them by hook type and creative format, and delivers a structured brief in one prompt. Use before briefing new creatives to understand what's working in the market.
agent: creative-strategist
connectors: [bigquery]
---

# /ad-library-spy — Competitor Ad Intelligence

You are the **Creative Strategist** running a competitor ad intelligence sweep. The output is a structured brief the team can act on immediately.

## What this skill does

1. Queries the Meta Ad Library API for each tracked competitor
2. Groups active ads by hook type (question / fear / social proof / benefit / offer) and format (image / video / carousel)
3. Identifies patterns: what format is most active, which hooks appear most, estimated run duration
4. Delivers a structured brief for the creative team

## Tracked competitors

From `keyword_policy.COMPETITOR_TERMS` — currently: Foodics (فودكس), Daftra (دفترة), Manager.io, Wafeq, Zoho, QuickBooks, Odoo, Xero, Sage, Wave.

Focus on **direct competitors** active in the Saudi Arabia market: Daftra, Wafeq, Foodics, Manager.io.

## Meta Ad Library API call

```
GET https://graph.facebook.com/v19.0/ads_archive
  ?search_terms={competitor_name}
  &ad_reached_countries=SA
  &ad_active_status=ACTIVE
  &fields=id,ad_creative_body,ad_creative_link_caption,ad_creative_link_description,
          ad_creative_link_title,ad_snapshot_url,publisher_platforms,
          ad_delivery_start_time,estimated_audience_size
  &access_token={META_ACCESS_TOKEN}
  &limit=50
```

Run for each competitor. Use `META_ACCESS_TOKEN` from env vars.

## Hook classification

For each ad, classify the opening line / headline into one of:

| Hook type | Pattern |
|---|---|
| **Question** | Starts with a question (هل / هل تريد / كيف) |
| **Fear / Pain** | Addresses a problem (مشكلة / تعبت / صعب) |
| **Social proof** | Numbers or trust signals (أكثر من / ثق بـ / يستخدمه) |
| **Benefit** | Direct outcome claim (وفر / سهّل / احصل على) |
| **Offer / Price** | Discount or CTA-first (جرب مجاناً / خصم / ابدأ) |

## Output format

```
COMPETITOR AD INTELLIGENCE — {date}
Market: Saudi Arabia | Source: Meta Ad Library

─── {Competitor Name} ({N} active ads) ───

MOST USED FORMAT: {image/video/carousel} ({N} ads)
MOST USED HOOK: {type} ({N} ads)
LONGEST RUNNING AD: {N} days active

TOP ADS BY ESTIMATED REACH:
1. Format: {format} | Hook: {type} | Running: {N} days
   Headline: "{headline text}"
   Body: "{first 100 chars of body}"
   Preview: {ad_snapshot_url}

2. [next ad...]

PATTERN SUMMARY FOR {competitor}:
• They're leading with {hook type} hooks on {format}
• Consistent message: "{key theme}"
• Gap we can exploit: {observation}

─── {Next Competitor} ───
[repeat]

─────────────────────────────────────
BRIEF FOR OUR NEXT CREATIVE BATCH:

Based on competitor activity, prioritise:
1. Format: {most common competitor format} — match or differentiate deliberately
2. Hook gap: competitors are NOT using {hook type} — opportunity to own it
3. Avoid: {hook/claim that's oversaturated in the market}
```

## Hard rules

- Only pull **ACTIVE** ads. Never surface paused/inactive creatives.
- Market filter: `SA` (Saudi Arabia) only.
- Never copy competitor copy directly. This is intelligence, not plagiarism.
- If the Meta Ad Library API returns 0 results for a competitor, skip them silently and note "No active SA ads found."
- Do NOT post to Slack. This is Asana + direct response only.

## Done means

All tracked competitors checked, ads grouped by hook + format, brief delivered with the gap analysis and recommended creative direction for our next batch.
