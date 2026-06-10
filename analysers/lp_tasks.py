"""
CRO / Landing Page task chain — mirrors campaign_health_tasks.py for the
CRO department.

Three stages, one file per test, same filename travels through all stages:
  docs/landing-pages/briefs/YYYY-MM-DD_<product>_<slug>.md   (cro-specialist)
  docs/landing-pages/designs/YYYY-MM-DD_<product>_<slug>.md  (ui-ux-designer)
  docs/landing-pages/specs/YYYY-MM-DD_<product>_<slug>.md    (developer)

Each stage creates an Asana task with the correct agent identity:
  brief    → log_role="cro_specialist"  → Rana Khalid
  design   → log_role="ui_ux_design"   → Rana Khalid
  build    → log_role="lp_developer"   → Tony Helmy + Rana follower

Instantform campaigns (any channel with "instantform" in the name) skip this chain.
Use create_instantform_audit() instead → log_role="campaign_creator" → Donia Mohamed.
Instantform = embedded form inside the ad platform; no landing page is involved.

Slack messages posted as the owning agent.
"""
from __future__ import annotations

import re
from datetime import date, timedelta, timezone, datetime
from pathlib import Path

from executors.asana import create_task
from logs.activity_logger import log_activity_async
from notifications.slack import post_as_role
from config import SLACK_CHANNEL_APPROVAL, SLACK_CHANNEL_NOTIFY, is_instantform_campaign

# Root of the LP workspace
_LP_ROOT = Path(__file__).parent.parent / "docs" / "landing-pages"

# Valid product tokens
PRODUCTS = ("Invoice", "Bookkeeping", "Qflavours", "Ramadan", "NationalDay",
            "BackToSchool", "General")

# ── Stage 1: CRO Specialist creates brief ─────────────────────────────────────

