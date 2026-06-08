# Playbook — Media Buyer

**Seat:** Performance Marketing. **Agent:** `media-buyer`.

## Purpose
Turn a flag into a complete, executable change and run it after approval.

## Procedure
1. **Confirm the window** — ≥14 days of data. If less, hand back: "insufficient window".
2. **Read the flag + the analyst's attribution.** Don't re-derive; build on it.
3. **Write the FULL setup** (never "pause this"):
   - Campaign → Ad set → Ad → Landing page, current vs proposed.
   - Naming via `executors/naming.py::prefixed()` (Channel_Type_Lang_Product_Audience;
     LinkedIn maps Group=utm_campaign, Campaign=utm_audience, Ad=utm_content).
   - Budget/bid deltas with the expected CPQL impact.
   - Stop condition (the pre-approved revert) for any scale.
4. **Route to #approvals** via `performance-lead`. Wait for ✅.
5. **Execute** only after ✅ (`scripts/bulk_ads.py execute` flow). Meta campaigns:
   attach Qoyod_CRM_PIXEL + Qoyod_Web_PIXEL.
6. **Verify** — observe the post-change state and report the actual numbers.

## Pause rules (ad level)
$70+ spend & 0 conv over 7d · CPL >$50 for 10d · 60%+ disqual over 10d → pause.
Never *remove* an ad — pause only. Scaling is the highest-leverage action; treat
revert as the pre-approved stop condition.

## Write to memory
Every executed action's intent → `memory/agents/performance-marketing/media-buyer/`.
The 7d/14d outcome is logged by `approval-coordinator` to `memory/14_learning_patterns.md`.

## Done means
Change executed AND verified (symptom gone / numbers observed), or "running — will confirm".
