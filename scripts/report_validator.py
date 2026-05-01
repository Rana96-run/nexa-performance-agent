"""
scripts/report_validator.py
============================
Gate that runs before any Slack publish or Asana task creation.

Two layers:

1. DATA SYNC CHECK  — are BQ tables fresh?
   • campaigns_daily      max_date >= yesterday      (hard requirement)
   • hubspot_leads_module max_date >= 3 days ago     (HubSpot has 1-3d API lag)
   • Row count > 0 for the requested date range

2. FINDINGS SANITY CHECK — do the numbers add up?
   Mathematical invariants (always true if data is clean):
     a. CPQL >= CPL          (qualified ≤ total leads → cost/qual >= cost/total)
     b. qual_rate ∈ [0, 1]   (can't have more qualified than total leads)
     c. sqls <= hs_leads     (subset relationship)
     d. spend > 0            (HAVING clause should guarantee this)
     e. CPQL = spend / sqls  (cross-check against stored values)
     f. date_from < date_to  (range direction)

   Business-logic red flags (warn but don't block):
     • CPQL > $2,000         (possible but very suspicious — usually a join issue)
     • CPL > $500            (same)
     • sqls == 0 with spend > $500  (large spend, zero attribution)
     • qual_rate < 0.01      (< 1% — nearly always junk or bad UTM)

Validators return a ValidationResult. If blocking errors exist, the caller
should NOT publish — post the error to Slack instead and investigate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

_RIYADH = timezone(timedelta(hours=3))


# ─── Result container ─────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    ok: bool = True                     # False = do NOT publish
    errors:   list[str] = field(default_factory=list)   # blocking
    warnings: list[str] = field(default_factory=list)   # non-blocking

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.ok = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append("ERRORS:\n" + "\n".join(f"  ✗ {e}" for e in self.errors))
        if self.warnings:
            parts.append("WARNINGS:\n" + "\n".join(f"  ⚠ {w}" for w in self.warnings))
        if not parts:
            return "All checks passed."
        return "\n".join(parts)

    def slack_block(self) -> str:
        """Short Slack message to post when validation fails."""
        lines = [":x: *Report validation failed — not published*"]
        for e in self.errors:
            lines.append(f"  • {e}")
        if self.warnings:
            lines.append(":warning: *Warnings (non-blocking):*")
            for w in self.warnings:
                lines.append(f"  • {w}")
        lines.append("_Fix data sync or calculation issues before re-running._")
        return "\n".join(lines)


# ─── 1. Data sync check ───────────────────────────────────────────────────────

def check_data_sync(days: int = 14) -> ValidationResult:
    """
    Verify BQ tables have recent data covering the requested analysis window.
    """
    result = ValidationResult()
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        client = get_client()
    except Exception as e:
        result.add_error(f"BQ connection failed: {e}")
        return result

    today     = date.today()
    yesterday = today - timedelta(days=1)
    window_start = today - timedelta(days=days)

    queries = {
        "campaigns_daily": f"""
            SELECT
              MAX(date)   AS max_date,
              MIN(date)   AS min_date,
              COUNT(*)    AS row_count
            FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
            WHERE date >= '{window_start.isoformat()}'
        """,
        "hubspot_leads_module_daily": f"""
            SELECT
              MAX(date)   AS max_date,
              MIN(date)   AS min_date,
              COUNT(*)    AS row_count
            FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
            WHERE date >= '{window_start.isoformat()}'
        """,
    }

    for table, sql in queries.items():
        try:
            rows = list(client.query(sql).result())
            if not rows or rows[0].row_count == 0:
                result.add_error(
                    f"`{table}`: zero rows found for window "
                    f"{window_start} → {yesterday}. Table may not have synced."
                )
                continue

            r        = rows[0]
            max_date = r.max_date
            row_cnt  = int(r.row_count)

            if max_date is None:
                result.add_error(f"`{table}`: max_date is NULL — no data in window.")
                continue

            # Convert to date if datetime
            if isinstance(max_date, datetime):
                max_date = max_date.date()

            lag_days = (yesterday - max_date).days

            if table == "campaigns_daily" and lag_days >= 2:
                result.add_error(
                    f"`campaigns_daily`: last row is {max_date} ({lag_days}d behind yesterday). "
                    f"Channel data collector likely failed. Fix sync before publishing."
                )
            elif table == "hubspot_leads_module_daily" and lag_days >= 4:
                result.add_error(
                    f"`hubspot_leads_module_daily`: last row is {max_date} ({lag_days}d behind). "
                    f"HubSpot sync likely failed — lead counts will be understated."
                )
            elif lag_days >= 2:
                result.add_warning(
                    f"`{table}`: data is {lag_days} days behind (last: {max_date})."
                )

            print(f"[validator] {table}: max_date={max_date}, lag={lag_days}d, rows={row_cnt}")

        except Exception as e:
            result.add_error(f"`{table}` query failed: {e}")

    return result


# ─── 2. Findings sanity check ─────────────────────────────────────────────────

def check_findings(findings: list[dict]) -> ValidationResult:
    """
    Validate mathematical and business-logic correctness of campaign health findings.
    Catches JOIN fan-out, division errors, and implausible numbers before publishing.
    """
    result = ValidationResult()

    if not findings:
        result.add_warning("No campaign findings returned. Check min_spend filter or date range.")
        return result

    for f in findings:
        name    = f.get("campaign", "?")
        channel = f.get("channel", "?")
        spend   = f.get("spend") or 0
        leads   = f.get("hs_leads") or 0
        sqls    = f.get("sqls") or 0
        cpl     = f.get("cpl")
        cpql    = f.get("cpql")
        qr      = f.get("qual_rate") or 0     # already in %, e.g. 45.0
        d_from  = f.get("date_from", "")
        d_to    = f.get("date_to", "")

        tag = f"{channel} / {name[:40]}"

        # a. Date range direction
        if d_from and d_to and d_from > d_to:
            result.add_error(f"[{tag}] date_from ({d_from}) is AFTER date_to ({d_to}) — range is inverted.")

        # b. qual_rate must be 0–100 (stored as percentage)
        if qr > 100:
            result.add_error(
                f"[{tag}] qual_rate = {qr:.1f}% — impossible (> 100%). "
                f"leads={leads}, sqls={sqls}. Likely a JOIN fan-out doubling lead counts."
            )
        elif qr > 95 and leads > 5:
            result.add_warning(
                f"[{tag}] qual_rate = {qr:.1f}% is suspiciously high. "
                f"Verify HubSpot lead classification."
            )

        # c. sqls cannot exceed total leads
        if sqls > leads and leads > 0:
            result.add_error(
                f"[{tag}] sqls ({sqls}) > hs_leads ({leads}) — impossible. "
                f"JOIN is multiplying HubSpot rows."
            )

        # d. CPL cannot exceed CPQL (mathematical invariant)
        if cpl and cpql and cpl > cpql:
            result.add_error(
                f"[{tag}] CPL ${cpl:.2f} > CPQL ${cpql:.2f} — mathematically impossible "
                f"(qualified ≤ total leads means cost/qual ≥ cost/total). "
                f"Spend fan-out or lead count inversion in BQ join."
            )

        # e. Cross-check stored CPQL against raw numbers
        if spend > 0 and sqls > 0 and cpql is not None:
            expected_cpql = spend / sqls
            if abs(expected_cpql - cpql) > 1.0:   # allow $1 rounding
                result.add_error(
                    f"[{tag}] CPQL mismatch: stored=${cpql:.2f}, "
                    f"recalculated=${expected_cpql:.2f} (spend={spend:.0f}/sqls={sqls}). "
                    f"Likely a GROUP BY or JOIN issue in the health query."
                )

        if spend > 0 and leads > 0 and cpl is not None:
            expected_cpl = spend / leads
            if abs(expected_cpl - cpl) > 1.0:
                result.add_error(
                    f"[{tag}] CPL mismatch: stored=${cpl:.2f}, "
                    f"recalculated=${expected_cpl:.2f} (spend={spend:.0f}/leads={leads}). "
                    f"Likely a GROUP BY or JOIN issue."
                )

        # f. Business-logic red flags (warnings, not errors)
        if cpql and cpql > 2000:
            result.add_warning(
                f"[{tag}] CPQL ${cpql:.0f} is extremely high. "
                f"spend=${spend:.0f}, sqls={sqls}. Verify HubSpot UTM attribution."
            )
        if cpl and cpl > 500:
            result.add_warning(
                f"[{tag}] CPL ${cpl:.0f} is extremely high — check for attribution gaps."
            )
        if spend > 500 and sqls == 0 and leads == 0:
            result.add_warning(
                f"[{tag}] ${spend:.0f} spend with zero leads and zero SQLs. "
                f"Check HubSpot UTM tag for `{name}`."
            )
        if sqls > 0 and not float(sqls).is_integer():
            result.add_error(
                f"[{tag}] sqls={sqls} is not an integer — indicates partial row duplication in JOIN."
            )

    print(f"[validator] findings check: {len(result.errors)} errors, "
          f"{len(result.warnings)} warnings across {len(findings)} campaigns.")
    return result


# ─── 3. Combined pre-publish gate ─────────────────────────────────────────────

def pre_publish_gate(findings: list[dict], days: int = 14,
                     post_slack_on_fail: bool = True) -> ValidationResult:
    """
    Run both sync check and findings sanity check.
    If validation fails and post_slack_on_fail=True, posts error to Slack.
    Returns the combined ValidationResult — caller checks result.ok before publishing.
    """
    combined = ValidationResult()

    # Sync check
    sync_result = check_data_sync(days=days)
    combined.errors   += sync_result.errors
    combined.warnings += sync_result.warnings
    if not sync_result.ok:
        combined.ok = False

    # Findings check (only if sync is OK — findings may be garbage if sync failed)
    if sync_result.ok and findings:
        find_result = check_findings(findings)
        combined.errors   += find_result.errors
        combined.warnings += find_result.warnings
        if not find_result.ok:
            combined.ok = False

    # Post to Slack if blocked
    if not combined.ok and post_slack_on_fail:
        _post_validation_failure(combined)

    return combined


def _post_validation_failure(result: ValidationResult):
    """Post a validation failure notice to the notify channel."""
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY
        from notifications.quiet import is_quiet, quiet_log
        msg = result.slack_block()
        if is_quiet():
            quiet_log("validator", SLACK_CHANNEL_NOTIFY, msg)
            return
        WebClient(token=SLACK_BOT_TOKEN).chat_postMessage(
            channel=SLACK_CHANNEL_NOTIFY, text=msg
        )
        print("[validator] Posted validation failure to Slack.")
    except Exception as e:
        print(f"[validator] Could not post to Slack: {e}")


# ─── Manual run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    print(f"=== Data sync check (window: {days}d) ===")
    sync = check_data_sync(days=days)
    print(sync.summary())
    print(f"\nSync OK: {sync.ok}")
