# Playbooks — Index

Each agent in `.claude/agents/` has exactly one playbook here. The agent file is
**identity + routing** (small, loaded every dispatch). The playbook is the
**operational procedure** — the steps, thresholds, scripts, and done-criteria.
An agent reads its own playbook on boot; it should not need any other agent's.

## Performance Marketing
- [performance-lead](performance-marketing/performance-lead.md) — runs the daily loop, routes flags, builds the #approvals digest
- [media-buyer](performance-marketing/media-buyer.md) — full pause/scale/budget setups, execution after ✅
- [paid-media-analyst](performance-marketing/paid-media-analyst.md) — period comparison, attribution, lead quality
- [paid-media-strategist](performance-marketing/paid-media-strategist.md) — channel mix, scale plans, forecasts
- [data-engineer](performance-marketing/data-engineer.md) — BQ schema, collectors, views, reconciliation
- [connector-police](performance-marketing/connector-police.md) — freshness gate, connector diagnosis
- [cro-paid-specialist](performance-marketing/cro-paid-specialist.md) — LP audit/specs, CPQL→LP loop
- [keyword-strategist](performance-marketing/keyword-strategist.md) — Google Ads keyword policy

## Growth Marketing
- [growth-lead](growth-marketing/growth-lead.md) — weekly brief + budget/channel directive
- [growth-strategist](growth-marketing/growth-strategist.md) — SOSTAC-X, roadmap, audience/creative direction
- [market-expansion-analyst](growth-marketing/market-expansion-analyst.md) — new-bet sizing + test design

## Marketing Operations
- [ops-manager](marketing-ops/ops-manager.md) — leadership reports, escalations
- [ops-reporter](marketing-ops/ops-reporter.md) — report tables, freshness check
- [approval-coordinator](marketing-ops/approval-coordinator.md) — approval tracking, 7d/14d outcomes

## Shared (every agent reads as needed)
- [../_shared/org-chart.md](../_shared/org-chart.md)
- [../_shared/handoff-protocol.md](../_shared/handoff-protocol.md)
- [../_shared/communication-rules.md](../_shared/communication-rules.md)
- Root non-negotiables: `../../CLAUDE.md` · `../../memory/CRITICAL_KPI_RULES.md`
