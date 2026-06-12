# Nexa Performance Agent — Memory Analysis Report
**Generated:** 2026-06-12  
**Scope:** `memory/` folder (17 files) + git log (last 30 commits)  
**Goals:** Action items & open gaps, Evolution of thinking

---

## Pattern 1 — The Same Bug Class Keeps Recurring: SQL Join Fan-Out

This is the single most repeated failure class in the entire memory. The same category of bug — a platform ↔ HubSpot join that inflates metrics — has been discovered, fixed, and rediscovered multiple times across different surfaces.

**How it keeps appearing:**

- **2026-05-11** (`hubspot_leads_module_daily`): `key_fields` included `qoyod_source` in the upsert scope, causing old rows with different sources to survive alongside new ones → 5x lead inflation (60,156 rows vs correct 12,326). Fixed by changing `key_fields=["date"]`.
- **2026-05-18** (`campaign_health.py`): spend fanned out 4× when one adset matched multiple HubSpot rows in the ad/adset view. Fixed with pre-aggregate CTE.
- **2026-06-09** (`v_adset_performance` and `v_ad_performance`): leads 3.57× over-count from name-keyed FULL OUTER JOIN. Fixed by adding ID to GROUP BY and adding lead window guards.
- **2026-06-09 post-fix**: Per-channel recon revealed the fix only fixed 4/5 channels. The Snapchat over-count was *upstream* in `utm_paid_attribution_daily` — because `spend_campaign` grouped by raw `campaign_name` while joins used `LOWER(TRIM())`. Second fix required.

**The root pattern:** Any time a CTE or view GROUPs on a name column while the join uses a normalized key (LOWER/TRIM), the right side fans. This rule has been documented in `08_pitfalls.md` at least 3 separate times with slightly different framings.

**Gap:** There is no automated reconciliation gate that runs after *every* view change (not just on-demand). The per-channel ≤1.05 ratio check is known, but it's manual and only sometimes triggered.

---

## Pattern 2 — Verification Discipline Has Gotten Progressively Stricter (Evolution of Thinking)

The "done means verified, not attempted" rule in `CLAUDE.md` didn't always exist. The git history and memory show a clear tightening arc:

**Early sessions (May 3–10):** Work was declared done on observation ("backfill ran") without systematic cross-checking. The HubSpot deals collector declared ✅ based on row count alone — later found to be 1.84× duplicated (discovered when user pushed back and a direct API check was run).

**Mid-sessions (May 11–15):** After the deals duplication incident, a new rule was established: always reconcile BQ to HubSpot on a 7-day sample before declaring done. The 08:00 Riyadh timing issue (health checker flagging stale data before nightly run) also established the "≥3 day freshness threshold" rule — a calibration from a false alarm.

**Recent sessions (June 9–12):** The reconciliation standard hardened to *per-channel* (not org-wide total). The June 9 entry in `14_learning_patterns.md` explicitly notes: "A reconciliation on the org-wide TOTAL is worthless — a large clean channel (Google Ads) masks 2× over-counts on smaller channels." This is a direct evolution from the May standard.

**The trajectory:** Each bug discovered at a higher level of granularity pushed the verification bar higher. The current standard (per-channel, ≤1.05 ratio, fresh BQ not cached memory) is significantly more rigorous than the original.

**Gap:** The "done means verified" principle is defined for the *agent*, but there's no equivalent forcing function for the *Cowork sandbox*. `14_learning_patterns.md` (2026-06-12) documents that the Cowork sandbox cannot run Python analysers or call Google/Slack APIs — but the 3 new Cowork automation skills (monthly-creative-report, daily-slack-audit, monthly-performance-deck) created on 2026-06-12 haven't been tested to confirm they don't hit the same sandbox limitations.

---

## Pattern 3 — Three Open Infrastructure Gaps That Block the Cowork Migration (Action Items)

The P0 Cowork migration spec (approved 2026-06-11) has 5 phases. Phases 1 and 2 are done. Three concrete blockers remain:

**Phase 3 — Cowork connectors (not started, owner: project-coordinator)**  
BigQuery, Slack, Asana, Meta, Google Ads, and HubSpot all need to be wired in the Cowork platform UI. Estimated 30–60 min manual setup. Nothing else in Phase 4 or 5 can start until this is done. There is no ticket, no due date, and no owner assignment beyond the role label.

**Phase 4 — Daily loop parallel run (blocked by Phase 3)**  
The 14-day parallel run of `/daily-loop` on Cowork vs Railway `main.py daily` cannot start until connectors are wired. The retirement of the Railway LLM layer depends on this passing for 14 consecutive days. This is the critical path item.

**Phase 5 — n8n collector replacement (optional, independent)**  
Replace Railway Python collectors one-by-one with n8n workflows. Listed as optional but it's the only path to removing Railway dependency entirely. No work has started. No n8n instance is referenced anywhere in the codebase.

