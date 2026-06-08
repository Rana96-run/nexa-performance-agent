# Agents — Nexa Operations HQ · The Team (index + how to use)

The **real** team: **9 agents** = 1 manager + 3 departments. Each `*.md` here
(except `README.md` and `_TEMPLATE.md`) is one teammate with its own isolated
context, playbook, and memory. Isolated context is what cuts hallucination — each
agent loads only its own small files, not the whole repo.

> Note: the `agent_activity_log` *function labels* (bq_refresh, health_monitor,
> performance_audit, ops_scheduler, …) are how work is **logged**, not the team
> roster. The team is the 9 below.

## Activation & troubleshooting
- **Make agents callable:** Claude Code loads `.claude/agents/` at session start. After
  adding/renaming/editing an agent, run **`/agents`** (or restart the session) so it's
  dispatchable by name. Until then a *new* agent isn't in the registry.
- **An agent silently won't load / "agent type not found"?** Its **frontmatter YAML is
  invalid** — Claude Code drops it. Most common cause: an unquoted `: ` (colon-space)
  inside `description`. Validate all 9:
  `python -c "import glob,re,yaml; [yaml.safe_load(re.match(r'^---\n(.*?)\n---',open(f,encoding='utf-8').read(),16).group(1)) for f in glob.glob('.claude/agents/*.md') if 'README' not in f]"`
  (2026-06-09: this dropped `growth-analyst`, `developer`, `ui-ux-designer` — fixed.)

## How to talk to a teammate
Name the seat in plain language:
- *"Ask the **campaign-manager** to build Meta_LeadGen_AR_Invoice_Interests."*
- *"Have the **growth-analyst** run the weekly period comparison on live BQ."*
- *"**cro-specialist**: start an LP test for the Invoice page."*
- *"**ai-orchestrator**: leads are down this month — route it."*

## The roster

| Agent | Dept | Role |
|---|---|---|
| `ai-orchestrator` | — | Manager over all 3 depts. 8-step loop 08:00, gates writes ✅, owns handoffs. |
| `performance-lead` | Performance (LEAD) | KPI zones, 14-day min, channel mix + budget, the ✅/❌ sign-off. |
| `campaign-manager` | Performance | 12-field naming, both Meta pixels, keyword policy buckets. |
| `creative-strategist` | Performance | OCEAN personas, A/B variants, LP alignment with CRO. |
| `cro-specialist` | CRO / LP (chain lead) | 8-section LP brief, hypothesis, ZATCA badge, test-result decision. |
| `ui-ux-designer` | CRO / LP | LP variant design to persona, annotated handoff to Developer. |
| `developer` | CRO / LP | Build LP, UTM passthrough, pixel fires, deploy, verify in Events Mgr. |
| `marketing-ops` | Support (OPS) | UTM/pixel/field-map policy, Railway secrets, #nexa-health on RED. |
| `growth-analyst` | Support (DATA) | Owns memory/; 8-step loop on live BQ, period compares, forecasts. |

## Parallel vs sequential
- **Parallel:** campaign-manager ∥ creative-strategist · marketing-ops ∥ growth-analyst.
- **Sequential (direct handoff):** cro-specialist → ui-ux-designer → developer.
- Manager `ai-orchestrator` gates every write and routes cross-dept work.

## The map
- `../../docs/INDEX.md` — **MASTER INDEX**: the one front door to everything (shared + per-role)
- `../../docs/playbooks/_shared.md` — the **shared playbook** (shared data + activities every role reads)
- `../../CLAUDE.manager.md` — the **Manager OS**: how `ai-orchestrator` runs the team (loop, routing, gate, cadence)
- `../../docs/_shared/how-to-use-the-team.md` — **start here:** how to talk to each agent + example asks
- `../../docs/_shared/org-chart.md` · `handoff-protocol.md` · `communication-rules.md`
- `_archived/` — retired agent definitions (not active; revive by moving back)
- `../../docs/playbooks/_index.md` — every agent's playbook
- `../../memory/agents/` — per-agent memory (`agents/README.md`)

## Adding / renaming a role
Copy `_TEMPLATE.md`, add a playbook + memory folder, update `org-chart.md` + this
table. Keep each agent file small. `.claude/agents/` is allowlisted in `.gitignore`.

## Relationship to the production runtime
These are **dev-time** subagents. The autonomous Railway product runs through
`claude/roles.py` + `claude/manager.py` (a separate layer). Editing an agent here
does NOT change Railway.
