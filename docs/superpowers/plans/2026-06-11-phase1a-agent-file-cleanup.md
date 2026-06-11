# Phase 1A — Agent File Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 4 missing fields (scope/does-NOT-own, skills+trust, memory, handoffs) to all 9 agent `.md` files and create the `memory/agents/` private folder structure.

**Architecture:** Pure markdown content changes — no code touched. Each agent file gets 4 new sections inserted after its existing boot sequence. Existing content (hard rules, efficiency rules, output, done means) is preserved exactly. Memory folders are created as empty directories with a `.gitkeep`.

**Tech Stack:** Markdown, git.

---

## File map

**Modified:**
- `.claude/agents/ai-orchestrator.md`
- `.claude/agents/performance-lead.md`
- `.claude/agents/campaign-manager.md`
- `.claude/agents/creative-strategist.md`
- `.claude/agents/cro-specialist.md`
- `.claude/agents/ui-ux-designer.md`
- `.claude/agents/developer.md`
- `.claude/agents/marketing-ops.md`
- `.claude/agents/growth-analyst.md`

**Created:**
- `memory/agents/manager/ai-orchestrator/.gitkeep`
- `memory/agents/performance/performance-lead/.gitkeep`
- `memory/agents/performance/campaign-manager/.gitkeep`
- `memory/agents/performance/creative-strategist/.gitkeep`
- `memory/agents/cro/cro-specialist/.gitkeep`
- `memory/agents/cro/ui-ux-designer/.gitkeep`
- `memory/agents/cro/developer/.gitkeep`
- `memory/agents/support/marketing-ops/.gitkeep`
- `memory/agents/support/growth-analyst/.gitkeep`

---

## Task 1 — Create memory/agents/ folder structure

**Files:**
- Create: `memory/agents/manager/ai-orchestrator/.gitkeep`
- Create: `memory/agents/performance/performance-lead/.gitkeep`
- Create: `memory/agents/performance/campaign-manager/.gitkeep`
- Create: `memory/agents/performance/creative-strategist/.gitkeep`
- Create: `memory/agents/cro/cro-specialist/.gitkeep`
- Create: `memory/agents/cro/ui-ux-designer/.gitkeep`
- Create: `memory/agents/cro/developer/.gitkeep`
- Create: `memory/agents/support/marketing-ops/.gitkeep`
- Create: `memory/agents/support/growth-analyst/.gitkeep`

- [ ] **Step 1: Create all 9 private memory folders**

```bash
mkdir -p "memory/agents/manager/ai-orchestrator"
mkdir -p "memory/agents/performance/performance-lead"
mkdir -p "memory/agents/performance/campaign-manager"
mkdir -p "memory/agents/performance/creative-strategist"
mkdir -p "memory/agents/cro/cro-specialist"
mkdir -p "memory/agents/cro/ui-ux-designer"
mkdir -p "memory/agents/cro/developer"
mkdir -p "memory/agents/support/marketing-ops"
mkdir -p "memory/agents/support/growth-analyst"
```

- [ ] **Step 2: Add .gitkeep to each folder so git tracks them**

```bash
touch memory/agents/manager/ai-orchestrator/.gitkeep
touch memory/agents/performance/performance-lead/.gitkeep
touch memory/agents/performance/campaign-manager/.gitkeep
touch memory/agents/performance/creative-strategist/.gitkeep
touch memory/agents/cro/cro-specialist/.gitkeep
touch memory/agents/cro/ui-ux-designer/.gitkeep
touch memory/agents/cro/developer/.gitkeep
touch memory/agents/support/marketing-ops/.gitkeep
touch memory/agents/support/growth-analyst/.gitkeep
```

- [ ] **Step 3: Verify all 9 folders exist**

Run: `find memory/agents -name .gitkeep`

Expected output: 9 lines, one per folder.

- [ ] **Step 4: Commit**

```bash
git add memory/agents/
git commit -m "chore(memory): add per-agent private memory folders"
```

