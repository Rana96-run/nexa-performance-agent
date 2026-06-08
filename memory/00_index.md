# Qoyod Performance Agent — Memory Index

**Purpose of this folder:** topical, append-only notes Claude reads on every
session so it doesn't re-discover the codebase from scratch. Each file is a
single concern. Read only what you need.

## ⚠️ CRITICAL AREA — read every session before any paid-media work
- **`CRITICAL_KPI_RULES.md`** — non-negotiables the agent has repeatedly violated;
  hook-enforced. Highest priority. **Decisions lean on this first.**

## Read-order convention

1. **First:** `CRITICAL_KPI_RULES.md` (the critical area, above) + `../PLAYBOOK.md`
2. Read `00_index.md` (this file)
3. Read the topical file for the task at hand
4. Don't read all memory files up-front — that's what burns tokens

> Memory is the one store and we lean on it for decisions — so it stays **clean,
> organized, fully indexed, with the critical area marked**. Adding knowledge?
> File it under the right section below and add its row here. Never dump it loose.

## Directory

| File | When to read |
|---|---|
| `01_architecture.md` | Before any structural change, "where does X live?" |
| `02_credentials.md` | Any "is X connected?" / token question |
| `03_bigquery.md` | Writing SQL, adding/altering tables, debugging views |
| `04_collectors.md` | Touching `collectors/*.py`, adding a new data source |
| `05_scheduler.md` | Anything about cadence, 6h refresh, always-on agent |
| `06_dashboard.md` | Editing `dashboard/*`, Streamlit/Replit questions |
| `07_attribution.md` | Lead ↔ campaign joins, qoyod_source vs UTM |
| `08_pitfalls.md` | API deprecations, BQ streaming-buffer trap, Unicode on Windows |
| `09_open_tasks.md` | "What's next?" — prioritized work queue |
| `10_google_drive.md` | Connecting to / reading the shared Drive folder |
| `11_agent_roles.md` | Which roles live in this repo vs external (Creative, MarkOps) |
| `12_funnel_io.md` | Funnel.io workspace audit, custom dims/metrics, Looker board mapping |
| `13_hubspot_fields.md` | HubSpot BQ schema, UTM→BQ field map, qoyod_source channel key map, CPL/CPQL methodology at every grain |
| `14_learning_patterns.md` | Outcome library — what worked / didn't after each recommended action. Read before recommending a similar action. |
| `14_activity_dashboard.md` | Nexa Agent Activity Hex app — design reference, BQ schema, SQL templates, canvas layout |
| `utm_template.md` | Canonical Google Ads UTM `final_url_suffix` template + custom-param convention. Read BEFORE proposing any UTM string. |
| `15_operational_history.md` | Institutional log of one-off learnings/steps/actions (distilled from the retired `scripts/_*.py`). "Have we done/investigated X before?" |
| `audit_findings.md` | Dated log of automated audit flags (attribution / spend-with-0-leads). Check when investigating a flagged channel/campaign. |

## The team (agents) — NEW

The team is **9 Claude Code subagents** (1 manager + 3 departments), matching the
live "NEXA OPERATIONS HQ — The Team" dashboard. (NOT the 13 `agent_activity_log`
role labels — those are how work is *logged*, not who the team *is*.) Start here:

| Where | What |
|---|---|
| `.claude/agents/README.md` | The roster + how to talk to a teammate |
| `../docs/_shared/org-chart.md` | Who exists, who manages whom, who owns what |
| `../docs/_shared/handoff-protocol.md` | How agents pass work to each other |
| `../docs/_shared/communication-rules.md` | How the team behaves |
| `../docs/playbooks/_index.md` | Every agent's operational playbook |
| `agents/<dept>/<role>/` | Each agent's **private memory** (see `agents/README.md`) |

The flat `NN_*.md` files in this folder are **shared org memory** — every agent
may read them; several are referenced by exact path in `CLAUDE.md` and the
production runtime, so they don't move.

## Knowledge base — curated reference guides

`knowledge_base/` holds longer-form reference docs (see `knowledge_base/README.md`):
- `knowledge_base/looker_to_bq_mapping.md` — Looker dashboards → BigQuery fields
- `knowledge_base/organic_setup_guide.md` — organic-channel setup

(Moved here 2026-06-08 from `md_files/` to stop reference docs scattering.)

## External references (not in repo)

- Google Drive: https://drive.google.com/drive/folders/1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74
  (Claude can't read Drive; ask user to paste relevant doc contents if needed)
- `md_files/` in repo: now **only the 6 runtime persona sources** loaded by
  `claude/roles.py` (+ `_archived/` for superseded ones). Brand identity lives at
  `md_files/qoyod-brand-identity.md` (runtime loads it by path).

## Update discipline

- When a fact changes, **edit the relevant memory file in place** — don't
  sprinkle updates across comments and commit messages.
- Append new pitfalls to `08_pitfalls.md` as they're discovered; one line
  each ("X deprecated in v21, use Y instead").
- When an open task lands, move it from `09_open_tasks.md` to the relevant
  topical file (e.g. LinkedIn token acquisition → `02_credentials.md`).
