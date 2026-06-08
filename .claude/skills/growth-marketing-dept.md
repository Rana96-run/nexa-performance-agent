---
name: growth-marketing-dept
description: |
  Department Skill — Higher Growth Marketing agent interface.
  Defines what strategic signals the Growth agent receives from Nexa,
  how to interpret them, and what strategic outputs it produces.
  Load when the Growth agent needs its data contract with Nexa,
  or when Nexa needs to verify what weekly signals to send.
---

# Growth Marketing Department Skill

> **Status & relationship to the 9-agent org (read first).** This skill describes
> an **aspirational EXTERNAL** higher-altitude Growth agent that would consume
> Nexa's weekly signals via an `agent_handoff_log` BQ table. As of 2026-06-08 that
> **table does not exist and no code writes it** — the integration was never wired.
>
> In the **current** org (`docs/_shared/org-chart.md`), the in-house Support seat
> **`growth-analyst`** does this work directly: 8-step loop on live BQ, period
> comparisons, forecasts, CRO A/B reads. Use this file as the **spec** for the
> frameworks below (SOSTAC-X, unit-economics matrix, the CPQL ceiling) — they're
> still how Growth thinking should be done — and as the build spec if/when an
> external Growth agent is stood up. Don't treat the handoff payloads as live.

## Department Mission

The Growth Marketing agent operates at a **higher strategic altitude** than the
Performance agent. It receives weekly performance signals, translates them into
growth strategy decisions, identifies expansion opportunities across channels and
products, and produces strategic recommendations that feed back into the
Performance agent's campaign roadmap.

It does NOT manage day-to-day campaign execution — that stays with Nexa.

---

## What Growth Receives from Nexa (Weekly — Sundays)

Via `agent_handoff_log` payload_type = `growth_signals`:

| Data point | How Growth uses it |
|---|---|
| `period_comparison` | Identifies structural shifts vs. tactical noise |
| `scale_candidates` | Prioritised expansion opportunities |
| `roas_trend` | Revenue-per-spend trajectory → budget allocation strategy |
| `forecast_eom` | Month-end projection → identifies if we'll hit monthly lead target |
| `strategic_observations` | Nexa's flagged patterns for Growth to act on |

---

## Growth Strategy Output Framework

### 🔵 CEO LAYER — Weekly Growth Brief
- **Growth status**: On track / At risk / Off track vs monthly target
- **Top opportunity**: Single biggest lever to pull this week
- **Budget recommendation**: Total spend increase/decrease + rationale
- **Channel strategy shift**: Any channel to deprioritise or accelerate
- **Product mix**: Which product is showing best unit economics this week

### 🟢 TEAM LAYER — Strategic Recommendations
- Channel expansion analysis (is there an underinvested channel?)
- Product mix optimisation (Invoice vs Bookkeeping vs Qflavours CPQL comparison)
- Audience expansion strategy (new Lookalike pools? new Interest segments?)
- Creative strategy direction (what format/hook is winning?)
- Competitive response (any new competitor activity impacting CPL?)
- New market test proposal (new city? new sector? new product angle?)

---

## Growth Frameworks Applied

### SOSTAC-X Applied to Qoyod
```
S — SITUATION    : Nexa's period comparison + ROAS trend
O — OBJECTIVES   : Monthly lead/SQL target + CPQL ceiling ($80 acceptable)
S — STRATEGY     : Channel mix + product priority + audience expansion
T — TACTICS      : Specific campaign/creative/LP changes (handed back to Nexa)
A — ACTION       : 30/60/90-day roadmap update
C — CONTROL      : Weekly signal review (this cycle)
X — AUTOMATION   : Handoff loop to Nexa for execution
```

### Unit Economics Matrix
Growth evaluates each product-channel combination weekly:
| Product | Channel | CPQL this week | CPQL target | Gap | Recommendation |
|---|---|---|---|---|---|
| Invoice | Meta | $XX | $80 | +/-$X | Scale / Hold / Shift |
| Bookkeeping | Google | $XX | $80 | +/-$X | Scale / Hold / Shift |
| Qflavours | Snapchat | $XX | $80 | +/-$X | Scale / Hold / Shift |

---

## Feedback Loop to Nexa

Growth sends strategic directives back to Nexa weekly:
```json
{
  "directive_type": "growth_strategy",
  "week": "YYYY-WXX",
  "budget_directive": {
    "total_weekly_spend_target": 0.0,
    "channel_allocation": {"meta": 0.40, "google": 0.30, "snapchat": 0.15, "other": 0.15}
  },
  "product_focus": "Invoice | Bookkeeping | Qflavours | Balanced",
  "new_tests_approved": [],
  "channels_to_scale": [],
  "channels_to_reduce": [],
  "strategic_rationale": ""
}
```
Nexa reads this directive at the start of the following week's analysis to calibrate recommendations.

---

## Rules & Guardrails

- **Growth recommends, Nexa executes** — Growth never touches BQ or platforms directly
- **All recommendations must have a forecast** — "increase budget" without projected CPQL impact is incomplete
- **CPQL ceiling is non-negotiable** — no growth recommendation that would push CPQL above $100
- **14-day minimum data window** — Growth never recommends based on < 2 weeks of signal
- **New channel proposals**: require 30-day test budget and measurement plan before approval

---

## Success Criteria

✅ Weekly growth brief posted within 4 hours of receiving Nexa's growth_signals
✅ Unit economics matrix completed for all 3 products × all active channels
✅ Strategic directive written and sent back to Nexa for next week
✅ All budget recommendations include projected CPQL impact
✅ Zero recommendations that would push any channel CPQL above $100
