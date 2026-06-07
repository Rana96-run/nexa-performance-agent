---
name: recommendation-writer
description: |
  Skill Library — Recommendation writing protocol.
  Defines how to turn a CPQL finding into a full, actionable recommendation
  with complete campaign setup, forecast, and Asana task body.
  Load whenever the agent needs to write a pause, scale, optimize, or
  drilldown recommendation after completing the 8-step intelligence loop.
---

# Recommendation Writer

## The Rule

A recommendation is **not done** until it has four parts:
1. **Period comparison** — what changed vs. the prior window
2. **Root cause** — exactly why it changed (not "performance declined")
3. **Fix with full setup** — complete campaign/adset/ad/LP configuration
4. **Forecast** — expected CPQL impact at 7 and 14 days post-action

A bullet list without all four parts is a draft, not a recommendation.

---

## Recommendation Types

| Type | Trigger | Output |
|---|---|---|
| `scale` | CPQL < $60 for 14d, budget not capped | Full scale spec + budget calc |
| `pause` | CPQL > $100 for 14d, or zero conv for 7d >$70 | Pause justification + replacement suggestion |
| `optimize` | CPQL $80–100 range, root cause identifiable | Specific change (creative/audience/bid/LP) |
| `junk` | Lead disqualification ≥ 60% for 10d | Junk analysis + audience/LP fix |
| `drilldown` | Anomaly detected, cause unknown | Investigation brief for the team |

---

## Scale Recommendation Template

```
SCALE RECOMMENDATION — {campaign_name}
Channel: {channel} | Product: {product} | Audience: {audience}

PERFORMANCE (last 14 days vs prior 14 days):
  Spend:  ${current} vs ${prior} ({delta}%)
  Leads:  {current} vs {prior} ({delta}%)
  SQLs:   {current} vs {prior} ({delta}%)
  CPL:    ${current} vs ${prior} ({delta}%)
  CPQL:   ${current} vs ${prior} ({delta}%) ← PRIMARY KPI

ROOT CAUSE:
  {1–2 sentences: what drove CPQL improvement. E.g., "Creative variant V3
  reduced CPL by 18% while lead qualification rate held at 42% — no quality
  dilution. Audience Lookalike 2% has a lower saturation rate than Lookalike 5%."}

PROPOSED ACTION:
  Current budget: ${current}/day
  Proposed budget: ${new}/day (+{pct}%)
  Scale rule: max +30% in one step (from config.SCALE_STEP_MAX)

FULL CAMPAIGN SETUP (for reference):
  Campaign: {full_name} (ID: {id})
  Ad Set:   {adset_name} (ID: {id})
  Audience: {audience_type} | Size: ~{size}
  Bid:      {bid_strategy} @ ${target}
  LP:       {url} (WP ID: {id} if applicable)
  Pixels:   Qoyod_CRM_PIXEL + Qoyod_Web_PIXEL ✓
  UTM:      utm_campaign={campaign_name} ✓

FORECAST (post-scale):
  +7d expected: CPQL ${forecast_7d} | Leads +{pct}%
  +14d expected: CPQL ${forecast_14d} | Leads +{pct}%
  Basis: 30% budget increase historically yields ~20–25% lead volume increase
  with CPQL stable within ±8% in first 14 days (from memory/14_learning_patterns.md)

DATE RANGE: {YYYY-MM-DD} to {YYYY-MM-DD}
```

---

## Pause Recommendation Template

```
PAUSE RECOMMENDATION — {ad_name or campaign_name}
Channel: {channel} | Level: {Campaign / Ad Set / Ad}

PERFORMANCE ({days}d window: {YYYY-MM-DD} to {YYYY-MM-DD}):
  Spend: ${total}
  Leads: {n} (CPL: ${cpl})
  SQLs:  {n} (CPQL: ${cpql})
  Disqualification rate: {pct}%

PAUSE TRIGGER:
  ☐ Zero conversions ($70+ spend, 7+ days)
  ☐ CPQL > $100 for 14+ days
  ☐ Junk rate ≥ 60% for 10+ days
  ☐ High CPL (> $50) for 10+ days

ROOT CAUSE:
  {1–2 sentences. E.g., "Audience Interests / Accountants is over-saturated —
  frequency 4.2 on 14d, CPM increased 38% while CTR dropped 22%. Creative
  fatigue confirmed: V1 and V2 both below 0.8% CTR."}

REPLACEMENT (if applicable):
  {What to launch instead. E.g., "Clone to Lookalike 1% source: Qoyod
  purchasers last 180 days. New creative brief: hook on ZATCA deadline urgency."}

FORECAST WITHOUT PAUSE:
  Projected 14d waste: ${spend_rate * 14}d at current CPQL ${cpql} →
  {leads} leads at ${cpql_projected} vs $80 target = ${waste_vs_target} over budget

DATE RANGE: {YYYY-MM-DD} to {YYYY-MM-DD}
```

---

## Asana Task Body Template

Every recommendation becomes an Asana task. The body must follow this structure:

```
CONTEXT
{1 paragraph: what we observed, what window, why it matters}

DATA ({YYYY-MM-DD} to {YYYY-MM-DD})
| Metric | Value | vs Prior 14d |
|--------|-------|--------------|
| Spend  | $X    | +/-X%        |
| Leads  | X     | +/-X%        |
| SQLs   | X     | +/-X%        |
| CPQL   | $X    | +/-X%        |

ROOT CAUSE
{Root cause statement — no bullet lists, one clear sentence}

ACTION
{Exact action: pause / scale to $X/day / update audience to X / swap creative to V3}

SETUP
Campaign: {name} (ID: {id})
Ad Set: {name} (ID: {id})
Ad: {name} (ID: {id}) [if ad-level]
LP: {url}

FORECAST
{Expected outcome at 7d and 14d post-action}

---
Created: {YYYY-MM-DD}
Due: {YYYY-MM-DD} (7 days for monitoring)
Priority: High / Medium / Low
Type: scale | pause | optimize | junk | drilldown
Channel: Meta | Google | Snapchat | LinkedIn | Bing
Asset level: Campaign | Ad Set | Ad | Keyword
Action: scale | pause | optimize | review
```

**Never omit the footer block** — it's required by the pre-send hook.

---

## Forecast Calculation

Use `analysers/forecaster.py` for month-end projections. For action-level
forecasts, apply these rules of thumb (sourced from `memory/14_learning_patterns.md`):

| Action | Expected impact at 14d |
|---|---|
| +30% budget scale | +20–25% lead volume, CPQL stable ±8% |
| Pause worst ad + keep best | CPQL improves 10–20% within 7d |
| Audience swap (saturated → fresh LAL) | CPM -15-25%, CTR +10-20% |
| Creative refresh | CTR +15-30% in first 7d; fades by day 21 |
| LP CRO fix (headline/form) | Form submission rate +10-25% |

Always state the basis for the forecast — "based on X" not just a number.

---

## Rules & Guardrails

1. **Never write a recommendation without running `verify-before-reporting.md`** first
2. **Always pre-aggregate HubSpot before joining** to avoid fan-out (see CLAUDE.md)
3. **Date ranges always explicit** — `YYYY-MM-DD to YYYY-MM-DD`, never "last 14 days"
4. **No platform conversion counts** — only HubSpot `leads_total` and `leads_qualified`
5. **CPQL first, CPL second** — the recommendation title always leads with CPQL
6. **Minimum 14-day window** — never recommend based on < 14 days
7. **Full setup required** — "pause this" without Campaign ID and LP URL is incomplete
8. **Forecast is mandatory** — a recommendation without expected impact is incomplete
