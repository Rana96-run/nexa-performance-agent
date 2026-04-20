"""
Scheduler — runs the performance agent on multiple cadences.

Cadences (all in Riyadh time, converted to UTC for APScheduler):
  - Daily     08:00 Riyadh (05:00 UTC)
  - Weekly    Mon 08:00 Riyadh
  - Monthly   1st 08:00 Riyadh
  - Quarterly Jan/Apr/Jul/Oct 1st 08:00 Riyadh
  - On-demand invoked via CLI: python main.py on_demand
"""
import schedule
import time
from datetime import date
from main import run_cadence


def _daily():   run_cadence("daily")
def _weekly():  run_cadence("weekly")


def _monthly():
    if date.today().day == 1:
        run_cadence("monthly")


def _quarterly():
    today = date.today()
    if today.day == 1 and today.month in (1, 4, 7, 10):
        run_cadence("quarterly")


def run():
    schedule.every().day.at("05:00").do(_daily)
    schedule.every().monday.at("05:00").do(_weekly)
    schedule.every().day.at("05:10").do(_monthly)
    schedule.every().day.at("05:20").do(_quarterly)

    print("Scheduler running.")
    print("  daily     05:00 UTC (08:00 Riyadh)")
    print("  weekly    Mon 05:00 UTC")
    print("  monthly   1st 05:10 UTC")
    print("  quarterly 1st of Jan/Apr/Jul/Oct 05:20 UTC")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run()
