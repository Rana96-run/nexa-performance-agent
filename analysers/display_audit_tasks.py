"""
analysers/display_audit_tasks.py
=================================
Turn display_audit.py findings into Asana tasks. One consolidated task
per (channel, bucket) — never one task per ad.

Logged under role='performance_audit', channel=<channel> so the activity
dashboard's performance_audit row aggregates Google + MS + all 4 display
channels in one place.
"""
from __future__ import annotations

from analysers.display_audit import run_full_audit
from executors.asana import create_task
from logs.activity_logger import log_activity_async


def _ad_card(rows: list[dict], mode: str) -> str:
    if not rows:
        return ""
    cards = []
    for i, r in enumerate(rows[:30], 1):
        header = f"**[{i}/{len(rows)}]**\n" if len(rows) > 1 else ""
        if mode == "ctr_fatigue":
            cards.append(
                f"{header}"
                f"**Ad:**           {r['ad_name']}\n"
                f"**Ad Set:**       {r['adset']}\n"
                f"**Campaign:**     {r['campaign']}\n"
                f"**14d Spend:**    ${r['spend_14d']:.0f}\n"
                f"**14d Conv:**     {r['conv_14d']:.0f}\n"
                f"**CTR drop:**     {r['ctr_first7d']:.2%} → {r['ctr_last7d']:.2%} ({r['ctr_drop_pct']:.0f}% decline)\n"
                f"**Verdict:**      Refresh creative — fatigue"
            )
        elif mode == "frequency_sat":
            cards.append(
                f"{header}"
                f"**Ad:**           {r['ad_name']}\n"
                f"**Ad Set:**       {r['adset']}\n"
                f"**Campaign:**     {r['campaign']}\n"
                f"**14d Spend:**    ${r['spend_14d']:.0f}\n"
                f"**14d Conv:**     {r['conv_14d']:.0f}\n"
                f"**Avg Frequency:**{r['avg_freq']:.1f}x  (threshold > 2.5)\n"
                f"**Verdict:**      Expand audience or pause — same users seeing this ad too often"
            )
        else:  # zero_conv_pause
            cards.append(
                f"{header}"
                f"**Ad:**           {r['ad_name']}\n"
                f"**Ad Set:**       {r['adset']}\n"
                f"**Campaign:**     {r['campaign']}\n"
                f"**14d Spend:**    ${r['spend_14d']:.0f}\n"
                f"**14d Conv:**     0\n"
                f"**Verdict:**      Pause — burnt $50+ over 14 days with zero conversions"
            )
    return "\n\n---\n\n".join(cards) + (
        f"\n\n_…and {len(rows) - 30} more_" if len(rows) > 30 else "\n"
    )


_CHANNEL_LABEL = {
    "meta":     "Meta",
    "snapchat": "Snapchat",
    "tiktok":   "TikTok",
    "linkedin": "LinkedIn",
}


def _create_one_bucket(channel: str, bucket: str, findings: list[dict]) -> str | None:
    if not findings:
        return None
    label = _CHANNEL_LABEL[channel]
    body_intro = {
        "ctr_fatigue":     (f"Daily creative-fatigue audit (last 14d). {len(findings)} {label} ad(s) "
                             f"with last-7d CTR ≥ 30% lower than the prior 7d.\n\n"
                             f"**Why this matters:** When an ad's audience has seen it too many times, "
                             f"CTR collapses and CPC rises. Refresh the creative or rotate it out.\n\n"),
        "frequency_sat":   (f"Daily frequency-saturation audit (last 14d). {len(findings)} {label} ad(s) "
                             f"with avg frequency > 2.5x.\n\n"
                             f"**Why this matters:** Audience is over-saturated — same users see this ad "
                             f"3+ times. Expand audience targeting or pause to avoid ad fatigue.\n\n"),
        "zero_conv_pause": (f"Daily zero-conversion pause audit (last 14d). {len(findings)} {label} ad(s) "
                             f"spent $50+ with 0 conversions over 14 days.\n\n"
                             f"**Why this matters:** This is wasted budget. Pause the ad and reallocate "
                             f"budget to performing creatives.\n\n"),
    }[bucket]
    title_suffix = {
        "ctr_fatigue":     f"creative fatigue ({len(findings)})",
        "frequency_sat":   f"frequency saturation ({len(findings)})",
        "zero_conv_pause": f"zero-conv pause ({len(findings)})",
    }[bucket]
    action = {
        "ctr_fatigue":     "optimize",
        "frequency_sat":   "optimize",
        "zero_conv_pause": "pause",
    }[bucket]

    body = body_intro + _ad_card(findings, mode=bucket)
    gid = create_task(
        title=f"{label} — {title_suffix}",
        description=body,
        project_key="daily_activity" if bucket == "zero_conv_pause" else "optimization",
        task_type="Recommendation" if bucket != "zero_conv_pause" else "Pause",
        channel=channel,
        asset_level="ad",
        action=action,
    )
    return gid


def create_audit_tasks() -> list[tuple[str, str | None]]:
    """Run all-channel display audit + create Asana tasks. Returns [(title, gid)]."""
    full = run_full_audit()
    out: list[tuple[str, str | None]] = []
    summary: dict[str, dict[str, int]] = {}

    for channel, buckets in full.items():
        summary[channel] = {k: len(v) for k, v in buckets.items()}
        for bucket, findings in buckets.items():
            gid = _create_one_bucket(channel, bucket, findings)
            if gid:
                out.append((f"{channel} {bucket} ({len(findings)})", gid))

    log_activity_async(
        role="performance_audit", action="create_audit_tasks",
        status="success", channel="display",
        rows_affected=sum(sum(v.values()) for v in summary.values()),
        details=summary,
    )
    return out
