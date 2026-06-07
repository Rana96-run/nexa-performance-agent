# consolidate-no-duplicates — One context, one entry point

## Principle

**When two or more files do related operations, consolidate them under one CLI/module — don't add a third sibling.** The goal is fewer commands to remember, fewer places to look, fewer drift opportunities. Codebases get cluttered one "just one more script" at a time; this skill is the muscle that resists that drift.

## When to apply

Trigger this skill any time you notice:

- A folder has **2+ files in the same family** (`audit_active_keywords.py`, `audit_active_negatives.py`, `action_audit_violations.py`)
- The user is about to ask for a **new sibling** (e.g. "add `audit_paused_keywords.py`") — instead, propose extending the unified CLI
- The same domain logic appears **duplicated across files** (e.g. cost-pricing constants in 3 modules — pull them into one)
- **Multiple env vars** mean the same thing (`ASANA_PROJECT_X` + `ASANA_PORTFOLIO_X` with `or` fallbacks — usually a sign one was renamed and never cleaned up)
- **Multiple endpoints / commands / Slack channels** for the same logical event

## The consolidation pattern

For scripts:

1. **Create one CLI dispatcher** (`scripts/<domain>.py`) using `argparse` subparsers.
2. **Each subcommand delegates** to a function in the original module — don't move ~1000 lines into one file just to satisfy "one place".
3. **Keep the underlying modules importable** — strip nothing if it would break other imports.
4. **Legacy CLIs continue to work** for backwards compatibility — they remain valid invocations until the team has fully migrated.
5. **Update `CLAUDE.md`** to point at the new canonical command. Mark legacy as "still works but prefer the new CLI".
6. **Document the trade-off** in the new dispatcher's docstring — explain why this file exists vs touching the originals.

For env vars / Slack channels / config keys:

1. Pick **one canonical name**.
2. Add a **fallback** in the loader: `os.getenv("NEW_NAME") or os.getenv("LEGACY_NAME")`.
3. Document the legacy name in a comment so future readers know it's deprecated.
4. Once migration is complete (Railway env stripped, all writers using new name), delete the fallback.

## Worked example — audit consolidation (2026-05-08)

**Before:** 3 sibling CLIs in `scripts/`:
- `audit_active_keywords.py` (`python scripts/audit_active_keywords.py`)
- `audit_active_negatives.py` (`python scripts/audit_active_negatives.py`)
- `action_audit_violations.py` (`python scripts/action_audit_violations.py`)

Three commands to remember; three files to update when adding shared options.

**After:** one CLI:
```
python scripts/audit.py keywords    [--silent]
python scripts/audit.py negatives
python scripts/audit.py violations  [--csv FILE] [--dry-run] [--asana-task GID]
```

Implementation: `scripts/audit.py` is ~140 lines. Each subcommand imports the relevant function from the original module and calls it with the right args. The 3 original files are unchanged — they remain importable, and their `__main__` blocks still work (legacy invocation kept alive).

**CLAUDE.md update:**
```markdown
- `python scripts/audit.py keywords` — scans all ENABLED keywords for…
- `python scripts/audit.py negatives` — scans all ACTIVE negatives for…
- `python scripts/audit.py violations` — executes rule-mandated PAUSE/DELETE…

Legacy direct invocations still work but the unified CLI above is preferred.
```

## Anti-patterns

- ❌ **Don't auto-merge code** that would require 1000+ lines moved across files. The dispatcher pattern gives you the UX win without the regression risk.
- ❌ **Don't delete the originals immediately** — wait until any tooling, CLAUDE.md, MEMORY.md, GitHub Actions, or Railway commands referencing them has been updated AND verified.
- ❌ **Don't consolidate things that aren't related** — `audit.py` for keyword audits is fine; `everything.py` for "all the scripts" is not.
- ❌ **Don't introduce new env vars when a legacy one exists**. Reuse the legacy name OR add a fallback that reads both. Never split one concept across two keys (`SLACK_BOT_TOKEN` + `SLACK_ACCESS_TOKEN` is a mess we already paid for).
- ❌ **Don't break things to be "clean"**. If a fallback `or` chain is ugly but works, leave it until you've tested the canonical name in production.

## The env-var audit rule (added 2026-05-08 after a foot-gun)

**"No Python import" ≠ "dead". Before deleting any env var, ask three questions:**

1. **Is it reserved for a feature that's currently disabled but expected to be re-enabled?** Examples: `EMAIL_*` is dormant because the agent posts to Slack today, but `notifications/notify.send_email()` is a documented future fallback. Removing it now means restoring it from a backup later when someone flips the channel.
2. **Does it hold metadata about a real human or external entity?** Examples: `ASANA_ASSIGNEE_DONIA` is a current team member's Asana GID, even if no Python `getenv` reads it yet — a pending Asana feature might consume it. `HUBSPOT_PORTAL_ID` is a portal ID baked into deep-link URLs.
3. **Is it referenced by a different runtime than the one I'm grepping?** Railway runs Python; GitHub Actions runs YAML + inline `python - <<EOF`. An env var with no `*.py` ref might still be consumed by the YAML inline script. Always grep `*.py *.yml *.yaml *.toml *.md` before declaring something dead.

**If any answer is "yes" or "unsure", keep the var.** Env vars are free; surprise outages when a feature gets re-enabled are not.

**Worked example (the foot-gun):** I deleted 8 "dead" Railway env vars after grepping only `*.py`. Three of them (`EMAIL_PERFORMANCE`, `EMAIL_TEAM_LEAD`, `EMAIL_TEAM_MANAGER`) were reserved for the email-fallback path. One (`ASANA_ASSIGNEE_DONIA`) held a current assignee's GID. The user — rightly — pushed back and I had to restore all 8. Don't repeat this. Bias toward restoration when in doubt; the cost of a kept-but-unused var is one row in Railway's variables panel.

**Audit cadence**: env-var cleanup belongs in a **standalone deletion proposal review**, not a casual "while I was in there" sweep. Always present the candidate list to the human first with each var's three-question answer before pressing delete.

## Future consolidation queue (as of 2026-05-08)

Already done: `scripts/audit.py` (3 → 1 CLI).

Remaining (proposed):
- `scripts/bulk.py` — merge `bulk_ads.py` + `bulk_keywords.py`
- `scripts/oauth.py` — merge `linkedin_oauth.py` + `microsoft_oauth.py` + `tiktok_oauth.py`
- `scripts/miro.py` — merge `miro_agent_workflow.py` + `miro_use_cases_v2.py`
- `scripts/probe.py` — merge `probe_hubspot_props.py` + `report_validator.py`

Trigger this skill whenever picking up one of those.
