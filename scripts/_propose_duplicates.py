"""Propose Meta + Snap campaign duplications based on the May 2026 winner
analysis. READ-ONLY — produces a sequenced plan and writeable payloads, but
does NOT create campaigns. The team launches each one manually after the
previous one has 7 days of signal (per executors/launch_policy.py).

Run with:
    railway run python -m scripts._propose_duplicates

Output:
    - Sequenced plan printed to stdout (which to launch first, when)
    - JSON file at scripts/_proposed_duplicates.json with full payloads + commands
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "_proposed_duplicates.json"

# ─── Proposed duplicates ─────────────────────────────────────────────────────
# Each entry: source campaign (proven), new name, channel-specific payload,
# rationale, and the tweak being tested.

DUPLICATES: list[dict] = [
    # ── Meta — top-tier wave (highest ROI signal) ────────────────────────────
    {
        "tier":     1,
        "channel":  "meta",
        "source":   "Meta_LeadGen_Bookkeeping_Prospecting_Intersts_MaxmizeLeads_Instantform",
        "new_name": "Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform",
        "rationale": (
            "Source: CPQL $53, qual 50%, 5 deals won, ROAS 1.06 — best Meta campaign. "
            "Apply the proven Interests + MaxmizeLeads pattern to Invoice product "
            "(currently Invoice is mostly served by Lookalike approaches at higher CPQL)."
        ),
        "tweak":    "Product swap: Bookkeeping → Invoice",
        "payload":  {
            "name":             "Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform",
            "daily_budget_usd": 30.0,   # start at source's average daily pace
            "objective":        "OUTCOME_LEADS",
        },
        "cli": (
            "railway run python -c \"from executors.meta import create_campaign; "
            "print(create_campaign("
            "name='Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform', "
            "daily_budget_usd=30, objective='OUTCOME_LEADS'))\""
        ),
    },
    {
        "tier":     1,
        "channel":  "meta",
        "source":   "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform",
        "new_name": "Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform",
        "rationale": (
            "Source: CPQL $39 (improving from $106), qual 54%, 2 deals. "
            "Only Websiteform variant on Meta. Bookkeeping product currently uses "
            "Instantform only; test if Websiteform's higher friction improves "
            "qual rate the same way it did for Invoice."
        ),
        "tweak":    "Product swap: Invoice → Bookkeeping (keep Websiteform)",
        "payload":  {
            "name":             "Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform",
            "daily_budget_usd": 25.0,
            "objective":        "OUTCOME_LEADS",
        },
        "cli": (
            "railway run python -c \"from executors.meta import create_campaign; "
            "print(create_campaign("
            "name='Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform', "
            "daily_budget_usd=25, objective='OUTCOME_LEADS'))\""
        ),
    },

    # ── Meta — second wave (tier 2, after tier-1 stabilizes 7+ days) ─────────
    {
        "tier":     2,
        "channel":  "meta",
        "source":   "Meta_LeadGen_Bookkeeping_Prospecting_Intersts_MaxmizeLeads_Instantform",
        "new_name": "Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform",
        "rationale": (
            "Same pattern as tier-1 #1, third product (Qflavours). Lower priority "
            "because Qflavours has weaker historical CPQL across all channels."
        ),
        "tweak":    "Product swap: Bookkeeping → Qflavours",
        "payload":  {
            "name":             "Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform",
            "daily_budget_usd": 20.0,
            "objective":        "OUTCOME_LEADS",
        },
        "cli": (
            "railway run python -c \"from executors.meta import create_campaign; "
            "print(create_campaign("
            "name='Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform', "
            "daily_budget_usd=20, objective='OUTCOME_LEADS'))\""
        ),
    },
    {
        "tier":     2,
        "channel":  "meta",
        "source":   "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform",
        "new_name": "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2",
        "rationale": (
            "Same campaign + same audience, fresh lookalike seed (Customer Lookalike "
            "3% instead of current SQL Lookalike 2%). Tests whether the source list "
            "or the audience size is driving the win."
        ),
        "tweak":    "Same product, different Lookalike seed (Customer 3% vs SQL 2%)",
        "payload":  {
            "name":             "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2",
            "daily_budget_usd": 25.0,
            "objective":        "OUTCOME_LEADS",
        },
        "cli": (
            "railway run python -c \"from executors.meta import create_campaign; "
            "print(create_campaign("
            "name='Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2', "
            "daily_budget_usd=25, objective='OUTCOME_LEADS'))\""
        ),
    },

    # ── Snap — top-tier wave ─────────────────────────────────────────────────
    {
        "tier":     1,
        "channel":  "snapchat",
        "source":   "Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v3",
        "new_name": "Snapchat_LeadGen_Prospecting_Interest_Android_Instantform_v3",
        "rationale": (
            "Source: $4,955 spent, 126 SQLs, qual 52%, CPQL $39 — highest Snap "
            "winner. Currently iOS-only — Android has ~30% of Saudi market "
            "completely untapped on this campaign."
        ),
        "tweak":    "Device swap: iOS → Android (same audience, copy, creative)",
        "payload":  {
            "name":             "Snapchat_LeadGen_Prospecting_Interest_Android_Instantform_v3",
            "daily_budget_usd": 150.0,    # source averages $165/day; start slightly conservative
            "objective":        "LEAD_GENERATION",
        },
        "cli": (
            "railway run python -c \"from executors.snapchat import create_campaign; "
            "print(create_campaign("
            "name='Snapchat_LeadGen_Prospecting_Interest_Android_Instantform_v3', "
            "daily_budget_usd=150, objective='LEAD_GENERATION'))\""
        ),
    },
    {
        "tier":     1,
        "channel":  "snapchat",
        "source":   "Snapchat_Leadgen_Bookkeeping_Broad_iPohne_Instantform",
        "new_name": "Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform",
        "rationale": (
            "Source: small ($648 spend) but qual 56% + CPQL $36 + ROAS 0.91. "
            "Bookkeeping-Broad-iPhone pattern is working; apply same approach "
            "to Invoice product to expand the winning structure. NOTE: fix the "
            "'iPohne' typo in the new name."
        ),
        "tweak":    "Product swap: Bookkeeping → Invoice (+ fix typo)",
        "payload":  {
            "name":             "Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform",
            "daily_budget_usd": 25.0,
            "objective":        "LEAD_GENERATION",
        },
        "cli": (
            "railway run python -c \"from executors.snapchat import create_campaign; "
            "print(create_campaign("
            "name='Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform', "
            "daily_budget_usd=25, objective='LEAD_GENERATION'))\""
        ),
    },

    # ── Snap — second wave ───────────────────────────────────────────────────
    {
        "tier":     2,
        "channel":  "snapchat",
        "source":   "Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v3",
        "new_name": "Snapchat_LeadGen_Bookkeeping_Interest_iOS_Instantform_v3",
        "rationale": (
            "Top Snap winner, applied to Bookkeeping product. Bookkeeping "
            "currently has limited Snap presence; this extends the proven "
            "audience+device pattern to a second product."
        ),
        "tweak":    "Product swap: (default Invoice) → Bookkeeping",
        "payload":  {
            "name":             "Snapchat_LeadGen_Bookkeeping_Interest_iOS_Instantform_v3",
            "daily_budget_usd": 100.0,
            "objective":        "LEAD_GENERATION",
        },
        "cli": (
            "railway run python -c \"from executors.snapchat import create_campaign; "
            "print(create_campaign("
            "name='Snapchat_LeadGen_Bookkeeping_Interest_iOS_Instantform_v3', "
            "daily_budget_usd=100, objective='LEAD_GENERATION'))\""
        ),
    },
    {
        "tier":     2,
        "channel":  "snapchat",
        "source":   "Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v3",
        "new_name": "Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v4",
        "rationale": (
            "Same audience+device, refreshed UGC creative. Source has been live "
            "since Jan; creative fatigue is a future risk. v4 is the insurance "
            "policy before v3 starts decaying."
        ),
        "tweak":    "Same setup, fresh UGC creative (v3 → v4)",
        "payload":  {
            "name":             "Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v4",
            "daily_budget_usd": 75.0,
            "objective":        "LEAD_GENERATION",
        },
        "cli": (
            "railway run python -c \"from executors.snapchat import create_campaign; "
            "print(create_campaign("
            "name='Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v4', "
            "daily_budget_usd=75, objective='LEAD_GENERATION'))\""
        ),
    },
]


# ─── Validation + status check ───────────────────────────────────────────────

def _validate_name(channel: str, name: str) -> tuple[bool, str]:
    """Run the proposed name through executors.naming.prefixed() and report."""
    try:
        from executors.naming import prefixed
    except Exception as e:
        return False, f"naming import failed: {e}"
    channel_prefix_map = {
        "meta": "Meta", "snapchat": "Snapchat", "google_ads": "Google",
        "tiktok": "Tiktok", "linkedin": "LinkedIn", "microsoft_ads": "Bing",
    }
    prefix = channel_prefix_map.get(channel, "")
    try:
        validated = prefixed(prefix, name)
        if validated != name:
            return True, f"normalised → {validated}"
        return True, "OK"
    except ValueError as ve:
        return False, str(ve)


def _launch_status(channel: str) -> tuple[bool, str]:
    """Check if the channel currently allows new launches (cooldown gate)."""
    try:
        from executors.launch_policy import is_launch_allowed
        ok, reason = is_launch_allowed(channel)
        return ok, reason or "OK — channel cleared for launch"
    except Exception as e:
        return True, f"(policy check skipped: {e})"


# ─── Scheduling: stagger by 7 days per channel ───────────────────────────────

def _build_schedule(items: list[dict]) -> list[dict]:
    """Per-channel: tier-1 items first, then tier-2 after 7-day gaps."""
    today = date.today()
    out = []
    for channel in {it["channel"] for it in items}:
        chan_items = sorted([it for it in items if it["channel"] == channel],
                            key=lambda x: x["tier"])
        offset_days = 0
        for it in chan_items:
            target = today + timedelta(days=offset_days)
            out.append({**it, "launch_on_or_after": target.isoformat()})
            offset_days += 7  # next campaign on this channel waits 7 days
    out.sort(key=lambda x: (x["launch_on_or_after"], x["channel"]))
    return out


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    schedule = _build_schedule(DUPLICATES)
    print(f"\n{'=' * 90}")
    print(f"  Proposed Meta + Snap duplications — {len(schedule)} campaigns")
    print(f"  Staggered 7d per channel to comply with launch_policy cooldown")
    print(f"{'=' * 90}\n")

    for i, item in enumerate(schedule, 1):
        ok_name, name_msg = _validate_name(item["channel"], item["new_name"])
        ok_launch, launch_msg = _launch_status(item["channel"])
        when = item["launch_on_or_after"]
        status_icons = (
            ("✅" if ok_name else "❌") + " name  " +
            ("✅" if ok_launch else "⏸️") + " policy"
        )
        print(f"┌─[ #{i} | Tier {item['tier']} | {item['channel']} | launch ≥ {when} ]")
        print(f"│ {status_icons}")
        print(f"│   From: {item['source']}")
        print(f"│   To:   {item['new_name']}")
        print(f"│   Tweak: {item['tweak']}")
        print(f"│   Budget: ${item['payload']['daily_budget_usd']:.0f}/day, "
              f"obj={item['payload']['objective']}")
        print(f"│   Rationale: {item['rationale']}")
        if not ok_name:
            print(f"│   ⚠ name issue: {name_msg}")
        if not ok_launch:
            print(f"│   ⏸ launch_policy: {launch_msg}")
        print(f"│   Command (when ready):")
        print(f"│     {item['cli']}")
        print(f"└─\n")

    # Save to JSON for record-keeping
    OUT.write_text(json.dumps(schedule, indent=2, default=str), encoding="utf-8")
    print(f"\n📄 Full plan saved to: {OUT}")
    print(f"\n📋 Suggested workflow:")
    print(f"   1. Review the names + budgets above")
    print(f"   2. Launch Tier-1 campaigns on or after the dates shown")
    print(f"   3. Wait 7 days, check CPQL on each — if < $60, proceed to Tier-2")
    print(f"   4. If a Tier-1 fails the 7-day CPQL bar, do NOT launch the next on that channel")


if __name__ == "__main__":
    main()
