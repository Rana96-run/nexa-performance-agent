# Phase 1B — Slack Digest Minimal Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `post_nightly_approvals_digest` in `notifications/slack.py` to produce the minimal format — one line per channel (spend · leads · CPQL), a single ACTIONS block, and a REVIEW ONLY block — replacing the current verbose multi-paragraph output.

**Architecture:** Add `channel_summary: list[dict] | None = None` as a new optional parameter to `post_nightly_approvals_digest`. The function body is rewritten to produce the new format. The one caller (`analysers/campaign_health_tasks.py:715`) is updated to fetch and pass channel_summary from BQ. All existing parameters (`scale_findings`, `pause_findings`, `review_findings`) and the approval-gating logic (pending_approval store, ✅/❌ pre-reactions) remain unchanged.

**Tech Stack:** Python 3.11, Slack WebClient, BigQuery client.

---

## File map

**Modified:**
- `notifications/slack.py` — `post_nightly_approvals_digest` function body + signature
- `analysers/campaign_health_tasks.py` — `_send_nightly_digest` caller updated to pass channel_summary

---

## Task 1 — Add channel_summary parameter and new message body

**Files:**
- Modify: `notifications/slack.py:125-255`

- [ ] **Step 1: Read the current function to confirm line range**

Run: `grep -n "def post_nightly_approvals_digest\|^def " notifications/slack.py | head -10`

Confirm the function starts at line 125 and the next top-level `def` follows it (currently around line 257).

- [ ] **Step 2: Replace the function body**

In `notifications/slack.py`, replace the body of `post_nightly_approvals_digest` (lines 125–255, keeping the function signature line + docstring header, replacing everything from the `if not scale_findings...` guard down to the `return ts` line) with the new implementation below.

New full function (replace from line 125 to the closing `return ts` / `return None`):

```python
def post_nightly_approvals_digest(
    scale_findings: list,
    pause_findings: list,
    review_findings: list,
    window_days: int | None = None,
    channel_summary: list | None = None,
) -> str | None:
    """
    THE ONE #approvals message.

    Minimal format:
      Nexa · {date}  |  {dashboard_url}

      PERFORMANCE
      {channel}   ${spend}  ·  {leads} leads  ·  ${cpql} CPQL   {icon}

      ACTIONS  —  ✅ executes all  ·  ❌ skips all
      ↗  {campaign}   +{pct}% budget  (${old} → ${new})
      ⏸  {campaign}   pause           (${cpql} CPQL · {days}d)

      REVIEW ONLY  (Asana tasks created)
      ⚡  {flag}  —  {asana_url}

    ✅ = execute all scale + pause  ·  ❌ = skip all
    Returns the Slack message ts, or None on failure.
    """
    from notifications.quiet import is_quiet, quiet_log

    if not scale_findings and not pause_findings and not review_findings:
        return None

    if window_days is None:
        try:
            from config import DAYS_FOR_PAUSE_DECISION
            window_days = DAYS_FOR_PAUSE_DECISION
        except Exception:
            window_days = 14

    from datetime import date as _date, timedelta as _td
    end_d   = _date.today() - _td(days=1)
    start_d = end_d - _td(days=window_days - 1)

    today_label = datetime.now(timezone.utc).strftime("%b %-d")

    # ── Dashboard URL ─────────────────────────────────────────────────────────
    try:
        from config import ACTIVITY_DEST_URL
        dash_url = ACTIVITY_DEST_URL
    except Exception:
        dash_url = "https://nexa-web-production-6a6b.up.railway.app/activity"

    lines = [f"*Nexa · {today_label}*  |  {dash_url}"]

    # ── PERFORMANCE block (one line per channel, sorted by spend desc) ────────
    _CPQL_SCALE   = 85    # below → ✅
    _CPQL_WARNING = 130   # above → 🔴, between → ⚠️

    if channel_summary:
        lines.append("\n*PERFORMANCE*")
        for ch in sorted(channel_summary, key=lambda x: x.get("spend", 0), reverse=True):
            name   = ch.get("channel", "?").title()
            spend  = ch.get("spend", 0)
            leads  = ch.get("leads", 0)
            cpql   = ch.get("cpql")
            if cpql is None:
                icon = "—"
            elif cpql < _CPQL_SCALE:
                icon = "✅"
            elif cpql < _CPQL_WARNING:
                icon = "⚠️"
            else:
                icon = "🔴"
            cpql_str = f"${cpql:.0f} CPQL" if cpql else "no leads"
            lines.append(
                f"{name:<10}  ${spend:.0f}  ·  {leads} leads  ·  {cpql_str}   {icon}"
            )

    # ── ACTIONS block ─────────────────────────────────────────────────────────
    executable_findings = []
    action_lines = []

    for f in scale_findings:
        avg   = f.get("avg_spend")
        new_b = f.get("new_budget")
        budget_str = f"  (${avg:.0f} → ${new_b:.0f}/day)" if avg and new_b else ""
        action_lines.append(f"↗  `{f.get('campaign', '?')}`   +25% budget{budget_str}")
        executable_findings.append(f)

    for f in pause_findings:
        cpql    = f.get("cpql")
        cpql_str = f"${cpql:.0f} CPQL" if cpql else "high CPQL"
        days_str = f"{window_days}d"
        action_lines.append(f"⏸  `{f.get('campaign', '?')}`   pause   ({cpql_str} · {days_str})")
        executable_findings.append(f)

    if action_lines:
        lines.append("\n*ACTIONS*  —  ✅ executes all  ·  ❌ skips all")
        lines.extend(action_lines)

    # ── REVIEW ONLY block ─────────────────────────────────────────────────────
    review_lines = []
    for f in review_findings:
        label = "Junk leads" if f.get("junk_leads") else f.get("action", "review").title()
        asana = f.get("asana_url", "")
        asana_part = f"  —  {asana}" if asana else ""
        review_lines.append(f"⚡  {label}: `{f.get('campaign', '?')}`{asana_part}")

    if review_lines:
        lines.append("\n*REVIEW ONLY*  (Asana tasks created)")
        lines.extend(review_lines)

    full_text = "\n".join(lines)

    if is_quiet():
        quiet_log("nightly-approvals-digest", SLACK_CHANNEL_APPROVAL, full_text)
        return None

    try:
        response = post_as_role(
            "performance_audit", SLACK_CHANNEL_APPROVAL, full_text
        ) or {}
        ts = response.get("ts", "")
        if not ts:
            return None
        for emoji in ("white_check_mark", "x"):
            try:
                client.reactions_add(channel=SLACK_CHANNEL_APPROVAL, name=emoji, timestamp=ts)
            except SlackApiError:
                pass
        save_pending_approval(ts, {
            "action":   "batch_scale_pause",
            "findings": [
                {
                    "action":      f.get("action"),
                    "channel":     f.get("channel"),
                    "campaign":    f.get("campaign"),
                    "campaign_id": f.get("campaign_id", ""),
                    "new_budget":  f.get("new_budget"),
                }
                for f in executable_findings
            ],
        })
        log_activity_async(
            role="daily_digest",
            action="posted_approvals_digest",
            status="success",
            details={
                "scale":  len(scale_findings),
                "pause":  len(pause_findings),
                "review": len(review_findings),
                "ts":     ts,
                "format": "minimal_v2",
            },
        )
        return ts
    except SlackApiError as e:
        print(f"[slack] post_nightly_approvals_digest failed: {e}")
        return None
```

