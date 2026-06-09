---
name: learning_stop-hook-auto-commit
description: "Stop hook auto-commits and pushes all local changes to origin/main, and logs to BQ activity dashboard"
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: Added a Stop hook to ensure no local changes are ever left uncommitted after a Claude session. Also extended it to write a `claude_session / code_committed` row to `agent_activity_log` so every code change appears in the Hex activity dashboard.

Outcome: Works correctly — hook fires after every turn, commits non-excluded files, pushes to origin/main, writes BQ row. Verified: `2026-06-09 08:25:18, code_committed, 4 files`.

Pattern: Stop hooks are the right place for end-of-turn housekeeping (commit, log, notify). They must always exit 0 — never block the session from stopping. BQ logging goes in a `try/except` that prints to stderr on failure rather than silently swallowing it.

Applies to: Any future session where auto-commit or end-of-turn BQ logging needs to be added or debugged.

Excluded patterns in the hook: `.env`, `secrets/`, `*.log`, `__pycache__`, `_diag_out.txt`, `_recon_out.txt`, root-level `_*.txt`/`_*.json`, `*.pyc`, `.cache/`.

[[feedback_deploy_workflow]]
