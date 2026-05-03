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

## Session start — always resume from latest state (non-negotiable)

Every session begins by reconstructing the current state, not starting fresh:

1. Run `git log --oneline -10` — read the last 10 commits to know what changed recently
2. Read `memory/09_open_tasks.md` — find pending/in-progress tasks and continue them
3. Read `memory/01_architecture.md` — confirm current schema, table names, view names
4. Check Railway deploy status (health endpoint) and recent log errors
5. Note any uncommitted local changes (`git status`) — address before new work

Then proceed directly to the most recent open task **without asking Amar to recap**.
See `.claude/skills/auto-update.md` for the full self-update protocol.

## Continuous learning (non-negotiable)

You build on accumulated knowledge every session — never from scratch:
- Before acting on any familiar topic, check `memory/` for existing context
- When you discover something new (API trap, naming edge case, schema change), write it to `memory/08_pitfalls.md` immediately
- When a task completes, close it in `memory/09_open_tasks.md` and update `memory/01_architecture.md` if the structure changed
- Each session must leave the agent more capable than it arrived

## Pre-send review (non-negotiable)

Before posting to Slack or creating Asana tasks, always verify:
1. **Slack daily format**: main message has dashboard URL (plain text), peak numbers (top + worst per channel with CPQL), agent actions spelled out in full (never abbreviations like IS/QS). Follow-up message has recommendations referencing Asana tasks + `#approvals` channel.
2. **Naming convention applied**: `{Channel}_{Type}_{Language}_{Product}_{Audience}` — no "Prospecting" audience, products normalized, LinkedIn UTM mapping correct (Group=utm_campaign, Campaign=utm_audience, Ad=utm_content).
3. **Asana task footer present**: every task description ends with Created, Due, Priority, Type, Channel, Asset level, Action.
4. **Approval flow correct**: scale/pause are auto-executed (logged as `EXECUTED:`); optimize/junk trigger an approval request to `#approvals` — never say "pending approval" for scale/pause.

A PreToolUse hook (`.claude/settings.json`) injects this checklist automatically before `slack_post_message` and `create_tasks`.

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

## KPI measurement rules (non-negotiable)

- **Cost comes from the channel** (`campaigns_daily.spend` — always USD).
- **Leads and SQLs come from HubSpot Lead Module only** (`hubspot_leads_module_daily`).
  Never use `hubspot_leads_daily` (legacy contact lifecycle — nothing writes to it).
- **Evaluation order: CPQL first, then CPL.** A good CPL with bad CPQL = bad campaign.
- **Minimum window for pause/scale decisions: 14 days** (`DAYS_FOR_PAUSE_DECISION = 14`).
  Never act on fewer than 14 days of data.
- **Always pre-aggregate HubSpot before joining** to avoid spend fan-out:
  ```sql
  WITH hs AS (
    SELECT date, lead_utm_campaign,
           SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
    FROM hubspot_leads_module_daily
    GROUP BY date, lead_utm_campaign
  )
  SELECT c.*, hs.*
  FROM campaigns_daily c
  LEFT JOIN hs ON c.date = hs.date
             AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
  ```
  Direct JOIN without CTE multiplies spend by the number of matching HubSpot rows.

## Campaign naming convention (non-negotiable)

Format: `{Channel}_{Type}_{Language}_{Product}_{Audience}`

**Audience rules — enforced by `executors/naming.py`:**
- Prospecting campaigns → audience must be `Interests` or `Lookalike`. "Prospecting" alone is invalid and raises `ValueError`.
- Retargeting campaigns → audience is `Retargeting`. Never combine with "Prospecting".

**Product normalization — enforced, auto-corrected:**
- E-Invoice / einvoice / e_invoice → `Invoice`
- Qbookkeeping / bookkeeping → `Bookkeeping`
- qflavours / flavours → `Qflavours`
- Seasonal campaigns → use the actual season name (e.g. `Ramadan`, `NationalDay`, `BackToSchool`)

**Valid audience values:** `Interests` | `Lookalike` | `Retargeting` | `Broad`

Examples (Meta / Google / Snapchat):
```
Meta_LeadGen_AR_Invoice_Interests          ✓ prospecting with Interests
Meta_LeadGen_AR_Invoice_Lookalike          ✓ prospecting with Lookalike
Meta_LeadGen_AR_Invoice_Retargeting        ✓ retargeting
Snapchat_LeadGen_AR_Bookkeeping_Interests  ✓ Qbookkeeping auto-normalised
Google_Search_AR_Ramadan_Broad             ✓ seasonal
Meta_LeadGen_AR_Invoice_Prospecting        ✗ raises ValueError — use Interests or Lookalike
```

**LinkedIn UTM mapping is DIFFERENT — each level maps to a different UTM param:**

| LinkedIn level  | UTM param      | Name format                             | Example                          |
|----------------|----------------|-----------------------------------------|----------------------------------|
| Campaign        | `utm_campaign` | `LinkedIn_{Product}`                    | `LinkedIn_Invoice`               |
| Ad Set          | `utm_audience` | `LinkedIn_{Type}_{Language}_{Audience}` | `LinkedIn_LeadGen_AR_Interests`  |
| Ad              | `utm_content`  | `LinkedIn_{CreativeVariant}`            | `LinkedIn_VideoV1_AR`            |

> LinkedIn UI now matches Meta (Campaign / Ad Set / Ad). Previously called Campaign Group / Campaign / Ad.

All executors delegate to `executors/naming.py::prefixed()` — never bypass it.

## Two runtimes (don't confuse them)

- `reporting_scheduler.py` — 6h data refresh, dashboard-only
- `main.py daily` — always-on operational agent (Slack, Asana, pause/scale
  watchers)

See `memory/05_scheduler.md`.

## Before asking a question (non-negotiable)

Before asking Amar anything, exhaust the knowledge base first:

1. Check `memory/00_index.md` — find the relevant memory file and read it
2. Check `memory/08_pitfalls.md` — the answer may already be documented as a known trap
3. Check `memory/01_architecture.md` — for schema, table names, field names
4. Search the codebase with Grep for the symbol, field, or pattern in question
5. Check `.claude/skills/README.md` — there may be a recipe for it

Only ask Amar **after all of the above have been checked and found no answer**.
When you do ask, state what you already checked so the answer can be written back to memory.

When raising a question, also include **3 follow-up questions** — things that
are likely to break or become ambiguous in future edits related to the same area.
Format them as:
> **While we're here — 3 things that may break later:**
> 1. …
> 2. …
> 3. …

This keeps decisions in memory before they become bugs, not after.

## Always choose simpler and sustainable (non-negotiable)

Before building anything new, ask: does a tool already in use solve this?

- **Use what exists** — Hex is the dashboard (not Streamlit). Railway hosts the agent (not Replit). HubSpot holds leads (not a custom DB).
- **No new infrastructure** unless the existing tool genuinely can't do it.
- **Prefer editing over rebuilding** — update a Hex cell before writing a new page; update a BQ view before adding a new collector.
- **If two options exist**, pick the one with fewer moving parts, fewer credentials to manage, and fewer things that can break.
- **Call it out** — if asked to build something that already exists elsewhere in the stack, say so and propose the simpler path instead.

## When unsure

- **Ask Amar in Slack** rather than invent data or guess a field name — **only after searching memory/ first**
- **Add to `memory/08_pitfalls.md`** the moment a new API trap is
  discovered — one line, include the fix
- **Add to `memory/09_open_tasks.md`** for work that spans sessions

## Update discipline

When a fact changes, edit the relevant `memory/*.md` in place. Don't
sprinkle updates across code comments or commit messages.
