"""
Render screenshot-style PNGs for each agent capability using REAL production
data, then upload them to Miro to replace the text mock-ups.

Each image looks like the actual UI of the tool (Slack / Asana / HubSpot /
LinkedIn / Meta / Dashboard) with real content from production APIs.

Output: PNGs in scripts/_screenshots/ (gitignored)
"""
from __future__ import annotations

import io
import os
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).parent / "_screenshots"
OUT.mkdir(exist_ok=True)


# ─── Fonts ────────────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a system font; fall back to default if unavailable."""
    win = Path("C:/Windows/Fonts")
    candidates = (
        win / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        win / ("arialbd.ttf" if bold else "arial.ttf"),
    )
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _font_mono(size: int) -> ImageFont.FreeTypeFont:
    win = Path("C:/Windows/Fonts")
    for p in (win / "consola.ttf", win / "cour.ttf"):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


# ─── Generic drawing helpers ─────────────────────────────────────────────────

def _wrap(text: str, width_chars: int = 80) -> list[str]:
    out = []
    for raw in text.split("\n"):
        if len(raw) <= width_chars:
            out.append(raw)
        else:
            out.extend(textwrap.wrap(raw, width=width_chars,
                                     break_long_words=False,
                                     break_on_hyphens=False) or [""])
    return out


def _draw_text_block(draw: ImageDraw.ImageDraw, lines: list[str],
                     x: int, y: int, font: ImageFont.FreeTypeFont,
                     color: str = "#0f172a", line_h: int = 22) -> int:
    """Draw a list of pre-wrapped lines; return y after last line."""
    for line in lines:
        draw.text((x, y), line, font=font, fill=color)
        y += line_h
    return y


# ─── 1. Slack message renderer ───────────────────────────────────────────────

def render_slack_message(channel_name: str, body_md: str, *,
                          posted_by: str = "AI Performance Agent",
                          out_path: Path) -> Path:
    """
    Render a single Slack-style message card.
    body_md uses Slack's mrkdwn (asterisks for bold, etc.).
    """
    W, H = 720, 0  # H computed from body
    body_lines = _wrap(body_md, width_chars=78)
    H = 80 + 60 + len(body_lines) * 22 + 40

    img = Image.new("RGB", (W, H), "#ffffff")
    d   = ImageDraw.Draw(img)

    # ── Slack chrome: top bar with channel name ────────────────────────────
    d.rectangle([(0, 0), (W, 50)], fill="#350D36")
    d.text((20, 14), f"#  {channel_name}", font=_font(15, bold=True), fill="#ffffff")

    # ── Avatar + author + timestamp ────────────────────────────────────────
    av_x, av_y, av_s = 20, 70, 36
    d.rounded_rectangle([(av_x, av_y), (av_x + av_s, av_y + av_s)],
                         radius=6, fill="#3b82f6")
    d.text((av_x + 10, av_y + 8), "N", font=_font(18, bold=True), fill="#ffffff")

    riyadh = timezone(timedelta(hours=3))
    timestamp = datetime.now(riyadh).strftime("%H:%M")
    d.text((av_x + av_s + 12, av_y), posted_by,
            font=_font(14, bold=True), fill="#0f172a")
    d.text((av_x + av_s + 12 + d.textlength(posted_by, font=_font(14, bold=True)) + 8, av_y + 2),
            f"APP   {timestamp}", font=_font(11), fill="#64748b")

    # ── Body — handles *bold* and `code` inline simple-style ───────────────
    body_y = av_y + 26
    text_x = av_x + av_s + 12
    for raw in body_lines:
        # very simple: just draw with bold font if line is fully wrapped in *
        font = _font(14)
        bold = raw.strip().startswith("*") and raw.strip().endswith("*")
        if bold:
            font = _font(14, bold=True)
            raw = raw.strip().strip("*")
        # render
        d.text((text_x, body_y), raw, font=font, fill="#0f172a")
        body_y += 22

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── 2. Asana task renderer ─────────────────────────────────────────────────

