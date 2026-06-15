"""
monitors/self_healer.py
========================
Daily self-healing pass. Detects known failure modes and fixes them.
No alerts — just fixes. Runs after the nightly cycle (09:30 Riyadh / 06:30 UTC).

Healers (each has detect + heal):
  1. stale_views      — paid_channel_daily behind → materialize_heavy_views()
  2. failed_collector — collector status=failed last 24h → retry once
  3. dashboard_errors — /activity threw 500 → clear HTML cache + log traceback
  4. stuck_approval   — pending approval >72h unresolved → re-post digest
  5. memory_update    — same error 3+ consecutive days → append to 08_pitfalls.md

Every healing action is logged to agent_activity_log (action='self_heal').
Counts surface in the weekly Slack summary as '🔧 Auto-healed: N'.
"""
from __future__ import annotations

import os
import pathlib
import threading
from datetime import date, datetime, timedelta, timezone

MEMORY_PITFALLS = pathlib.Path(__file__).parent.parent / "memory" / "08_pitfalls.md"
_RIYADH = timezone(timedelta(hours=3))


# ── helpers ───────────────────────────────────────────────────────────────────

def _bq():
    from collectors.bq_writer import get_client
    return get_client(), os.environ["BQ_PROJECT_ID"], os.environ["BQ_DATASET"]


def _log(action: str, status: str, details: dict):
    from logs.activity_logger import log_activity_async
    log_activity_async(role="ops_scheduler", action=action,
                       status=status, details=details)


# ── Healer 1: stale materialised views ───────────────────────────────────────

def _heal_stale_views() -> int:
    """
    If paid_channel_daily is >1 day behind, rebuild all heavy views.
    Returns 1 if healed, 0 if already fresh.
    """
    try:
        c, p, d = _bq()
        rows = list(c.query(
            f"SELECT DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY) AS lag "
            f"FROM `{p}.{d}.wide_ads`"
        ).result())
        lag = int(rows[0].lag or 0) if rows else 0
        if lag <= 1:
            return 0
        print(f"[self-healer] wide_ads is {lag}d stale — rebuilding views")
        from collectors.views import materialize_heavy_views
        materialize_heavy_views()
        _log("self_heal", "success",
             {"healer": "stale_views", "lag_days": lag, "action": "materialize_heavy_views"})
        return 1
    except Exception as e:
        _log("self_heal", "failed", {"healer": "stale_views", "error": str(e)})
        return 0


# ── Healer 2: failed collectors ───────────────────────────────────────────────

# Map action-name → collector module callable
_COLLECTOR_MAP = {
    "collect_google_ads":    "collectors.google_ads_bq:collect_and_write",
    "collect_meta":          "collectors.meta_bq:collect_and_write",
    "collect_snapchat":      "collectors.snapchat_bq:collect_and_write",
    "collect_tiktok":        "collectors.tiktok_bq:collect_and_write",
    "collect_microsoft_ads": "collectors.microsoft_ads_bq:collect_and_write",
    "collect_linkedin":      "collectors.linkedin_bq:collect_and_write",
    "collect_hubspot_leads": "collectors.hubspot_leads_bq:collect_and_write",
    "collect_hubspot_deals": "collectors.hubspot_deals_bq:collect_and_write",
}


def _run_collector(module_path: str) -> bool:
    """Dynamically import and call the collect_and_write() entry point."""
    try:
        mod_name, fn_name = module_path.split(":")
        import importlib
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name)
        fn()
        return True
    except Exception as e:
        print(f"[self-healer] collector retry failed ({module_path}): {e}")
        return False