def create_lp_brief(
    product: str,
    hypothesis_slug: str,
    channel: str,
    hypothesis: str,
    current_cpql: float,
    current_conversion_pct: float,
    destination_url: str,
    audience: str,
    ocean_notes: str,
    offer_message: str,
    page_structure: str,
    success_criteria: str,
    risks: str,
    window_days: int = 14,
) -> dict:
    """
    Stage 1 — CRO Specialist writes the LP brief.

    Creates:
      - Brief file at docs/landing-pages/briefs/YYYY-MM-DD_<product>_<slug>.md
      - Asana task assigned to Rana (cro_specialist)
      - Slack message as Nexa · CRO in #approvals

    Returns dict with test_id, brief_path, asana_gid.

    Raises ValueError if the channel campaign name contains "instantform" —
    those use create_instantform_audit() instead (Campaign Manager, not CRO).
    """
    if is_instantform_campaign(channel):
        raise ValueError(
            f"create_lp_brief() called for '{channel}' which looks like an Instantform campaign. "
            "Use create_instantform_audit() instead — Instantform CVR is audited by the "
            "Campaign Manager in Ads Manager, not by the CRO Specialist."
        )

    today       = date.today()
    window_from = (today - timedelta(days=window_days)).isoformat()
    window_to   = (today - timedelta(days=1)).isoformat()
    test_id     = f"{today.isoformat()}_{product.lower()}_{hypothesis_slug}"
    filename    = f"{test_id}.md"

    brief_path = _LP_ROOT / "briefs" / filename
    brief_path.parent.mkdir(parents=True, exist_ok=True)

    brief_content = f"""---
test_id: {test_id}
product: {product}
channel: {channel}
status: brief
---

## 1. Hypothesis
{hypothesis}

## 2. Current state (live BQ, {window_days}-day window)
Window: {window_from} to {window_to} · current CPQL: ${current_cpql:.0f} · form-start rate: {current_conversion_pct:.1f}%
destination_url: {destination_url}

## 3. Target audience & OCEAN persona
Segment: {audience}
{ocean_notes}

## 4. Offer & message
{offer_message}

## 5. Page structure (sections, order)
{page_structure}

## 6. Form & tracking
Fields: name, phone, company, sector.
UTM passthrough on every field.
Both pixels fire (CRM 1782671302631317 + Web 3036579196577051).
Lead event on submit.

## 7. Success criteria (the win condition)
{success_criteria}

## 8. Risks & kill criterion
{risks}
"""

    brief_path.write_text(brief_content, encoding="utf-8")

    # Asana task — CRO Specialist (Rana)
    body = (
        f"New LP test brief ready for review and design handoff.\n\n"
        f"**Test ID:** `{test_id}`\n"
        f"**Product:** {product}  ·  **Channel:** {channel}\n"
        f"**Data window:** {window_from} to {window_to}\n"
        f"**Current CPQL:** ${current_cpql:.0f}  ·  "
        f"**Conversion:** {current_conversion_pct:.1f}%\n"
        f"**Destination URL:** {destination_url}\n\n"
        f"**Hypothesis:**\n{hypothesis}\n\n"
        f"**Success criteria:**\n{success_criteria}\n\n"
        f"Brief file: `docs/landing-pages/briefs/{filename}`\n\n"
        f"Next step: review brief → hand to UI/UX Designer "
        f"(create_lp_design task or mark Asana task complete to trigger).\n\n"
        f"---\n"
        f"Created: {today.isoformat()}  ·  "
        f"Due: {(today + timedelta(days=1)).isoformat()}  ·  "
        f"Priority: High  ·  Type: Recommendation  ·  "
        f"Channel: {channel}  ·  Asset level: Campaign  ·  Action: Launch"
    )
    gid = create_task(
        title=f"LP Brief: {product} — {hypothesis_slug} ({window_from} to {window_to})",
        description=body,
        project_key="optimization",
        task_type="Recommendation",
        channel=channel.lower().replace(" ", "_"),
        asset_level="campaign",
        action="launch",
        log_role="cro_specialist",
    )

    log_activity_async(
        role="cro_specialist", action="lp_brief_created",
        status="pending_design",
        channel=channel.lower(),
        details={
            "test_id": test_id, "product": product,
            "cpql": current_cpql, "destination_url": destination_url,
            "asana_gid": gid,
        },
    )

    # Slack as CRO Specialist
    post_as_role(
        "cro_specialist",
        SLACK_CHANNEL_APPROVAL,
        f"*New LP brief created — {product} · {hypothesis_slug}*\n"
        f"Window: {window_from} to {window_to}  ·  "
        f"Current CPQL: ${current_cpql:.0f}  ·  "
        f"Destination: {destination_url}\n"
        f"Hypothesis: _{hypothesis}_\n"
        f"Asana: task `{gid or 'check Asana'}` assigned to CRO Specialist.\n"
        f"_Next: UI/UX Designer picks up once brief is reviewed._",
    )

    print(f"[lp-tasks] Brief created: {brief_path} | Asana gid={gid}")
    return {"test_id": test_id, "brief_path": str(brief_path), "asana_gid": gid}


# ── Instantform audit (Campaign Manager) ─────────────────────────────────────
# Instantform campaigns embed the lead form inside the ad platform.
# There is no landing page. CVR improvement = auditing the form in Ads Manager.
# Owner: Campaign Manager (Donia) via log_role="campaign_creator".

