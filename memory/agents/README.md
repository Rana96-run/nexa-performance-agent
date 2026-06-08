# Per-Agent Memory

Each agent has its own folder here: `memory/agents/<department>/<role>/`. This is
**that agent's private memory** — the feedback it has received, the patterns it
has learned, and its own critical reminders. An agent reads its own folder on
boot and writes to it whenever it learns something durable.

## Why separate from `memory/*.md`
The flat `memory/NN_*.md` files (architecture, bigquery, pitfalls, learning
patterns, CRITICAL_KPI_RULES …) are **shared org memory** — cross-cutting facts
every agent may need, and several are referenced by exact path in `CLAUDE.md`
and the production runtime. Those stay where they are. Per-agent memory layers
on top: role-specific, small, and owned by one seat.

## File convention (same as the root memory system)
One fact per file, kebab-case name, with frontmatter:

```markdown
---
name: <short-slug>
description: <one-line summary — used to decide relevance on recall>
metadata:
  type: feedback | learning | critical | reference
---

<the fact. For feedback/learning add **Why:** and **How to apply:** lines.
Link related memories with [[their-name]].>
```

Each folder has a `MEMORY.md` index — one line per fact, newest on top.

## Types
- **feedback** — guidance a manager gave this role (with the why).
- **learning** — a pattern the role discovered (what worked / failed).
- **critical** — a must-never-violate reminder specific to this role.
- **reference** — a pointer (a script, a dashboard, a BQ view) the role reuses.

## Routing rule
- Role-specific → here. Cross-cutting trap → `memory/08_pitfalls.md`.
- Action outcome → `memory/14_learning_patterns.md`. Must-never → `memory/CRITICAL_KPI_RULES.md`.
