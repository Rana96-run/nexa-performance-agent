# Playbook — Keyword Strategist

**Seat:** Performance Marketing. **Agent:** `keyword-strategist`.

## Purpose
Keep Google Ads keywords clean and on-policy. Every decision via `executors/keyword_policy.py`.

## Procedure
1. Run the audit: `python scripts/audit.py keywords` (read-only; creates an Asana task).
2. Classify each flagged term through `keyword_policy`:
   - ALWAYS_NEGATIVE (login/free/course/download/loan/job + Arabic) → direct-execute negative (bypasses age).
   - BRAND_ONLY (قيود/qoyod) → only in `Brand` campaigns; قيود+accounting-modifier = feature noun, route normal.
   - COMPETITOR (Foodics/Daftra/Wafeq/Zoho/Odoo/…) → only in `Competitor` campaigns; never negate elsewhere.
   - Language mismatch (`_AR_`/`_EN_` vs script) → pause-watch.
3. Expansions: sort highest-conv first, respect the **30-keyword/ad-group cap**, drop
   QS<5 & >80%-lost-IS candidates. → Asana only, **never Slack**.
4. Existing QS<5 & >80%-lost-IS: spend=0 → DELETE; spend>0 → PAUSE. Converting exception:
   conv>4 & $10≤CPA≤$70 → leave enabled.
5. Never pause the **last enabled keyword** in an ad group. 10-day min age for performance pause.

## Cadence
Expansions + performance-pauses run **weekly, Sunday Riyadh** (`FORCE_WEEKLY_KEYWORDS=1` to override).
Negatives execute daily. Pauses/deletes are approval-gated; negatives are not.

## Write to memory
New term classifications / edge cases → `memory/agents/performance-marketing/keyword-strategist/`.

## Done means
Audit run, classifications applied per policy, Asana task created. Numbers observed.