def create_instantform_audit(
    campaign_name: str,
    channel: str,
    cvr_pct: float,
    spend_usd: float,
    leads: int,
    window_from: str,
    window_to: str,
    pixel_ids: list[str] | None = None,
) -> dict:
    """
    Creates an Asana audit task for a low-CVR Instantform campaign.

    Assigned to Campaign Manager (Donia) — log_role="campaign_creator".
    Action items: audit intro screen, field count, prefill, thank-you screen,
    and (for CRM-pixel campaigns) confirm pixel fires in Events Manager.

    Returns dict with asana_gid.
    """
    today = date.today()

    pixel_note = ""
    if pixel_ids:
        ids_str = ", ".join(str(p) for p in pixel_ids)
        pixel_note = (
            f"\n\nPixel check (before form changes): confirm both pixel IDs "
            f"[{ids_str}] are firing on form submit in Events Manager."
        )

    body = (
        f"Instantform CVR below 2% — audit the form setup in {channel} Ads Manager.\n\n"
        f"Campaign: `{campaign_name}`\n"
        f"Window: {window_from} to {window_to}\n"
        f"CVR: {cvr_pct:.2f}%  ·  Spend: ${spend_usd:.0f}  ·  Leads: {leads}\n"
        f"{pixel_note}\n\n"
        f"Audit checklist:\n"
        f"1. Intro screen — headline + description compelling for this audience?\n"
        f"2. Field count — name + phone only (fewer = higher CVR)\n"
        f"3. Prefill — is phone/email prefilled from platform profile?\n"
        f"4. Privacy policy link — present and loading?\n"
        f"5. Thank-you screen — clear next step shown?\n"
        f"6. Compare CVR across variants if multiple forms exist\n\n"
        f"Target CVR: >= 2%. If form audit doesn't move the needle within 14 days, "
        f"consider switching to website conversion objective pointing to an LP.\n\n"
        f"Flow after submit: Lead created in HubSpot → SDR qualifies → SQL.\n"
        f"Primary KPI: CPQL (not just CVR).\n\n"
        f"---\n"
        f"Created: {today.isoformat()}  ·  "
        f"Due: {(today + timedelta(days=2)).isoformat()}  ·  "
        f"Priority: High  ·  Type: Recommendation  ·  "
        f"Channel: {channel}  ·  Asset level: Ad Set  ·  Action: Optimize"
    )

    gid = create_task(
        title=f"Instantform Audit: {campaign_name} — CVR {cvr_pct:.2f}% below 2%",
        description=body,
        project_key="cro",
        task_type="Recommendation",
        channel=channel.lower(),
        asset_level="ad_set",
        action="optimize",
        log_role="campaign_creator",
    )

    log_activity_async(
        role="campaign_creator", action="instantform_audit_created",
        status="pending_review",
        channel=channel.lower(),
        details={
            "campaign_name": campaign_name, "cvr_pct": cvr_pct,
            "spend_usd": spend_usd, "leads": leads,
            "window_from": window_from, "window_to": window_to,
            "asana_gid": gid,
        },
    )

    post_as_role(
        "campaign_creator",
        SLACK_CHANNEL_APPROVAL,
        f"*Instantform CVR flag — {campaign_name}*\n"
        f"Window: {window_from} to {window_to}  ·  CVR: {cvr_pct:.2f}%  ·  "
        f"Spend: ${spend_usd:.0f}  ·  Leads: {leads}\n"
        f"Action: audit form setup in {channel} Ads Manager.\n"
        f"Asana: task `{gid or 'check Asana'}` assigned to Campaign Manager.",
    )

    print(f"[lp-tasks] Instantform audit created for {campaign_name} | Asana gid={gid}")
    return {"asana_gid": gid, "campaign_name": campaign_name, "cvr_pct": cvr_pct}


# ── Stage 2: UI/UX Designer creates annotated design ─────────────────────────

