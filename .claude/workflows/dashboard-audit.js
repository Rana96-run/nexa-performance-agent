export const meta = {
  name: 'dashboard-audit',
  description: 'Capture dashboard violations, fix them, report results — 3-agent pipeline',
  phases: [
    { title: 'Capture', detail: 'Growth Analyst reads violations queue and assesses root causes' },
    { title: 'Fix',     detail: 'Developer + Growth Analyst apply targeted fixes in parallel' },
    { title: 'Report',  detail: 'Project Coordinator marks violations resolved, writes audit log' },
  ],
}

// ── Shared constants ──────────────────────────────────────────────────────────
const BASE  = 'D:/Nexa Performance Agent'
const QUEUE = `${BASE}/memory/dashboard_violations.jsonl`

// ── Schemas ───────────────────────────────────────────────────────────────────
const CAPTURE_SCHEMA = {
  type: 'object',
  required: ['violations', 'open_count', 'by_agent', 'assessment'],
  properties: {
    violations: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'type', 'severity', 'agent', 'description', 'file', 'fix_hint'],
        properties: {
          id:          { type: 'string' },
          type:        { type: 'string' },
          severity:    { type: 'string' },
          agent:       { type: 'string' },
          description: { type: 'string' },
          file:        { type: 'string' },
          fix_hint:    { type: 'string' },
        },
      },
    },
    open_count: { type: 'number' },
    by_agent:   { type: 'object' },
    assessment: { type: 'string' },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  required: ['fixed_ids', 'skipped_ids', 'summary'],
  properties: {
    fixed_ids:  { type: 'array', items: { type: 'string' } },
    skipped_ids: { type: 'array', items: { type: 'string' } },
    summary:    { type: 'string' },
  },
}

const REPORT_SCHEMA = {
  type: 'object',
  required: ['fixed_count', 'still_open_count', 'summary'],
  properties: {
    fixed_count:      { type: 'number' },
    still_open_count: { type: 'number' },
    summary:          { type: 'string' },
    log_entry:        { type: 'string' },
  },
}

// ── PHASE 1: CAPTURE  (Growth Analyst) ───────────────────────────────────────
// Growth Analyst owns memory/ and BQ activity data.
// They read the violations queue and classify exactly what needs fixing.
phase('Capture')

const capture = await agent(`
You are the Growth Analyst for Nexa Ops. Your job right now is to read the
dashboard violations queue and produce a structured assessment.

READ this file: ${QUEUE}

Rules:
- If the file does not exist or is empty, return open_count=0, violations=[],
  by_agent={}, assessment="Queue is clean — no open violations."
- If it exists, parse every JSONL line. Keep only lines where status="open".
- Populate the violations array with all open items.
- Set by_agent to a dict of { agent_name: count_of_open_violations }.
- In assessment (2–3 sentences), explain what the open violations mean for
  the dashboard's data accuracy and visual correctness. Be specific about
  which agent cards are affected and why.

Return the structured result.
`, { schema: CAPTURE_SCHEMA, phase: 'Capture', agentType: 'growth-analyst', label: 'analyst:capture' })

if (!capture) {
  log('Capture phase failed — aborting audit.')
  return { error: 'Capture agent returned null.' }
}

log(`Capture: ${capture.open_count} open violation(s) — ${capture.assessment}`)

if (capture.open_count === 0) {
  // Still run report to confirm clean state in the audit log
  log('Queue is clean. Running report phase to confirm.')
}

// ── PHASE 2: FIX  (Developer + Growth Analyst in parallel) ───────────────────
// Each agent fixes the violations assigned to their role.
// They run at the same time — Developer on CSS/HTML, Analyst on data defs.
phase('Fix')

const violations     = capture.violations || []
const dev_items      = violations.filter(v => v.agent === 'developer')
const analyst_items  = violations.filter(v => v.agent === 'growth-analyst')

