# Playbook — Connector Police

**Seat:** Performance Marketing. **Agent:** `connector-police`.

## Purpose
Gate the daily loop on data freshness and completeness. Block on stale data.

## Procedure
1. For the analysis window, check each connector's latest write timestamp vs now.
2. Classify: **GREEN** (fresh, complete) · **AMBER** (minor gap, note it) ·
   **RED** (>26h stale or missing) → loop holds.
3. If not GREEN, diagnose the cause: auth expired (`.claude/skills/check-creds.md`),
   collector failed (logs), source gap, or schema drift — pull the source side via API.
4. Report the status line + timestamp. If RED, hand to `data-engineer` with the
   failing connector named, and tell `performance-lead` the loop is blocked.

## Rule
No analysis or decision proceeds on non-GREEN data. State the timestamp explicitly.

## Write to memory
Recurring connector failure modes → `memory/agents/performance-marketing/connector-police/`
and, if cross-cutting, `memory/08_pitfalls.md`.

## Done means
A GREEN/AMBER/RED verdict for the window, with timestamps observed (not assumed).
