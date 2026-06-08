---
name: agent-handoff
description: |
  Workflow Skill — Cross-agent communication protocol for the Qoyod AI agent ecosystem.
  Load when writing data for the Marketing Ops agent or Growth Marketing agent,
  when reading a handoff from another agent, or when debugging why a receiving
  agent has stale or missing data.
  ALWAYS use for: after morning analysis (write ops brief), after weekly review
  (write growth signals), when receiving agent reports issues with data freshness.
---

# Agent Handoff Skill

> **Status (2026-06-08): aspirational — not wired.** This protocol writes/reads an
> `agent_handoff_log` BQ table that **does not exist** (no code creates or writes
> it). It describes a planned external-agent ecosystem. In the current 9-agent org
> (`docs/_shared/org-chart.md`), handoffs are **in-process** between subagents via
> the packet format in `docs/_shared/handoff-protocol.md` — not BQ rows. Use this
> skill as the build spec if/when the external BQ handoff is implemented.

## The 3-Agent Ecosystem

```
┌─────────────────────────────────────────────────────────────┐
│                  Qoyod AI Agent Ecosystem                    │
│                                                              │
│  ┌──────────────────┐     BQ handoff_log     ┌───────────┐  │
│  │  Nexa Performance│ ──────────────────────▶│  Marketing│  │
│  │  Agent (this one)│                         │  Ops Mgmt │  │
│  │                  │ ──────────────────────▶│  Agent    │  │
│  │  • Collects data │                         └───────────┘  │
│  │  • Analyses CPQL │     BQ handoff_log                     │
│  │  • Creates tasks │ ──────────────────────▶┌───────────┐  │
│  │  • Police checks │                         │  Growth   │  │
│  └──────────────────┘                         │  Marketing│  │
│                                               │  Agent    │  │
│                                               └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**This agent** is the data source. It never receives handoffs — it only sends them.
**Ops agent** receives daily operational briefs.
**Growth agent** receives weekly strategic signals.

---

## BQ Table: `agent_handoff_log`

Schema:
```sql
handoff_ts      TIMESTAMP    -- when this record was written (UTC)
source_agent    STRING       -- always "nexa_performance"
target_agent    STRING       -- "ops_management" | "growth_marketing"
payload_type    STRING       -- "daily_ops_brief" | "growth_signals" | "connector_status"
payload_json    JSON         -- structured payload (see templates below)
period_start    DATE         -- data window start
period_end      DATE         -- data window end
ttl_hours       INT64        -- expiry (26h for daily, 170h for weekly)
is_consumed     BOOL         -- set to TRUE by receiving agent after reading
```

---

## Payload Templates

### Template 1 — daily_ops_brief (→ Ops Management Agent)
Written: every morning after Stage 6 of morning analysis flow
TTL: 26 hours
```json
{
  "report_date": "YYYY-MM-DD",
  "period": "YYYY-MM-DD to YYYY-MM-DD",
  "connector_health": {
    "overall": "GREEN | AMBER | RED",
    "broken_connectors": [],
    "warning_connectors": []
  },
  "kpi_summary": {
    "total_spend_usd": 0.0,
    "total_leads": 0,
    "total_sqls": 0,
    "blended_cpql": 0.0,
    "blended_cpl": 0.0,
    "channels": [
      {"channel": "meta", "spend": 0.0, "leads": 0, "cpql": 0.0, "status": "SCALE|HOLD|WATCH|PAUSE"}
    ]
  },
  "active_asana_tasks": {
    "total_open": 0,
    "pending_approval": 0,
    "task_urls": []
  },
  "approvals_pending": {
    "scale_items": 0,
    "pause_items": 0,
    "digest_posted": true,
    "digest_url": ""
  },
  "flags": [],
  "generated_by": "nexa_performance",
  "confidence": "HIGH | MEDIUM | LOW"
}
```

### Template 2 — growth_signals (→ Growth Marketing Agent)
Written: every Sunday after weekly analysis
TTL: 170 hours (7 days)
```json
{
  "week_ending": "YYYY-MM-DD",
  "period": "YYYY-MM-DD to YYYY-MM-DD",
  "period_comparison": {
    "this_week_cpql": 0.0,
    "prior_week_cpql": 0.0,
    "cpql_delta_pct": 0.0,
    "this_week_leads": 0,
    "prior_week_leads": 0,
    "leads_delta_pct": 0.0,
    "channel_breakdown": []
  },
  "scale_candidates": [
    {
      "campaign_name": "",
      "channel": "",
      "current_cpql": 0.0,
      "current_spend_daily": 0.0,
      "recommended_spend_daily": 0.0,
      "confidence": "HIGH | MEDIUM | LOW",
      "full_spec_asana_url": ""
    }
  ],
  "roas_trend": {
    "this_week": 0.0,
    "prior_week": 0.0,
    "trend": "IMPROVING | STABLE | DECLINING"
  },
  "forecast_eom": {
    "projected_spend": 0.0,
    "projected_leads": 0,
    "projected_cpql": 0.0,
    "projected_roas": 0.0,
    "status_quo_vs_action_gap": ""
  },
  "strategic_observations": [],
  "generated_by": "nexa_performance"
}
```

### Template 3 — connector_status (→ Both agents, on-demand)
```json
{
  "check_ts": "ISO timestamp",
  "overall_status": "GREEN | AMBER | RED",
  "connectors": [
    {
      "channel": "meta",
      "status": "HEALTHY | WARNING | BROKEN",
      "freshness_hours": 0,
      "fix_command": "railway run python collectors/meta_bq.py 3 | NONE"
    }
  ]
}
```

---

## Write Protocol (This Agent — Sender)

```python
# After morning analysis Stage 7:
from logs.activity_logger import log_activity_async
import json

