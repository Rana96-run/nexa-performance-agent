"""
scripts/log_cro_work.py
=======================
CLI helper for CRO / Landing Page dev-time agents to log their work to BQ.

Called by cro-specialist, ui-ux-designer, and developer at the end of each
task so the activity dashboard shows CRO department activity.

Usage:
    railway run python scripts/log_cro_work.py \
        --role lp_deploy \
        --action lp_deployed \
        --details "Invoice LP variant A — UTM passthrough + pixels verified" \
        [--channel meta] [--campaign "Meta_LeadGen_AR_Invoice_Interests"]

Roles:
    cro_analysis   → cro-specialist (brief written, test called)
    lp_design      → ui-ux-designer (design + annotations complete)
    lp_deploy      → developer (LP built, deployed, pixels verified)

Actions (suggested, not enforced):
    lp_brief_written      cro-specialist wrote an LP brief
    lp_test_called        cro-specialist decided test result
    lp_design_complete    ui-ux-designer annotated design handed to developer
    lp_deployed           developer deployed LP to production
    lp_pixels_verified    developer confirmed pixel fires in Events Manager
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description="Log CRO/LP work to BQ agent_activity_log")
    parser.add_argument("--role",     required=True,
                        choices=["cro_analysis", "lp_design", "lp_deploy"],
                        help="Agent role (cro_analysis | lp_design | lp_deploy)")
    parser.add_argument("--action",   required=True,
                        help="Action name, e.g. lp_deployed, lp_brief_written")
    parser.add_argument("--details",  default=None,
                        help="Short human-readable summary of what was done")
    parser.add_argument("--channel",  default=None,
                        help="Ad channel if relevant (meta, google, etc.)")
    parser.add_argument("--campaign", default=None,
                        help="Campaign or LP name if relevant")
    parser.add_argument("--status",   default="success",
                        choices=["success", "failed", "pending_approval"],
                        help="Outcome status (default: success)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    from logs.activity_logger import log_activity
    log_activity(
        role=args.role,
        action=args.action,
        status=args.status,
        channel=args.channel,
        campaign_name=args.campaign,
        details={"summary": args.details} if args.details else None,
    )
    print(f"Logged: role={args.role} action={args.action} status={args.status}")


if __name__ == "__main__":
    main()
