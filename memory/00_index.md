# Qoyod Performance Agent — Memory Index

**Purpose of this folder:** topical, append-only notes Claude reads on every
session so it doesn't re-discover the codebase from scratch. Each file is a
single concern. Read only what you need.

## Read-order convention

1. **First:** read `../PLAYBOOK.md` (who we are, voice, goals, market rules)
2. Read `00_index.md` (this file)
3. Read the topical file for the task at hand
4. Don't read all memory files up-front — that's what burns tokens

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

## External references (not in repo)

- Google Drive: https://drive.google.com/drive/folders/1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74
  (Claude can't read Drive; ask user to paste relevant doc contents if needed)
- `md_files/` in repo: Looker mapping, organic setup guide, brand identity,
  agent spec. Longer-form than memory files; read when doing relevant work.

## Update discipline

- When a fact changes, **edit the relevant memory file in place** — don't
  sprinkle updates across comments and commit messages.
- Append new pitfalls to `08_pitfalls.md` as they're discovered; one line
  each ("X deprecated in v21, use Y instead").
- When an open task lands, move it from `09_open_tasks.md` to the relevant
  topical file (e.g. LinkedIn token acquisition → `02_credentials.md`).