- [ ] **Step 3: Verify the existing alias still works**

Check that `post_scale_pause_digest` (around line 259) still calls `post_nightly_approvals_digest` — it passes `[]` for review_findings and omits channel_summary, which is fine since channel_summary defaults to None.

Run: `grep -A2 "def post_scale_pause_digest" notifications/slack.py`

Expected:
```
def post_scale_pause_digest(scale_findings: list, pause_findings: list) -> str | None:
    return post_nightly_approvals_digest(scale_findings, pause_findings, [])
```

No change needed.

- [ ] **Step 4: Syntax check**

Run: `railway run python -c "from notifications.slack import post_nightly_approvals_digest; print('OK')"`

Expected: `OK`

---

## Task 2 — Update the caller to pass channel_summary

**Files:**
- Modify: `analysers/campaign_health_tasks.py` (around line 700–720)

- [ ] **Step 1: Find the `_send_nightly_digest` function**

Run: `grep -n "_send_nightly_digest\|post_nightly_approvals_digest" analysers/campaign_health_tasks.py`

Note the line numbers for the function definition and the call site.

- [ ] **Step 2: Add channel_summary fetch above the call site**

Find the block that calls `post_nightly_approvals_digest(scale_findings, pause_findings, review_findings)` and replace it with:

```python
        # Fetch yesterday's channel summary (spend · leads · CPQL per channel)
        channel_summary = []
        try:
            from collectors.bq_writer import get_client as _bq
            from datetime import date as _d, timedelta as _td
            _bq_client = _bq()
            _P = os.environ.get("BQ_PROJECT_ID", "angular-axle-492812-q4")
            _D = os.environ.get("BQ_DATASET", "qoyod_marketing")
            _yesterday = (_d.today() - _td(days=1)).isoformat()
            _sql = f"""
                SELECT
                  channel,
                  SUM(spend)          AS spend,
                  SUM(leads_total)    AS leads,
                  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)) AS cpql
                FROM `{_P}.{_D}.paid_channel_daily`
                WHERE date = '{_yesterday}'
                  AND spend > 0
                GROUP BY channel
                ORDER BY spend DESC
            """
            for row in _bq_client.query(_sql).result():
                channel_summary.append({
                    "channel": row.channel,
                    "spend":   float(row.spend or 0),
                    "leads":   int(row.leads or 0),
                    "cpql":    float(row.cpql) if row.cpql else None,
                })
        except Exception as _e:
            print(f"[health-tasks] channel_summary fetch failed (non-fatal): {_e}")
            channel_summary = []

        from notifications.slack import post_nightly_approvals_digest
        ts = post_nightly_approvals_digest(
            scale_findings,
            pause_findings,
            review_findings,
            channel_summary=channel_summary,
        )
```