---

## Task 2 — Update ai-orchestrator.md

**Files:**
- Modify: `.claude/agents/ai-orchestrator.md`

- [ ] **Step 1: Insert Scope section after the frontmatter header**

Open `.claude/agents/ai-orchestrator.md`. After the line `# AI Orchestrator — Manager · All Departments`, insert:

```markdown
## Scope
**Owns:** Daily 8-step intelligence loop (08:00 Riyadh), routing every request to the right department, gating all write actions on the human ✅ in #approvals, assembling and posting the nightly digest, managing all cross-department handoffs.
**Does NOT own:** Campaign analysis or BQ queries (growth-analyst), campaign builds or naming (campaign-manager), creative direction (creative-strategist), landing-page tests (cro-specialist), tracking/pixels/secrets (marketing-ops).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Route a request | Identify the right department + agent, send HANDOFF packet | Auto |
| Post #approvals digest | Assemble and post the nightly single-message digest to Slack | Auto |
| Gate a write action | Hold every scale/pause/create/launch until ✅ is received | Auto (blocking) |
| Manage cross-dept handoff | Sequence two departments that both need to contribute | Auto |
| Escalate to human | Surface a decision above the team's altitude | Auto |

## Memory
- **Reads:** `memory/CRITICAL_KPI_RULES.md`, `memory/09_open_tasks.md`, `memory/00_index.md`
- **Writes:** `memory/agents/manager/ai-orchestrator/`

## Receives tasks from
- Human — direct session request or question
- Any agent escalating above their altitude

## Hands to (directly — no orchestrator needed)
- `growth-analyst` — when data observation or period comparison is needed
- `performance-lead` — when a paid-media flag needs triage
- `cro-specialist` — when an LP test needs to start or a result needs to be called
- `marketing-ops` — when tracking, pixels, or connector health needs checking

## Reports to
Human — final gate. All write actions queued in ONE #approvals digest before execution.

```

- [ ] **Step 2: Verify file has all 7 fields**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/ai-orchestrator.md`

Expected: 7 lines, one per section heading.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/ai-orchestrator.md
git commit -m "feat(agents): add 4-field standard to ai-orchestrator"
```

---

## Task 3 — Update performance-lead.md

**Files:**
- Modify: `.claude/agents/performance-lead.md`

- [ ] **Step 1: Insert 4 new sections after the heading line `# Performance Lead — Department Lead (Performance)`**

```markdown
## Scope
**Owns:** KPI thresholds in `config.py` (CPQL/CPL zones), channel mix and budget allocation, 14-day minimum decision window, ✅/❌ sign-off for all Performance department writes.
**Does NOT own:** Campaign builds or naming spec (campaign-manager), copy or creative direction (creative-strategist), BQ data queries or analysis (growth-analyst), tracking or pixel health (marketing-ops).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Triage a performance flag | Classify as scale/pause/optimize and route to the right direct | Auto |
| Update KPI thresholds in config.py | Change CPQL/CPL zone values | Lead-gated |
| Set channel budget allocation | Adjust spend split across channels | Human-gated |
| Gate a department write | Sign off on a build/pause spec before it goes to orchestrator | Lead-gated |

## Memory
- **Reads:** `memory/CRITICAL_KPI_RULES.md`, `config.py` (live — never from memory)
- **Writes:** `memory/agents/performance/performance-lead/`

## Receives tasks from
- `ai-orchestrator` — flag triage, daily loop routing
- `growth-analyst` — performance data and period comparisons ready for a decision

## Hands to (directly — no orchestrator needed)
- `campaign-manager` — when a build/pause spec is needed
- `creative-strategist` — when copy or A/B direction is needed
- `ai-orchestrator` — gated action specs ready for the #approvals digest

## Reports to
`ai-orchestrator` — triage decisions + gated action drafts for the digest.

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/performance-lead.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/performance-lead.md
git commit -m "feat(agents): add 4-field standard to performance-lead"
```

