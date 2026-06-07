---
name: slack-reporter
description: |
  Skill Library — Slack reporting protocol.
  Defines the exact format for the daily Slack digest, weekly summary,
  and ad-hoc performance alerts. Load before any slack_post_message call
  to ensure the format, tone, and content pass the pre-send hook.
---

# Slack Reporter

## The Two Slack Channels

| Channel | Purpose | Cadence |
|---|---|---|
| `#nexa-reports` | Daily performance digest + weekly summary | Daily (nightly) + Monday |
| `#approvals` | Nightly action digest (scale/pause items) | Nightly (nightly sweep) |
| `#nexa-health` | Connector health alerts (BROKEN only) | On-demand / when RED |

**Never mix channels.** Performance numbers go to `#nexa-reports`. Actions go to
`#approvals`. Data errors go to `#nexa-health`.

---

## Daily Slack Digest Format

### Message 1 — Performance Summary (post to `#nexa-reports`)

```
*Daily Performance — {YYYY-MM-DD}* | {dashboard_short_url}

*7-Day Summary ({YYYY-MM-DD} to {YYYY-MM-DD}):*
Blended CPQL: *${blended_cpql}* {vs_prior_emoji} vs ${prior_cpql} prior 7d
Blended CPL:  *${blended_cpl}*
Total Spend:  *${total_spend}*
Total Leads:  *{total_leads}*
Total SQLs:   *{total_sqls}*

*Channel Breakdown:*
| Channel  | Spend  | Leads | CPQL   | vs Prior |
|----------|--------|-------|--------|----------|
| Meta     | ${X}   | {n}   | ${X}   | {±X%}   |
| Google   | ${X}   | {n}   | ${X}   | {±X%}   |
| Snapchat | ${X}   | {n}   | ${X}   | {±X%}   |
| LinkedIn | ${X}   | {n}   | ${X}   | {±X%}   |

*Top performer:* {channel} — CPQL ${X} ({improvement vs prior})
*Needs attention:* {channel} — CPQL ${X} ({reason in 1 sentence})

*Data status:* {GREEN ✅ / AMBER ⚠️ / RED ❌} ({connector_issue if not green})
```

### Message 2 — Actions & Recommendations (reply in thread)

```
*Actions (in #approvals):*
• {N} items queued for approval tonight — scale: {n}, pause: {n}
• See #approvals for full list and ✅/❌ reaction

*Asana tasks created:*
• {N} new tasks — {n} optimize, {n} review, {n} drilldown
• → {asana_project_url}

*Key observations:*
• {Observation 1 — specific, data-backed, 1 sentence}
• {Observation 2}
• {Observation 3 max}
```

---

## Weekly Summary Format (every Monday, `#nexa-reports`)

```
*Weekly Review — Week of {YYYY-MM-DD}* | {dashboard_short_url}

*Performance (last 7 days vs prior 7 days):*
| Metric | This Week | Prior Week | Delta |
|--------|-----------|------------|-------|
| Spend  | ${X}      | ${X}       | {±%}  |
| Leads  | {n}       | {n}        | {±%}  |
| SQLs   | {n}       | {n}        | {±%}  |
| CPQL   | ${X}      | ${X}       | {±%}  |
| CPL    | ${X}      | ${X}       | {±%}  |

*Month-to-date forecast:*
  Spend EOM:  ${forecast} (on pace: {YES/NO})
  Leads EOM:  {forecast} (target: {target})
  CPQL EOM:   ${forecast} (target: $80)

*Biggest win:* {1 sentence}
*Biggest risk:* {1 sentence}
*Action this week:* {1 sentence — what the team should do}

*Data reliability:* {connector health summary}
*Keyword auto-fix (Sunday):* {n} paused, {n} negated, {n} removed
```

---

## Ad-Hoc Alert Format

For time-sensitive issues (CPQL spike, connector failure, budget cap hit):

```
⚠️ *ALERT — {issue_type}* — {YYYY-MM-DD HH:MM} Riyadh

{1 sentence: what happened}
{1 sentence: which campaigns / channels affected}
{1 sentence: current CPQL vs threshold}

*Immediate action needed:* {YES/NO}
{If YES: exactly what and where}

*Asana task:* {url}
```

Post alerts to the relevant channel only:
- Performance issue → `#nexa-reports`
- Data gap → `#nexa-health`
- Action needed → `#approvals`

---

## Format Rules (enforced by pre-send hook)

1. **Dashboard URL** — always plain text in message 1 (not link text, not buried in thread)
2. **Date ranges** — always `YYYY-MM-DD to YYYY-MM-DD`, never "last 7 days" or "this week"
3. **No keywords in Slack** — keyword changes are Asana-only
4. **No abbreviations** — "IS" → "Impression Share", "QS" → "Quality Score"
5. **No platform conversion counts** — only HubSpot leads_total and leads_qualified
6. **Emojis are structural only** — ✅ ⚠️ ❌ 🔴 🟢 for status; no decorative emojis
7. **Two-message structure** — message 1 is numbers, message 2 (thread reply) is actions
8. **CPQL always before CPL** — ordering signals priority; CPL is never the headline metric
9. **Spend always in USD** — never SAR, never mixed
10. **No weekly check-in message** — we never post "all clear" or "no issues" messages;
    only post when there is something to report or an action to take

---

## Pre-Send Checklist (verify before every post)

- [ ] Dashboard URL present in message 1 (plain text)
- [ ] Date range is explicit (`YYYY-MM-DD to YYYY-MM-DD`)
- [ ] CPQL is the first metric in every table and summary
- [ ] No keywords included
- [ ] No abbreviations (spell out all acronyms)
- [ ] Channel is correct (`#nexa-reports` for performance, `#approvals` for actions)
- [ ] Data verified via `verify-before-reporting.md` before quoting any number
- [ ] Connector health status included (GREEN / AMBER / RED)
- [ ] Actions clearly separated from observations (message 2 in thread)