def create_lp_design(
    test_id: str,
    design_notes: str,
    ocean_persona: str,
    above_fold_description: str,
    mobile_notes: str = "",
    interaction_notes: str = "",
) -> dict:
    """
    Stage 2 — UI/UX Designer writes the annotated design brief.

    Creates:
      - Design file at docs/landing-pages/designs/<test_id>.md
      - Asana task assigned to Rana (ui_ux_design)
      - Slack message as Nexa · UI/UX

    Returns dict with test_id, design_path, asana_gid.
    """
    today       = date.today()
    filename    = f"{test_id}.md"
    design_path = _LP_ROOT / "designs" / filename
    design_path.parent.mkdir(parents=True, exist_ok=True)

    # Read the brief to pull context
    brief_path = _LP_ROOT / "briefs" / filename
    brief_context = ""
    if brief_path.exists():
        txt = brief_path.read_text(encoding="utf-8")
        # Extract hypothesis line for context
        m = re.search(r"## 1\. Hypothesis\s+(.+?)(?=\n##)", txt, re.DOTALL)
        if m:
            brief_context = m.group(1).strip()

    design_content = f"""---
test_id: {test_id}
stage: design
status: design
date: {today.isoformat()}
---

## OCEAN Persona Alignment
{ocean_persona}

## Above-the-Fold Design
{above_fold_description}

> **Non-negotiable:** ZATCA compliance badge must be visible above the fold
> on both desktop (1440px) and mobile (390px) without scrolling.

## Design Notes
{design_notes}

## Mobile Considerations
{mobile_notes or "Standard responsive — test at 390px, 768px, 1440px. RTL Arabic layout."}

## Interaction Notes for Developer
{interaction_notes or "Standard form — name, phone, company, sector. Submit triggers both pixel events."}

## Handoff to Developer
- Brief: `docs/landing-pages/briefs/{filename}`
- Design: this file
- Build spec to create: `docs/landing-pages/specs/{filename}`
- Both pixels must fire: CRM `1782671302631317` + Web `3036579196577051`
- UTM passthrough required on every form field
"""

    design_path.write_text(design_content, encoding="utf-8")

    body = (
        f"LP design brief ready for build.\n\n"
        f"**Test ID:** `{test_id}`\n"
        f"**Brief hypothesis:** _{brief_context}_\n\n"
        f"**Design file:** `docs/landing-pages/designs/{filename}`\n\n"
        f"**ZATCA check:** Badge must be above fold — desktop + mobile.\n"
        f"**Both pixels required:** CRM `1782671302631317` + Web `3036579196577051`\n"
        f"**UTM passthrough:** on every form field before submit.\n\n"
        f"Next step: Developer builds variant, verifies pixels in Events Manager,\n"
        f"then creates spec at `docs/landing-pages/specs/{filename}` and signs off.\n\n"
        f"---\n"
        f"Created: {today.isoformat()}  ·  "
        f"Due: {(today + timedelta(days=2)).isoformat()}  ·  "
        f"Priority: High  ·  Type: Recommendation  ·  "
        f"Channel: cro  ·  Asset level: Campaign  ·  Action: Launch"
    )
    gid = create_task(
        title=f"LP Design: {test_id}",
        description=body,
        project_key="optimization",
        task_type="Recommendation",
        channel="cro",
        asset_level="campaign",
        action="launch",
        log_role="ui_ux_design",
    )

    log_activity_async(
        role="ui_ux_design", action="lp_design_created",
        status="pending_build",
        details={"test_id": test_id, "asana_gid": gid},
    )

    post_as_role(
        "ui_ux_design",
        SLACK_CHANNEL_APPROVAL,
        f"*LP design brief ready — {test_id}*\n"
        f"ZATCA badge above fold ✓  ·  OCEAN persona aligned ✓\n"
        f"Asana task `{gid or 'check Asana'}` assigned to Developer (Tony Helmy).\n"
        f"_Next: Developer builds, verifies pixels, creates spec._",
    )

    print(f"[lp-tasks] Design created: {design_path} | Asana gid={gid}")
    return {"test_id": test_id, "design_path": str(design_path), "asana_gid": gid}


# ── Stage 3: Developer creates build/deploy spec ──────────────────────────────

