---
name: finding_email-module-missing-crashes-scheduler
description: "NOTIFY_VIA=both but notifications/email.py didn't exist — module-level import crashed operational scheduler on every startup"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `NOTIFY_VIA=both` was set but `notifications/email.py` did not exist. The import ran at startup (not lazily), crashing the operational scheduler with an ImportError every 30 seconds. The process was restarting in a tight loop on Railway without any Slack alert.

Source: Session 98abfa4b — confirmed by Railway logs; health checks showed agent unhealthy.

Impact: The operational scheduler — which handles pause/scale watchers, keyword audits, Asana tasks — was down for an unknown period before discovery.

Fix / How to handle: Make third-party notification imports lazy (inside the function body) rather than at module level. Always set `NOTIFY_VIA=slack` unless email is actually implemented. Before removing any import, grep for where the module file should live — a missing file at import time vs. at call time is a silent startup crash vs. a graceful runtime error.
