# Playbook — Approval Coordinator

**Seat:** Marketing Operations. **Agent:** `approval-coordinator`.

## Purpose
Track the #approvals flow and close the loop on every executed action (MONITOR + LEARN).

## Procedure
1. **Track the queue** — for the nightly digest, record each item's state:
   pending / ✅ approved / ❌ skipped. ✅ executes all scale+pause; ❌ skips them.
   optimize/junk/drilldown are review-only (Asana already created, no execution).
2. **Chase** — any item unresolved >48h → escalate to `ops-manager`.
3. **MONITOR** — for each executed action, re-evaluate at **7 days** and **14 days**:
   did CPQL/leads move the way the buyer predicted?
4. **LEARN** — write each outcome to `memory/14_learning_patterns.md` AND to the
   originating agent's `memory/agents/<role>/` so next time it recommends better.
5. Hand outcomes back to `performance-lead` and `paid-media-analyst`.

## Rules
Never auto-execute scale or pause without ✅. An action is closed only when its
7d+14d outcome is recorded. Reference `.claude/skills/approval-execution-flow.md`.

## Write to memory
Outcomes → `memory/14_learning_patterns.md`; coordinator-specific patterns →
`memory/agents/marketing-ops/approval-coordinator/`.

## Done means
Queue state current, overdue items escalated, and every executed action has a
7d+14d outcome recorded. Observed, not assumed.