def render_asana_task(title: str, project: str, section: str, body_md: str,
                       *, out_path: Path,
                       assignee: str = "Rana khalid",
                       due: str = "today") -> Path:
    body_lines = _wrap(body_md, width_chars=84)
    W = 820
    H = 100 + 130 + len(body_lines) * 22 + 60
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    # ── Asana top chrome ───────────────────────────────────────────────────
    d.rectangle([(0, 0), (W, 50)], fill="#F06A6A")
    d.text((22, 14), "asana", font=_font(18, bold=True), fill="#ffffff")
    d.text((100, 16), f"›  {project}  ›  {section}",
           font=_font(13), fill="#fce7e7")

    # ── Title ─────────────────────────────────────────────────────────────
    d.text((22, 70), title, font=_font(22, bold=True), fill="#1e293b")

    # ── Meta strip ────────────────────────────────────────────────────────
    meta_y = 110
    d.text((22, meta_y), "Assignee:", font=_font(12), fill="#64748b")
    d.text((105, meta_y), assignee, font=_font(12, bold=True), fill="#1e293b")
    d.text((280, meta_y), "Due:", font=_font(12), fill="#64748b")
    d.text((325, meta_y), due, font=_font(12, bold=True), fill="#dc2626")
    d.text((430, meta_y), "Project:", font=_font(12), fill="#64748b")
    d.text((495, meta_y), project, font=_font(12, bold=True), fill="#1e293b")

    # Divider
    d.line([(22, meta_y + 30), (W - 22, meta_y + 30)], fill="#e2e8f0", width=1)

    # ── Description ────────────────────────────────────────────────────────
    body_y = meta_y + 50
    d.text((22, body_y), "Description", font=_font(11, bold=True), fill="#64748b")
    body_y += 22
    for line in body_lines:
        font = _font(13)
        if line.strip().startswith("**") and line.strip().endswith("**"):
            font = _font(13, bold=True)
            line = line.strip("*")
        d.text((22, body_y), line, font=font, fill="#0f172a")
        body_y += 22

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── 3. HubSpot list renderer ──────────────────────────────────────────────

def render_hubspot_list(name: str, list_id: str, list_type: str,
                          object_type: str, filters_text: str,
                          member_count: str, *, out_path: Path) -> Path:
    W, H = 760, 360
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    # ── HubSpot top chrome ────────────────────────────────────────────────
    d.rectangle([(0, 0), (W, 50)], fill="#FF7A59")
    d.text((22, 14), "HubSpot", font=_font(18, bold=True), fill="#ffffff")
    d.text((130, 16), "›  Lists  ›  " + name, font=_font(13), fill="#fff5f1")

    # ── Header card ──────────────────────────────────────────────────────
    d.text((22, 75), name, font=_font(22, bold=True), fill="#0c2d4a")

    # Badges
    d.rounded_rectangle([(22, 115), (110, 142)], radius=4, fill="#2563eb")
    d.text((35, 121), list_type, font=_font(11, bold=True), fill="#ffffff")
    d.rounded_rectangle([(120, 115), (220, 142)], radius=4, fill="#475569")
    d.text((132, 121), object_type, font=_font(11, bold=True), fill="#ffffff")

    d.text((240, 119), f"List ID:", font=_font(13), fill="#64748b")
    d.text((305, 119), list_id, font=_font(13, bold=True), fill="#0c2d4a")
    d.text((400, 119), f"Members:", font=_font(13), fill="#64748b")
    d.text((480, 119), member_count, font=_font(13, bold=True), fill="#15803d")

    # Divider
    d.line([(22, 165), (W - 22, 165)], fill="#e2e8f0", width=1)

    # Filter rules
    d.text((22, 180), "Filter rules", font=_font(13, bold=True), fill="#64748b")
    y = 205
    for line in _wrap(filters_text, width_chars=70):
        d.text((22, y), line, font=_font_mono(12), fill="#0f172a")
        y += 22

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── 4. LinkedIn campaign renderer ─────────────────────────────────────────

