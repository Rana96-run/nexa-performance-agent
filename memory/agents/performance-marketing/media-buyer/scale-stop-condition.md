---
name: scale-stop-condition
description: Every scale action must ship with a pre-approved revert (stop condition) so a bad scale auto-reverts
metadata:
  type: learning
---

Every budget scale I propose must include a pre-approved stop condition (the
revert) in the same approval. If the scaled campaign's CPQL crosses its ceiling
within the monitor window, the revert is already approved and executes without a
new round-trip.

**Why:** scaling is the highest-leverage action but also the fastest way to burn
budget; a pre-approved revert caps the downside.

**How to apply:** in the change spec, add a "Stop condition" line with the CPQL
threshold and the exact revert. Verified end-to-end on 2026-06-08.
