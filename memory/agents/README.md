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
