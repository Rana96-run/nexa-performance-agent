---
name: finding_slack-events-raw-body-consumed
description: Flask Slack signature verification fails because get_json() consumes the body before get_data() — HMAC always built on empty string
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `_verify_slack_signature()` called `req.get_data()` AFTER `get_json()` had already consumed the request body. The signature was built on an empty string and always failed with a 403, blocking all Slack event delivery.

Source: Session 98abfa4b — debugging why ✅ reactions never triggered approval execution.

Impact: All Slack Events (reaction_added, app_mention) returned 403 and were never processed, making the entire reaction-based approval loop non-functional.

Fix / How to handle: Read raw body ONCE first (`raw = request.get_data()`), then parse JSON from it (`json.loads(raw)`) and use `raw` for HMAC signature computation. Never call `get_json()` and `get_data()` on the same request — they compete for the body stream.

[[finding_slack-bot-missing-reactions-read-scope]]
