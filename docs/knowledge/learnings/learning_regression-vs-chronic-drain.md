---
name: learning_regression-vs-chronic-drain
description: "Prior-period CPQL determines FIX vs PAUSE — a campaign with good prior CPQL that regressed is a FIX candidate, not a drain to pause"
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: `Search_E-invoice_AR_Test` had prior CPQL $73.98 (acceptable zone) and current CPQL $308.96. Was classified as a "drain" requiring consideration for pause. This was wrong — a campaign with good prior performance that regressed is a FIX candidate.

Outcome: Wrong action recommendation (pause vs fix).

Pattern: Period comparison classification:
- Prior CPQL good AND current bad → REGRESSION → FIX (keyword cleanup, budget cap, LP review)
- Prior CPQL bad AND current bad → CHRONIC DRAIN → PAUSE (keep paused until structural fix)
- Prior CPQL bad AND current worse → ACCELERATING DRAIN → PAUSE IMMEDIATELY

Growth-analyst must classify prior/current delta BEFORE performance-lead decides action.

Applies to: Every campaign-level action recommendation; any performance-lead escalation.