- [ ] **Step 3: Confirm `os` is imported at the top of campaign_health_tasks.py**

Run: `head -20 analysers/campaign_health_tasks.py | grep "^import os"`

If not present, add `import os` to the imports at the top of the file.

- [ ] **Step 4: Syntax check**

Run: `railway run python -c "from analysers.campaign_health_tasks import _send_nightly_digest; print('OK')" 2>&1 | tail -3`

Expected: `OK` (or the function is private and raises ImportError — in that case, run:)
```bash
railway run python -c "import analysers.campaign_health_tasks; print('OK')"
```

Expected: `OK`

---

## Task 3 — Manual smoke test

- [ ] **Step 1: Run a dry-run digest with test data**

```bash
railway run python -c "
from notifications.slack import post_nightly_approvals_digest
from notifications.quiet import set_quiet
set_quiet(True)   # writes to console, does not post to Slack

ts = post_nightly_approvals_digest(
    scale_findings=[{
        'campaign': 'Meta_LeadGen_AR_Invoice_Interests',
        'channel': 'meta',
        'cpql': 32.0,
        'avg_spend': 210.0,
        'new_budget': 252.0,
        'action': 'scale',
    }],
    pause_findings=[{
        'campaign': 'Snap_Bookkeeping_AR_Lookalike',
        'channel': 'snapchat',
        'cpql': 94.0,
        'qual_rate': 28.0,
        'action': 'pause',
    }],
    review_findings=[{
        'campaign': 'Google_Search_AR_Invoice_Broad',
        'action': 'optimize',
        'asana_url': 'https://app.asana.com/0/123/456',
    }],
    channel_summary=[
        {'channel': 'meta',     'spend': 420.0, 'leads': 12, 'cpql': 35.0},
        {'channel': 'google',   'spend': 180.0, 'leads': 4,  'cpql': 45.0},
        {'channel': 'snapchat', 'spend': 90.0,  'leads': 1,  'cpql': 90.0},
    ],
)
print('ts =', ts)
"
```

Expected output includes:
```
Nexa · Jun ...  |  https://...

PERFORMANCE
Meta        $420  ·  12 leads  ·  $35 CPQL   ✅
Google      $180  ·  4 leads  ·  $45 CPQL   ⚠️
Snapchat    $90  ·  1 leads  ·  $90 CPQL   ⚠️

ACTIONS  —  ✅ executes all  ·  ❌ skips all
↗  `Meta_LeadGen_AR_Invoice_Interests`   +25% budget  ($210 → $252/day)
⏸  `Snap_Bookkeeping_AR_Lookalike`   pause   ($94 CPQL · 14d)

REVIEW ONLY  (Asana tasks created)
⚡  Optimize: `Google_Search_AR_Invoice_Broad`  —  https://app.asana.com/0/123/456
ts = None
```

- [ ] **Step 2: Verify no ACTIONS block when no executable findings**

```bash
railway run python -c "
from notifications.slack import post_nightly_approvals_digest
from notifications.quiet import set_quiet
set_quiet(True)
post_nightly_approvals_digest(
    scale_findings=[],
    pause_findings=[],
    review_findings=[{'campaign': 'X', 'action': 'optimize', 'asana_url': ''}],
    channel_summary=[{'channel': 'meta', 'spend': 100, 'leads': 3, 'cpql': 33}],
)
"
```

Expected: output has PERFORMANCE and REVIEW ONLY blocks. No ACTIONS block.

- [ ] **Step 3: Verify graceful degradation when channel_summary is None**

```bash
railway run python -c "
from notifications.slack import post_nightly_approvals_digest
from notifications.quiet import set_quiet
set_quiet(True)
post_nightly_approvals_digest(
    scale_findings=[{'campaign': 'Test', 'channel': 'meta', 'cpql': 30, 'avg_spend': 100, 'new_budget': 125, 'action': 'scale'}],
    pause_findings=[],
    review_findings=[],
)
"
```

Expected: output has ACTIONS block but no PERFORMANCE block. No crash.

---

## Task 4 — Commit and push

- [ ] **Step 1: Stage and commit both files**

```bash
git add notifications/slack.py analysers/campaign_health_tasks.py
git commit -m "feat(slack): minimal digest format — spend·leads·CPQL per channel, single ✅/❌"
```

- [ ] **Step 2: Push to origin/main**

```bash
git push origin main
```

Expected: Railway auto-deploys within ~2 minutes.

- [ ] **Step 3: Verify deploy on Railway**

Run: `railway logs --tail 50 | grep "digest\|slack"`

Expected: No errors related to the digest function on the next scheduled run.

- [ ] **Step 4: Update open tasks**

In `memory/09_open_tasks.md`, mark the Slack format item as done:
```
- [x] Slack digest: implement minimal format  ← mark complete, add date 2026-06-11
```
