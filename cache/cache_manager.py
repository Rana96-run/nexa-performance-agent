"""
Cache & deduplication layer for the Qoyod Performance Agent.

Solves three problems:
  1. API data cache  — don't re-hit Google Ads / Meta / HubSpot for the same
                       date window; saves API quota and response time.
  2. Task ledger     — fingerprint every Asana task before creating it; skip if
                       one with the same fingerprint was created today.
  3. Analysis ledger — skip a full Claude call if this cadence already ran for
                       today (e.g. cron fires twice due to a restart).

Storage: a single .cache/ directory of JSON files in the project root.
         Nothing sensitive is stored here — add .cache/ to .gitignore.

Usage:
    from cache.cache_manager import get_or_fetch, can_run_analysis, mark_analysis_done
    from cache.cache_manager import task_is_new, record_task

    # Data caching
    data = get_or_fetch("google_ads_daily", fetcher_fn, ttl_hours=22)

    # Analysis guard
    if not can_run_analysis("daily"):
        sys.exit("Already ran today — skipping.")
    ... run analysis ...
    mark_analysis_done("daily")

    # Task deduplication
    if task_is_new(title, project_key):
        gid = create_task(...)
        record_task(title, project_key, gid)
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
CACHE_DIR = _ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

_DATA_CACHE  = CACHE_DIR / "data_cache.json"
_TASK_LEDGER = CACHE_DIR / "task_ledger.json"
_RUN_LEDGER  = CACHE_DIR / "run_ledger.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now_utc().strftime("%Y-%m-%d")


def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _fingerprint(*parts: str) -> str:
    """Stable SHA-256 fingerprint from one or more strings."""
    combined = "|".join(str(p) for p in parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 1. API Data Cache
# ---------------------------------------------------------------------------

def get_or_fetch(key: str, fetcher, ttl_hours: int = 22):
    """
    Return cached value for `key` if still fresh; otherwise call `fetcher()`,
    cache the result, and return it.

    Args:
        key:       Unique identifier (e.g. "google_ads_daily_4d").
        fetcher:   Zero-argument callable that returns the fresh data.
        ttl_hours: How long the cached value stays valid (default 22 h so a
                   daily cron that fires at 08:00 always uses today's data).

    Returns:
        The data (from cache or freshly fetched).
    """
    store = _load(_DATA_CACHE)
    entry = store.get(key)

    if entry:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        age_hours = (_now_utc() - fetched_at).total_seconds() / 3600
        if age_hours < ttl_hours:
            print(f"[cache] HIT  {key!r}  (age {age_hours:.1f}h / ttl {ttl_hours}h)")
            return entry["data"]
        print(f"[cache] STALE {key!r}  (age {age_hours:.1f}h)")
    else:
        print(f"[cache] MISS {key!r}")

    data = fetcher()
    store[key] = {"fetched_at": _now_utc().isoformat(), "data": data}
    _save(_DATA_CACHE, store)
    print(f"[cache] SAVED {key!r}")
    return data


def bust_cache(key: str):
    """Force-expire a cached entry so the next call re-fetches."""
    store = _load(_DATA_CACHE)
    if key in store:
        del store[key]
        _save(_DATA_CACHE, store)
        print(f"[cache] BUSTED {key!r}")


def bust_all():
    """Wipe the entire data cache (use on demand / debug runs)."""
    _save(_DATA_CACHE, {})
    print("[cache] All data cache cleared.")


# ---------------------------------------------------------------------------
# 2. Task Deduplication Ledger
# ---------------------------------------------------------------------------

def task_is_new(title: str, project_key: str) -> bool:
    """
    Return True if no task with this title+project was created today.
    False means a duplicate would be created — skip the API call.
    """
    fp   = _fingerprint(title, project_key)
    date = _today()
    ledger = _load(_TASK_LEDGER)
    day_entries = ledger.get(date, {})
    if fp in day_entries:
        print(f"[cache] TASK DUP  {title[:60]!r}  project={project_key}")
        return False
    return True


def record_task(title: str, project_key: str, gid: str):
    """Record that a task was created so future calls skip it."""
    fp     = _fingerprint(title, project_key)
    date   = _today()
    ledger = _load(_TASK_LEDGER)
    ledger.setdefault(date, {})[fp] = {"title": title[:80], "project": project_key, "gid": gid}
    _save(_TASK_LEDGER, ledger)

    # Trim entries older than 7 days to keep the file small
    cutoff = (_now_utc() - timedelta(days=7)).strftime("%Y-%m-%d")
    for old_date in [d for d in list(ledger) if d < cutoff]:
        del ledger[old_date]
    _save(_TASK_LEDGER, ledger)


def get_task_gid(title: str, project_key: str) -> str | None:
    """Return the GID of an already-created task, or None if not found."""
    fp   = _fingerprint(title, project_key)
    date = _today()
    return _load(_TASK_LEDGER).get(date, {}).get(fp, {}).get("gid")


# ---------------------------------------------------------------------------
# 3. Analysis Run Ledger
# ---------------------------------------------------------------------------

def can_run_analysis(cadence: str) -> bool:
    """
    True if this cadence has NOT been completed today.
    Prevents double-runs when the scheduler restarts mid-day.
    """
    ledger = _load(_RUN_LEDGER)
    entry  = ledger.get(_today(), {}).get(cadence)
    if entry:
        print(f"[cache] ANALYSIS already ran today: cadence={cadence}  completed={entry['completed_at']}")
        return False
    return True


def mark_analysis_done(cadence: str):
    """Record that the analysis for this cadence completed successfully today."""
    ledger = _load(_RUN_LEDGER)
    ledger.setdefault(_today(), {})[cadence] = {
        "completed_at": _now_utc().isoformat(),
    }
    # Trim to last 30 days
    cutoff = (_now_utc() - timedelta(days=30)).strftime("%Y-%m-%d")
    for old in [d for d in list(ledger) if d < cutoff]:
        del ledger[old]
    _save(_RUN_LEDGER, ledger)
    print(f"[cache] ANALYSIS marked done: cadence={cadence}")


def reset_analysis(cadence: str | None = None):
    """
    Force-reset the run ledger so the analysis re-runs.
    Pass a cadence to reset just that one, or None to reset all of today.
    """
    ledger = _load(_RUN_LEDGER)
    today  = _today()
    if cadence:
        ledger.get(today, {}).pop(cadence, None)
        print(f"[cache] ANALYSIS reset: cadence={cadence}")
    else:
        ledger.pop(today, None)
        print("[cache] ANALYSIS reset: all cadences for today")
    _save(_RUN_LEDGER, ledger)


# ---------------------------------------------------------------------------
# 4. Cache Status (for debugging)
# ---------------------------------------------------------------------------

def cache_status() -> dict:
    """Return a human-readable summary of all cache state."""
    data   = _load(_DATA_CACHE)
    tasks  = _load(_TASK_LEDGER)
    runs   = _load(_RUN_LEDGER)
    today  = _today()
    now    = _now_utc()

    data_summary = {}
    for key, entry in data.items():
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        age_h = (now - fetched_at).total_seconds() / 3600
        data_summary[key] = f"age {age_h:.1f}h  rows={len(entry['data']) if isinstance(entry['data'], list) else '—'}"

    return {
        "today": today,
        "data_cache": data_summary,
        "tasks_today": len(tasks.get(today, {})),
        "analyses_today": runs.get(today, {}),
    }


# ---------------------------------------------------------------------------
# CLI: python -m cache.cache_manager status|bust|reset
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        import pprint; pprint.pprint(cache_status())
    elif cmd == "bust":
        bust_all()
    elif cmd == "reset":
        cadence = sys.argv[2] if len(sys.argv) > 2 else None
        reset_analysis(cadence)
    else:
        print("Usage: python -m cache.cache_manager [status|bust|reset [cadence]]")
