---
name: learning_health-check-grep-source-before-writing
description: health_check.py called non-existent _get_token() on Snapchat and wrong DATASET constant — always grep source files before writing check code
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: When adding `check_snapchat()` to `health_check.py`, the actual Snapchat module function was assumed from memory without checking the source file. The correct function name is `_refresh_access_token()` with accounts from `_ad_accounts()`. Similarly, `DATASET_ID` was assumed as the BQ constant name but the actual export from `bq_writer` is `DATASET`.

Outcome: Both health checks failed immediately on first run; required a second fix commit.

Pattern: Never assume function or variable names when writing code that calls another module. Always grep the module first: `grep -n "def _" collectors/snap_bq.py` and `grep -n "^DATASET" collectors/bq_writer.py`. This reinforces the "Verify before use" rule specifically for health/monitoring scripts which often call into other modules at arm's length.

Applies to: Any new health check, connector check, or monitoring script that imports from existing collectors.

[[feedback_verify_before_use]]