const [dev_result, analyst_result] = await parallel([

  // ── Developer: CSS / HTML structural fixes ──────────────────────────────
  () => agent(`
You are the Developer in the CRO/LP chain. You have been dispatched to fix
dashboard code violations captured by the Growth Analyst.

VIOLATIONS ASSIGNED TO YOU:
${JSON.stringify(dev_items, null, 2)}

For each violation in the list above:
1. Read the file listed in the "file" field.
2. Understand the problem in "description".
3. Apply exactly the fix described in "fix_hint" — surgical changes only.
4. Do not touch code outside the scope of the violation.

After all fixes:
- fixed_ids: list the violation IDs you successfully fixed.
- skipped_ids: list any you could not fix, with a one-line reason each.
- summary: one paragraph describing what you changed and why.

${dev_items.length === 0 ? 'No violations assigned to you. Return fixed_ids=[], skipped_ids=[], summary="No developer violations in this run."' : ''}
`, { schema: FIX_SCHEMA, phase: 'Fix', agentType: 'developer', label: 'developer:fix' }),

  // ── Growth Analyst: data attribution fixes in app.py ───────────────────
  () => agent(`
You are the Growth Analyst. You have been dispatched to fix data attribution
violations in the dashboard configuration.

VIOLATIONS ASSIGNED TO YOU:
${JSON.stringify(analyst_items, null, 2)}

For each violation in the list above:
1. Read the file listed in "file" (typically reports/app.py).
2. Find _TEAM_DEFS. Locate the duplicate role string named in "description".
3. Remove it from all but the one agent that rightfully owns it.
   Ownership rules (apply in order):
     spike_detector  → growth-analyst   (detects BQ anomalies)
     bq_refresh      → growth-analyst   (owns BQ layer)
     llm_cadence     → growth-analyst   (runs the 8-step loop)
     daily_digest    → project-coordinator    (posts the Slack digest)
     cro_analysis    → cro-specialist   (LP brief + hypothesis)
     lp_deploy       → developer        (ships to production)
     lp_design       → ui-ux-designer   (LP design)
     performance_audit → performance-lead
     keyword_management → campaign-manager
     health_monitor  → project-coordinator
     slack_approval  → project-coordinator
     ops_scheduler   → ai-orchestrator
4. After editing, verify no role string appears in more than one roles set.

After all fixes:
- fixed_ids: list the violation IDs you fixed.
- skipped_ids: list any you could not fix, with a one-line reason.
- summary: one paragraph describing what you changed.

${analyst_items.length === 0 ? 'No violations assigned to you. Return fixed_ids=[], skipped_ids=[], summary="No analyst violations in this run."' : ''}
`, { schema: FIX_SCHEMA, phase: 'Fix', agentType: 'growth-analyst', label: 'analyst:fix' }),

])

const all_fixed   = [...(dev_result?.fixed_ids || []),   ...(analyst_result?.fixed_ids || [])]
const all_skipped = [...(dev_result?.skipped_ids || []), ...(analyst_result?.skipped_ids || [])]
log(`Fix: ${all_fixed.length} fixed, ${all_skipped.length} skipped`)

// ── PHASE 3: REPORT  (Project Coordinator) ─────────────────────────────────────────
// Project Coordinator marks resolved violations in the queue, writes the audit log
// entry, and confirms the system is clean. They own "ops hygiene" — closing
// the loop is exactly their charter.
phase('Report')

const today = new Date().toISOString().slice(0, 10)

const report = await agent(`
You are Project Coordinator for Nexa Ops. You own the plumbing — closing this
audit loop is your responsibility.

AUDIT RESULTS:
  Open violations found:       ${capture.open_count}
  Fixed by Developer:          ${JSON.stringify(dev_result?.fixed_ids || [])}
  Developer summary:           ${dev_result?.summary || 'n/a'}
  Fixed by Growth Analyst:     ${JSON.stringify(analyst_result?.fixed_ids || [])}
  Analyst summary:             ${analyst_result?.summary || 'n/a'}
  Skipped (still open):        ${JSON.stringify(all_skipped)}

DO THE FOLLOWING (all four steps):

STEP 1 — Update the violations queue.
  Read ${QUEUE}.
  For every JSONL line, if the line's "id" is in this fixed list:
    ${JSON.stringify(all_fixed)}
  update that line's "status" from "open" to "fixed" and add "fixed_ts":"${today}".
  Rewrite the entire file with the updated lines (Read → modify in memory → Write back).
  If the file does not exist, skip this step.

STEP 2 — Append to the audit log.
  Append ONE line to ${BASE}/memory/14_activity_dashboard.md (create file if missing):
  "${today}: dashboard-audit — fixed ${all_fixed.length} violation(s) (${all_fixed.join(', ') || 'none'}), skipped ${all_skipped.length} (${all_skipped.join(', ') || 'none'})"

STEP 3 — Return the report object.
  fixed_count:      number of violations you marked as fixed
  still_open_count: number still with status="open" after your update
  summary:          2 sentences — what was fixed + what (if anything) remains open
  log_entry:        the exact string you appended to 14_activity_dashboard.md
`, { schema: REPORT_SCHEMA, phase: 'Report', agentType: 'project-coordinator', label: 'mktg-ops:report' })

log(`Report: fixed=${report?.fixed_count} still-open=${report?.still_open_count}`)
log(report?.summary || '')

return {
  open_found:   capture.open_count,
  fixed:        all_fixed,
  skipped:      all_skipped,
  still_open:   report?.still_open_count ?? all_skipped.length,
  summary:      report?.summary,
}
