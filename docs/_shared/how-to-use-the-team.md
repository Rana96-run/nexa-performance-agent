# How to Use the Team — talking to the 9 agents

This is the human-facing guide: how to reach each agent, what to expect back, and
the rules they all follow. Pair it with `org-chart.md` (who exists),
`handoff-protocol.md` (how work moves), and `communication-rules.md` (how they behave).

## Two ways to reach an agent

1. **Name the seat.** Say *"ask the `<agent>` to …"* and that one subagent runs in
   its **own isolated context** (only its playbook + memory), and answers *as that
   role*. This is what avoids the "one giant agent" hallucination.
2. **Let the manager route.** If you're not sure who, ask **`ai-orchestrator`**:
   *"leads are down this month — who handles it?"* It routes to the right department.

> **Activation:** agents are loaded when Claude Code starts. If you just added or
> renamed one, run `/agents` or restart the session so it's invokable by name.

## Example asks, per agent

| Want to… | Say |
|---|---|
| Route an unclear request | *"`ai-orchestrator`: organic + paid both dipped, who looks at it?"* |
| Set/adjust KPI thresholds or budget | *"`performance-lead`: should we raise the CPQL pause ceiling for Bookkeeping?"* |
| Build/clone a campaign on spec | *"`campaign-manager`: build Meta_LeadGen_AR_Invoice_Interests with both pixels."* |
| Plan copy / creative variants | *"`creative-strategist`: scope 3 A/B hooks for the Invoice retargeting set."* |
| Start / decide an LP test | *"`cro-specialist`: open a test for the Invoice page, hypothesis = ZATCA above fold."* |
| Design an LP variant | *"`ui-ux-designer`: design the variant from the Invoice brief."* |
| Build + ship + verify an LP | *"`developer`: build the Invoice variant, wire UTM + both pixels, verify in Events Manager."* |
| Fix tracking / pixels / secrets | *"`marketing-ops`: the Web pixel stopped firing — check it."* |
| Pull data / compare / forecast | *"`growth-analyst`: 7d-vs-prior CPQL by channel, explicit dates, live BQ."* |

## What every agent does on dispatch (so you know what to expect)
1. Reads its own playbook (`docs/playbooks/<dept>/<role>.md`) + its own memory
   (`memory/agents/<dept>/<role>/`) + `memory/CRITICAL_KPI_RULES.md`.
2. Stays in its lane; hands off anything outside it (see `handoff-protocol.md`).
3. Returns a **HANDOFF packet** or a result — numbers only if observed
   ("running — will confirm" otherwise).
4. Writes anything durable it learned back to its memory.

## The rules they all obey (communication guidelines, in brief)
Full text in `communication-rules.md`. The non-negotiables:
- **Stay in your lane** — decide only at your altitude; otherwise hand off.
- **Read before acting** — playbook → own memory → CRITICAL_KPI_RULES → CLAUDE.md.
- **Verified, not attempted** — never claim done / quote a number you didn't observe.
- **Explicit date windows** always (`YYYY-MM-DD to YYYY-MM-DD`).
- **Write what you learn** — `growth-analyst` keeps `memory/` honest.
- **The ✅ gate is sacred** — no scale/pause/create/launch/LP-deploy without the
  human ✅ in #approvals (negative keywords are the only direct-execute exception).

## Who works together vs alone
- **Parallel:** `campaign-manager` ∥ `creative-strategist` · `marketing-ops` ∥ `growth-analyst`.
- **Direct sequential handoff:** `cro-specialist` → `ui-ux-designer` → `developer`.
- **Manager over all:** `ai-orchestrator` gates writes + owns cross-dept handoffs.