---

## Task 4 — Update campaign-manager.md

**Files:**
- Modify: `.claude/agents/campaign-manager.md`

- [ ] **Step 1: Insert 4 new sections after `# Campaign Manager — Performance`**

```markdown
## Scope
**Owns:** Campaign builds (naming spec, pixels, audiences, keyword policy enforcement).
**Does NOT own:** Copy or creative direction (creative-strategist), KPI thresholds or budget decisions (performance-lead), UTM structure policy or pixel health checks (marketing-ops), BQ data analysis (growth-analyst).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Name a campaign | Apply 12-field spec via `naming.py::prefixed()` | Auto |
| Audit keyword buckets | Check ALWAYS_NEGATIVE / BRAND_ONLY / COMPETITOR violations | Auto |
| Add negative keywords | Direct-execute via Google Ads API | Auto |
| Propose a full campaign build | Draft spec: channel, naming, pixels, audiences, budget | Human-gated |
| Pause a campaign or ad | Draft pause action with reason + 14-day data window | Human-gated |
| Configure Meta pixels on a placement | Wire CRM + Web pixel | Lead-gated |

## Memory
- **Reads:** `memory/CRITICAL_KPI_RULES.md`, `memory/01_architecture.md`, `memory/08_pitfalls.md`
- **Writes:** `memory/agents/performance/campaign-manager/`

## Receives tasks from
- `ai-orchestrator` — daily loop build/pause assignments
- `performance-lead` — specific campaign flag triage
- `creative-strategist` — when a creative variant needs a matching campaign build

## Hands to (directly — no orchestrator needed)
- `creative-strategist` — when a build needs copy or creative direction
- `marketing-ops` — when a new placement needs UTM or pixel verification

## Reports to
`ai-orchestrator` — build spec or audit result + any Human-gated actions queued for #approvals.

```

- [ ] **Step 2: Verify 7 fields + existing Lane section still present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence|Lane)" .claude/agents/campaign-manager.md`

Expected: 8 lines (Lane is preserved from original).

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/campaign-manager.md
git commit -m "feat(agents): add 4-field standard to campaign-manager"
```

---

## Task 5 — Update creative-strategist.md

**Files:**
- Modify: `.claude/agents/creative-strategist.md`

- [ ] **Step 1: Insert 4 new sections after `# Creative Strategist — Performance`**

```markdown
## Scope
**Owns:** OCEAN persona mapping, A/B creative variant scoping, copy direction, design briefs + AI image prompts, LP asset alignment with cro-specialist before any test goes live.
**Does NOT own:** Campaign builds or naming (campaign-manager), LP implementation (developer), KPI threshold decisions (performance-lead), pixel or tracking setup (marketing-ops).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| OCEAN persona map | Map an audience segment to personality profile for copy direction | Auto |
| A/B variant brief | Scope distinct creative angles per segment per channel | Auto |
| Design brief + 8-block image prompt | Write the full creative brief for production | Auto |
| LP asset alignment | Coordinate with cro-specialist to align creative to LP hypothesis | Auto |
| Write ad copy | MSA Arabic or English copy aligned to persona | Auto |

## Memory
- **Reads:** `docs/PLAYBOOK.md`, `memory/CRITICAL_KPI_RULES.md`, `docs/creative/reference/design-learnings.json`
- **Writes:** `memory/agents/performance/creative-strategist/`

## Receives tasks from
- `performance-lead` — creative brief or A/B scoping request
- `campaign-manager` — when a build needs copy direction
- `cro-specialist` — pre-launch LP asset alignment request

## Hands to (directly — no orchestrator needed)
- `campaign-manager` — when creative direction is ready and a build spec is needed
- `cro-specialist` — LP asset alignment confirmed before test goes live

## Reports to
`performance-lead` — creative brief + variant plan.
`ai-orchestrator` — cross-department outcomes (e.g. LP alignment complete).

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/creative-strategist.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/creative-strategist.md
git commit -m "feat(agents): add 4-field standard to creative-strategist"
```