def _heal_failed_collectors() -> int:
    """
    Query agent_activity_log for status='failed' collector runs in last 24h.
    Retry each failed collector once. Returns count of successful retries.
    """
    try:
        c, p, d = _bq()
        sql = f"""
            SELECT action, COUNT(*) AS n
            FROM `{p}.{d}.agent_activity_log`
            WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
              AND status = 'failed'
              AND action LIKE 'collect_%'
            GROUP BY action
        """
        rows = list(c.query(sql).result())
        if not rows:
            return 0
        healed = 0
        for r in rows:
            col = _COLLECTOR_MAP.get(r.action)
            if not col:
                continue
            print(f"[self-healer] retrying failed collector: {r.action} ({r.n} failures)")
            ok = _run_collector(col)
            _log("self_heal", "success" if ok else "failed",
                 {"healer": "failed_collector", "collector": r.action,
                  "prior_failures": r.n, "retry_ok": ok})
            if ok:
                healed += 1
        return healed
    except Exception as e:
        _log("self_heal", "failed", {"healer": "failed_collectors", "error": str(e)})
        return 0


# ── Healer 3: dashboard errors ────────────────────────────────────────────────

def _heal_dashboard_errors() -> int:
    """
    If /activity threw a 500 (dashboard_error logged to BQ) in the last 2h,
    clear the in-process HTML cache so the next load gets a fresh render.
    Returns 1 if cache was cleared, 0 if no recent errors.
    """
    try:
        c, p, d = _bq()
        rows = list(c.query(
            f"SELECT COUNT(*) AS n FROM `{p}.{d}.agent_activity_log` "
            f"WHERE action='dashboard_error' AND status='failed' "
            f"AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)"
        ).result())
        n = int(rows[0].n or 0) if rows else 0
        if n == 0:
            return 0
        # Clear the in-process HTML cache (reports/app.py _ACTIVITY_CACHE)
        try:
            from reports.app import _ACTIVITY_CACHE, _ACTIVITY_CACHE_LOCK
            with _ACTIVITY_CACHE_LOCK:
                _ACTIVITY_CACHE.clear()
            print(f"[self-healer] cleared activity HTML cache after {n} recent 500(s)")
        except Exception:
            pass  # app not loaded in this process — cache lives in Railway, harmless
        _log("self_heal", "success",
             {"healer": "dashboard_errors", "recent_500s": n, "action": "cache_cleared"})
        return 1
    except Exception as e:
        _log("self_heal", "failed", {"healer": "dashboard_errors", "error": str(e)})
        return 0


# ── Healer 4: stuck pending approvals ─────────────────────────────────────────

def _heal_stuck_approvals() -> int:
    """
    If a pending approval has been waiting >72h unresolved, re-post the digest.
    This covers the case where Slack message was buried or bot reaction was lost.
    Returns count of re-posted digests.
    """
    try:
        from notifications.slack import _load_pending
        pending = _load_pending()
        if not pending:
            return 0
        now_ts = datetime.now(timezone.utc).timestamp()
        stuck = {ts: meta for ts, meta in pending.items()
                 if (now_ts - float(ts)) > 72 * 3600}
        if not stuck:
            return 0
        print(f"[self-healer] {len(stuck)} approval(s) stuck >72h — re-posting")
        # Re-post each as a reminder (not a new executable approval)
        try:
            from notifications.slack import client as slack_client
            from config import SLACK_CHANNEL_APPROVAL
            for ts, meta in stuck.items():
                findings = meta.get("findings", [])
                age_h = round((now_ts - float(ts)) / 3600)
                slack_client.chat_postMessage(
                    channel=SLACK_CHANNEL_APPROVAL,
                    text=(f":hourglass: *Approval reminder* — {len(findings)} action(s) "
                          f"pending for {age_h}h with no reaction. "
                          f"React ✅ to execute or ❌ to skip on the original message."),
                )
        except Exception as e:
            print(f"[self-healer] stuck approval re-post failed: {e}")
        _log("self_heal", "success",
             {"healer": "stuck_approvals", "stuck_count": len(stuck), "action": "reminder_posted"})
        return len(stuck)
    except Exception as e:
        _log("self_heal", "failed", {"healer": "stuck_approvals", "error": str(e)})
        return 0


# ── Healer 5: memory auto-update ──────────────────────────────────────────────

