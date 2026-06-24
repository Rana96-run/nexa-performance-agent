---
name: morning-analysis-flow
description: |
  Workflow Skill — End-to-end morning analysis flow for the Qoyod Performance Agent.
  Load when running the daily nightly cycle, the morning digest, or any "run the
  full analysis" request. This skill defines the exact sequence of steps, tools,
  and checks that constitute a complete daily analysis run.
  Trigger: operational_scheduler.py daily cycle / manual "run daily analysis"
---

# Morning Analysis Flow

## Trigger
- **Scheduled**: `main.py daily` operational scheduler — 08:00 Riyadh (05:00 UTC)
- **Manual**: User requests "run the analysis" / "what happened yesterday?"
- **Auto-resume**: Loop wakeup detects no analysis ran in last 26h

---

## Flow: 8 Stages in Order

### Stage 1 — DATA REFRESH (prerequisite gate)
```
1a. Verify GitHub Actions collectors.yml ran successfully (pulls yesterday's data from all platforms)
1b. Run connector_tracker.py         (5-check health for all 9 connectors)
1c. GATE: If any connector is ❌ BROKEN → fix before proceeding to analysis
           If connector is ⚠️ WARNING  → proceed but note in output
           If all ✅ HEALTHY          → proceed
```
**Never** run analysis on stale data. The gate is non-negotiable.

### Stage 2 — OBSERVE (pull live numbers)
```
2a. Query paid_channel_daily for last 7 days — spend, leads, CPQL by channel
2b. Query hubspot_leads_module_daily for same window — qualified, disqualified
2c. Query hubspot_deals_daily for revenue attribution
2d. Note: ALL from live BQ — never from recollection or yesterday's summary
```

### Stage 3 — COMPARE (period-over-period)
```
3a. Use analysers/period_compare.py — never hand-roll this
3b. Compare last 7d vs prior 7d for each channel
3c. Compute delta for: spend, leads, CPQL, ROAS, qual rate
3d. Flag any metric that moved > 20% in either direction
```

### Stage 4 — INVESTIGATE (root cause)
```
For each flagged metric:
4a. Check campaign mix change (new campaigns launched? paused?)
4b. Check creative performance (CTR change → fatigue?)
4c. Check audience signals (frequency spike? reach plateau?)
4d. Check LP routing (LP changed? UTM broken?)
4e. Check launch wave (new campaign < 5 days old inflating CPQL?)
4f. Check attribution gap (no-UTM row growing?)
```

### Stage 5 — DECIDE (recommendations)
```
5a. Classify each campaign: SCALE / HOLD / WATCH / PAUSE CANDIDATE
5b. For PAUSE CANDIDATE: compute alternatives-considered (budget cut %)
5c. For SCALE: confirm CPQL < $60 AND ROAS > threshold (both required)
5d. Write Asana tasks for each action: full campaign/adset/ad spec
5e. NEVER auto-execute scale or pause — only create the Asana task
```

### Stage 6 — POST TO SLACK (approval gate)
```
6a. Compose #nexa-daily message (CEO Layer format)
6b. Pre-send review: naming convention ✓, dashboard URL ✓, date range explicit ✓
6c. Follow-up message: recommendations + Asana task links + #approvals reference
6d. Post to #approvals digest: one ✅ executes all scale+pause items
6e. Keyword candidates → Asana only, NEVER to Slack
```

### Stage 7 — HANDOFF (multi-agent data export)
```
7a. Write daily_ops_brief to agent_handoff_log (target: ops_management)
    Payload: CPQL by channel, active tasks, connector health, approvals pending
7b. If week = Sunday: write growth_signals (target: growth_marketing)
    Payload: 7d period comparison, scale candidates, ROAS trend, forecast
7c. TTL: 26 hours (next cycle overwrites)
```

### Stage 8 — LOG & LEARN
```
8a. Log full run to agent_activity_log (role=daily_digest, action=morning_analysis)
8b. If any new pattern found (e.g., launch-wave CPQL spike, seasonal drop):
    → Append to memory/14_learning_patterns.md
8c. Update memory/09_open_tasks.md if any task completed or opened
8d. Commit memory changes if substantial
```

---

## Output Checklist (before posting)

- [ ] Connector health: all checked, any ❌ BROKEN fixed or noted
- [ ] Date range: explicit YYYY-MM-DD to YYYY-MM-DD in every mention
- [ ] Period comparison: 7d vs 7d prior computed for all channels
- [ ] Root cause: stated for every flagged metric (not just "CPQL rose")
- [ ] Recommendations: FULL spec in Asana, not "scale this ad"
- [ ] Slack format: dashboard URL + peak numbers + channel breakdown
- [ ] Approval gate: scale/pause items in #approvals digest only
- [ ] Handoff: agent_handoff_log written for Ops and Growth agents
- [ ] Learning: new patterns recorded if found

---

## Rules & Guardrails

- **Never** post to Slack before Stage 1 gate passes (stale data = bad decisions)
- **Never** skip Stage 3 (period compare) — a single-period read misleads
- **Never** auto-execute from Stage 5 — everything goes to approval
- **Never** include keywords in Slack output
- **Always** complete all 8 stages even if no flags fire (clean run is also logged)
- **Always** write Stage 7 handoff — the other agents depend on it
