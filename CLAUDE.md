# CLAUDE.md — Entry point for every Claude session

**You are working on the Qoyod Performance Agent.** Read in this order
before doing anything else:

1. **`docs/PLAYBOOK.md`** — who we are, audience, voice, goals,
   market rules. This is identity context; ~5 minute read.
2. **`memory/00_index.md`** — directory of topical memory files. Read
   only the ones relevant to the task at hand. Do **not** read them all
   up-front; that burns tokens for no gain.
3. **`.claude/skills/README.md`** — reusable recipes for repetitive
   tasks (running a collector, checking creds, verifying BQ, Drive
   reads, OAuth, Meta probes).

## Golden rules (non-negotiable)

- **No streaming BQ inserts.** Use `load_table_from_file(BytesIO(ndjson))`
  always. See `memory/08_pitfalls.md`.
- **HubSpot is read-only** unless Amar explicitly approves in Slack.
  No PATCH / DELETE / POST to HubSpot without sign-off.
- **Arabic copy is MSA.** Never colloquial. See `docs/PLAYBOOK.md` §4.
- **Secrets come from `.env` / Replit Secrets.** Never hardcode.
- **Currency is SAR.** Platforms returning micros (Google Ads cost_micros,
  Snap spend) are divided by 1,000,000.
- **Time zone is Asia/Riyadh (UTC+3)** for user-facing times; BQ stores UTC.

## Two runtimes (don't confuse them)

- `reporting_scheduler.py` — 6h data refresh, dashboard-only
- `main.py daily` — always-on operational agent (Slack, Asana, pause/scale
  watchers)

See `memory/05_scheduler.md`.

## When unsure

- **Ask Amar in Slack** rather than invent data or guess a field name
- **Add to `memory/08_pitfalls.md`** the moment a new API trap is
  discovered — one line, include the fix
- **Add to `memory/09_open_tasks.md`** for work that spans sessions

## Update discipline

When a fact changes, edit the relevant `memory/*.md` in place. Don't
sprinkle updates across code comments or commit messages.
