"""
scripts/audit.py
================
Unified entry point for the keyword/negative-keyword audit family.
Replaces three separate CLIs with one — fewer commands to remember.

Usage:
  python scripts/audit.py keywords    [--silent]
      Scan all ENABLED Google Ads keywords for policy violations
      (always-negative-as-keyword, قيود-in-non-brand, competitor-in-generic,
      language-mismatch). Writes CSV + creates Asana review task.

  python scripts/audit.py negatives
      Scan all ACTIVE negative keywords for items that should NOT be
      negatives (competitor brands, our own brand). Auto-removes safe
      cases, surfaces the rest in Asana for human review.

  python scripts/audit.py violations  [--csv FILE] [--dry-run] [--asana-task GID]
      Execute the rule-mandated action (PAUSE/DELETE) for each row in the
      most recent active_keyword_violations CSV. Comments back to the
      originating Asana task with counts.

  python scripts/audit.py --help
      Show this help.

Behavior matches the legacy individual CLIs exactly — under the hood we
just re-route to scripts.audit_active_keywords, audit_active_negatives,
and action_audit_violations. Those files continue to work standalone for
backwards compatibility.

Why this file exists:
  - One filename to remember instead of three.
  - One place to look when adding new audits.
  - Future audits (e.g. `audit.py adsets` for display creative checks)
    plug in by adding a new subcommand here, not a new top-level script.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Allow running as `python scripts/audit.py …` from project root
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _cmd_keywords(args: argparse.Namespace) -> int:
    """Scan ENABLED keywords. Mirrors audit_active_keywords.py."""
    from scripts.audit_active_keywords import (
        scan_active_keywords, write_csv, print_summary, create_review_task,
    )
    violations = scan_active_keywords()
    csv_path = write_csv(violations)
    print_summary(violations)
    print(f"\nCSV written: {csv_path}")
    if violations and not args.silent:
        create_review_task(violations, csv_path)
    elif not violations:
        print("\nNo policy violations among ENABLED keywords. ✅")
    return 0


def _cmd_negatives(_: argparse.Namespace) -> int:
    """Scan ACTIVE negative keywords. Mirrors audit_active_negatives.py."""
    from scripts.audit_active_negatives import (
        scan_active_negatives, write_csv, print_summary,
        remove_negatives, create_review_task,
    )
    violations = scan_active_negatives()
    csv_path = write_csv(violations)
    print_summary(violations)
    print(f"\nCSV written: {csv_path}")
    if violations:
        # Removing negatives is safe (no spend at risk) — direct-execute,
        # then surface to Asana for sanity check.
        removed = remove_negatives(violations)
        create_review_task(violations, csv_path, removed)
    else:
        print("\nNo policy violations among active negatives. ✅")
    return 0


def _cmd_violations(args: argparse.Namespace) -> int:
    """Execute rule-mandated actions on a violations CSV. Mirrors
    action_audit_violations.py."""
    from scripts.action_audit_violations import (
        load_violations, execute, comment_back_to_asana,
    )
    csv_path = Path(args.csv) if args.csv else (
        REPO / "logs"
        / f"active_keyword_violations_{date.today().isoformat()}.csv"
    )
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1
    violations = load_violations(csv_path)
    print(f"Loaded {len(violations)} violations from {csv_path}")
    counts = execute(violations, dry_run=args.dry_run)
    print(f"\nFinal counts: {counts}")
    if not args.dry_run:
        comment_back_to_asana(args.asana_task, counts, violations)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audit",
        description="Unified keyword & negative-keyword audit CLI.",
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{keywords,negatives,violations}")

    sp_kw = sub.add_parser("keywords", help="Scan ENABLED keywords for policy violations")
    sp_kw.add_argument("--silent", action="store_true",
                       help="Skip Asana task creation (used by weekly auto-fix)")
    sp_kw.set_defaults(func=_cmd_keywords)

    sp_ng = sub.add_parser("negatives", help="Scan ACTIVE negatives for policy violations")
    sp_ng.set_defaults(func=_cmd_negatives)

    sp_vi = sub.add_parser("violations",
                           help="Execute rule-mandated PAUSE/DELETE on a violations CSV")
    sp_vi.add_argument("--csv", default=None, help="Path to a specific CSV (default: today's)")
    sp_vi.add_argument("--dry-run", action="store_true",
                       help="Print what would happen without making changes")
    sp_vi.add_argument("--asana-task", default=None,
                       help="Asana task gid to comment back to")
    sp_vi.set_defaults(func=_cmd_violations)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
