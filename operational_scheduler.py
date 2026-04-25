"""
Operational scheduler — fires the performance agent at the right cadences.

All times in Riyadh (UTC+3). Heavy work at 3 AM so tasks and summaries
are ready when the team wakes up.

  03:00 Riyadh = 00:00 UTC  → daily (always)
  Mon   03:00               → + weekly analysis
  1st   03:00               → + monthly analysis
  Jan/Apr/Jul/Oct 1st 03:00 → + quarterly analysis
"""
import schedule
import time
import traceback
from datetime import date
from logs.logger import setup_global_logging

setup_global_logging("operational-scheduler")  # captures every print() into logs/
from main import run_cadence
from notifications.notify import send_heartbeat


def _run_with_heartbeat(cadence: str):
    """Run a cadence and emit a heartbeat on completion or failure."""
    t0 = time.time()
    try:
        run_cadence(cadence)
        send_heartbeat(f"agent-{cadence}", status="ok",
                       detail=f"{cadence} cadence completed",
                       duration_s=time.time() - t0)
    except Exception as e:
        traceback.print_exc()
        send_heartbeat(f"agent-{cadence}", status="failed",
                       detail=str(e)[:200],
                       duration_s=time.time() - t0)


def _nightly():
    """One combined nightly run — chains weekly/monthly/quarterly where applicable."""
    _run_with_heartbeat("daily")

    today = date.today()
    if today.weekday() == 0:                              # Monday → weekly
        _run_with_heartbeat("weekly")
    if today.day == 1:                                    # 1st → monthly
        _run_with_heartbeat("monthly")
    if today.day == 1 and today.month in (1, 4, 7, 10):  # Quarter start
        _run_with_heartbeat("quarterly")


def run():
    schedule.every().day.at("00:00").do(_nightly)   # 03:00 Riyadh = 00:00 UTC

    print("=" * 52)
    print("  Qoyod Operational Scheduler — LIVE")
    print("=" * 52)
    print("  Nightly  03:00 Riyadh (00:00 UTC)")
    print("  Weekly   added Mon nights")
    print("  Monthly  added on 1st of month")
    print("  Manual:  python main.py on_demand")
    print("=" * 52)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