**One urgent human fix:**  
Deal `505631711439` has a phone number (+966 50 440 6958) in the Amount field, inflating pipeline value to $257.7B. HubSpot is read-only for the agent — a human (Nouran Emad's manager or admin) must correct the amount. This has been open since 2026-06-08 and is still in the `🔴` bucket in `09_open_tasks.md`.

---

## Pattern 4 — The Agent Has Systematically Accumulated Rules to Guard Its Own Past Mistakes

`CRITICAL_KPI_RULES.md` and `08_pitfalls.md` together form a self-correcting knowledge base, but they reveal a pattern: almost every rule was written *after* a violation was caught, usually by Rana or Amar pushing back.

**Examples of violation → rule pairs:**

| Violation caught | Rule written |
|---|---|
| Reported $1.48 CPL for Bing WebsiteTraffic (channel leads, not HubSpot leads) | Rule #1: NEVER use `campaigns_daily.leads` |
| Created TikTok campaign with wrong naming format | Rule #3: Query existing campaigns before creating |
| Auto-applied UTM suffix at campaign level when account-level already existed | Rule #4: Check account-level UTM before flagging missing |
| 5 anonymous scan workers with no seat ownership in codebase review | Rule #5: No anonymous agents |
| Declared "done" on deals work that was 1.84× duplicated | CLAUDE.md: "Done means verified, not attempted" |
| Reported "CPQL regression" on an ImpressionShare campaign (awareness, no CPQL target) | `08_pitfalls.md`: ImpressionShare_ campaigns never get CPQL |

**The meta-pattern:** Each violation is documented with the specific date and who caught it. This is good institutional memory. The gap is that the critical rules are spread across at least 3 files (`CRITICAL_KPI_RULES.md`, `08_pitfalls.md`, `CLAUDE.md`) and some rules appear in slightly different forms in multiple places.

**One specific open gap:** Rule #6 in `CRITICAL_KPI_RULES.md` (self-check before running a script) only scans for 3 SQL patterns. The `ImpressionShare_` campaign type check, the per-channel reconciliation requirement, and the `LOWER(TRIM())` GROUP BY rule are all documented elsewhere but not in the self-check gate.

---

## Pattern 5 — The System Is Mid-Migration From Railway-Centric to Cowork-Centric

The git log from the last 30 commits (all on 2026-06-11 and 2026-06-12) is almost entirely Cowork-related: agent file rewrites (7-field standard), 12 new Cowork skill files, dashboard redesigns, and Slack digest simplification. This is a deliberate architectural pivot.

**The current state is a hybrid:**  
- **Railway** runs all data collection, BQ writes, analysis, and the operational agent
- **Cowork** is being wired to run the *human-facing* layer: daily digests, approval flows, scheduled reports
- **The transition plan** has a 14-day parallel run to validate before retiring Railway's LLM layer

**Evolution visible in the dashboard redesign:**  
The activity dashboard went through at least 3 structural changes in the last 2 days: "Recently Created Tasks panel" was added (commit `d94c0d9`), then removed (commit `297e0dd`), then replaced with an "Agent Directory panel" (commit `696df02`). The 4-panel redesign landed on 2026-06-12 (`5e3e0f8`). This rapid iteration suggests the Cowork integration UX is still being figured out.

**Key tension not yet resolved:**  
`14_learning_patterns.md` (2026-06-12) documents that the Cowork sandbox cannot run BQ analysis. But the `monthly-performance-deck` and `monthly-creative-report` skills created on 2026-06-12 appear to pull BQ data. Either these skills call Railway's API (not documented) or they will hit the same sandbox limitation. This needs verification before the first of next month.

---

## Open Gaps Summary (Prioritized)

| # | Gap | Owner | Urgency |
|---|---|---|---|
| 1 | HubSpot deal `505631711439` — phone number in Amount field, inflating pipeline $257.7B | Human (admin/Nouran's manager) | 🔴 Immediate |
| 2 | Phase 3 Cowork connectors not wired — blocks Phase 4 daily loop parallel run | project-coordinator | 🔴 Critical path |
| 3 | New Cowork automation skills (monthly-creative-report, monthly-performance-deck) need BQ access verification before month-end | project-coordinator / developer | 🟡 Before July 1 |
| 4 | P3 nice-to-have items have no owner or due date: weekly email digest, A/B test tracker, SEMrush integration | — | 🟢 Low priority |
| 5 | `v_ad_performance` Snapchat reconciliation is ≤1.05 but the original diagnosis note (kept in `08_pitfalls.md`) is confusing — two contradictory entries for the same bug class | developer / growth-analyst | 🟡 Clarity |
| 6 | Hex dashboards still use legacy column names (`deals_won`, `revenue_won`, `roas`) instead of the renamed `new_biz_*` columns noted in `09_open_tasks.md` | developer | 🟡 Data integrity |
| 7 | LinkedIn token expires 2026-07-19 — proactive refresh reminder needed | project-coordinator | 🟡 Before July 19 |

---

*This report was generated from `memory/` folder (17 files) + git log (30 commits). Source files: `09_open_tasks.md`, `14_learning_patterns.md`, `08_pitfalls.md`, `CRITICAL_KPI_RULES.md`, `00_index.md`.*
