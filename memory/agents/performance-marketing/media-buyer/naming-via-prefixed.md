---
name: naming-via-prefixed
description: Always build campaign/adset/ad names through executors/naming.py::prefixed(), never by hand
metadata:
  type: critical
---

Never hand-format a campaign, ad set, or ad name. Always call
`executors/naming.py::prefixed()` — it enforces `{Channel}_{Type}_{Language}_
{Product}_{Audience}`, auto-normalises products (E-Invoice→Invoice,
bookkeeping→Bookkeeping), rejects "Prospecting" as an audience, and applies the
LinkedIn UTM mapping (Campaign=utm_campaign, Ad Set=utm_audience, Ad=utm_content).

**Why:** hand-typed names drift from the convention and break the UTM→lead join,
which silently corrupts CPQL attribution downstream.

**How to apply:** import and call `prefixed()`; if it raises `ValueError`, fix the
inputs — don't bypass it. See the naming section of [[../../../../CLAUDE.md]].
