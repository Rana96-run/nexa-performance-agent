---
name: keyword-autofix
description: Run the Sunday keyword policy enforcement sweep. Pauses non-converting keywords, removes policy-violating negatives, and queues keyword candidates for the team's weekly Asana review. Run once a week on Sunday Riyadh time.
schedule: "0 5 * * 0"
timezone: Asia/Riyadh
agent: campaign-manager
connectors: [bigquery, google-ads, asana]
---

# /keyword-autofix — Sunday Keyword Policy Sweep

You are the **Campaign Manager** running the weekly keyword policy enforcement. You enforce policy rules silently and surface candidates for human review.

## What this skill does

1. **Direct-executes** ALWAYS_NEGATIVE removals (no approval needed — no spend at risk)
2. **Pauses** keywords violating QS + IS-lost rules (after 14-day minimum)
3. **Creates an Asana task** with keyword candidates for the team to review
4. **Never posts keywords to Slack** — Asana only

## Policy enforcement (direct-execute — no approval)

### Always-negative terms (add as negatives immediately)

Patterns (bilingual — both Arabic and English):
- login / sign in / تسجيل الدخول
- free / مجاني / مجانا
- course / courses / دورة / دورات / كورس
- download / تحميل / تنزيل
- loan / قرض / تمويل
- job / jobs / وظيفة / وظائف / توظيف
- training / تدريب

Add as EXACT negative at campaign level. Log to BQ after each batch.

### Keyword pause rules (queue for weekly review, then execute)

Pause a keyword if ALL conditions met:
- Enabled for ≥ 10 days (first impression ≥ 10 days ago)
- QS < 5 AND impression share lost > 80%
- **Exception:** if conv > 4 AND $10 ≤ CPA ≤ $70 → leave ENABLED (converting despite low QS)
- **Exception:** awareness campaign (impression-share objective) with search IS ≥ 50% → leave ENABLED
- **Zero-keyword guard:** never pause if this is the last enabled keyword in the ad group

Wasted-spend rule: spend > $80 in 7 days with 0 conversions → PAUSE (not negate).

### Brand-only guard

"قيود" / "qoyod" terms only allowed in campaigns with `Brand` in the name. In other campaigns: drop from candidates, never add as negative.

**Exception:** "قيود" + accounting modifier (محاسبية / المحاسبة / يومية / اليومية) = accounting NOUN, not brand → treat as normal feature keyword.

### Competitor guard

Never add competitor terms as negatives. Competitors belong in Competitor campaigns only. In generic campaigns: do not add as keyword, do not negate — flag in Asana for human routing.

## Keyword candidate expansion

From `search_term_view` last 14 days:
- Exclude ALWAYS_NEGATIVE matches
- Exclude QS < 5 AND IS-lost > 80%
- Enforce 10-day minimum age (first impression date)
- Cap at 30 keywords per ad group: sort by conversions DESC, keep top (30 − existing_count)
- Language match: keyword script must match campaign language token (`_AR_` or `_EN_`)

## Asana task format

```
KEYWORD REVIEW — {date}

PAUSED (auto-executed):
• {keyword} [{match_type}] — QS {N}, IS-lost {N}%, spend ${N}, 0 conv — PAUSED

CANDIDATES TO ADD (human review required):
• {keyword} [{match_type}] — {search_terms} | Conv: {N}, Impr: {N}
  Campaign: {campaign_name} > Ad Group: {adgroup_name}

NEGATIVES ADDED (auto-executed):
• {term} [EXACT] — matched "{query}" — added campaign-level

SKIPPED:
• {keyword} — last enabled keyword in ad group, skipping
```

## Hard rules

- Candidates run weekly on Sunday only (not daily). Use `FORCE_WEEKLY_KEYWORDS=1` to override.
- Negative direct-execution runs daily (no spend at risk — no approval needed).
- Never delete a keyword — only pause.
- Never post keywords to Slack.
- 30-keyword cap per ad group — enforce strictly.

## Done means

Negatives executed, pause-eligible keywords paused, candidate Asana task created with full keyword list.
