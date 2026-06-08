# Playbook — Ops Reporter

**Seat:** Marketing Operations. **Agent:** `ops-reporter`.

## Purpose
Assemble clean report tables from the Performance handoff and flag stale data.

## Procedure
1. **Freshness first** — if the handoff timestamp is >26h old, output
   "Data unavailable as of <timestamp>" and stop. Do not fabricate numbers.
2. Build the channel table from `kpi_summary.channels`:
   `| Channel | Spend(USD) | Leads | CPQL | vs Prior | Status |` with explicit
   date windows in the header.
3. Pull approval-queue count from `approvals_pending` and open-task counts from
   `active_asana_tasks`.
4. Apply status icons against the zones (CPQL <$60 ✅ / warn / >$100 🔴).
5. Hand the assembled block to `ops-manager`.

## Rules
Never query BQ — handoff only. Spend USD. CPQL from SQLs, CPL from leads.
Slack formatting per `.claude/skills/slack-reporter.md` + CLAUDE.md checklist.

## Write to memory
Formatting/edge cases (e.g. a channel with no prior-period data) →
`memory/agents/marketing-ops/ops-reporter/`.

## Done means
Report-ready tables handed to `ops-manager`, with freshness confirmed.