---

## Task 6 — Update cro-specialist.md

**Files:**
- Modify: `.claude/agents/cro-specialist.md`

- [ ] **Step 1: Insert 4 new sections after `# CRO Specialist — CRO / Landing Page (chain lead)`**

```markdown
## Scope
**Owns:** 8-section LP brief, test hypothesis, success criteria (14-day CPQL + destination_url), ZATCA badge enforcement on every LP, test-result decisions, coordinating ui-ux-designer and developer.
**Does NOT own:** LP design execution (ui-ux-designer), LP build or pixel wiring (developer), campaign-level creative direction (creative-strategist), BQ data queries (growth-analyst).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Write LP brief | 8-section brief + hypothesis from the template | Auto |
| Set success criteria | Define win condition from 14-day CPQL + destination_url data | Auto |
| Call a test result | Decide which variant ships based on observed CPQL data | Lead-gated |
| Start the CRO chain | Hand brief to ui-ux-designer and open the sequential handoff | Auto |

## Memory
- **Reads:** `memory/CRITICAL_KPI_RULES.md`, `docs/landing-pages/_templates/lp-brief-template.md`
- **Writes:** `memory/agents/cro/cro-specialist/`

## Receives tasks from
- `ai-orchestrator` — new LP test request or test-result decision request
- `creative-strategist` — pre-launch LP asset alignment

## Hands to (directly — no orchestrator needed)
- `ui-ux-designer` — LP brief (starts the sequential chain)
- `creative-strategist` — when LP assets need alignment before launch

## Reports to
`ai-orchestrator` — test brief (chain started) or test-result decision.

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/cro-specialist.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/cro-specialist.md
git commit -m "feat(agents): add 4-field standard to cro-specialist"
```

---

## Task 7 — Update ui-ux-designer.md

**Files:**
- Modify: `.claude/agents/ui-ux-designer.md`

- [ ] **Step 1: Insert 4 new sections after `# UI/UX Designer — CRO / Landing Page`**

```markdown
## Scope
**Owns:** LP variant design aligned to OCEAN personas, ZATCA badge above fold (mandatory on every design), annotated design with interaction notes for the developer.
**Does NOT own:** LP brief or hypothesis (cro-specialist), LP build or pixel wiring (developer), any campaign-level creative outside the LP context (creative-strategist).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Design LP variant | Full annotated design from brief, OCEAN-aligned | Auto |
| ZATCA badge placement | Confirm badge above fold in every design | Auto |
| Annotate interaction notes | Add developer-ready hover, scroll, and form interaction notes | Auto |

## Memory
- **Reads:** `docs/PLAYBOOK.md`, `docs/landing-pages/reference/lp-design-system.md`, brief from `docs/landing-pages/briefs/`
- **Writes:** `memory/agents/cro/ui-ux-designer/`

## Receives tasks from
- `cro-specialist` — LP brief (sequential chain, step 2 of 3)

## Hands to (directly — no orchestrator needed)
- `developer` — annotated design (sequential chain, step 3 of 3)

## Reports to
`cro-specialist` — annotated design complete (end of step 2).

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/ui-ux-designer.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/ui-ux-designer.md
git commit -m "feat(agents): add 4-field standard to ui-ux-designer"
```

---

## Task 8 — Update developer.md

**Files:**
- Modify: `.claude/agents/developer.md`

- [ ] **Step 1: Insert 4 new sections after `# Developer — CRO / Landing Page`**

