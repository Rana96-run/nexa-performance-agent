"""
Stop hook: auto-commit and push any uncommitted local changes to origin/main.
Fires every time Claude finishes a turn. Exits 0 silently if nothing to commit.
Outputs a systemMessage JSON line if it commits something.
Also logs the commit to agent_activity_log in BQ so it appears in the
Hex activity dashboard automatically.
"""
import json
import os
import re
import subprocess
import sys

REPO_ROOT = r"D:\Nexa Performance Agent"
BQ_PROJECT = "angular-axle-492812-q4"
BQ_DATASET = "qoyod_marketing"

# Files and patterns that must never be auto-committed
EXCLUDED = [
    r"(^|[\\/])\.env$",
    r"(^|[\\/])secrets[\\/]",
    r"\.log$",
    r"__pycache__",
    r"_diag_out\.txt$",
    r"_recon_out\.txt$",
    r"(^|[\\/])_[^\\/]+\.(txt|json)$",  # root-level or any _*.txt / _*.json
    r"\.pyc$",
    r"(^|[\\/])\.cache[\\/]",
]


def is_excluded(path: str) -> bool:
    for pat in EXCLUDED:
        if re.search(pat, path.replace("\\", "/")):
            return True
    return False


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def main() -> None:
    # Collect unstaged + untracked files
    status = run(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        sys.exit(0)

    to_stage: list[str] = []
    for line in status.stdout.splitlines():
        if not line:
            continue
        filepath = line[3:].strip()
        if " -> " in filepath:          # rename: take the destination
            filepath = filepath.split(" -> ", 1)[1].strip()
        if not is_excluded(filepath):
            to_stage.append(filepath)

    if not to_stage:
        sys.exit(0)

    # Stage
    run(["git", "add", "--"] + to_stage)

    # Verify something is actually staged (exclusions might have cleared the diff)
    staged = run(["git", "diff", "--cached", "--stat"])
    if not staged.stdout.strip():
        sys.exit(0)

    # Commit
    msg = (
        "chore: auto-commit local changes\n\n"
        + staged.stdout.strip()
        + "\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    )
    commit = run(["git", "commit", "-m", msg])
    if commit.returncode != 0:
        # Don't block the stop — just log to stderr
        print(f"[auto-commit] commit failed: {commit.stderr}", file=sys.stderr)
        sys.exit(0)

    # Push
    push = run(["git", "push", "origin", "main"])
    if push.returncode != 0:
        print(f"[auto-commit] push failed: {push.stderr}", file=sys.stderr)
        sys.exit(0)

    # Get commit hash for the dashboard log
    commit_hash = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()

    # Log to BQ activity dashboard
    _log_to_dashboard(to_stage, commit_hash, staged.stdout.strip())

    # Notify the user
    print(json.dumps({
        "systemMessage": (
            f"[auto-commit] {len(to_stage)} file(s) committed ({commit_hash}) "
            f"and pushed to origin/main — activity dashboard updated"
        )
    }))


def _log_to_dashboard(files: list[str], commit_hash: str, stat_summary: str) -> None:
    """Write one row to agent_activity_log so the Hex dashboard picks it up."""
    try:
        # Load local .env so GOOGLE_APPLICATION_CREDENTIALS is available
        env_path = os.path.join(REPO_ROOT, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())

        os.environ.setdefault("BQ_PROJECT_ID", BQ_PROJECT)
        os.environ.setdefault("BQ_DATASET",    BQ_DATASET)

        # Resolve relative credential path against repo root
        cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if cred and not os.path.isabs(cred):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(REPO_ROOT, cred)

        sys.path.insert(0, REPO_ROOT)
        from logs.activity_logger import log_activity

        log_activity(
            role="claude_session",
            action="code_committed",
            status="success",
            details={
                "commit": commit_hash,
                "files_changed": len(files),
                "files": files[:20],          # cap at 20 to keep details readable
                "stat": stat_summary[:500],
            },
            rows_affected=len(files),
        )
    except Exception as exc:
        print(f"[auto-commit] dashboard log skipped: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
