---
name: gate-every-write
description: Every write action is gated on one #approvals ✅; ❌ skips; negatives are the only direct-execute exception
metadata:
  type: critical
---

Every write — scale, pause, create, campaign launch, LP deploy — waits for the
human **✅** in the ONE nightly #approvals digest. ❌ skips all of it. The only
direct-execute exception is negative keywords (no spend at risk).

**Why:** the whole org's safety rests on a single human gate; auto-executing any
write breaks the trust model and risks live spend.

**How to apply:** assemble one digest, queue every write decision into it, wait
for the reaction. Never let a department lead execute a write before the ✅.
