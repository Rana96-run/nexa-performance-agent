---
name: finding_claude-agent-yaml-colon-drops-agent
description: Claude Code agent description with unquoted colon-space silently drops the agent from dispatch registry — validate YAML before deploying
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Three of 9 agents (growth-analyst, developer, ui-ux-designer) were silently dropped from the dispatch registry because their `description:` field had an unquoted `: ` (colon-space) — e.g. "everything: the 8-step loop". YAML reads the embedded colon as a new mapping key → ScannerError → agent dropped.

Source: memory/08_pitfalls.md "Claude Code subagents — invalid YAML frontmatter".

Impact: `Agent type 'growth-analyst' not found` mid-session; dispatch fails silently for 3/9 agents.

Fix / How to handle: Remove embedded `: ` (use `—`) or double-quote the entire description value. Validate with `yaml.safe_load` on the frontmatter before deploying. Run `/agents` or restart after fixing. Rule: agent `description` must be valid YAML — never an unquoted colon-space.
