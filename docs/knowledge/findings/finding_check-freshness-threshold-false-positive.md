---
name: finding_check-freshness-threshold-false-positive
description: health_check.py used > 1 day staleness threshold — fired false red every night before 08:00 KSA before nightly collector ran
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `health_check.py` had a staleness threshold of `> 1 day`, but the nightly collector runs at 08:00 KSA. Before 08:00, data is legitimately 2 days behind by design. This caused a false red every single night. The authoritative `check_freshness.py` uses 3 days. Also: `0 or 99` in Python evaluates to `99` because 0 is falsy — `days_ago or 99` incorrectly marked today's data as 99 days stale. Required explicit `is not None` check.

Source: Session e83785ce — health_check.py threshold fix commit.

Impact: Activity Dashboard Data Hygiene section showed red every morning until 08:00 KSA; false alert noise.

Fix / How to handle: Threshold in health_check.py is now `>= 3` days (matching check_freshness.py). Known-paused channels (LinkedIn) are excluded from freshness checks. Always use `val is not None` instead of `val or default` for zero-safe numeric comparisons.