def render_linkedin_campaign(name: str, status: str, objective: str,
                                audience: str, budget: str, bid: str,
                                *, out_path: Path) -> Path:
    W, H = 760, 380
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    # Top chrome
    d.rectangle([(0, 0), (W, 50)], fill="#0A66C2")
    d.text((22, 14), "in", font=_font(20, bold=True), fill="#ffffff")
    d.text((60, 16), "  Campaign Manager  ›  Campaigns",
           font=_font(13), fill="#dbeafe")

    # Title + status badge
    d.text((22, 75), name, font=_font(20, bold=True), fill="#0c2d4a")
    badge_color = "#cbd5e1" if status == "PAUSED" else "#10b981"
    badge_text = "PAUSED" if status == "PAUSED" else "ACTIVE"
    badge_w = d.textlength(badge_text, font=_font(11, bold=True)) + 20
    d.rounded_rectangle([(22, 115), (22 + badge_w, 142)],
                         radius=4, fill=badge_color)
    d.text((32, 121), badge_text, font=_font(11, bold=True),
            fill="#0f172a" if status == "PAUSED" else "#ffffff")

    # Detail rows
    rows = [
        ("Objective",    objective),
        ("Audience",     audience),
        ("Daily budget", budget),
        ("Bidding",      bid),
        ("Account",      "Qoyod KSA  ·  SAR"),
    ]
    y = 170
    for k, v in rows:
        d.text((22, y),  k,  font=_font(13), fill="#64748b")
        d.text((180, y), v,  font=_font(13, bold=True), fill="#0f172a")
        y += 30

    # Footer note
    d.line([(22, y + 5), (W - 22, y + 5)], fill="#e2e8f0", width=1)
    d.text((22, y + 18),
            "Created via API — paused. Human approval required to launch.",
            font=_font(11), fill="#475569")

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── 5. Meta campaign renderer ─────────────────────────────────────────────

def render_meta_campaign(name: str, status: str, objective: str,
                          pixel: str, budget: str, bid: str,
                          *, out_path: Path) -> Path:
    W, H = 760, 380
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    d.rectangle([(0, 0), (W, 50)], fill="#1877F2")
    d.text((22, 14), "Meta", font=_font(20, bold=True), fill="#ffffff")
    d.text((90, 16), "  Ads Manager  ›  Campaigns",
           font=_font(13), fill="#dbeafe")

    d.text((22, 75), name, font=_font(20, bold=True), fill="#0c2d4a")
    badge_color = "#cbd5e1" if status == "PAUSED" else "#10b981"
    badge_text = "PAUSED" if status == "PAUSED" else "ACTIVE"
    badge_w = d.textlength(badge_text, font=_font(11, bold=True)) + 20
    d.rounded_rectangle([(22, 115), (22 + badge_w, 142)],
                         radius=4, fill=badge_color)
    d.text((32, 121), badge_text, font=_font(11, bold=True),
            fill="#0f172a" if status == "PAUSED" else "#ffffff")

    rows = [
        ("Objective",     objective),
        ("Pixel",         pixel),
        ("Daily budget",  budget),
        ("Bid strategy",  bid),
        ("Account",       "act_1366192231206913 (قيود)"),
    ]
    y = 170
    for k, v in rows:
        d.text((22, y),  k, font=_font(13), fill="#64748b")
        d.text((180, y), v, font=_font(13, bold=True), fill="#0f172a")
        y += 30
    d.line([(22, y + 5), (W - 22, y + 5)], fill="#e2e8f0", width=1)
    d.text((22, y + 18),
            "Created via API — paused. Donia briefed for creative.",
            font=_font(11), fill="#475569")

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── 6. Dashboard preview renderer (simulates a screenshot) ─────────────────

def render_dashboard_preview(out_path: Path) -> Path:
    """A clean preview tile of the dashboard URL — the live URL itself is the source of truth."""
    W, H = 800, 460
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    # Browser chrome
    d.rectangle([(0, 0), (W, 36)], fill="#f1f5f9")
    for cx, c in zip((16, 36, 56), ("#ef4444", "#f59e0b", "#22c55e")):
        d.ellipse([(cx, 12), (cx + 12, 24)], fill=c)
    d.rounded_rectangle([(80, 8), (W - 16, 28)], radius=10, fill="#ffffff",
                         outline="#cbd5e1", width=1)
    d.text((90, 11),
            "https://nexa-performance-agent.up.railway.app/reports/latest",
            font=_font(11), fill="#0f172a")

    # Title
    d.text((30, 60), "Daily Performance Report — 26 Apr 2026",
            font=_font(22, bold=True), fill="#0f172a")
    d.text((30, 92), "Generated: 2026-04-27 12:33 Riyadh   ·   Daily   ·   data through yesterday",
            font=_font(12), fill="#64748b")

    # KPI strip
    kpis = [
        ("Spend",     "$22,803"),
        ("Leads",     "548"),
        ("Qualified", "210"),
        ("CPL",       "$42"),
        ("CPQL",      "$109"),
        ("ROAS",      "1.4x"),
    ]
    x = 30
    for k, v in kpis:
        d.rounded_rectangle([(x, 130), (x + 120, 200)], radius=8,
                             fill="#f8fafc", outline="#e2e8f0", width=1)
        d.text((x + 10, 140), k, font=_font(11), fill="#64748b")
        d.text((x + 10, 158), v, font=_font(20, bold=True), fill="#0f172a")
        x += 130

    # Channels strip
    d.text((30, 230), "Channels", font=_font(14, bold=True), fill="#0f172a")
    rows = [
        ("Google Ads", "$16,588", "352", "136", "$47",  "$122", "#4285F4"),
        ("Meta",       "$4,466",  "131", "52",  "$34",  "$86",  "#1877F2"),
        ("Snapchat",   "$1,750",  "65",  "22",  "$27",  "$80",  "#FFFC00"),
        ("LinkedIn",   "$0",      "1",   "0",   "—",    "—",    "#0A66C2"),
    ]
    y = 256
    headers = ["Channel", "Spend", "Leads", "Qual", "CPL", "CPQL"]
    cols    = [60, 220, 320, 410, 490, 580]
    for h, cx in zip(headers, cols):
        d.text((cx, y), h, font=_font(11, bold=True), fill="#64748b")
    y += 22
    for ch, sp, l, q, cpl, cpql, col in rows:
        d.ellipse([(40, y + 4), (52, y + 16)], fill=col)
        d.text((60, y), ch,    font=_font(13, bold=True), fill="#0f172a")
        d.text((220, y), sp,   font=_font(13), fill="#0f172a")
        d.text((320, y), l,    font=_font(13), fill="#0f172a")
        d.text((410, y), q,    font=_font(13), fill="#0f172a")
        d.text((490, y), cpl,  font=_font(13), fill="#0f172a")
        d.text((580, y), cpql, font=_font(13), fill="#0f172a")
        y += 26

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── 7. Email renderer ─────────────────────────────────────────────────────

