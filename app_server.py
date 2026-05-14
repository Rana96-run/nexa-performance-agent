"""
app_server.py
=============
Single process entry point for Railway deployment.

Runs Flask (reports + webhooks) and all background threads in one dyno:
  Thread 1 — operational_scheduler  (agent cadences: daily/weekly/monthly)
  Thread 2 — reporting_scheduler    (BQ data refresh — runs inline from
                                     operational_scheduler at 08:00 + 20:00 Riyadh)
  Thread 3 — slack_listener         (responds to @Nexa mentions)

Flask is served by gunicorn (via this module's `application` callable) when
Railway binds the PORT env var.  The background threads are started once via
@app.before_request guard so they only start in the master worker.

Usage (Railway):
    Start Command: python app_server.py

Usage (local):
    python app_server.py
"""
from __future__ import annotations

import os
import threading
import time
import traceback

from scripts import bootstrap  # noqa — materializes BQ creds from env

from logs.logger import setup_global_logging
setup_global_logging("app_server")

from reports.app import app  # Flask app with all blueprints registered

# ─── Background thread runner ─────────────────────────────────────────────────

_threads_started = False
_lock = threading.Lock()


def _run_forever(name: str, target_fn, restart_delay: int = 30):
    """Run target_fn() in a loop, restarting on any exception."""
    while True:
        try:
            print(f"[app_server] Starting thread: {name}")
            target_fn()
        except Exception:
            print(f"[app_server] Thread {name} crashed — restarting in {restart_delay}s")
            traceback.print_exc()
        time.sleep(restart_delay)


def _start_background_threads():
    global _threads_started
    with _lock:
        if _threads_started:
            return
        _threads_started = True

    def _op():
        from operational_scheduler import run
        run()

    def _slack():
        from slack_listener import run
        run()

    # Note: reporting-scheduler thread removed. BQ refresh runs inline from
    # the operational_scheduler at:
    #   - 05:00 UTC / 08:00 Riyadh — via _nightly() (full nightly + BQ refresh)
    #   - 17:00 UTC / 20:00 Riyadh — second BQ refresh only (no nightly cadence)
    # Updated 2026-05-15 from once-a-day to twice-a-day to halve attribution lag.
    for name, fn, delay in [
        ("operational-scheduler", _op, 30),
        ("slack-listener", _slack, 15),
    ]:
        t = threading.Thread(
            target=_run_forever,
            args=(name, fn, delay),
            name=name,
            daemon=True,
        )
        t.start()
        print(f"[app_server] Thread started: {name}")


# Start threads when the app boots (works with gunicorn --preload or plain python)
_start_background_threads()


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[app_server] Flask listening on 0.0.0.0:{port}")
    # Use threaded=True so Flask can handle requests while workers run
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
