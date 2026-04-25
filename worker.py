"""
worker.py
=========
Single entry point for the Railway worker dyno.
Runs three long-lived processes in parallel threads:

  Thread 1 — operational_scheduler  (agent cadences: daily/weekly/monthly)
  Thread 2 — reporting_scheduler    (BQ data refresh every 6h)
  Thread 3 — slack_listener         (responds to @Nexa mentions)

Each thread is wrapped in a restart loop so one crash doesn't kill the others.
Logs go to stdout (Railway captures them automatically).
"""
import threading
import time
import traceback
from logs.logger import setup_global_logging

setup_global_logging("worker")


def _run_forever(name: str, target_fn, restart_delay: int = 30):
    """Run target_fn() in a loop, restarting on any exception."""
    while True:
        try:
            print(f"[worker] Starting {name}...")
            target_fn()
        except Exception:
            print(f"[worker] {name} crashed — restarting in {restart_delay}s")
            traceback.print_exc()
        time.sleep(restart_delay)


def _start_operational():
    from operational_scheduler import run
    run()


def _start_reporting():
    from reporting_scheduler import run_loop
    run_loop()


def _start_slack():
    from slack_listener import run
    run()


if __name__ == "__main__":
    threads = [
        threading.Thread(
            target=_run_forever,
            args=("operational-scheduler", _start_operational),
            name="operational",
            daemon=True,
        ),
        threading.Thread(
            target=_run_forever,
            args=("reporting-scheduler", _start_reporting, 60),
            name="reporting",
            daemon=True,
        ),
        threading.Thread(
            target=_run_forever,
            args=("slack-listener", _start_slack, 15),
            name="slack",
            daemon=True,
        ),
    ]

    for t in threads:
        t.start()
        print(f"[worker] Thread started: {t.name}")

    print("[worker] All threads running. Waiting...")
    try:
        while True:
            time.sleep(60)
            alive = [t.name for t in threads if t.is_alive()]
            print(f"[worker] Alive threads: {alive}")
    except KeyboardInterrupt:
        print("[worker] Shutting down.")