handoff = {
    "handoff_ts": datetime.utcnow().isoformat(),
    "source_agent": "nexa_performance",
    "target_agent": "ops_management",
    "payload_type": "daily_ops_brief",
    "payload_json": json.dumps(ops_brief_payload),
    "period_start": period_start.isoformat(),
    "period_end": period_end.isoformat(),
    "ttl_hours": 26,
    "is_consumed": False,
}
# Write to BQ agent_handoff_log via load_table_from_file
```

---

## Read Protocol (Receiving Agents)

The Ops and Growth agents query BQ to read their handoffs:
```sql
SELECT payload_json, handoff_ts, period_start, period_end
FROM `{project}.{dataset}.agent_handoff_log`
WHERE target_agent = 'ops_management'        -- or 'growth_marketing'
  AND payload_type = 'daily_ops_brief'       -- or 'growth_signals'
  AND TIMESTAMP_ADD(handoff_ts, INTERVAL ttl_hours HOUR) > CURRENT_TIMESTAMP()
  AND is_consumed = FALSE
ORDER BY handoff_ts DESC
LIMIT 1
```

After consuming, set `is_consumed = TRUE`.

**Validation before consuming:**
1. Check `handoff_ts` is within TTL — reject if expired
2. Check `period_end` matches expected date — reject if wrong period
3. Check `connector_health.overall != "RED"` — flag to user if broken data

---

## Staleness Handling

| Condition | Action |
|---|---|
| No handoff in last 26h (daily brief) | Receiving agent flags "data unavailable" — does not proceed with analysis |
| TTL expired | Handoff is ignored — agent uses last known state |
| `connector_health.overall = RED` | Receiving agent notes data may be unreliable in its output |
| `confidence = LOW` | Receiving agent downgrades its own confidence level |

---

## Rules & Guardrails

- **Never** write a handoff with placeholder data — if analysis failed, write a failure record
- **Never** include PII in payload_json — only aggregate metrics and task URLs
- **Never** let a receiving agent auto-execute based on handoff data — all actions still require human approval
- **Always** write Stage 7 handoff even when no flags fire — clean run data is still valuable
- **Always** include `period_start` and `period_end` in explicit `YYYY-MM-DD` format
- **Always** set TTL appropriate to cadence (26h daily, 170h weekly)

---

## Success Criteria

✅ Handoff written within 5 minutes of Stage 6 completing
✅ All three payload fields populated (connector_health + kpi_summary + approvals_pending)
✅ Receiving agent can query and parse without error
✅ TTL set correctly for the payload type
✅ Written to BQ via load job (not streaming insert)
✅ `is_consumed` starts as FALSE — receiving agent sets TRUE after reading