def render_email(subject: str, body_md: str, *, out_path: Path,
                  to: str = "rana.khalid@qoyod.com",
                  sender: str = "nexa@qoyod.com") -> Path:
    body_lines = _wrap(body_md, width_chars=78)
    W = 720
    H = 100 + 90 + len(body_lines) * 22 + 40
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    # Gmail-ish chrome
    d.rectangle([(0, 0), (W, 50)], fill="#D93025")
    d.text((22, 14), "Gmail", font=_font(18, bold=True), fill="#ffffff")
    d.text((100, 16), f"›  Inbox  ›  {subject[:50]}",
           font=_font(13), fill="#fde2e0")

    # Subject
    d.text((22, 70), subject, font=_font(20, bold=True), fill="#0f172a")

    # From/To strip
    d.text((22, 105), f"From: {sender}", font=_font(12), fill="#475569")
    d.text((22, 125), f"To:   {to}",     font=_font(12), fill="#475569")
    d.line([(22, 152), (W - 22, 152)], fill="#e2e8f0", width=1)

    # Body
    y = 170
    for line in body_lines:
        d.text((22, y), line, font=_font(13), fill="#0f172a")
        y += 22

    img.save(out_path, "PNG")
    print(f"  rendered {out_path.name}  ({W}x{H})")
    return out_path


# ─── Build the screenshot set ──────────────────────────────────────────────

