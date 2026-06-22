# Handoff Protocol — who hands to whom, who runs in parallel

A handoff is how one agent passes work to another without doing that other
agent's job. This is what stops "talking to myself": each seat finishes its
piece and hands a clean packet onward.

> **Two properties every agent has:**
> 1. **Self-contained** — each agent has its full operating data to work
>    *independently*: its own playbook (`docs/playbooks/<dept>/<role>.md`), its own
>    memory (`memory/agents/<dept>/<role>/`), and the shared playbook
>    (`docs/playbooks/_shared.md`). It never needs another agent's internals to do
>    its own job.
> 2. **Linkable to ANY other agent** — the map below is the *default* flow, not a
>    wall. Any agent can hand a packet to any other agent when the work calls for
>    it (directly, or routed by `ai-orchestrator`). The packet format is the same
>    regardless of who → whom.

## The standard handoff packet
```
HANDOFF
from:    <your-agent-name>
to:      <target-agent-name>
why:     <one line: what triggered this>
window:  <YYYY-MM-DD to YYYY-MM-DD>   ← explicit dates, never "last 14 days"
payload: <facts the receiver needs — numbers, IDs, campaign/adset/ad/LP path>
ask:     <the single decision or action you want back>
```
The receiver must act without re-deriving your work.

## The map (from the live org chart)

### Manager — ai-orchestrator
Runs the 8-step loop daily 08:00 Riyadh. Receives reports from all 3 departments,
queues every write into ONE #approvals digest, **gates every write on ✅**, and
owns all cross-department handoffs. Routes a request to one department, never
fans out blindly.

### Dept 1 — Performance
```
project-coordinator ──► campaign-manager      (KPI flags: CPQL, CPL, ROAS, IS, CTR — DIRECT, no performance-lead hop)
project-coordinator ──► creative-strategist   (copy, A/B, persona — DIRECT)

performance-lead ──► campaign-manager         (strategic follow-through only: budget reallocation, channel launch/sunset)
performance-lead ──► creative-strategist      (strategic creative direction change)
```
`campaign-manager` and `creative-strategist` run **in parallel — they do NOT hand
off to each other.** KPI flags bypass performance-lead and go project-coordinator → campaign-manager directly.
`performance-lead` is reserved for 4 strategic cases: budget reallocation, channel launch/sunset, KPI threshold change, weekly channel mix review.
`creative-strategist` makes ONE cross-dept handoff: align LP assets with `cro-specialist` before a test goes live.

### Dept 2 — CRO / Landing Page (direct sequential chain — 2 steps)
```
cro-specialist ──► developer ──► (back to) cro-specialist
   (brief +          (build, UTM,        (calls the
    design spec)      pixels, deploy,     test result)
                      verify in Events Mgr)
```
This is the only **direct, sequential handoff chain** in the org. CRO Specialist produces BOTH
the 8-section brief AND the annotated design spec, then hands the combined package to developer.
The artifact travels through the shared workspace `docs/landing-pages/` with **one filename per test**:
`briefs/` (cro-specialist brief) → developer implements from the same package → result back to cro-specialist.

### Dept 3 — Support (parallel, no internal handoff)
```
project-coordinator      growth-analyst
   (UTM/pixel/         (BQ analysis,
    secrets)            memory, forecasts)
```
Both **serve both departments above** and have **no internal handoff** — they're
called directly, run in parallel, and don't chain to each other.

## Escalation & gate
- A role reports up to its lead; a lead reports to `ai-orchestrator`.
- **Every write** (scale / pause / create / launch / LP deploy) waits for the
  human **✅** in #approvals. ❌ skips. No exceptions except negative keywords
  (no spend at risk).
- Stale data (not live BQ) → `growth-analyst` blocks; `project-coordinator` fires
  #nexa-health on RED only.

## After the handoff (close the loop)
`growth-analyst` records every action outcome in `memory/14_learning_patterns.md`
and writes new API traps to `memory/08_pitfalls.md`. A handoff isn't done until
its outcome is recorded.
