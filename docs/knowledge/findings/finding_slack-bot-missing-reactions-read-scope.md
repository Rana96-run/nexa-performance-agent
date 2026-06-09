---
name: finding_slack-bot-missing-reactions-read-scope
description: Nexa Slack bot missing reactions:read + channels:history scopes — all ✅ approval reactions silently swallowed
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The Nexa bot's OAuth scopes were: `app_mentions:read, chat:write, files:write, assistant:write, im:history, users:read`. Missing `reactions:read` and `channels:history`. When a ✅ reaction fired, `reaction_added` event arrived but `_handle_reaction()` called `reactions_get()`, which Slack rejected with `missing_scope` — handler bailed silently, nothing logged. Confirmed: zero `action_approved_via_slack` events in agent_activity_log over 7 days despite ✅ reactions being sent.

Source: Session 98abfa4b.

Impact: The entire approval execution loop was dead. Every ✅ reaction from the team was swallowed with no acknowledgment.

Fix / How to handle: Add `reactions:read` and `channels:history` scopes in the Slack App's OAuth & Permissions page, then reinstall the app to the workspace. After that, `reaction_added` events carry enough data to confirm and execute without a secondary API call.

[[finding_slack-events-raw-body-consumed]]
