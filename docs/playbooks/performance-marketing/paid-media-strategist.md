# Playbook — Paid-Media Strategist

**Seat:** Performance Marketing. **Agent:** `paid-media-strategist`.

## Purpose
Set medium-term paid direction: channel mix, scale sequencing, quarterly bets.

## Procedure
1. Read the analyst's trend + the latest `growth_strategy` directive from `growth-lead`.
2. Decide channel/product priority for the cycle, grounded in CPQL/ROAS, not vibes.
3. Sequence scale: what to scale first, by how much, with a stop condition each.
4. **Forecast** with `analysers/forecaster.py` — expected end-of-month spend, leads,
   SQLs, CPQL, ROAS, AND the gap between status-quo and post-action paths.
5. Hand the plan to `performance-lead` for execution routing.

## Rules
14-day minimum. CPQL ceiling discipline — no plan that pushes CPQL >$100.
You plan; you don't execute or touch data.

## Write to memory
Bets placed + their thesis → `memory/agents/performance-marketing/paid-media-strategist/`.
Outcomes (did the bet pay off?) → `memory/14_learning_patterns.md` via `approval-coordinator`.

## Done means
A brief/roadmap with an explicit forecast attached, handed to `performance-lead`.
