"""
Pre-send review hook — fires before Slack posts and Asana task creation.
Injects a checklist into Claude's context so it verifies format/content
before every send.
"""
import json

context = (
    "STOP — Pre-send review checklist. Verify EVERY item before proceeding:\n\n"
    "1. SLACK MESSAGE RULES — 2 MESSAGES TOTAL PER NIGHT\n"
    "   #notify: exactly 1 message. Format:\n"
    "   - Line 1: date + dashboard link\n"
    "   - 7d Performance: channel totals ONLY (spend / leads / CPQL) — NO campaign names\n"
    "   - Alerts: spike alerts if any\n"
    "   - → #approvals: category × count only (e.g. 'Scale ×2  ·  Pause ×1') — NO names\n"
    "   - Asana: X new · Y pending · Z overdue\n"
    "   #approvals: exactly 1 message (post_nightly_approvals_digest — scale+pause+review all in one)\n\n"
    "2. NAMING CONVENTION\n"
    "   Format: {Channel}_{Type}_{Language}_{Product}_{Audience}\n"
    "   - 'Prospecting' is NEVER a valid audience — use Interests or Lookalike\n"
    "   - Products: E-Invoice->Invoice, Qbookkeeping->Bookkeeping, qflavours->Qflavours\n"
    "   - LinkedIn UTM: Group=utm_campaign, Campaign=utm_audience, Ad=utm_content\n\n"
    "3. ASANA TASK RULES\n"
    "   - ONE task per campaign (not one task for all campaigns)\n"
    "   - Every task must have footer: Created, Due, Priority, Type, Channel, Asset level, Action\n\n"
    "4. APPROVAL FLOW\n"
    "   - scale/pause: approval-gated via #approvals batch digest (✅=all, ❌=skip all)\n"
    "   - optimize/junk/drilldown: review digest sent to #approvals\n"
    "   - Awareness campaigns: routed by IS metrics (Lost Budget→scale, Lost Rank→optimize)\n\n"
    "If ANY check fails, stop and correct before sending."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": context
    }
}))
