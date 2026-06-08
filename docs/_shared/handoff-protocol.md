# Handoff Protocol — How agents pass work to each other

A handoff is how one agent gives work to another **without doing that other
agent's job.** This is what stops "talking to myself": instead of one context
trying to be analyst + buyer + reporter at once, each seat finishes its piece
and hands a clean package to the next.

## The standard handoff packet

Every handoff — up, down, or sideways — is a small structured block:

```
HANDOFF
from:    <your-agent-name>
to:      <target-agent-name>
why:     <one line: what triggered this>
window:  <YYYY-MM-DD to YYYY-MM-DD>   ← always explicit dates, never "last 14 days"
payload: <the facts the receiver needs — numbers, IDs, campaign/adset/ad path>
ask:     <the single decision or action you want back>
```

The receiver must be able to act **without re-deriving your work.** If they'd
have to re-pull the data you already pulled, your payload is incomplete.

## The core loop (daily)

```
connector-police  → "data is GREEN for 2026-06-01..06-07"   (gate)
        │
paid-media-analyst → flags: CPQL_REGRESSED on Meta_LeadGen_AR_Invoice_Interests
        │            (period comparison + root cause in payload)
        ▼
performance-lead   → routes the flag to the right owner
   ├──► media-buyer        → drafts full pause/scale setup → #approvals
   ├──► cro-paid-specialist→ if the problem is the landing page
   ├──► keyword-strategist → if the problem is search terms
   └──► data-engineer      → if the numbers look wrong (schema/collector)
        │
   human ✅ in #approvals
        ▼
   media-buyer executes  →  approval-coordinator logs outcome at 7d & 14d
        ▼
   ops-reporter folds result into the leadership report
        ▼
   growth-lead (weekly) reads the trend, sends budget/channel directive back down
```

## Who may hand to whom

| From | May hand to | May NOT |
|---|---|---|
| any role | its own dept manager | the CMO directly (go through your manager) |
| dept manager | any role in its dept, the CMO, a sibling manager | reach into another dept's roles directly |
| cmo-orchestrator | any dept manager | execute platform/BQ changes itself |
| paid-media-analyst | performance-lead | execute a pause/scale (analyst surfaces only) |
| growth/ops roles | their manager | touch BQ or ad platforms (read via handoff only) |

## Escalation
- **Up:** a role escalates to its manager; a manager escalates to the CMO.
- **Trigger to escalate:** decision is above your altitude, crosses departments,
  or risks spend/CPQL beyond your guardrail.
- **Stale data (>26h / not GREEN):** connector-police blocks; no decisions made
  on stale data — report "Data unavailable" with the timestamp.

## After the handoff (non-negotiable close-out)
Every executed action gets re-evaluated at **7 and 14 days** by
approval-coordinator, the outcome written to `memory/14_learning_patterns.md`,
and the originating agent's `memory/agents/<role>/` updated. A handoff isn't
"done" until its outcome is recorded — see `communication-rules.md`.

## Cross-repo handoff (creative / LP / content)
This repo never does creative or content *production*. To reach the Landing
Page Agent, open an Asana `[Creative Brief]` task with the full context (window,
CPQL, target, page URL, exact ask). That task IS the handoff packet.
