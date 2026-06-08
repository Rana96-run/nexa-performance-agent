# Skills — Qoyod AI Agent Skill Library

Built following the 5-type AI Team Eco-system framework (Abdelrahman Sleem, Claude Skill Guide).
Each skill gives Claude a specific identity, framework, output format, and guardrails for a task.

---

## Skill Types

| Type | Purpose | Files |
|---|---|---|
| **Role Skills** | Who Claude is when doing the work | paid-media-analyst, connector-police, data-engineer, media-buyer, cro-paid-specialist |
| **Client Skill** | Qoyod product knowledge + brand rules | qoyod-brand |
| **Department Skills** | How each department operates | marketing-ops-dept, growth-marketing-dept |
| **Workflow Skills** | End-to-end process automation | morning-analysis-flow, agent-handoff, approval-execution-flow |
| **Skill Library** | Procedure playbooks (how to do X) | All others below |

---

## Role Skills — Load These First

| Skill | When to load |
|---|---|
| `paid-media-analyst.md` | Any CPQL analysis, period comparison, health check, Slack digest |
| `connector-police.md` | Connector health checks, data gaps, freshness diagnosis |
| `data-engineer.md` | BQ schema changes, new tables, backfills, view rebuilds |
| `media-buyer.md` | Campaign creation, cloning, scaling, audience setup |
| `cro-paid-specialist.md` | Landing page design/audit for paid campaigns, CPQL-to-LP loop |

---

## Client Skill — Always Available

| Skill | When to load |
|---|---|
| `qoyod-brand.md` | Writing Arabic copy, naming campaigns, competitor comparisons, KPI benchmarks, audience strategy |

---

## Department Skills — Agent Interfaces

| Skill | When to load |
|---|---|
| `marketing-ops-dept.md` | Writing/reading ops briefs for the Marketing Ops Management agent |
| `growth-marketing-dept.md` | Writing/reading growth signals for the Growth Marketing agent |

---

## Workflow Skills — End-to-End Flows

| Skill | When to load |
|---|---|
| `morning-analysis-flow.md` | Running the full daily analysis cycle (8 stages) |
| `agent-handoff.md` | Writing handoffs to Ops/Growth agents, debugging stale data |
| `approval-execution-flow.md` | Building nightly #approvals digest, executing ✅ actions, logging outcomes |

---

## Skill Library — Procedure Playbooks

| Skill | When to use |
|---|---|
| `auto-update.md` | **Every session** — resume from latest state + keep memory current |
| `auto-commit-and-push.md` | **Every code change** — commit + push to origin/main |
| `run-collector.md` | "Re-pull X" / "backfill Y" / anything that writes to BQ |
| `check-creds.md` | "Is X connected?" / diagnosing empty tables (ad-hoc) |
| `bq-verify.md` | After a collector run, or dashboard looks off |
| `oauth-helper.md` | New integration or expired LinkedIn token |
| `drive.md` | Read from / write to Google Drive (replaces drive-read + drive-docs) |
| `meta-probe.md` | Meta/IG API 400 on a specific metric |
| `utm-lead-measurement.md` | CPL/CPQL joins at any grain — campaign / adset / ad / channel |
| `hex-sql-cells.md` | Add or update SQL cells in the Hex notebook |
| `consolidate-no-duplicates.md` | 2+ scripts doing related work — collapse to one entry point |
| `review-and-fix.md` | After adding a new action type — audit all logging gaps |
| `verify-before-reporting.md` | **Before stating any BQ number** — cross-check query logic |
| `deploy-verify.md` | After a Railway deploy — verify health + recent logs |
| `railway-sync.md` | Railway env var management and deploy sync |
| `memory-refresh.md` | Consolidate memory files after a long session |
| `funnel-io.md` | Funnel.io data questions |
| `recommendation-writer.md` | Turn a CPQL finding into a full recommendation + Asana task |
| `slack-reporter.md` | **Before any Slack post** — format, channel rules, pre-send checklist |

---

## Adding a New Skill

Only add when the same task has been done ≥ 2 times.
Follow the 12-section anatomy: YAML frontmatter → Role & Identity → Output Framework →
Strategic Framework → Knowledge Pillars → Deliverables → Rules & Guardrails →
Language & Tone → Success Criteria.

Bad: a playbook that says "run this command".
Good: a skill that says "you are X, you think like Y, you always output Z, you never do W".

---

## Multi-Agent Architecture

**Current (the team):** 9 in-house Claude Code subagents — see
`docs/_shared/org-chart.md` and `CLAUDE.manager.md`. CRO/Landing Page is now an
**in-house** department (`cro-specialist → ui-ux-designer → developer`); Marketing
Ops + Growth are in-house **Support** seats (`marketing-ops`, `growth-analyst`).

```
ai-orchestrator (mgr, gates ✅)
    ├── Performance : performance-lead → campaign-manager ∥ creative-strategist
    ├── CRO / LP    : cro-specialist → ui-ux-designer → developer
    └── Support     : marketing-ops ∥ growth-analyst   (growth-analyst owns memory/)
            ↕ docs/landing-pages/reference/  (local snapshot of D:\Landing Page Agent)
```

**Aspirational (not wired):** the `growth-marketing-dept.md` / `marketing-ops-dept.md`
skills describe EXTERNAL strategic agents fed by an `agent_handoff_log` BQ table —
**that table does not exist and no code writes it.** Treat those skills as specs,
not live integrations (each carries a status header). Same for `agent-handoff.md`.

---

## Companion Context

- `../../CLAUDE.md` — root non-negotiables (always takes priority over skills)
- `../../memory/00_index.md` — topical memory files
- `../../docs/PLAYBOOK.md` — Qoyod voice / market / goals
- `../../memory/CRITICAL_KPI_RULES.md` — KPI rules enforced by hook
