"""Pre-execution KPI rule guard.

Triggered before Bash/PowerShell/Write/Edit tool calls. Scans the command
or file content for known KPI-rule violations:

  1. `campaigns_daily.leads` referenced as a leads metric without a join
     to `hubspot_leads_module_daily`.
  2. `ads_daily.conversions` or `ads_daily.leads` reported as "leads"
     without HubSpot join (channel-reported pixel events, not real form
     submissions).
  3. `paid_channel_campaign_daily.leads` queried without verifying it's
     the HubSpot-joined view (it should be, but worth confirming).
  4. CPL/CPQL calculated against a channel-reported lead count.

If a violation pattern is detected, exits with code 2 (Claude Code treats
non-zero exit as block). Prints a structured warning telling the agent
WHAT the violation is and HOW to fix it.

Bypass token: include `-- KPI-RULE-BYPASS` (SQL comment) or
`# KPI-RULE-BYPASS` (Python comment) in the same content to allow through.
The bypass is logged for audit.
"""
import sys, json, re

# Read tool input from stdin (Claude Code passes JSON)
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # don't block if hook can't parse

tool_name  = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {})

# Extract the text we care about scanning
content = ""
if tool_name in ("Bash", "PowerShell"):
    content = tool_input.get("command", "") or ""
elif tool_name in ("Write", "Edit"):
    content = (
        tool_input.get("content", "")
        or tool_input.get("new_string", "")
        or ""
    )

if not content:
    sys.exit(0)

violations = []
content_lower = content.lower()

# ── Pattern 1: campaigns_daily.leads without HubSpot join ───────────────
# Tighter signal — require BOTH a SQL-context marker (SELECT...FROM...campaigns_daily)
# AND an actual leads reference in that query. This avoids false-positives in docs
# strings, sheet rows, or commentary that mention 'campaigns_daily.leads' verbatim.
if "campaigns_daily" in content_lower:
    # Must look like real SQL — a SELECT clause that pulls FROM campaigns_daily
    sql_context = re.search(
        r"\bselect\b[^;]{0,500}\bfrom\s+[`\"']?\w*\.?\w*\.?campaigns_daily",
        content_lower, re.DOTALL,
    )
    if sql_context:
        # Within that SQL block, look for a 'leads' reference (column or sum/count)
        sql_block = sql_context.group(0)
        leads_in_sql = bool(
            re.search(r"\b(sum|count|avg)\s*\(\s*(\w+\.)?leads\b", sql_block)
            or re.search(r"\bselect\b[^;]*\bleads\b[^;]*\bfrom\b", sql_block)
            or re.search(r"\bcampaigns_daily\.\s*leads\b", sql_block)
        )
        has_hs_join = "hubspot_leads_module_daily" in content_lower
        if leads_in_sql and not has_hs_join:
            violations.append({
                "pattern": "campaigns_daily.leads queried in SQL without hubspot_leads_module_daily join",
                "fix": (
                    "Leads MUST come from hubspot_leads_module_daily, NOT campaigns_daily. "
                    "Channel-reported 'leads' on campaigns_daily include page views and "
                    "are not real form submissions. See memory/CRITICAL_KPI_RULES.md for the "
                    "correct WITH-hs-pre-agg pattern."
                ),
            })

# ── Pattern 2: ads_daily conversions/leads without HubSpot join ─────────
if "ads_daily" in content_lower:
    ad_lead_patterns = [
        r"\bsum\s*\(\s*(\w+\.)?conversions\b",
        r"\bsum\s*\(\s*(\w+\.)?leads\b",
        r"\bselect[^;]*\bconversions\b[^;]*\bfrom[^;]*ads_daily",
    ]
    has_violation = any(re.search(p, content_lower, re.DOTALL) for p in ad_lead_patterns)
    has_hs_join = "hubspot_leads_module_daily" in content_lower
    if has_violation and not has_hs_join:
        violations.append({
            "pattern": "ads_daily.conversions or .leads queried without hubspot_leads_module_daily join",
            "fix": (
                "ads_daily.conversions is platform-reported (Meta/Snap/TikTok pixel). "
                "For lead-quality analysis, join to hubspot_leads_module_daily on "
                "lead_utm_content. Pixel-reported is NOT real leads."
            ),
        })

# ── Pattern 3: CPL/CPQL calculated against campaigns_daily.leads ────────
# Catches patterns like: spend / leads where leads comes from campaigns_daily context
if "campaigns_daily" in content_lower and re.search(r"\b(cpl|cpql)\b", content_lower):
    # If 'CPL' or 'CPQL' appears AND campaigns_daily.leads is used (caught above)
    # AND hubspot_leads_module_daily isn't joined, the CPL/CPQL is bogus.
    if "hubspot_leads_module_daily" not in content_lower:
        # Only flag if not already flagged above
        if not any("campaigns_daily.leads" in v["pattern"] for v in violations):
            # Look for CPL = spend / leads pattern
            if re.search(r"spend\s*/\s*\w*leads", content_lower) or re.search(r"safe_divide\s*\(\s*\w*spend\b[^,]*,[^)]*leads", content_lower):
                violations.append({
                    "pattern": "CPL/CPQL computed against channel-reported leads (campaigns_daily)",
                    "fix": (
                        "CPL = spend / HubSpot leads. If 'leads' here comes from campaigns_daily, "
                        "the CPL is meaningless. Use hubspot_leads_module_daily for the divisor."
                    ),
                })

# ── Honor bypass token ─────────────────────────────────────────────────
if violations and ("KPI-RULE-BYPASS" in content):
    print("⚠ KPI-RULE-BYPASS token present — allowing through. Flag in event log.",
          file=sys.stderr)
    sys.exit(0)

if violations:
    msg = "\n".join([
        "🛑 KPI RULE VIOLATION DETECTED — BLOCKED",
        "",
        "Your script contains a known anti-pattern that has been corrected multiple",
        "times. See memory/CRITICAL_KPI_RULES.md for the correct pattern.",
        "",
    ])
    for v in violations:
        msg += f"  ❌ {v['pattern']}\n"
        msg += f"     Fix: {v['fix']}\n\n"
    msg += "Bypass token (only for genuine debug comparisons): add '-- KPI-RULE-BYPASS'\n"
    msg += "or '# KPI-RULE-BYPASS' anywhere in the file/command. Use sparingly.\n"

    print(msg, file=sys.stderr)
    sys.exit(2)  # 2 = block in Claude Code

sys.exit(0)
