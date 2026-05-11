# verify-before-reporting — never state a BQ number without a sub-agent cross-check

## Purpose

Before reporting any metric (lead count, spend, CPL, CPQL, etc.) to the user,
a sub-agent must independently verify the query logic and the result.
"I ran the query and it returned X" is not verification — it is the first step.

This rule exists because on 2026-05-11, a direct query on `hubspot_leads_module_daily`
returned 2,649 leads for May 5–9 and was reported as the answer. The real number
was 883. The table had 5x ghost-row corruption that only a cross-check caught.

## When to invoke

- Any time a number will be stated to the user as correct
- Any time the answer to "how many X" or "what is the Y" comes from a BQ query
- Any time the result feels unexpectedly high or low vs prior session notes

## Steps

### 1. Run the primary query
Run the query and record the result.

### 2. Spawn a code-reviewer sub-agent
Before reporting the number, invoke:

```
Agent(
  subagent_type="superpowers:code-reviewer",
  prompt="""
  Review this BQ query for correctness. Report:
  1. Is the query logically correct for the stated goal?
  2. Are there any sources of double-counting (duplicate rows, multiple aggregation levels)?
  3. What secondary check should be run to confirm the result?
  4. If the result is unexpectedly different from prior session notes, what explains it?

  Query: <paste query>
  Result: <paste result>
  Context: <describe what table is queried, key schema details, prior known values>
  """
)
```

### 3. Run the cross-check the sub-agent recommends
Typically this means:
- Compare against the raw individual table (e.g. `COUNT(DISTINCT hs_object_id)` from
  `hubspot_leads_individual` vs `SUM(leads_total)` from `hubspot_leads_module_daily`)
- Check for duplicate build timestamps (`GROUP BY updated_at`)
- Cross-check against a second aggregation path (e.g. `paid_channel_daily` materialized
  table vs direct `hubspot_leads_module_daily` query)

### 4. Only report after step 3 passes

If steps 2 and 3 disagree with step 1, fix the data or the query before reporting.
State the method used: "BQ shows 883 — confirmed by cross-checking individual table
(883 distinct hs_object_id for May 5–9)."

## Template response format

> BQ has **883 paid leads for May 5–9**, confirmed via cross-check:
> - `hubspot_leads_module_daily` SUM = 883 ✅
> - `hubspot_leads_individual` COUNT(DISTINCT) = 883 ✅
> - Single build timestamp (no ghost rows) ✅

## What triggers this skill

- User asks "how many leads / spend / CPQL for [date range]"
- A BQ query result is about to be stated as the answer
- The result differs from what was expected or previously noted
