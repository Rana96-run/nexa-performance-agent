---
name: finding_fstring-double-conversion
description: "Python f-strings only allow one conversion specifier (!r, !s, !a) — chaining two like !r!s is a SyntaxError"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `f"{term!r!s}"` in `scripts/audit_active_keywords.py` line 184 caused a SyntaxError that blocked the entire nightly keyword scan (`scripts/audit.py keywords`).

Source: Pre-existing bug in the codebase, surfaced by user report.

Impact: `audit.py keywords --silent` could not import, so the nightly keyword policy scan was completely broken.

Fix / How to handle: Use only ONE conversion: `!r` (repr — adds quotes, escapes special chars, best for debug output of terms/names) or `!s` (str — plain string). For keyword names in diagnostic prints, `!r` is correct. Changed `{term!r!s}` → `{term!r}` and `{r.ad_group.name!r!s}` → `{r.ad_group.name!r}`.
