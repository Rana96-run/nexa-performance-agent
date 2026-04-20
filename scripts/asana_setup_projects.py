"""
Sets up Asana projects for the Qoyod Performance Agent:
  - optimization portfolio: adds missing channels (Snapchat, TikTok, LinkedIn, YouTube)
  - seasonal portfolio: adds End of Year (EOY) + National Day campaigns
  - daily_activity portfolio: creates 6 daily ops projects

Writes the resulting GIDs to .env (ASANA_PROJECT_* keys).
"""
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
WORKSPACE = os.getenv("ASANA_WORKSPACE_ID")
if not TOKEN or not WORKSPACE:
    sys.exit("Missing ASANA_ACCESS_TOKEN or ASANA_WORKSPACE_ID")

PORT_OPT     = os.getenv("ASANA_PORTFOLIO_OPTIMIZATION")
PORT_SEASON  = os.getenv("ASANA_PORTFOLIO_SEASONAL")
PORT_DAILY   = os.getenv("ASANA_PORTFOLIO_DAILY_ACTIVITY")

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
           "Content-Type": "application/json"}
API = "https://app.asana.com/api/1.0"


def get(url, **params):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data")


def post(url, body):
    r = requests.post(url, headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
    return r.json().get("data")


def find_team_from_portfolio(portfolio_gid):
    """Peek at an existing project in a portfolio to reuse its team."""
    items = get(f"{API}/portfolios/{portfolio_gid}/items") or []
    for it in items:
        if it.get("resource_type") == "project":
            proj = get(f"{API}/projects/{it['gid']}", opt_fields="team")
            team = proj.get("team") if proj else None
            if team:
                return team.get("gid")
    return None


def create_project(name, team_gid):
    body = {"data": {"name": name, "workspace": WORKSPACE, "team": team_gid}}
    data = post(f"{API}/projects", body)
    return data["gid"]


def add_to_portfolio(portfolio_gid, project_gid):
    post(f"{API}/portfolios/{portfolio_gid}/addItem", {"data": {"item": project_gid}})


def existing_names(portfolio_gid):
    items = get(f"{API}/portfolios/{portfolio_gid}/items") or []
    return {it["name"].strip().lower() for it in items}


OPTIMIZATION_NEW = [
    "Snapchat Ads Optimization",
    "TikTok Ads Optimization",
    "LinkedIn Ads Optimization",
    "YouTube Ads Optimization",
]
SEASONAL_NEW = [
    "End of Year Campaign (EOY)",
    "National Day Campaign",
]
DAILY_ACTIVITY_NEW = [
    "Daily Performance Review",
    "Budget Pacing & Alerts",
    "Creative Refresh & QA",
    "Keyword & Placement Audit",
    "Conversion Tracking & CRM Sync",
    "Competitive & Market Monitoring",
]


def ensure(portfolio_gid, names, team_gid, label):
    print(f"\n=== {label} ===")
    existing = existing_names(portfolio_gid)
    created = {}
    for n in names:
        if n.strip().lower() in existing:
            print(f"  = exists: {n}")
            continue
        gid = create_project(n, team_gid)
        add_to_portfolio(portfolio_gid, gid)
        created[n] = gid
        print(f"  + created {gid}  {n}")
    return created


def pick_gid(portfolio_gid, name_contains):
    items = get(f"{API}/portfolios/{portfolio_gid}/items") or []
    for it in items:
        if name_contains.lower() in it["name"].lower() and it.get("resource_type") == "project":
            return it["gid"]
    return None


def write_env(updates: dict):
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines()
    keys = set(updates.keys())
    out = []
    seen = set()
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in keys:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for k in keys - seen:
        out.append(f"{k}={updates[k]}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    team = (find_team_from_portfolio(PORT_OPT)
            or find_team_from_portfolio(PORT_SEASON)
            or find_team_from_portfolio(PORT_DAILY))
    if not team:
        sys.exit("Could not resolve team GID from any portfolio. Add one project manually first.")
    print(f"Using team GID: {team}")

    ensure(PORT_OPT,    OPTIMIZATION_NEW,   team, "optimization")
    ensure(PORT_SEASON, SEASONAL_NEW,       team, "seasonal")
    ensure(PORT_DAILY,  DAILY_ACTIVITY_NEW, team, "daily_activity")

    # Map one project GID per top-level key (for agent's ASANA_PROJECTS dict).
    env_updates = {}
    daily = pick_gid(PORT_DAILY, "Daily Performance Review")
    if daily:
        env_updates["ASANA_PROJECT_DAILY_ACTIVITY"] = daily
    opt = pick_gid(PORT_OPT, "Google Ads Optimization")
    if opt:
        env_updates["ASANA_PROJECT_OPTIMIZATION"] = opt
    season = pick_gid(PORT_SEASON, "End of Year")
    if season:
        env_updates["ASANA_PROJECT_SEASONAL"] = season
    hub = pick_gid(PORT_DAILY, "Daily Performance Review")
    if hub:
        env_updates["ASANA_PROJECT_CAMPAIGNS_HUB"] = hub

    if env_updates:
        write_env(env_updates)
        print("\nWrote to .env:")
        for k, v in env_updates.items():
            print(f"  {k}={v}")


if __name__ == "__main__":
    main()