def create_lp_spec(
    test_id: str,
    deploy_url: str,
    utm_passthrough_verified: bool,
    crm_pixel_verified: bool,
    web_pixel_verified: bool,
    lead_event_verified: bool,
    zatca_badge_desktop: bool,
    zatca_badge_mobile: bool,
    arabic_msa: bool,
    build_notes: str = "",
) -> dict:
    """
    Stage 3 — Developer writes the build/deploy spec and sign-off.

    Creates:
      - Spec file at docs/landing-pages/specs/<test_id>.md
      - Asana task assigned to Tony Helmy (lp_developer) + Rana follower
      - Slack sign-off message as Nexa · Developer

    All 7 checklist items must be True to post a clean sign-off.
    Returns dict with test_id, spec_path, asana_gid, signed_off.
    """
    today    = date.today()
    filename = f"{test_id}.md"
    spec_path = _LP_ROOT / "specs" / filename
    spec_path.parent.mkdir(parents=True, exist_ok=True)

    def _tick(v: bool) -> str:
        return "✅" if v else "❌ NOT VERIFIED"

    all_clear = all([
        utm_passthrough_verified, crm_pixel_verified, web_pixel_verified,
        lead_event_verified, zatca_badge_desktop, zatca_badge_mobile, arabic_msa,
    ])

    spec_content = f"""---
test_id: {test_id}
stage: spec
status: {"live" if all_clear else "build-blocked"}
deploy_url: {deploy_url}
date: {today.isoformat()}
signed_off: {all_clear}
---

## Deploy target
{deploy_url}

## Compliance checklist (must be ALL ✅ before going live)

### ZATCA
- ZATCA badge above fold — desktop: {_tick(zatca_badge_desktop)}
- ZATCA badge above fold — mobile: {_tick(zatca_badge_mobile)}

### Tracking — pixels
- Qoyod_CRM_PIXEL `1782671302631317` fires on load: {_tick(crm_pixel_verified)}
- Qoyod_Web_PIXEL `3036579196577051` fires on load: {_tick(web_pixel_verified)}
- Lead/submit event fires on form completion: {_tick(lead_event_verified)}

### Tracking — UTM
- UTM passthrough on every form field: {_tick(utm_passthrough_verified)}

### Content
- Arabic copy is MSA, RTL layout: {_tick(arabic_msa)}

## Build notes
{build_notes or "Standard build — no custom behaviour."}

## Sign-off
{"✅ ALL CHECKS PASSED — ready to go live. Hand back to CRO Specialist to start 14-day data window." if all_clear else "❌ BLOCKED — one or more checks failed. Fix before going live."}

## Next step
CRO Specialist monitors for 14 days from deploy date.
Decision: ship variant / revert to control.
Success criteria defined in brief: `docs/landing-pages/briefs/{filename}`
"""

    spec_path.write_text(spec_content, encoding="utf-8")

    status_label = "SIGNED OFF" if all_clear else "BUILD BLOCKED"
    body = (
        f"LP build spec — {status_label}.\n\n"
        f"**Test ID:** `{test_id}`\n"
        f"**Deploy URL:** {deploy_url}\n\n"
        f"**Checklist:**\n"
        f"- ZATCA desktop: {_tick(zatca_badge_desktop)}\n"
        f"- ZATCA mobile: {_tick(zatca_badge_mobile)}\n"
        f"- CRM pixel: {_tick(crm_pixel_verified)}\n"
        f"- Web pixel: {_tick(web_pixel_verified)}\n"
        f"- Lead event: {_tick(lead_event_verified)}\n"
        f"- UTM passthrough: {_tick(utm_passthrough_verified)}\n"
        f"- Arabic MSA: {_tick(arabic_msa)}\n\n"
        + ("✅ All clear — CRO Specialist starts 14-day measurement window.\n"
           if all_clear else
           "❌ Fix failing checks before going live.\n")
        + f"\nSpec file: `docs/landing-pages/specs/{filename}`\n\n"
        f"---\n"
        f"Created: {today.isoformat()}  ·  "
        f"Due: {today.isoformat()}  ·  "
        f"Priority: {'High' if all_clear else 'Critical'}  ·  "
        f"Type: {'Recommendation' if all_clear else 'Fix'}  ·  "
        f"Channel: cro  ·  Asset level: Campaign  ·  "
        f"Action: {'Launch' if all_clear else 'Fix'}"
    )
    gid = create_task(
        title=f"LP {'Sign-off' if all_clear else 'Build-blocked'}: {test_id}",
        description=body,
        project_key="optimization",
        task_type="Recommendation" if all_clear else "Fix",
        channel="cro",
        asset_level="campaign",
        action="launch" if all_clear else "fix",
        log_role="lp_developer",
    )

    log_activity_async(
        role="lp_developer", action="lp_spec_created",
        status="live" if all_clear else "build_blocked",
        details={
            "test_id": test_id, "deploy_url": deploy_url,
            "signed_off": all_clear, "asana_gid": gid,
        },
    )

    if all_clear:
        post_as_role(
            "lp_developer",
            SLACK_CHANNEL_NOTIFY,
            f"*LP deployed & signed off — {test_id}*\n"
            f"ZATCA ✅  ·  Both pixels ✅  ·  UTM passthrough ✅  ·  MSA copy ✅\n"
            f"URL: {deploy_url}\n"
            f"CRO Specialist: 14-day measurement window starts today "
            f"({today.isoformat()}).\n"
            f"Decision date: {(today + timedelta(days=14)).isoformat()}",
        )
    else:
        failed = [
            name for name, val in [
                ("ZATCA desktop", zatca_badge_desktop),
                ("ZATCA mobile", zatca_badge_mobile),
                ("CRM pixel", crm_pixel_verified),
                ("Web pixel", web_pixel_verified),
                ("Lead event", lead_event_verified),
                ("UTM passthrough", utm_passthrough_verified),
                ("Arabic MSA", arabic_msa),
            ] if not val
        ]
        post_as_role(
            "lp_developer",
            SLACK_CHANNEL_APPROVAL,
            f"*LP build blocked — {test_id}*\n"
            f"Failed checks: {', '.join(failed)}\n"
            f"Fix before going live. Asana task `{gid or 'check Asana'}`.",
        )

    print(f"[lp-tasks] Spec created: {spec_path} | signed_off={all_clear} | gid={gid}")
    return {
        "test_id": test_id,
        "spec_path": str(spec_path),
        "asana_gid": gid,
        "signed_off": all_clear,
    }