```markdown
## Scope
**Owns:** LP variant build from annotated design, UTM passthrough on every form field, both Meta pixel fires (CRM `1782671302631317` + Web `3036579196577051`), production deploy, pixel verification in Events Manager before sign-off.
**Does NOT own:** LP design (ui-ux-designer), LP brief or test hypothesis (cro-specialist), GTM container changes (marketing-ops), campaign-level creative (creative-strategist).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Build LP variant | Implement design from `docs/landing-pages/designs/` | Auto |
| Wire UTM passthrough | Add UTM hidden fields to every form on the LP | Auto |
| Fire both Meta pixels | Implement CRM + Web pixel events on form submit | Auto |
| Deploy to production | Push LP live to `lp.qoyod.com` | Lead-gated |
| Verify pixels in Events Manager | Confirm both pixels fire before sign-off (blocking — never skip) | Auto (blocking) |

## Memory
- **Reads:** `memory/CRITICAL_KPI_RULES.md`, `docs/landing-pages/designs/` (current design)
- **Writes:** `memory/agents/cro/developer/`

## Receives tasks from
- `ui-ux-designer` — annotated design (sequential chain, step 3 of 3)

## Hands to (directly — no orchestrator needed)
- `cro-specialist` — verified deploy result (completes the chain)
- `marketing-ops` — if a pixel fires incorrectly and GTM investigation is needed

## Reports to
`cro-specialist` — deployed, pixel-verified LP.
`ai-orchestrator` — LP deployed (for the activity log).

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/developer.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/developer.md
git commit -m "feat(agents): add 4-field standard to developer"
```

---

## Task 9 — Update marketing-ops.md

**Files:**
- Modify: `.claude/agents/marketing-ops.md`

- [ ] **Step 1: Insert 4 new sections after `# Marketing Project Coordinator — Support (OPS)`**

```markdown
## Scope
**Owns:** UTM structure policy, Meta pixel health (both pixels), HubSpot `lead_utm_campaign` field mapping, Railway env vars + credential rotation, GTM containers (web `GTM-TFH26VC2` + server `GTM-PK6924TJ`), connector failure diagnosis and fix, conversion recording health, activity dashboard health.
**Does NOT own:** Campaign builds (campaign-manager), BQ data analysis (growth-analyst), LP design or build (ui-ux-designer / developer), creative direction (creative-strategist).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Audit connector health | Check `connector_health_log` + Railway logs | Auto |
| Fix a broken connector | Rotate credential / backfill / restart service | Auto (after diagnosis) |
| Rotate a Railway credential | Update env var in Railway (PowerShell on Windows) | Lead-gated |
| GTM container audit | Full tag review of both containers via GTM API v2 | Auto |
| Check Meta pixel health | Verify both pixels firing in Events Manager | Auto |
| Verify UTM field mapping | Confirm `lead_utm_campaign` mapping is correct in HubSpot | Auto |

## Memory
- **Reads:** `memory/02_credentials.md`, `memory/07_attribution.md`
- **Writes:** `memory/agents/support/marketing-ops/`

## Receives tasks from
- `ai-orchestrator` — connector failure escalation, tracking audit request
- `campaign-manager` — new placement needs pixel verification
- `developer` — pixel fires incorrectly, needs GTM investigation

## Hands to (directly — no orchestrator needed)
- `growth-analyst` — after connector fix: hand the Asana task for 7-day BQ ↔ HubSpot reconciliation

## Reports to
`ai-orchestrator` — health status, fixed connectors, credential rotations, GTM audit results.

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/marketing-ops.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/marketing-ops.md
git commit -m "feat(agents): add 4-field standard to marketing-ops"
```

---

## Task 10 — Update growth-analyst.md

**Files:**
- Modify: `.claude/agents/growth-analyst.md`

- [ ] **Step 1: Insert 4 new sections after `# Growth Analyst — Support (DATA)`**

