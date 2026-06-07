# Skill: memory-refresh — reload context every 2 hours in long sessions

Use this skill proactively in long-running sessions to prevent stale context
from causing wrong decisions. Trigger it automatically when:
- The session has been running > 2 hours
- You're about to make an architecture decision
- You notice you haven't re-read memory since session start
- Context window is filling up (> 60% used)

---

## What to refresh (in order, read only what's relevant to current task)

```
1. memory/09_open_tasks.md       — what's open, what was just closed
2. memory/01_architecture.md     — current table/view names (they change)
3. memory/08_pitfalls.md         — traps discovered recently (check before any API call)
4. git log --oneline -5          — what shipped since session start
5. git status                    — any uncommitted work drifting
```

## What NOT to reload every time

- `memory/02_*` through `memory/07_*` — reload only if the current task
  touches that domain (e.g. channels.md only if wiring a new channel)
- `CLAUDE.md` — reload only if a naming/KPI decision is being made
- Skills — reload only when about to use that skill

## Refresh trigger checklist

Before refreshing, ask:
- Have I made any wrong assumptions about table names in the last hour? → reload 01
- Have I hit an API error I may have documented before? → reload 08
- Is there a task I closed recently that I might redo? → reload 09
- Did code ship (Railway deploy) that I haven't accounted for? → git log

## After refresh

- Note the refresh happened (one line in your reasoning)
- If anything in memory contradicts what you thought → stop, correct, continue
- If memory is stale (hasn't been updated this session) → update it now per `auto-update.md`

## Cleanup rule (run when condensing memory)

When `09_open_tasks.md` grows beyond ~200 lines:
1. Move all `[x]` done items older than the current session into the
   "Archived sessions (condensed)" block at the bottom — one bullet per session
2. Keep the current session's `[x]` items in full for audit trail
3. Keep ALL `[ ]` open items in full — never archive uncompleted work
4. Temp files (`scripts/_*.py`, `scripts/_diag_*.py`) — delete before committing
5. Duplicate entries (same fix described twice across sessions) — keep latest only