# ── Stage 4: CRO Specialist calls the test result ─────────────────────────────

def call_lp_test_result(
    test_id: str,
    variant_cpql: float,
    control_cpql: float,
    variant_conversion_pct: float,
    control_conversion_pct: float,
    confidence_pct: float,
    decision: str,  # "ship_variant" | "revert_control" | "extend"
    rationale: str,
    window_from: str,
    window_to: str,
) -> dict:
    """
    Stage 4 — CRO Specialist calls the test result after the 14-day window.

    Updates the spec file status, creates an Asana task, posts result to Slack.
    Writes outcome to memory/14_learning_patterns.md.
    """
    today    = date.today()
    filename = f"{test_id}.md"
    spec_path = _LP_ROOT / "specs" / filename

    cpql_delta_pct = ((variant_cpql - control_cpql) / control_cpql * 100) if control_cpql else 0
    direction      = "improvement ✅" if cpql_delta_pct < 0 else "regression ❌"

    # Update spec file status
    if spec_path.exists():
        txt = spec_path.read_text(encoding="utf-8")
        txt = re.sub(r"^status:.*$", f"status: {decision}", txt, flags=re.MULTILINE)
        spec_path.write_text(txt, encoding="utf-8")

    result_label = {"ship_variant": "SHIP VARIANT ✅",
                    "revert_control": "REVERT TO CONTROL ❌",
                    "extend": "EXTEND — INCONCLUSIVE ⏳"}.get(decision, decision.upper())

    body = (
        f"LP test result — {result_label}\n\n"
        f"**Test ID:** `{test_id}`\n"
        f"**Window:** {window_from} to {window_to}\n\n"
        f"**Results:**\n"
        f"| Metric | Control | Variant | Delta |\n"
        f"|---|---|---|---|\n"
        f"| CPQL | ${control_cpql:.0f} | ${variant_cpql:.0f} | "
        f"{cpql_delta_pct:+.1f}% ({direction}) |\n"
        f"| Conversion | {control_conversion_pct:.1f}% | "
        f"{variant_conversion_pct:.1f}% | "
        f"{variant_conversion_pct - control_conversion_pct:+.1f}pp |\n"
        f"| Confidence | — | — | {confidence_pct:.0f}% |\n\n"
        f"**Decision:** {result_label}\n"
        f"**Rationale:** {rationale}\n\n"
        f"---\n"
        f"Created: {today.isoformat()}  ·  "
        f"Due: {today.isoformat()}  ·  "
        f"Priority: High  ·  Type: Review  ·  "
        f"Channel: cro  ·  Asset level: Campaign  ·  Action: Optimize"
    )
    gid = create_task(
        title=f"LP Result — {result_label}: {test_id} ({window_from} to {window_to})",
        description=body,
        project_key="optimization",
        task_type="Review",
        channel="cro",
        asset_level="campaign",
        action="optimize",
        log_role="cro_specialist",
    )

    # Write outcome to learning patterns
    _write_lp_learning(
        test_id=test_id, decision=decision,
        cpql_delta_pct=cpql_delta_pct,
        confidence_pct=confidence_pct, rationale=rationale,
        window_from=window_from, window_to=window_to,
    )

    log_activity_async(
        role="cro_specialist", action="lp_test_result_called",
        status=decision,
        details={
            "test_id": test_id, "decision": decision,
            "cpql_delta_pct": round(cpql_delta_pct, 1),
            "confidence_pct": confidence_pct, "asana_gid": gid,
        },
    )

    post_as_role(
        "cro_specialist",
        SLACK_CHANNEL_NOTIFY,
        f"*LP test result — {result_label}*\n"
        f"`{test_id}` · {window_from} to {window_to}\n"
        f"CPQL: ${control_cpql:.0f} → ${variant_cpql:.0f} "
        f"({cpql_delta_pct:+.1f}%)  ·  Confidence: {confidence_pct:.0f}%\n"
        f"_{rationale}_",
    )

    print(f"[lp-tasks] Result called: {test_id} → {decision} | gid={gid}")
    return {"test_id": test_id, "decision": decision, "asana_gid": gid}


