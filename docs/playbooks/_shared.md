# Shared Playbook — what EVERY role reads (shared data + activities)

The one playbook every agent reads alongside its own role playbook. It catches
the **shared data** the whole team works from and the **shared activities** they
all participate in. Role-specific procedure lives in `docs/playbooks/<dept>/<role>.md`.

## Shared data (the single source the whole team works from)
| Data | Where | Rule |
|---|---|---|
| **Spend** | `campaigns_daily.spend` | always **USD**, never SAR |
| **Leads / SQLs** | `hubspot_leads_module_daily` (`leads_total` / `leads_qualified`) | the ONLY lead source — never `campaigns_daily.leads` or `hubspot_leads_daily` |
| **Deal / revenue** | `hubspot_deals_daily` + views | already **USD** (collector converts; don't ÷3.75) |
| **Attribution** | UTM → lead join | pre-aggregate HubSpot in a CTE before joining (spend fan-out) |
| Schema / tables | `memory/01_architecture.md`, `03_bigquery.md`, `13_hubspot_fields.md`, `07_attribution.md` | read live schema, not recollection |
| Reference guides | `memory/knowledge_base/` | Looker map, organic setup; LP design in `docs/landing-pages/reference/` |

## Shared activities (everyone participates)
1. **The 8-step loop** (daily 08:00 Riyadh, run by `ai-orchestrator`): observe →
   compare → investigate → decide-with-full-setup → execute-after-✅ → monitor
   (7d/14d) → learn → forecast. Full detail: `../../CLAUDE.manager.md`.
2. **The #approvals gate:** every write (scale / pause / create / launch / LP
   deploy) waits for the human **✅**. ❌ skips. Negatives are the only direct-execute.
3. **Handoffs:** packet format + who-hands-to-whom in `../_shared/handoff-protocol.md`.
   Parallel: campaign-manager ∥ creative-strategist · marketing-ops ∥ growth-analyst.
   Sequential: cro-specialist → ui-ux-designer → developer.
4. **Memory discipline:** `growth-analyst` owns `memory/` — new traps →
   `08_pitfalls.md`, outcomes → `14_learning_patterns.md`. Each seat writes its own
   learnings to `memory/agents/<dept>/<role>/`.

## Shared rules (non-negotiable, every role)
- **CPQL before CPL.** Lead ≠ SQL. **14-day minimum** for pause/scale.
- **Verified, not attempted** — never claim done / quote an unobserved number.
- **Explicit date windows** (`YYYY-MM-DD to YYYY-MM-DD`), never "last 14 days".
- **Naming** via `executors/naming.py::prefixed()`; **both Meta pixels** on every campaign.
- **No streaming BQ inserts**; **HubSpot read-only** without Slack approval; **Arabic = MSA**.
- Conflicts resolve to `../../CLAUDE.md` then `../../memory/CRITICAL_KPI_RULES.md`.

## Read order for any role
1. `../../memory/CRITICAL_KPI_RULES.md` → 2. **this file** → 3. your role playbook
`docs/playbooks/<dept>/<role>.md` → 4. your memory `memory/agents/<dept>/<role>/`
→ 5. `../_shared/communication-rules.md` + `handoff-protocol.md` as needed.
