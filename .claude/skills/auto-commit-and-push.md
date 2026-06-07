# Auto-commit & push — never leave work uncommitted

**When to use:** Every time you Edit or Write a file in this repo. This is a
**rigid skill** — follow it exactly. Do not adapt away the discipline.

## Why this exists

On 2026-05-10 we discovered 4 production-critical files sitting uncommitted
for days from a prior session — including a Snapchat slug bug that was
silently dropping all Snapchat leads from the dashboard. The fix had been
done, verified, and documented, but the session ended without a commit.
That's a failure mode of "session drift" we won't repeat.

## The rule

**After any successful change to production code (collectors/, analysers/,
notifications/, executors/, scripts/, reports/, config.py,
operational_scheduler.py, reporting_scheduler.py, main.py, or any
top-level .py file), commit and push to `origin/main` before continuing.**

"Successful" = the change works (tests pass, syntax valid, manual
verification done if applicable). Don't commit broken intermediate states.

## What "auto" means

- **You (Claude) initiate the commit and push without asking.** No
  "should I commit this?" prompt — just do it. The user already opted in.
- One commit per logical task. If you fix two unrelated bugs, that's two
  commits. If you fix one bug across three files, that's one commit.
- Always push immediately after committing. Railway auto-deploys from
  `origin/main`, and the whole point of this skill is "anything done
  locally lands in production". A local commit that never pushes is the
  same failure mode this skill exists to prevent.

## Commit format

Use the existing repo style — conventional commits:

```
fix(views): align Microsoft Ads slug in v_channel_key_map

The channel-key map produced 'microsoft' as paid_channel for HubSpot
"Microsoft Ads" deals, but the Microsoft Ads collector writes
'microsoft_ads' to campaigns_daily.channel. The mismatch caused
channel_roas_daily to produce two separate rows (...).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

- Scope prefix: `fix`, `feat`, `refactor`, `docs`, `chore`
- Optional scope in parens: `(views)`, `(deals)`, `(slack)`
- Body explains WHY, not just WHAT
- Always include the Claude co-author footer

## What NOT to auto-commit

Skip auto-commit (and tell the user) when:

1. **Pre-existing uncommitted changes from a prior session.** If `git status`
   shows files you didn't touch, surface them — don't bundle them into your
   commit. Run a git status audit at session start (per `auto-update.md`).
2. **Files that may contain secrets.** Anything matching `.env*`,
   `credentials*.json`, `*-key.json`, `*token*.txt`. Stop and ask.
3. **`logs/*.csv` or `logs/*.log`.** These are runtime outputs. Add to
   `.gitignore` instead if they're appearing as untracked.
4. **`.cache/` files.** Per-machine state (e.g., `last_scale_pause_run.txt`).
5. **Memory files (`memory/*.md`)** — DO commit these (they're docs), but
   keep them in their own commit, separate from code changes, so the
   commit history stays scannable.

## Verification after push

After every push, run:
```bash
git log --oneline -1                        # confirm commit exists
git log --oneline origin/main..HEAD         # should be empty
```

If the second command shows commits, you forgot to push. Push.

## When the user says "anything I did just now":

Run:
```bash
git status -sb                              # see what's uncommitted
git diff --stat <files>                     # quick size check
```

If the changes look intentional and complete, commit + push. If they look
half-finished or ambiguous, surface them to the user with a one-line
summary per file before deciding.

## Edge case: session ended with uncommitted changes

If you see files modified but the session is wrapping up (user says "done"
/ "thanks" / similar), do a final `git status` audit. If anything is
uncommitted, commit + push it before signing off. Better to ship one extra
commit than leave a critical fix on disk for days.

## Anti-pattern: committing every file individually

Don't. One commit per task. If you edited config.py, then operational_scheduler.py,
then notifications/slack.py — and they're all part of the same feature — they
go in **one** commit. Read the diff, write a coherent message, ship it.

## Anti-pattern: --amend or rebase on shared branches

Never `--amend` or rebase commits already on `origin/main`. Always create a
NEW commit (even for typo fixes). The rule "create new commits, never
modify pushed history" is non-negotiable.