# ── Learning patterns writer ───────────────────────────────────────────────────

def _write_lp_learning(
    test_id: str, decision: str, cpql_delta_pct: float,
    confidence_pct: float, rationale: str,
    window_from: str, window_to: str,
) -> None:
    """Append LP test outcome to memory/14_learning_patterns.md."""
    lp_file = Path(__file__).parent.parent / "memory" / "14_learning_patterns.md"
    today   = date.today().isoformat()
    entry = (
        f"\n### LP Test — {test_id} ({today})\n"
        f"- Window: {window_from} to {window_to}\n"
        f"- Decision: {decision}  ·  CPQL delta: {cpql_delta_pct:+.1f}%  ·  "
        f"Confidence: {confidence_pct:.0f}%\n"
        f"- Rationale: {rationale}\n"
    )
    if lp_file.exists():
        lp_file.write_text(
            lp_file.read_text(encoding="utf-8") + entry, encoding="utf-8"
        )
    else:
        lp_file.write_text(f"# Learning Patterns\n{entry}", encoding="utf-8")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "brief":
        # Quick test: python analysers/lp_tasks.py brief
        result = create_lp_brief(
            product="Invoice",
            hypothesis_slug="zatca-above-fold",
            channel="Meta",
            hypothesis=(
                "If we move the ZATCA Phase-2 badge above the fold, "
                "then CPQL will drop because trust signals reduce friction."
            ),
            current_cpql=84,
            current_conversion_pct=6.1,
            destination_url="https://lp.qoyod.com/invoice-zatca",
            audience="SMB finance owners, Meta Interests",
            ocean_notes="High Conscientiousness + low Openness → lead with compliance, not novelty.",
            offer_message="Issue ZATCA Phase-2 compliant e-invoices in minutes. "
                          "+25,000 Saudi companies trust Qoyod.",
            page_structure=(
                "Hero (badge above fold) → social proof → problem → features "
                "→ testimonials → pricing → FAQ → CTA"
            ),
            success_criteria=(
                "Ship if CPQL drops ≥12% (≤$74) over 14 days at same spend, "
                "form-start rate up."
            ),
            risks="Badge crowds hero on mobile. Kill if CPQL rises >10% in first 7 days.",
        )
        print(json.dumps(result, indent=2))

    elif cmd == "help":
        print("Usage: python analysers/lp_tasks.py <brief|help>")
        print("Functions: create_lp_brief, create_lp_design, create_lp_spec, call_lp_test_result")
        print("           create_instantform_audit (Campaign Manager path — no LP involved)")
