"""
scripts/action_audit_violations.py
===================================
One-off executor — reads the latest active_keyword_violations_<date>.csv and
takes the rule-mandated action:

  • always_negative              → PAUSE (login/free/etc. should never be a keyword)
  • low_qs_high_lost_is_delete   → DELETE (zero spend, safe per "no-cost-no-delete")
  • low_qs_high_lost_is_pause    → PAUSE (had spend, keep history)
  • brand_only_block             → PAUSE (move-or-pause, default to pause)
  • competitor_in_generic        → PAUSE (move-or-pause, default to pause)
  • language_mismatch            → PAUSE

All actions are LOGGED + posted back to the originating Asana task as a
comment so there's a complete audit trail.

This script requires explicit invocation — it is NOT in the nightly schedule.
The user must approve in chat (per CLAUDE.md) before running.

Usage:
  python scripts/action_audit_violations.py            # execute today's CSV
  python scripts/action_audit_violations.py --csv X.csv
  python scripts/action_audit_violations.py --dry-run  # show what would happen
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.google_ads import get_client


PAUSE_VIOLATIONS = {
    "always_negative",
    "low_qs_high_lost_is_pause",
    "brand_only_block",
    "competitor_in_generic",
    "language_mismatch",
}
DELETE_VIOLATIONS = {"low_qs_high_lost_is_delete"}


def load_violations(csv_path: Path) -> list[dict]:
    return list(csv.DictReader(csv_path.open(encoding="utf-8")))


def execute(violations: list[dict], dry_run: bool = False) -> dict:
    """Returns {paused, deleted, errors}."""
    client = get_client()
    svc = client.get_service("AdGroupCriterionService")

    by_cid_action: dict[tuple[str, str], list[str]] = defaultdict(list)
    for v in violations:
        cid = v["customer_id"]
        rn  = v["criterion_resource"]
        if v["violation"] in PAUSE_VIOLATIONS:
            by_cid_action[(cid, "pause")].append(rn)
        elif v["violation"] in DELETE_VIOLATIONS:
            by_cid_action[(cid, "delete")].append(rn)

    counts = {"paused": 0, "deleted": 0, "errors": 0}
    keyword_names = [v.get("keyword", "") for v in violations]
    for (cid, action), resources in by_cid_action.items():
        verb = "WOULD-" + action.upper() if dry_run else action.upper()
        print(f"\n[{verb}] account={cid}  {len(resources)} keyword(s)")
        for rn in resources:
            print(f"   {rn}")

        if dry_run:
            counts[action + "d"] = counts.get(action + "d", 0) + len(resources)
            continue

        ops = []
        for rn in resources:
            op = client.get_type("AdGroupCriterionOperation")
            if action == "pause":
                op.update.resource_name = rn
                op.update.status = client.enums.AdGroupCriterionStatusEnum.PAUSED
                op.update_mask.paths.append("status")
            else:  # delete
                op.remove = rn
            ops.append(op)

        try:
            svc.mutate_ad_group_criteria(customer_id=cid, operations=ops)
            counts[action + "d"] = counts.get(action + "d", 0) + len(resources)
            print(f"   ✓ {action}d {len(resources)} keyword(s) in {cid}")
        except Exception as e:
            counts["errors"] += 1
            print(f"   X mutate failed for {cid}/{action}: {e}")

    if not dry_run and (counts["paused"] or counts["deleted"]):
        try:
            from logs.activity_logger import log_activity_async
            if counts["paused"]:
                log_activity_async(
                    role="manual_script", action="keywords_paused",
                    channel="google_ads", rows_affected=counts["paused"],
                    details={"keywords": keyword_names[:30],
                             "source": "action_audit_violations.py"},
                )
            if counts["deleted"]:
                log_activity_async(
                    role="manual_script", action="keywords_deleted",
                    channel="google_ads", rows_affected=counts["deleted"],
                    details={"keywords": keyword_names[:30],
                             "source": "action_audit_violations.py"},
                )
        except Exception:
            pass

    return counts


def comment_back_to_asana(task_gid: str, counts: dict, violations: list[dict]) -> None:
    if not task_gid:
        return
    try:
        import asana
        from executors.asana import get_client as get_asana_client
        client = get_asana_client()
        stories_api = asana.StoriesApi(client)

        lines = [
            f"**Actions executed** — {date.today().isoformat()}",
            "",
            f"• Paused: {counts.get('paused', 0)}",
            f"• Deleted: {counts.get('deleted', 0)}",
            f"• Errors: {counts.get('errors', 0)}",
            "",
            "Detail:",
        ]
        for v in violations:
            action_taken = "PAUSE" if v["violation"] in PAUSE_VIOLATIONS else (
                "DELETE" if v["violation"] in DELETE_VIOLATIONS else "—"
            )
            lines.append(f"  • [{action_taken}] `{v['keyword']}` — {v['violation']} — {v['campaign']}")

        body = "\n".join(lines)
        stories_api.create_story_for_task({"data": {"text": body}}, task_gid, {})
        print(f"\n[asana] commented on task {task_gid}")
    except Exception as e:
        print(f"\n[asana] comment failed: {e}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=None,
                   help="path to violations CSV (default: today's file)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--asana-task", default=None,
                   help="Asana task gid to comment back to")
    args = p.parse_args()

    csv_path = Path(args.csv) if args.csv else (
        Path(__file__).resolve().parent.parent / "logs" /
        f"active_keyword_violations_{date.today().isoformat()}.csv"
    )
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    violations = load_violations(csv_path)
    print(f"Loaded {len(violations)} violations from {csv_path}")
    counts = execute(violations, dry_run=args.dry_run)
    print(f"\nFinal counts: {counts}")

    if not args.dry_run:
        comment_back_to_asana(args.asana_task, counts, violations)
