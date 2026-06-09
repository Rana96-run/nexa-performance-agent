---
name: learning_named-agent-seats-vs-workflow-workers
description: "Named team agents vs anonymous workflow workers — use named seats for judgment/domain work, anonymous workers for mechanical parallelizable tasks"
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: The 9-agent team (`.claude/agents/*.md`) are named seats with personas, domain ownership, memory, and playbooks. Claude Code also supports anonymous `agent()` calls inside `Workflow()` for parallel mechanical tasks.

Outcome: A codebase review workflow correctly spawned anonymous workers for file-scan tasks. Named agents should only be invoked for judgment-requiring work.

Pattern: Named agent via `Agent` tool + `subagent_type`: use when the task needs role judgment, domain knowledge, or follows a defined handoff chain (e.g., `cro-specialist → ui-ux-designer → developer`). Anonymous `agent()` in `Workflow()`: use for parallelizable mechanical work (grep, scan, transform). Rule of thumb — if the task is "read this file and find X pattern": anonymous. If the task is "decide whether this campaign should be paused and write a recommendation": named seat.

Applies to: Any multi-agent dispatch from CLAUDE.manager.md; `Workflow()` usage in orchestrator scripts.

[[project_agent_team_structure]]
