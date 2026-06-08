# The Police Loop — autonomous detect → route → fix → verify → report

How the team catches and closes **any stale / error / bug ANYWHERE in the system**
without it falling through — not just inbound data connectors. This wires the
**hand-off after detection** so nothing sits unfixed.

## Scope — the police watches the WHOLE system (not just connectors→BQ)
Detection must cover every surface that can break. Aggregate ALL detectors into one
health view; each finding routes through the loop below.

| Surface | Detector | Status |
|---|---|---|
| Inbound: connectors → BQ | `connector_tracker` (freshness/rows/spend/attrib/creds/amount) | ✅ |
| Transforms: BQ views / schema drift | `self_healer` (stale_views), reconciliation | ✅ partial |
| Config / structure (role overlap, mapping drift) | `dashboard_guard` | ✅ |
| Data quality (anomalies, corrupt amounts, dedup/fan-out, attribution) | `spike_detector`, `amount_sanity` | 🟡 scattered |
| Runtime (nightly loop fired? Railway up? stuck approvals?) | `self_healer`, heartbeats, `/health` | 🟡 partial |
| Credentials PRESENT (all integrations) | `health.py` | ✅ presence-only |
| **Outbound delivery — Databox push** (both datasets pushed within 28h?) | `connector_tracker` SYSTEM_MONITORS (checks 6-8) | ✅ 2026-06-08 |
| **Runtime health — Railway /health** | `connector_tracker` SYSTEM_MONITORS | ✅ 2026-06-08 |
| **Runtime health — scheduler fired** | `connector_tracker` SYSTEM_MONITORS (agent_activity_log query) | ✅ 2026-06-08 |
| **Outbound delivery — Slack/Asana** (digest posted? tasks created?) | failure heartbeats only | 🔴 **gap** |
| **Executor actions** (did an approved pause/scale/keyword actually apply on-platform?) | — | 🔴 **gap** |
| **Credential LIVENESS** (token present but expired/revoked → silent fail) | — | 🔴 **gap** |
| **Cost / consumption anomalies** (token/BQ spend spike) | `cost_tracking` logs only | 🔴 **gap** |

Closing the 🔴 gaps is the police-expansion backlog (`memory/09_open_tasks.md`). The
detection above isn't complete — treat any *new* surface that can fail and has no
detector as itself a police finding.

## The loop (every issue follows it)
```
DETECT ─► ROUTE ─► FIX ─► VERIFY ─► REPORT
(police)  (orchestr) (owner) (analyst) (orchestr + push)
```

| Stage | Owner | What happens |
|---|---|---|
| **DETECT** | `marketing-ops` | Surfaces every signal: `connector_health_log` (BROKEN/WARNING + fix_command), `collector_failures`, the QA gate blocks, `dashboard_violations.jsonl`, and `self_healer` scans. Fires #nexa-health on RED. Escalate a WARNING unchanged 3+ days to BROKEN — **but only for channels expected to have activity** (see idle rule). |

> **⚠️ Idle ≠ broken (the cry-wolf guard).** A channel with **no active campaigns /
> no recent spend** that shows zero/stale data is **HEALTHY-IDLE, not a fault** —
> zero data is correct. Do NOT flag it stale/BROKEN or escalate it. (LinkedIn was
> stale 95 days simply because there are no active LinkedIn campaigns — not a bug.)
> Mirrors the MS Ads "Success + null = no activity" pitfall. The police must check
> *is activity expected here?* before raising any stale/broken flag.
| **ROUTE** | `ai-orchestrator` | Reads the detected issue, classifies it, hands a HANDOFF packet to the owning seat (below). |
| **FIX** | the owning seat | Applies the fix. **Autonomy depends on the class — see the boundary.** |
| **VERIFY** | `growth-analyst` | Re-runs the exact check (re-query freshness / re-run the audit). "Done = the symptom is gone, observed." |
| **REPORT** | `ai-orchestrator` | Confirms closure, ensures the fix is committed + pushed, logs the outcome to `memory/14_learning_patterns.md`. |

## Who fixes what (routing table)
| Issue class | Owner | Autonomy |
|---|---|---|
| Stale view / failed collector (re-runnable) | `growth-analyst` (data) / `self_healer` | **autonomous** ✅ — re-run the collector/view |
| Connector health, pixel, UTM/field-map | `marketing-ops` | autonomous for re-runs; **human-gated** for OAuth/credential refresh |
| Dashboard / config bug (e.g. role_overlap) | owner of the file | autonomous ✅ (code reviewed before push) |
| Schema / attribution drift | `growth-analyst` | autonomous detect + reconcile; schema change = reviewed |
| Wasteful / mis-set ad campaign | `performance-lead` → `campaign-manager` | **NEVER autonomous** — human ✅ in #approvals |

## ⚠️ The boundary (this is what keeps us unbreakable, not reckless)
- **Autonomous, no human hands:** data/view/collector self-heal, dashboard/config fixes, schema reconciliation checks. (`self_healer` already does several of these.)
- **Human-gated, always:** (1) any **ad-account write** (pause/scale/create/budget) — the #approvals ✅; (2) **credential/OAuth** changes (LinkedIn token, MS re-auth); (3) **source-code** changes push only after review. An agent that auto-pushes unreviewed code or auto-spends is breakable, not unbreakable.

## Status — 2026-06-08 (after the loop ran end-to-end)
Tracked in `memory/09_open_tasks.md`. The morning's 5 flags were VERIFIED:
- **LinkedIn 95-day stale → RESOLVED:** idle, not a bug (no active campaigns). Idle-aware guard added.
- **`bing` / `google` / `hubspot_leads` BROKEN → RESOLVED:** false positives from 3 tracker
  bugs (channel-label mismatch, channel-less HubSpot tables, too-tight freshness threshold) — all fixed.
- **`hubspot_deals` BROKEN → ROOT-CAUSED:** the "$257.7B" amount was a **phone number**
  (deal `505631711439`, `966504406958 SAR` = +966 50 440 6958) typed into the Amount field.
  **HUMAN fix open** (HubSpot read-only); police now auto-diagnoses the phone signature.

Net: 5 flags → 4 were police false-positives (fixed), 1 real human-error (open for human).

## Coverage rule (so nothing is unseated)
**Every one of the 13 `agent_activity_log` roles must be owned by a seat** (see the
mapping in `../../memory/11_agent_roles.md`). If a new role/label appears in the
log and no seat owns it, that is itself a police finding — assign it before it
runs unattended.