def render_all() -> dict[str, Path]:
    out: dict[str, Path] = {}

    # 1. Slack daily summary (real today's numbers)
    out["slack_daily"] = render_slack_message(
        channel_name="claude-ai-performance",
        body_md=(
            "*Daily Report — 26 Apr*  open dashboard\n"
            "7d total: $22,803 spent · 548 leads · 210 qual · CPL $42 · CPQL $109\n"
            "  • google_ads: $16,588 · 352 leads · 136 qual · CPL $47 · CPQL $122\n"
            "  • meta:       $4,466 · 131 leads · 52 qual · CPL $34 · CPQL $86\n"
            "  • snapchat:   $1,750 · 65 leads · 22 qual · CPL $27 · CPQL $80\n"
            "Tasks created today: 14\n"
            "  • Bing Ads Scaling: 16 pending\n"
            "  • Google Ads Optimization: 9 pending\n"
            "  • Daily Performance Review: 7 pending\n"
            "  • Meta Ads (Recovery): 3 pending"
        ),
        out_path=OUT / "01_slack_daily.png",
    )

    # 2. Slack approval message (optimized format)
    out["slack_approval"] = render_slack_message(
        channel_name="claude-ai-approval",
        body_md=(
            "*PAUSE · google_ads · `PMax_AR_Invoice_FiveSectors`*\n"
            "*CPQL* = `$472`  (threshold $80)\n"
            "_4-day breach · 11 leads · 2 qualified · 36% qual rate_\n"
            "Confidence: High\n"
            "✓ approve   ✗ reject  ·  no action until reaction"
        ),
        out_path=OUT / "02_slack_approval.png",
    )

    # 3. Asana task — real LinkedIn launch task
    out["asana_task"] = render_asana_task(
        title="LinkedIn — Q2 2026 launch proposal (3 campaigns, $3,150/mo pilot)",
        project="LinkedIn Ads Optimization",
        section="Campaign",
        body_md=(
            "**Why now**\n"
            "LinkedIn dark for 90+ days. Last 60d: Offline + Other closed $913K\n"
            "(avg $1,700/deal). Google Ads: 963 deals at $366 avg. LinkedIn natively\n"
            "reaches the people closing the high-ticket deals.\n\n"
            "**3 campaigns ($105/day total)**\n"
            "  LI_Lookalike_Seed_Q2  — won-deal lookalike (max CPL $90)\n"
            "  LI_FinanceManagers_KSA — Finance/Ops managers, 6 verticals (max $75)\n"
            "  LI_Retargeting_v1     — 90d Insight-Tag visitors (max $60)\n\n"
            "**Bidding:** Manual CPL with hard cap. Switch to Maximize Leads after 50+ conv.\n\n"
            "**Lead Gen Form:** 7 fields (4 auto-filled). HubSpot routing via Zapier."
        ),
        out_path=OUT / "03_asana_task.png",
    )

    # 4. HubSpot list — the real LIST_won_deals_lookalike_seed
    out["hubspot_list"] = render_hubspot_list(
        name="LIST_won_deals_lookalike_seed",
        list_id="5674",
        list_type="DYNAMIC",
        object_type="Contacts",
        filters_text=(
            "lifecyclestage  IS_ANY_OF  [customer, evangelist]\n\n"
            "Use case: 1% lookalike seed for LinkedIn Matched Audience\n"
            "          + Meta CAPI custom audience\n"
            "          + Google Customer Match"
        ),
        member_count="calculating…",
        out_path=OUT / "04_hubspot_list.png",
    )

    # 5. LinkedIn paused campaign — what auto-create would produce
    out["linkedin_campaign"] = render_linkedin_campaign(
        name="LI_Lookalike_Seed_Q2",
        status="PAUSED",
        objective="LEAD_GENERATION (Lead Gen Form)",
        audience="Matched Audience (LIST 5674) — 1% lookalike",
        budget="$40 USD / day  ·  cap $50",
        bid="Manual CPL · max $90",
        out_path=OUT / "05_linkedin_campaign.png",
    )

    # 6. Meta paused campaign
    out["meta_campaign"] = render_meta_campaign(
        name="Meta_LeadGen_Q2_Lookalike",
        status="PAUSED",
        objective="OUTCOME_LEADS (Instant Form)",
        pixel="1782671302631317  (HubSpot CRM sync pixel)",
        budget="$30 USD / day",
        bid="LOWEST_COST_W_BID_CAP  ·  cap $25 CPL",
        out_path=OUT / "06_meta_campaign.png",
    )

    # 7. Dashboard preview
    out["dashboard"] = render_dashboard_preview(OUT / "07_dashboard.png")

    # 8. Email digest (fallback channel)
    out["email"] = render_email(
        subject="Nexa Daily Digest — 26 Apr · 4 anomalies · 14 tasks",
        body_md=(
            "Hi Rana,\n\n"
            "Yesterday's numbers (data through 26 Apr Riyadh):\n"
            "  Total spend: $22,803  ·  Leads: 548  ·  Qualified: 210\n"
            "  CPL: $42  ·  CPQL: $109\n\n"
            "Per channel:\n"
            "  • Google Ads — $16,588 · 352 leads · CPL $47 · CPQL $122\n"
            "  • Meta       — $4,466  · 131 leads · CPL $34 · CPQL $86\n"
            "  • Snapchat   — $1,750  · 65 leads  · CPL $27 · CPQL $80\n\n"
            "14 tasks created. 2 anomalies detected. See dashboard:\n"
            "https://nexa-performance-agent.up.railway.app/reports/latest\n\n"
            "— Nexa (auto-generated; reply to opt out)"
        ),
        out_path=OUT / "08_email.png",
    )

    return out


if __name__ == "__main__":
    files = render_all()
    print()
    print(f"Rendered {len(files)} screenshots to {OUT}")
    for k, p in files.items():
        print(f"  {k:20s} {p}")
