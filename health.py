"""
Nexa Health Check — verifies all credentials and connections before the agent runs.

Usage:
    python health.py           # print full health report
    python health.py --quiet   # only print failures

Called from CONTROL_PANEL option [H].
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)   # always prefer .env over stale system env vars

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

QUIET = "--quiet" in sys.argv


def check(name: str, ok: bool, detail: str = "", warn: bool = False) -> bool:
    if ok:
        if not QUIET:
            print(f"  {GREEN}✓{RESET}  {name:<30} {DIM}{detail}{RESET}")
    elif warn:
        print(f"  {YELLOW}⚠{RESET}  {name:<30} {YELLOW}{detail}{RESET}")
    else:
        print(f"  {RED}✗{RESET}  {name:<30} {RED}{detail}{RESET}")
    return ok


def env(key: str) -> str:
    return os.getenv(key, "")


def run_health_check() -> bool:
    print(f"\n{CYAN}{BOLD}Nexa — Health Check{RESET}")
    print(f"{DIM}{'─' * 52}{RESET}\n")

    all_ok = True

    # ── Anthropic ──────────────────────────────────────────────────────────
    print(f"{BOLD}  Anthropic{RESET}")
    key = env("ANTHROPIC_API_KEY")
    ok = bool(key and key.startswith("sk-ant-"))
    all_ok &= check("API Key", ok, "present" if ok else "missing or malformed")

    # ── Slack ──────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Slack{RESET}")
    check("Bot token",          bool(env("SLACK_BOT_TOKEN")),          "present" if env("SLACK_BOT_TOKEN") else "MISSING — bot won't respond")
    check("Notify channel",     bool(env("SLACK_CHANNEL_NOTIFY")),     env("SLACK_CHANNEL_NOTIFY") or "MISSING")
    check("Approval channel",   bool(env("SLACK_CHANNEL_APPROVAL")),   env("SLACK_CHANNEL_APPROVAL") or "MISSING")

    # ── Google Ads ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Google Ads{RESET}")
    check("Developer token",    bool(env("GOOGLE_ADS_DEVELOPER_TOKEN")), "present" if env("GOOGLE_ADS_DEVELOPER_TOKEN") else "MISSING")
    check("Refresh token",      bool(env("GOOGLE_ADS_REFRESH_TOKEN")),   "present" if env("GOOGLE_ADS_REFRESH_TOKEN") else "MISSING")
    check("Customer IDs",       bool(env("GOOGLE_ADS_CUSTOMER_IDS")),    env("GOOGLE_ADS_CUSTOMER_IDS") or "MISSING")

    # ── Meta ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Meta{RESET}")
    check("Access token",       bool(env("META_ACCESS_TOKEN")),  "present" if env("META_ACCESS_TOKEN") else "MISSING")
    check("Ad account 1",       bool(env("META_AD_ACCOUNT_1")),  env("META_AD_ACCOUNT_1") or "MISSING")
    check("Ad account 2",       bool(env("META_AD_ACCOUNT_2")),  env("META_AD_ACCOUNT_2") or "missing (optional)")

    # ── Snapchat ───────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Snapchat{RESET}")
    check("Client ID",          bool(env("SNAPCHAT_CLIENT_ID")),      "present" if env("SNAPCHAT_CLIENT_ID") else "MISSING")
    check("Client secret",      bool(env("SNAPCHAT_CLIENT_SECRET")),  "present" if env("SNAPCHAT_CLIENT_SECRET") else "MISSING")
    check("Refresh token",      bool(env("SNAPCHAT_REFRESH_TOKEN")),  "present" if env("SNAPCHAT_REFRESH_TOKEN") else "MISSING")

    # ── TikTok ─────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  TikTok{RESET}")
    tt_token = env("TIKTOK_ACCESS_TOKEN")
    check("Access token",       bool(tt_token),
          "present" if tt_token else "NOT SET — get from Ads Manager -> Tools -> API",
          warn=not tt_token)
    check("Ad account 2024",    bool(env("TIKTOK_AD_ACCOUNT_2024")), env("TIKTOK_AD_ACCOUNT_2024") or "missing")
    check("Ad account 2025",    bool(env("TIKTOK_AD_ACCOUNT_2025")), env("TIKTOK_AD_ACCOUNT_2025") or "missing")

    # ── LinkedIn ───────────────────────────────────────────────────────────
    print(f"\n{BOLD}  LinkedIn{RESET}")
    li_token = env("LI_ACCESS_TOKEN")
    check("Access token",       bool(li_token),     "present (expires every 60 days)" if li_token else "MISSING")
    check("Ad account URN",     bool(env("LI_AD_ACCOUNT_URN")),  env("LI_AD_ACCOUNT_URN") or "MISSING")

    # ── Microsoft Ads ──────────────────────────────────────────────────────
    print(f"\n{BOLD}  Microsoft Ads{RESET}")
    ms_token = env("MS_REFRESH_TOKEN")
    check("Developer token",    bool(env("MS_DEVELOPER_TOKEN")),  "present" if env("MS_DEVELOPER_TOKEN") else "MISSING")
    check("Client ID",          bool(env("MS_CLIENT_ID")),        "present" if env("MS_CLIENT_ID") else "MISSING")
    check("Refresh token",      bool(ms_token),
          "present" if ms_token else "NOT SET — run: python collectors/microsoft_ads.py auth",
          warn=not ms_token)

    # ── HubSpot ────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  HubSpot{RESET}")
    check("Access token",       bool(env("HUBSPOT_ACCESS_TOKEN")),  "present" if env("HUBSPOT_ACCESS_TOKEN") else "MISSING")

    # ── BigQuery ───────────────────────────────────────────────────────────
    print(f"\n{BOLD}  BigQuery{RESET}")
    bq_creds = env("GOOGLE_APPLICATION_CREDENTIALS")
    # Resolve relative paths the same way bq_writer does
    if bq_creds and not os.path.isabs(bq_creds):
        bq_creds = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                bq_creds.lstrip("./\\"))
    if not bq_creds:
        bq_creds = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "bigquery-key.json")
    creds_exist = os.path.exists(bq_creds)
    check("Credentials file",   creds_exist,
          bq_creds if creds_exist else f"NOT FOUND at {bq_creds}")
    check("Project ID",         bool(env("BQ_PROJECT_ID")),  env("BQ_PROJECT_ID") or "MISSING")
    check("Dataset",            bool(env("BQ_DATASET")),     env("BQ_DATASET") or "MISSING")

    # ── Asana ──────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Asana{RESET}")
    check("Access token",       bool(env("ASANA_ACCESS_TOKEN")),          "present" if env("ASANA_ACCESS_TOKEN") else "MISSING")
    check("Daily Activity proj",bool(env("ASANA_PROJECT_DAILY_ACTIVITY")),env("ASANA_PROJECT_DAILY_ACTIVITY") or "MISSING")
    check("Optimization proj",  bool(env("ASANA_PROJECT_OPTIMIZATION")),  env("ASANA_PROJECT_OPTIMIZATION") or "MISSING")

    # ── Email ─────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Email (SMTP){RESET}")
    check("SMTP user",          bool(env("SMTP_USER")),  env("SMTP_USER") or "MISSING")
    check("SMTP password",      bool(env("SMTP_PASS")),  "set" if env("SMTP_PASS") else "MISSING")
    check("Email recipients",   bool(env("EMAIL_ALL")),  env("EMAIL_ALL") or "MISSING")

    # ── Logs ──────────────────────────────────────────────────────────────
    print(f"\n{BOLD}  Logs{RESET}")
    from pathlib import Path
    log_dir = Path(__file__).parent / "logs"
    log_files = sorted(log_dir.glob("nexa_*.log"), reverse=True)
    check("Log directory",      log_dir.exists(),     str(log_dir))
    check("Recent log files",   bool(log_files),
          f"{len(log_files)} file(s) — latest: {log_files[0].name}" if log_files else "none yet")

    # ── Notify mode ───────────────────────────────────────────────────────
    print(f"\n{BOLD}  Notifications{RESET}")
    nv = env("NOTIFY_VIA") or "email"
    check("NOTIFY_VIA",         True, f"{nv} (set to 'both' for Slack + Email)")

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{DIM}{'─' * 52}{RESET}")
    if all_ok:
        print(f"  {GREEN}{BOLD}All critical checks passed.{RESET}")
    else:
        print(f"  {RED}{BOLD}Some checks failed — see ✗ items above.{RESET}")
    print()

    return all_ok


if __name__ == "__main__":
    ok = run_health_check()
    sys.exit(0 if ok else 1)
