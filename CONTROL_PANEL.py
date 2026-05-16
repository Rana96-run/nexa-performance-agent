"""
Nexa — Qoyod Performance Agent | Control Panel

Run:  .venv\Scripts\python.exe CONTROL_PANEL.py

One place for everything. No separate terminal windows needed — this
script starts background processes and lets you trigger any action
from a numbered menu.
"""
import os
import sys
import subprocess
import time
from datetime import datetime

VENV_PY  = os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "python.exe")
BASE     = os.path.dirname(__file__)
LOGS_DIR = os.path.join(BASE, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Tee stdout/stderr into logs/nexa_YYYY-MM-DD.log so every print from this
# panel (and everything launched from it) lands in the rotating log file.
from logs.logger import setup_global_logging
setup_global_logging("control-panel")

# Colours (work on Windows 10+ terminal)
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"

_procs: dict[str, subprocess.Popen] = {}


def _run(label: str, script: str, *args):
    """Start a background process silently (no extra windows)."""
    cmd = [VENV_PY, os.path.join(BASE, script)] + list(args)
    p   = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NO_WINDOW,   # no popup windows
        stdout=open(os.path.join(BASE, "logs", f"{label}.log"), "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    _procs[label] = p
    return p


def _run_fg(script: str, *args):
    """Run a script in the foreground (blocks until done)."""
    cmd = [VENV_PY, os.path.join(BASE, script)] + list(args)
    subprocess.run(cmd)


def _status(label: str) -> str:
    p = _procs.get(label)
    if p is None:
        return f"{RED}● stopped{RESET}"
    if p.poll() is None:
        return f"{GREEN}● running  PID {p.pid}{RESET}"
    return f"{YELLOW}● exited ({p.returncode}){RESET}"


def header():
    os.system("cls" if os.name == "nt" else "clear")
    now = datetime.now().strftime("%A, %d %b %Y  %H:%M")
    print(f"{CYAN}{BOLD}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║          Nexa — Qoyod Performance Agent              ║")
    print(f"║  {now:<52}║")
    print("╚══════════════════════════════════════════════════════╝")
    print(RESET)


def show_menu():
    header()

    # Background process status
    print(f"{BOLD}  Background Processes{RESET}")
    print(f"  {DIM}─────────────────────────────────────────{RESET}")
    print(f"  [B1] BQ Data Refresh (24h)     {_status('bq')}")
    print(f"  [B2] Nightly Scheduler (03:00) {_status('scheduler')}")
    print(f"  [B3] Slack/@mention Listener   {_status('listener')}")
    print()

    # Manual triggers
    print(f"{BOLD}  Run Now{RESET}")
    print(f"  {DIM}─────────────────────────────────────────{RESET}")
    print(f"  {YELLOW}[1]{RESET}  Run daily analysis right now")
    print(f"  {YELLOW}[2]{RESET}  Run weekly analysis right now")
    print(f"  {YELLOW}[3]{RESET}  Run monthly analysis right now")
    print(f"  {YELLOW}[4]{RESET}  Force BQ data refresh right now (incremental)")
    print(f"  {YELLOW}[4B]{RESET} Full BQ backfill — ALL data year-to-date")
    print()

    # Data & reports
    print(f"{BOLD}  Data & Reports{RESET}")
    print(f"  {DIM}─────────────────────────────────────────{RESET}")
    print(f"  {YELLOW}[5]{RESET}  Show data cache status")
    print(f"  {YELLOW}[6]{RESET}  Clear data cache (force fresh pull)")
    print(f"  {YELLOW}[7]{RESET}  Refresh BigQuery views only (no data pull)")
    print(f"  {YELLOW}[L]{RESET}  View latest log file")
    print()

    # On-demand agent tasks
    print(f"{BOLD}  On-Demand Agent Tasks{RESET}")
    print(f"  {DIM}─────────────────────────────────────────{RESET}")
    print(f"  {YELLOW}[8]{RESET}  List all overdue Asana tasks")
    print(f"  {YELLOW}[9]{RESET}  Generate performance report")
    print(f"  {YELLOW}[10]{RESET} Generate campaign brief")
    print(f"  {YELLOW}[11]{RESET} Generate scaling strategy")
    print(f"  {YELLOW}[12]{RESET} Generate campaign setup plan")
    print(f"  {YELLOW}[13]{RESET} Post optimization tasks for ALL campaigns to Asana")
    print()

    # Setup / Auth
    print(f"{BOLD}  Setup & Auth{RESET}")
    print(f"  {DIM}─────────────────────────────────────────{RESET}")
    print(f"  {YELLOW}[MS]{RESET} Microsoft Ads — get refresh token (OAuth)")
    print(f"  {YELLOW}[TT]{RESET} TikTok — where to get access token (guide)")
    print(f"  {YELLOW}[H]{RESET}  Health check — verify all credentials")
    print()

    # System
    print(f"{BOLD}  System{RESET}")
    print(f"  {DIM}─────────────────────────────────────────{RESET}")
    print(f"  {YELLOW}[S]{RESET}  Start all background processes")
    print(f"  {YELLOW}[K]{RESET}  Stop all background processes")
    print(f"  {YELLOW}[R]{RESET}  Restart all background processes")
    print(f"  {YELLOW}[Q]{RESET}  Quit control panel")
    print()
    print(f"  {DIM}Notify: C0ARMQKK8GK  |  Approvals: C0AT1AP8TJ4  |  @Nexa in Slack or Asana{RESET}")
    print()


def run_health_check_inline():
    """Run health check and print results directly in the control panel."""
    sys.path.insert(0, BASE)
    from health import run_health_check
    run_health_check()


def start_all():
    print(f"\n{GREEN}Starting all background processes...{RESET}")
    _run("bq",        "reporting_scheduler.py")
    time.sleep(1)
    _run("scheduler", "operational_scheduler.py")
    time.sleep(1)
    _run("listener",  "slack_listener.py")
    print(f"{GREEN}All started.{RESET}")
    time.sleep(1.5)


def stop_all():
    print(f"\n{YELLOW}Stopping all background processes...{RESET}")
    for label, p in _procs.items():
        try:
            p.terminate()
            print(f"  Stopped: {label}")
        except Exception:
            pass
    _procs.clear()
    time.sleep(1)


def ask(prompt: str) -> str:
    print(f"\n{CYAN}{prompt}{RESET} ", end="")
    return input().strip()


def run_agent_inline(task: str):
    """Run a quick agent task via Claude API inline and print result."""
    from dotenv import load_dotenv
    load_dotenv()
    import anthropic, os
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("LLM disabled — ANTHROPIC_API_KEY not set.")
        return
    client = anthropic.Anthropic(api_key=key)

    from config import (
        CPL_WARNING, CPQL_WARNING, QUAL_RATE_TARGET, ROAS_TARGET,
        USD_SAR_PEG,
    )
    SYSTEM = f"""You are Nexa — Qoyod's AI Performance Marketing Agent.
    Saudi SaaS company. Paid media: Google Ads, Meta, Snapchat, LinkedIn, Microsoft Ads, TikTok.
    Currency USD (all spend values normalized to USD; SAR pegged at {USD_SAR_PEG}).
    CPL target <{CPL_WARNING} USD, CPQL target <{CPQL_WARNING} USD, Qual rate >{int(QUAL_RATE_TARGET*100)}%, ROAS >{ROAS_TARGET}.
    You create campaign setups, briefs, and scaling strategies.
    Be specific, structured, and data-driven. Plain text formatting."""

    print(f"\n{DIM}Thinking...{RESET}")
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": task}],
    )
    result = msg.content[0].text
    print(f"\n{CYAN}{'─'*54}{RESET}")
    print(result)
    print(f"{CYAN}{'─'*54}{RESET}")


def optimize_all_campaigns():
    """Tell the agent to generate optimization tasks for ALL campaigns."""
    from dotenv import load_dotenv
    load_dotenv()

    print(f"\n{DIM}Fetching campaign data and generating optimization tasks...{RESET}")
    print(f"{DIM}This may take 1-2 minutes.{RESET}\n")

    # Import live data collectors
    try:
        from collectors.google_ads import get_campaign_performance
        from collectors.meta import get_ad_performance
        import json

        gads = get_campaign_performance(days=180)  # 6-month window for paused check
        meta = get_ad_performance(days=180)

        prompt = f"""
Today is {datetime.now().strftime('%Y-%m-%d')}.

Below is 6-month campaign performance data for all channels.

TASK: Generate Asana optimization tasks for EVERY campaign — both active and
paused. For paused campaigns that had CPL < 30 or CPQL < 80 at any point in
the last 6 months, propose re-activation or creative refresh tasks.

For each campaign output a JSON array of tasks:
{{
  "title": "[Channel] Campaign Name — Optimization action",
  "description": "Full description with data, rationale, and specific steps",
  "project_key": "optimization",
  "task_type": "Recommendation"
}}

Google Ads data (last 6 months):
{json.dumps(gads[:30], indent=2, default=str)}

Meta data (last 6 months):
{json.dumps(meta[:30], indent=2, default=str)}

Output ONLY the JSON array. No preamble.
"""
        from dotenv import load_dotenv
        import anthropic, os, re
        load_dotenv()
        _key = os.getenv("ANTHROPIC_API_KEY")
        if not _key:
            print("LLM disabled — ANTHROPIC_API_KEY not set.")
            return
        client = anthropic.Anthropic(api_key=_key)
        msg    = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text

        # Extract JSON
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            print(f"{RED}Could not extract task list from agent response.{RESET}")
            print(raw[:500])
            return

        tasks = json.loads(m.group(0))
        print(f"\n{GREEN}Agent generated {len(tasks)} optimization tasks.{RESET}")
        print("Creating in Asana...\n")

        from executors.asana import create_task
        created = 0
        for t in tasks:
            gid = create_task(
                title=t.get("title", "Optimization task"),
                description=t.get("description", ""),
                project_key=t.get("project_key", "optimization"),
                task_type=t.get("task_type", "Recommendation"),
            )
            if gid:
                created += 1
                print(f"  {GREEN}✓{RESET} {t.get('title', '')[:70]}")

        print(f"\n{GREEN}{created}/{len(tasks)} tasks created in Asana > Optimization.{RESET}")

        # Notify Slack
        from notifications.slack import client as slack_client
        slack_client.chat_postMessage(
            channel=os.getenv("SLACK_CHANNEL_NOTIFY", ""),
            text=(
                f"📋 *Campaign Optimization Batch Complete*\n"
                f"Generated and created *{created} optimization tasks* in Asana "
                f"(including historically well-performing paused campaigns).\n"
                f"Check Asana › Optimization project."
            ),
        )

    except Exception as e:
        print(f"{RED}Error: {e}{RESET}")
        import traceback; traceback.print_exc()


def main():
    # Show menu immediately — press [S] to start background processes
    while True:
        show_menu()
        choice = ask("Enter choice:").upper()

        if choice == "B1":
            _run("bq", "reporting_scheduler.py")
            input(f"{GREEN}BQ scheduler started. Press Enter.{RESET}")

        elif choice == "B2":
            _run("scheduler", "operational_scheduler.py")
            input(f"{GREEN}Operational scheduler started. Press Enter.{RESET}")

        elif choice == "B3":
            _run("listener", "slack_listener.py")
            input(f"{GREEN}Slack listener started. Press Enter.{RESET}")

        elif choice == "1":
            print(f"\n{YELLOW}Running daily analysis now...{RESET}")
            _run_fg("main.py", "on_demand")
            input("\nDone. Press Enter to return.")

        elif choice == "2":
            print(f"\n{YELLOW}Running weekly analysis now...{RESET}")
            _run_fg("main.py", "weekly", "--force")
            input("\nDone. Press Enter to return.")

        elif choice == "3":
            print(f"\n{YELLOW}Running monthly analysis now...{RESET}")
            _run_fg("main.py", "monthly", "--force")
            input("\nDone. Press Enter to return.")

        elif choice == "4":
            print(f"\n{YELLOW}Forcing BQ data refresh (incremental — last 2 days)...{RESET}")
            _run_fg("reporting_scheduler.py", "once")
            input("\nDone. Press Enter to return.")

        elif choice == "4B":
            print(f"\n{YELLOW}Running FULL BQ backfill (year-to-date — may take 5-15 min)...{RESET}")
            print(f"{DIM}All channels: Google Ads, Meta, Snap, LinkedIn, TikTok, HubSpot{RESET}")
            _run_fg("reporting_scheduler.py", "backfill")
            input(f"\n{GREEN}Backfill complete. Press Enter.{RESET}")

        elif choice == "5":
            _run_fg("main.py", "status")
            input("\nPress Enter to return.")

        elif choice == "6":
            _run_fg("main.py", "on_demand", "--bust")
            input(f"\n{GREEN}Cache cleared and fresh run done. Press Enter.{RESET}")

        elif choice == "7":
            print(f"\n{YELLOW}Refreshing BigQuery views...{RESET}")
            from dotenv import load_dotenv; load_dotenv()
            from collectors.views import refresh_all_views
            refresh_all_views()
            input(f"\n{GREEN}Views refreshed. Press Enter.{RESET}")

        elif choice == "L":
            import glob
            log_dir = os.path.join(BASE, "logs")
            print(f"\n{CYAN}{BOLD}  Log files in {log_dir}{RESET}\n")
            all_logs = sorted(glob.glob(os.path.join(log_dir, "*.log")), reverse=True)
            if not all_logs:
                input(f"{YELLOW}No log files yet — run the agent first. Press Enter.{RESET}")
            else:
                for i, lf in enumerate(all_logs[:6]):
                    size = os.path.getsize(lf) // 1024
                    name = os.path.basename(lf)
                    print(f"  {YELLOW}[{i}]{RESET}  {name}  {DIM}({size} KB){RESET}")
                print()
                pick = ask("Enter number to view (or Enter to skip):").strip()
                if pick.isdigit() and int(pick) < len(all_logs):
                    chosen = all_logs[int(pick)]
                    lines  = open(chosen, encoding="utf-8", errors="replace").readlines()
                    print(f"\n{CYAN}--- {os.path.basename(chosen)} (last 60 lines) ---{RESET}\n")
                    for line in lines[-60:]:
                        print(line, end="")
                input(f"\n{DIM}Press Enter to return.{RESET}")

        elif choice == "8":
            from dotenv import load_dotenv; load_dotenv()
            sys.path.insert(0, BASE)
            from slack_listener import handle_past_due
            result = handle_past_due()
            print(f"\n{result}")
            input("\nPress Enter to return.")

        elif choice == "9":
            topic = ask("Report topic (e.g. 'Meta last 7 days' or 'all channels weekly'):")
            run_agent_inline(f"Generate a performance report for: {topic}. "
                             "Include channel breakdown, CPL/CPQL status, top campaigns, recommendations.")
            input("\nPress Enter to return.")

        elif choice == "10":
            topic = ask("Brief for (e.g. 'Google Search brand awareness campaign'):")
            run_agent_inline(f"Create a detailed campaign brief for: {topic}. "
                             "Include objective, audience, budget guidance, channels, "
                             "targeting, KPIs, and creative direction.")
            input("\nPress Enter to return.")

        elif choice == "11":
            topic = ask("Scaling target (e.g. 'Meta Lead Gen' or 'Google ZATCA campaign'):")
            run_agent_inline(
                f"Generate a scaling strategy for: {topic}. "
                "Base it on Qoyod's thresholds: CPL<30 SAR, CPQL<80 SAR, Qual rate>30%. "
                "Include: scale criteria met/not met, recommended budget increase %, "
                "audience expansion, creative refresh plan, risk flags."
            )
            input("\nPress Enter to return.")

        elif choice == "12":
            topic = ask("Campaign to set up (e.g. 'Google Search ZATCA awareness Q3'):")
            run_agent_inline(
                f"Generate a full campaign setup plan for: {topic}. "
                "Include: objective, channel, budget in SAR, audience targeting, "
                "ad structure (campaigns/ad sets/ads), creative direction, "
                "pixel/tracking setup, scale and pause triggers."
            )
            input("\nPress Enter to return.")

        elif choice == "13":
            optimize_all_campaigns()
            input("\nPress Enter to return.")

        elif choice == "MS":
            print(f"\n{CYAN}Microsoft Ads — OAuth Setup{RESET}")
            print(f"{DIM}{'─'*50}{RESET}")
            from dotenv import load_dotenv; load_dotenv()
            sys.path.insert(0, BASE)
            try:
                from collectors.microsoft_ads import run_auth_flow
                run_auth_flow()
                # After flow completes, ask user to paste token and write it to .env
                print(f"\n{CYAN}Paste your refresh token below and press Enter.{RESET}")
                print(f"{DIM}(It will be written to .env automatically){RESET}")
                token = input("Token: ").strip()
                if token:
                    env_path = os.path.join(BASE, ".env")
                    content  = open(env_path, encoding="utf-8").read()
                    if "MS_REFRESH_TOKEN=" in content:
                        import re
                        content = re.sub(r"MS_REFRESH_TOKEN=.*", f"MS_REFRESH_TOKEN={token}", content)
                    else:
                        content += f"\nMS_REFRESH_TOKEN={token}\n"
                    open(env_path, "w", encoding="utf-8").write(content)
                    print(f"\n{GREEN}✓ Token saved to .env — Microsoft Ads is now active.{RESET}")
                else:
                    print(f"{YELLOW}No token entered — .env not changed.{RESET}")
            except Exception as e:
                print(f"{RED}Error: {e}{RESET}")
            input("\nPress Enter to return.")

        elif choice == "TT":
            print(f"\n{CYAN}TikTok — Access Token Guide{RESET}")
            print()
            print(f"  1. Go to: {YELLOW}https://ads.tiktok.com/marketing_api/apps/{RESET}")
            print(f"  2. Select your app (or create one)")
            print(f"  3. Go to {YELLOW}My Apps -> App Details -> Access Token{RESET}")
            print(f"  4. Copy the long-lived access token")
            print(f"  5. Open: {YELLOW}D:\\Nexa Performance Agent\\.env{RESET}")
            print(f"  6. Find the line: {YELLOW}TIKTOK_ACCESS_TOKEN={RESET}")
            print(f"  7. Paste:  {YELLOW}TIKTOK_ACCESS_TOKEN=<your token>{RESET}")
            print(f"  8. Save the file — Nexa will pick it up on next run")
            input(f"\n{DIM}Press Enter to return.{RESET}")

        elif choice == "H":
            run_health_check_inline()
            input("\nPress Enter to return.")

        elif choice == "S":
            start_all()

        elif choice == "K":
            stop_all()
            input(f"{YELLOW}All stopped. Press Enter.{RESET}")

        elif choice == "R":
            stop_all()
            start_all()

        elif choice == "Q":
            stop_all()
            print(f"\n{DIM}Goodbye.{RESET}\n")
            sys.exit(0)

        else:
            input(f"{RED}Unknown choice. Press Enter.{RESET}")


if __name__ == "__main__":
    main()
