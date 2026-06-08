# Handoff Protocol — who hands to whom, who runs in parallel

A handoff is how one agent passes work to another without doing that other
agent's job. This is what stops "talking to myself": each seat finishes its
piece and hands a clean packet onward.

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

### Dept 1 — Performance (parallel directs)
```
performance-lead ──┬──► campaign-manager      (build: naming, pixels, keywords)
                   └──► creative-strategist   (copy, A/B, persona)
```
`campaign-manager` and `creative-strategist` run **in parallel — they do NOT hand
off to each other.** Both return to `performance-lead`, who gates and reports up.
`creative-strategist` makes ONE cross-dept handoff: align LP assets with
`cro-specialist` before a test goes live.

### Dept 2 — CRO / Landing Page (direct sequential chain)
```
cro-specialist ──► ui-ux-designer ──► developer ──► (back to) cro-specialist
   (brief +          (annotated         (build, UTM,        (calls the
    hypothesis)       design + notes)     pixels, deploy,     test result)
                                          verify in Events Mgr)
```
This is the only **direct, sequential handoff chain** in the org. Each link waits
for the previous one's output. The artifact travels through the shared workspace
`docs/landing-pages/` with **one filename per test**: `briefs/` (cro-specialist)
→ `designs/` (ui-ux-designer) → `specs/` (developer) → result back to cro-specialist.

### Dept 3 — Support (parallel, no internal handoff)
```
marketing-ops      growth-analyst
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
- Stale data (not live BQ) → `growth-analyst` blocks; `marketing-ops` fires
  #nexa-health on RED only.

## After the handoff (close the loop)
`growth-analyst` records every action outcome in `memory/14_learning_patterns.md`
and writes new API traps to `memory/08_pitfalls.md`. A handoff isn't done until
its outcome is recorded.
