"""
Session-start review hook — fires automatically at the start of every Claude session.

Checks:
  1. Git status (uncommitted changes, branch, commits ahead of origin)
  2. Railway deployment status (latest deploy + health endpoint)
  3. Recent Railway error logs (last 20 lines)
  4. Latest session learning — reads the most recent session summary so the
     agent always starts from where the last conversation left off.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # D:\Nexa Performance Agent


def _run(cmd: list[str], cwd=None) -> str:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            cwd=cwd or str(ROOT),
        )
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:
        return f"(error: {e})"


# ── 1. Git status ─────────────────────────────────────────────────────────────

git_branch  = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
git_status  = _run(["git", "status", "--short"])
git_ahead   = _run(["git", "rev-list", "--count", "HEAD@{upstream}..HEAD"])
git_log     = _run(["git", "log", "--oneline", "-5"])

git_section = (
    f"Branch: {git_branch}  |  {git_ahead} commit(s) ahead of origin\n"
    + (f"Uncommitted changes:\n{git_status}\n" if git_status else "Working tree clean.\n")
    + f"Recent commits:\n{git_log}"
)

# ── 2. Railway deployment ─────────────────────────────────────────────────────

railway_token   = os.getenv("RAILWAY_API_TOKEN", "")
railway_svc_id  = os.getenv("RAILWAY_SERVICE_ID", "")
railway_domain  = (
    os.getenv("RAILWAY_PUBLIC_DOMAIN")
    or os.getenv("RAILWAY_STATIC_URL", "").removeprefix("https://")
    or "nexa-performance-agent.up.railway.app"
)
base_url = f"https://{railway_domain}"

deploy_section = ""
try:
    import requests as _req

    # Health endpoint
    try:
        h = _req.get(f"{base_url}/health", timeout=8)
        health_status = f"✅ {base_url}/health → {h.status_code}" if h.ok else f"❌ /health → HTTP {h.status_code}"
    except Exception as e:
        health_status = f"❌ /health unreachable: {e}"

    # Latest Railway deployment via GraphQL API
    deploy_status = "(no RAILWAY_API_TOKEN or SERVICE_ID set)"
    if railway_token and railway_svc_id:
        q = """
        query($sid: String!) {
          deployments(input: { serviceId: $sid }, first: 1) {
            edges { node { status createdAt url } }
          }
        }
        """
        try:
            r = _req.post(
                "https://backboard.railway.app/graphql/v2",
                json={"query": q, "variables": {"serviceId": railway_svc_id}},
                headers={"Authorization": f"Bearer {railway_token}"},
                timeout=10,
            )
            edges = r.json().get("data", {}).get("deployments", {}).get("edges", [])
            if edges:
                n = edges[0]["node"]
                deploy_status = f"{n['status']}  (deployed {n['createdAt'][:16]})"
            else:
                deploy_status = "No deployments found"
        except Exception as e:
            deploy_status = f"Railway API error: {e}"

    deploy_section = f"Health: {health_status}\nLatest deploy: {deploy_status}"

except ImportError:
    deploy_section = "(requests not available — skip Railway check)"

# ── 3. Recent Railway logs via CLI ────────────────────────────────────────────

logs_section = ""
try:
    log_out = _run(["railway", "logs", "--tail", "20"])
    if log_out and "error" in log_out.lower():
        # Only surface if there are errors
        logs_section = f"\nRecent Railway log errors:\n{log_out[-1500:]}"
except Exception:
    pass   # railway CLI not available — skip

# ── 4. Latest session learning ────────────────────────────────────────────────
# Read the most recent session transcript for this project and extract the last
# compaction summary so the agent knows what happened last session.

session_section = ""
try:
    import glob as _glob

    # Claude projects are stored under:  ~/.claude/projects/<sanitized-cwd>/
    home = Path.home()
    cwd_sanitized = str(ROOT).replace("\\", "-").replace("/", "-").replace(":", "-").lstrip("-")
    projects_dir = home / ".claude" / "projects" / cwd_sanitized

    if not projects_dir.exists():
        # Try alternate sanitization (Windows drive letter variation)
        candidates = list((home / ".claude" / "projects").glob("*Nexa*"))
        if candidates:
            projects_dir = candidates[0]

    if projects_dir.exists():
        jsonl_files = sorted(
            projects_dir.glob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if jsonl_files:
            latest_file = jsonl_files[0]
            # Read last 200 lines — compaction summaries live near the end
            lines = latest_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            tail = lines[-200:] if len(lines) > 200 else lines

            # Extract the most recent compaction/summary text
            summary_text = ""
            for line in reversed(tail):
                try:
                    obj = json.loads(line)
                    # Compaction events carry the summary in message.content
                    msg = obj.get("message", {})
                    role = msg.get("role", "")
                    if role == "user":
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    t = block.get("text", "")
                                    if "This session is being continued" in t or "Summary:" in t:
                                        summary_text = t[:2000]
                                        break
                        elif isinstance(content, str) and ("This session is being continued" in content or "Summary:" in content):
                            summary_text = content[:2000]
                    if summary_text:
                        break
                except Exception:
                    continue

            if summary_text:
                # Trim to the "Current Work" / "Pending Tasks" sections only
                for marker in ["Current Work:", "Pending Tasks:", "Optional Next Step:"]:
                    idx = summary_text.find(marker)
                    if idx != -1:
                        summary_text = summary_text[idx:]
                        break
                session_section = (
                    f"\n── Last session (continued from) ──\n"
                    f"{summary_text[:1200]}\n"
                    f"Rule: continue from where the last session left off. "
                    f"Do NOT ask 'where were we?' — you already know."
                )
            else:
                session_section = f"\n── Last session ──\n(No summary found in {latest_file.name})"
    else:
        session_section = "\n── Last session ──\n(Projects dir not found — skip)"

except Exception as e:
    session_section = f"\n── Last session ──\n(Session read error: {e})"

# ── Output ────────────────────────────────────────────────────────────────────

context = (
    "═══ SESSION START — LIVE STATE REVIEW ═══\n\n"
    "── Git ──\n"
    f"{git_section}\n\n"
    "── Railway ──\n"
    f"{deploy_section}"
    f"{logs_section}\n"
    f"{session_section}\n\n"
    "Rule: review the above BEFORE making any code changes. "
    "If there are uncommitted local changes or the deploy is not SUCCESS/ACTIVE, "
    "address that first. If Railway logs show errors, fix those before anything else.\n"
    "══════════════════════════════════════════"
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }
}))
