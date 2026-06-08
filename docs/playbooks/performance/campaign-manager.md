# Playbook — Campaign Manager

**Seat:** Performance. **Agent:** `campaign-manager`. Parallel peer: `creative-strategist`.

## Purpose
Build campaigns exactly to spec, on-policy, gated.

## Procedure
1. Build names via `executors/naming.py::prefixed()` — the 12-field spec
   `{Channel}_{Type}_{Language}_{Product}_{Audience}`. Audience must be `Interests`
   or `Lookalike`; `Prospecting` raises `ValueError` (don't bypass). LinkedIn UTM
   mapping: Campaign=utm_campaign, Ad Set=utm_audience, Ad=utm_content.
2. Attach **both Meta pixels on every campaign**: Qoyod_CRM_PIXEL `1782671302631317`
   + Qoyod_Web_PIXEL `3036579196577051`.
3. Apply keyword policy via `executors/keyword_policy.py`: ALWAYS_NEGATIVE (login/
   free/course/download/loan/job + Arabic) · BRAND_ONLY (قيود/qoyod, Brand campaigns
   only) · COMPETITOR (Foodics/Daftra/… Competitor campaigns only).
4. Hand the build spec to `performance-lead` for the gate. Execute only after ✅.

## Hard rules
Never execute without ✅. Negatives may direct-execute (no spend at risk).
Never pause the last enabled keyword in an ad group.

## Done means
A complete, on-policy build spec gated and (after ✅) executed + verified.