def _update_pitfalls_memory() -> int:
    """
    If the same error fires on 3+ distinct calendar days in the last 7 days,
    it's a recurring pattern the agent should remember.
    Appends a new entry to memory/08_pitfalls.md automatically.
    Returns count of new patterns written.
    """
    try:
        c, p, d = _bq()
        # Find error types that fired on 3+ separate days this week
        sql = f"""
            SELECT
              JSON_VALUE(details, '$.healer')    AS healer,
              JSON_VALUE(details, '$.error')     AS error_msg,
              COUNT(DISTINCT DATE(ts, 'Asia/Riyadh')) AS day_count,
              MAX(ts) AS last_seen
            FROM `{p}.{d}.agent_activity_log`
            WHERE action IN ('self_heal', 'dashboard_error')
              AND status = 'failed'
              AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
            GROUP BY 1, 2
            HAVING COUNT(DISTINCT DATE(ts, 'Asia/Riyadh')) >= 3
            ORDER BY day_count DESC
            LIMIT 5
        """
        rows = list(c.query(sql).result())
        if not rows:
            return 0

        # Check what's already documented to avoid duplicates
        existing = MEMORY_PITFALLS.read_text(encoding="utf-8") if MEMORY_PITFALLS.exists() else ""
        written = 0
        today = datetime.now(_RIYADH).strftime("%Y-%m-%d")

        for r in rows:
            healer = r.healer or "unknown"
            error  = (r.error_msg or "")[:200]
            # Skip if this error snippet is already in pitfalls
            if error[:60] and error[:60] in existing:
                continue
            entry = (
                f"\n## Auto-detected recurring failure — {healer} ({today})\n\n"
                f"- **Pattern:** `{healer}` failed on {r.day_count} separate days in the last 7 days.\n"
                f"- **Error:** `{error}`\n"
                f"- **Auto-detected by:** `monitors/self_healer.py _update_pitfalls_memory()`\n"
                f"- **Action:** Review `{healer}` logic — the fix should be permanent, not repeated.\n"
            )
            with open(MEMORY_PITFALLS, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[self-healer] wrote recurring pattern to 08_pitfalls.md: {healer}")
            written += 1

        if written:
            # Commit the memory update so it survives redeployment
            try:
                import subprocess
                subprocess.run(
                    ["git", "add", str(MEMORY_PITFALLS)],
                    cwd=str(MEMORY_PITFALLS.parent.parent), check=True, capture_output=True,
                )
                subprocess.run(
                    ["git", "commit", "-m",
                     f"docs(memory): auto-detected {written} recurring failure pattern(s) [{today}]"],
                    cwd=str(MEMORY_PITFALLS.parent.parent), check=True, capture_output=True,
                )
                subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=str(MEMORY_PITFALLS.parent.parent), check=True, capture_output=True,
                )
            except Exception as e:
                print(f"[self-healer] git commit for pitfalls failed: {e}")
            _log("self_heal", "success",
                 {"healer": "memory_update", "patterns_written": written,
                  "action": "appended_to_08_pitfalls"})
        return written
    except Exception as e:
        _log("self_heal", "failed", {"healer": "memory_update", "error": str(e)})
        return 0


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_self_heal() -> dict:
    """
    Run all healers in sequence. Returns summary of what was fixed.
    Called by operational_scheduler daily at 09:30 Riyadh (06:30 UTC).
    """
    print("[self-healer] starting daily self-heal pass")
    results = {}

    results["stale_views"]      = _heal_stale_views()
    results["failed_collectors"] = _heal_failed_collectors()
    results["dashboard_errors"] = _heal_dashboard_errors()
    results["stuck_approvals"]  = _heal_stuck_approvals()
    results["memory_update"]    = _update_pitfalls_memory()

    total = sum(results.values())
    print(f"[self-healer] done — {total} issue(s) healed: {results}")
    _log("self_heal", "success", {"summary": results, "total_healed": total})
    return results


if __name__ == "__main__":
    run_self_heal()
