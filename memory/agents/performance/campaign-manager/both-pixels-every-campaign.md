---
name: both-pixels-every-campaign
description: Every Meta campaign must attach BOTH Qoyod pixels (CRM 1782671302631317 + Web 3036579196577051), and names go through prefixed()
metadata:
  type: critical
---

Every Meta campaign attaches **both** pixels, without exception:
Qoyod_CRM_PIXEL `1782671302631317` + Qoyod_Web_PIXEL `3036579196577051`. All
names are built via `executors/naming.py::prefixed()` (12-field spec); audience
must be `Interests` or `Lookalike` — `Prospecting` raises `ValueError`.

**Why:** a missing pixel loses conversion signal; a hand-typed name breaks the
UTM→lead join and corrupts CPQL.

**How to apply:** never hand-format a name or skip a pixel. If `prefixed()` raises,
fix the inputs, don't bypass it. See [[../../../../CLAUDE.md]].
