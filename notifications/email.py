"""
Email notifier — routes messages to the right team members based on event type.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_NAME = os.getenv("SMTP_FROM_NAME", "Nexa — Qoyod Performance Agent")

TEAM_LEAD = os.getenv("EMAIL_TEAM_LEAD")         # rana.khalid@qoyod.com
TEAM_MANAGER = os.getenv("EMAIL_TEAM_MANAGER")   # yelfiky@qoyod.com
PERFORMANCE = os.getenv("EMAIL_PERFORMANCE")     # dmohamed@qoyod.com
ALL = [e.strip() for e in (os.getenv("EMAIL_ALL") or "").split(",") if e.strip()]


# Routing table — who gets what type of event
ROUTES = {
    "daily_summary":           ALL,
    "threshold_breach":        [TEAM_LEAD, TEAM_MANAGER],
    "auto_action":             ALL,
    "budget_overspend":        [TEAM_LEAD, TEAM_MANAGER],
    "creative_brief":          [PERFORMANCE, TEAM_LEAD],   # Donia + Rana
    "creative_sample":         [PERFORMANCE, TEAM_LEAD],
    "winning_ad":              [PERFORMANCE, TEAM_LEAD],
    "weekly_review":           ALL,
    "monthly_review":          ALL,
    "blocker":                 ALL,
    "qoyod_source_coverage":   ALL,
    "stuck_deal":              [TEAM_LEAD, TEAM_MANAGER],
    "approval_needed":         [TEAM_LEAD, TEAM_MANAGER],
    "test":                    [TEAM_LEAD],
}

ICONS = {
    "daily_summary": "📊", "threshold_breach": "🚨", "auto_action": "✅",
    "budget_overspend": "💰", "creative_brief": "📝", "creative_sample": "🎨",
    "winning_ad": "🏆", "weekly_review": "📈", "monthly_review": "📆",
    "blocker": "🚫", "qoyod_source_coverage": "⚠️", "stuck_deal": "⏰",
    "approval_needed": "🚨", "test": "🧪",
}


def _wrap_html(title: str, body_html: str, meta: dict | None = None) -> str:
    meta_rows = ""
    if meta:
        meta_rows = "<table style='border-collapse:collapse;margin-top:12px'>"
        for k, v in meta.items():
            meta_rows += f"<tr><td style='padding:4px 12px 4px 0;color:#7a8599;font-size:13px'>{k}</td><td style='padding:4px 0;font-size:13px'><b>{v}</b></td></tr>"
        meta_rows += "</table>"
    return f"""
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f7fa;margin:0;padding:24px;color:#1a1f36">
  <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;padding:28px;border:1px solid #e4e8ef">
    <h1 style="margin:0 0 16px 0;font-size:20px;color:#021544">{title}</h1>
    <div style="font-size:14px;line-height:1.6;color:#3a4356">{body_html}</div>
    {meta_rows}
    <hr style="border:none;border-top:1px solid #e4e8ef;margin:24px 0 12px">
    <p style="font-size:11px;color:#7a8599;margin:0">Nexa — Qoyod Performance Agent · automated · do not reply</p>
  </div>
</body></html>
"""


def send(event_type: str, subject: str, body_html: str,
         meta: dict | None = None,
         to_override: list[str] | None = None,
         attachments: list[tuple[str, bytes]] | None = None):
    """Send an email routed by event_type."""
    recipients = to_override or ROUTES.get(event_type, ALL)
    recipients = [r for r in recipients if r]
    if not recipients:
        print(f"[email] No recipients for event_type={event_type}")
        return False

    icon = ICONS.get(event_type, "•")
    full_subject = f"[Qoyod Agent] {icon} {subject}"
    html = _wrap_html(subject, body_html, meta)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = full_subject
    msg["From"] = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_html.replace("<br>", "\n"), "plain"))
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)

    for fname, data in (attachments or []):
        from email.mime.base import MIMEBase
        from email import encoders
        part = MIMEBase("application", "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
        msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, recipients, msg.as_string())
    print(f"[email] Sent '{event_type}' -> {len(recipients)} recipient(s)")
    return True


if __name__ == "__main__":
    # Demo: send test email
    send(
        "test",
        "Routing module is live",
        "<p>The Qoyod Performance Agent email router is configured and working.</p>"
        "<p><b>Routing table active for:</b> daily summaries, threshold breaches, "
        "creative samples, weekly/monthly reviews, blockers, and more.</p>",
        meta={
            "Sender": SMTP_USER,
            "Team Lead (Rana)": TEAM_LEAD,
            "Team Manager (Yomna)": TEAM_MANAGER,
            "Performance Specialist (Donia)": PERFORMANCE,
        }
    )
