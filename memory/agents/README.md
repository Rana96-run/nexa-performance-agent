# Per-Agent Memory

Each of the 9 agents has its own folder: `memory/agents/<dept>/<role>/` (the
manager sits at `memory/agents/ai-orchestrator/`). This is that agent's private
memory — feedback received, patterns learned, critical reminders. An agent reads
its own folder on boot and writes to it when it learns something durable.

`growth-analyst` additionally owns the **shared** `memory/` (writes
`08_pitfalls.md`, updates `14_learning_patterns.md`). The flat `memory/NN_*.md`
files are shared org memory and several are referenced by exact path in
`CLAUDE.md` + the runtime, so they don't move.

## File convention
One fact per file, kebab-case, with frontmatter:
```markdown
---
name: <slug>
description: <one-line summary for recall>
metadata:
  type: feedback | learning | critical | reference
---
<the fact. feedback/learning add **Why:** and **How to apply:**. Link [[other-slug]].>
```
Each folder has a `MEMORY.md` index — one line per fact, newest on top.

## The four kinds of memory & where each lives
| Kind | `type:` | Home | Example |
|---|---|---|---|
| **Files / knowledge** | `reference` | shared `memory/NN_*.md`, `memory/knowledge_base/`; role-specific → here | architecture, BQ schema, LP design system |
| **Feedback** (guidance you were given) | `feedback` | the relevant agent's `memory/agents/<dept>/<role>/` | "build from the org chart, not the log table" |
| **Edits / traps** (something changed or broke + the fix) | — | shared `memory/08_pitfalls.md` (one line + fix); role-specific → here as `learning` | "field renamed leads→leads_total" |
| **Recommendations / outcomes** (what to do, what worked) | `learning` | shared `memory/14_learning_patterns.md` (action outcomes); role-specific → here | "scale ships with a pre-approved revert" |
| **Critical** (must-never-violate) | `critical` | here, or `memory/CRITICAL_KPI_RULES.md` if org-wide | "gate every write on ✅" |

`growth-analyst` is responsible for keeping the shared homes current (08_pitfalls
+ 14_learning_patterns). Each agent writes its own role-specific entries. **Breadth
accrues with use** — the seeds here are starters; the team adds entries every cycle.