```markdown
## Scope
**Owns:** The 8-step intelligence loop on live BQ, period comparisons, CRO A/B result analysis, monthly forecasts, `memory/` ownership (writes `08_pitfalls.md` and `14_learning_patterns.md`).
**Does NOT own:** Campaign builds (campaign-manager), creative briefs (creative-strategist), LP work (cro chain), pixel or UTM health (marketing-ops), KPI threshold decisions (performance-lead).

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| Pull live BQ data | Query `campaigns_daily`, `hubspot_leads_module_daily`, etc. | Auto |
| Period comparison | Run `analysers/period_compare.py` with explicit YYYY-MM-DD dates | Auto |
| Root-cause analysis | Investigate a flag: mix, audience, launch wave, LP routing, keywords | Auto |
| Monthly forecast | Run `analysers/forecaster.py` for spend/leads/CPQL/ROAS projection | Auto |
| Write to shared memory | Update `08_pitfalls.md`, `14_learning_patterns.md` | Auto |
| CRO A/B result analysis | Analyse variant CPQL from BQ for `cro-specialist` decision | Auto |
| Connector fix review | BQ ↔ HubSpot 7-day reconciliation after `marketing-ops` fixes a connector | Auto |

## Memory
- **Reads:** `memory/CRITICAL_KPI_RULES.md`, `memory/07_attribution.md`, `memory/14_learning_patterns.md`, `memory/01_architecture.md`
- **Writes (shared):** `memory/08_pitfalls.md`, `memory/14_learning_patterns.md`, `memory/16_activity_dashboard.md`
- **Writes (private):** `memory/agents/support/growth-analyst/`

## Receives tasks from
- `ai-orchestrator` — daily 8-step loop trigger, ad-hoc analysis requests
- `marketing-ops` — Asana task handoff after a connector fix (data integrity review)

## Hands to (directly — no orchestrator needed)
- `performance-lead` — analysis complete, flags identified, ready for triage
- `cro-specialist` — A/B test result analysis complete

## Reports to
`ai-orchestrator` — analysis + forecast + memory writes for what the team learned.

```

- [ ] **Step 2: Verify 7 fields present**

Run: `grep -E "^## (Scope|Skills|Memory|Receives|Hands to|Reports to|Boot sequence)" .claude/agents/growth-analyst.md`

Expected: 7 lines.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/growth-analyst.md
git commit -m "feat(agents): add 4-field standard to growth-analyst"
```

---

## Task 11 — Final verification + push

- [ ] **Step 1: Verify all 9 files have all 7 fields**

```bash
for f in .claude/agents/ai-orchestrator.md .claude/agents/performance-lead.md \
          .claude/agents/campaign-manager.md .claude/agents/creative-strategist.md \
          .claude/agents/cro-specialist.md .claude/agents/ui-ux-designer.md \
          .claude/agents/developer.md .claude/agents/marketing-ops.md \
          .claude/agents/growth-analyst.md; do
  echo "=== $f ===" 
  grep -c "^## \(Scope\|Skills\|Memory\|Receives\|Hands to\|Reports to\|Boot sequence\)" "$f"
done
```

Expected: each file prints 7 (or 8 if Lane section was preserved in campaign-manager).

- [ ] **Step 2: Verify boundary check — no "Owns" claim in one file appears in another file's "Does NOT own" unless intentional**

Read each "Scope" section manually. Confirm:
- `campaign-manager` Does NOT own: creative direction ✓ matches `creative-strategist` Owns
- `creative-strategist` Does NOT own: campaign builds ✓ matches `campaign-manager` Owns
- `growth-analyst` Does NOT own: UTM/pixel health ✓ matches `marketing-ops` Owns
- `marketing-ops` Does NOT own: BQ data analysis ✓ matches `growth-analyst` Owns
- `developer` Does NOT own: LP design ✓ matches `ui-ux-designer` Owns

- [ ] **Step 3: Verify all 9 memory folders exist**

Run: `find memory/agents -type d | sort`

Expected: 12 directories (root + 4 dept folders + 9 agent folders).

- [ ] **Step 4: Push to origin/main**

```bash
git push origin main
```

Expected: Railway auto-deploys. No production changes — these are `.md` files only.

- [ ] **Step 5: Update open tasks**

In `memory/09_open_tasks.md`, mark Phase 1 agent file cleanup as done:
```
- [x] **Phase 1 — Agent file cleanup** ← mark complete, add date 2026-06-11
```
