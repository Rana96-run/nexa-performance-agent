# Review & Fix — find missing logging, broken mappings, silent gaps

**When to use:** When the user asks to "review for missing pieces / bugs",
after a major feature lands (new action type, new script, new executor), or
when the dashboard shows unexpected zeros. This is a **rigid skill** — run
every check, fix every gap found, then commit.

## Why this exists

Across multiple sessions we found the same class of bugs repeatedly:
- A new action type logged by a script → not mapped in `_CAT_MAP` or the BQ view → invisible on the heatmap
- A manual script pausing/deleting something → no `log_activity_async` call → dashboard shows 0
- A new GID field name (`asana_gid` vs `gid`) → sync or query uses the wrong key → completions never surface
- A new action added to `exec_sql` but forgotten in `_ACTION_VERB` → shows raw action name instead of human label

## The checklist — run every item, in order

### 1. Trace every "write" action → does it log to BQ?

```bash
grep -rn "log_activity_async" scripts/ executors/ analysers/ --include="*.py" | grep "log_activity"
```

For each script or executor that performs a real-world mutation (pause, scale,
add keyword, remove negative, create Asana task), confirm there is a
`log_activity_async(role=..., action=..., ...)` call after the API succeeds.

**Common misses:** `scripts/bulk_ads.py`, `scripts/action_audit_violations.py`,
`scripts/audit_active_negatives.py`, any new one-off executor.

Fix: add the call wrapped in `try/except Exception: pass` so the script
still completes if BQ is unavailable.

### 2. Trace every action name → is it in the BQ view CASE block?

Read `collectors/views.py` and find the CASE block in `v_agent_activity_dashboard`.
For every `action=` value you found in step 1, verify it maps to a category.

Categories: `Campaigns Created`, `Campaigns Paused`, `Campaigns Scaled`,
`Keywords Added`, `Keywords Paused`, `Negatives Added`, `Ads Paused`,
`Asana Tasks`, `Slack Messages`, `Approvals`, `User Actions`.

**Common misses:** New audit task action types (`scale_task_created`,
`optimize_task_created`), new script actions (`keywords_deleted`,
`negative_keywords_removed`, `ads_enabled`), new user snapshot actions.

Fix: add the WHEN clause to the CASE block in `collectors/views.py`, then
call `refresh_all_views()` (or the next 6h scheduler run will pick it up).

### 3. Trace every action name → is it in `_CAT_MAP` in `reports/app.py`?

```python
grep -n "_CAT_MAP\|'action_name'" reports/app.py
```

`_CAT_MAP` drives the sidebar count bars and the recent activity feed grouping.
If an action isn't here it still runs, but the sidebar won't count it.

Fix: add `"action_name": "Category Label"` to the dict.

### 4. Trace every action name → is it in `detail_sql` IN filter?

`detail_sql` (in the `/activity` route) has a hardcoded `AND action IN (...)`
whitelist. Any action missing from it will never appear in the metric cards
or drilldown tables, even if it exists in BQ.

Fix: add the action name to the IN list.

### 5. Check GID field consistency for Asana tasks

Two logging paths exist:
- `executors/asana.py` logs `action='asana_task_created'` with `details.gid`
- `campaign_health_tasks.py` logs `action='*_task_created'` with `details.asana_gid`

Verify both `asana_sync.py` (gid_sql + known_sql) and `app.py` (_ts_base_sql)
UNION both sources. If a new Asana-creating path is added (new analyser,
new script), check which field name it uses and add to the UNION.

### 6. Check `_ACTION_VERB` in `reports/app.py`

Every action that can appear in the Executed Actions card needs a human-readable
label in `_ACTION_VERB`. Missing entries fall back to `action.replace("_", " ").title()`
which is readable but inconsistent.

```python
grep -n "_ACTION_VERB" reports/app.py
```

Fix: add `"action_name": "Human label"` for any new action types.

### 7. Check `exec_sql` IN filter in `reports/app.py`

`exec_sql` populates the Executed Actions card. It has its own IN filter
separate from `detail_sql`. New execution actions must be added here too.

### 8. Run a quick consistency check across all three filter lists

These three must stay in sync for any execution action:
- `detail_sql` IN filter
- `exec_sql` IN filter  
- `_ACTION_VERB` dict

For any action in one, it should be in all three (or intentionally excluded
from `exec_sql` if it's a recommendation-only action).

## After finding gaps

1. Fix ALL gaps found in this pass — don't defer any.
2. For BQ view changes, the view auto-refreshes on the next scheduler run.
   If the user needs it now, call `refresh_all_views()` in the refresh endpoint.
3. Commit all fixes in ONE commit with message format:
   `fix(activity): close logging/mapping gaps — [brief list]`
4. Push immediately.

## What triggers this skill

- User says "anything else?", "did I miss anything?", "check for gaps"
- A new collector, executor, or script is added to the project
- A new action type is introduced anywhere in the codebase
- Dashboard metrics show unexpected zeros after a known operation ran
- After any session where new `log_activity_async` calls were added
