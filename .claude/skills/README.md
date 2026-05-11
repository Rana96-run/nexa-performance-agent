# Skills — Reusable task recipes

Each file is a small playbook for a repetitive task Claude (or Amar) might
run in this project. Skills are **read when relevant**, not up-front, to
save tokens.

| Skill | When to use |
|---|---|
| `auto-update.md` | **Every session** — resume from latest state + keep memory current after every change |
| `auto-commit-and-push.md` | **Every code change** — commit + push to origin/main automatically; never leave uncommitted work on disk |
| `run-collector.md` | "Re-pull X" / "backfill Y" / anything that writes to BQ |
| `check-creds.md` | "Is X connected?" / diagnosing empty tables |
| `bq-verify.md` | After a collector run, or dashboard looks off |
| `oauth-helper.md` | New integration or expired LinkedIn token |
| `drive-read.md` | "Check the brief in Drive" / pull a Drive file |
| `meta-probe.md` | Meta/IG API 400 on a specific metric |
| `utm-lead-measurement.md` | CPL/CPQL joins at any grain — campaign / adset / ad / channel; zero-lead diagnosis |
| `hex-sql-cells.md` | Add or update SQL cells in the Hex notebook programmatically |
| `consolidate-no-duplicates.md` | When 2+ scripts/configs/env vars do related work — collapse them to one entry point with subcommands. Resists per-task script proliferation. |
| `review-and-fix.md` | "Anything else?" / after adding a new action type or script — audit all logging gaps, BQ view mappings, _CAT_MAP, detail_sql filters, GID consistency, and _ACTION_VERB. Fix everything found, commit once. |
| `verify-before-reporting.md` | **Before stating any BQ number to the user** — spawn code-reviewer sub-agent to cross-check query logic, then run the recommended secondary check. Never report a number without both steps passing. |

## Adding a new skill

Only add when the same task has been done ≥ 2 times. Keep skills small and
actionable — if it starts reading like a tutorial, it belongs in `memory/`,
not here.

## Companion context

- `../../PLAYBOOK.md` — who we are / voice / goals
- `../../memory/00_index.md` — topical memory files
- `../../CLAUDE.md` — root instructions
