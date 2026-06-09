---
name: finding_runtime-personas-never-move-delete
description: runtime_personas/ files are live Railway runtime loaded by claude/roles.py at startup — moving or deleting them breaks production immediately
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: During a dead-code audit, runtime_personas/ files were at risk of deletion. `claude/roles.py` loads 6 specific files from that directory on every Railway startup. Moving or deleting them breaks production immediately.

Source: memory/08_pitfalls.md "2026-06-08 — Agent-system rebuild (critical gates)".

Impact: Railway production agent fails to start; all automated Slack/Asana/analysis workflows go dark.

Fix / How to handle: The 6 protected files are: `qoyod-manager-os`, `qoyod-brand-identity`, `qoyod-paid-media-agent`, `qoyod-analyst-agent`, `nexa-strategist`, `qoyod-daily-report`. Treat as immutable production config. Also: `agent_handoff_log` does NOT exist (no BQ table, no code) — skills assuming it are aspirational specs. New `.claude/agents/*.md` aren't dispatchable by name until `/agents` reload or restart.
