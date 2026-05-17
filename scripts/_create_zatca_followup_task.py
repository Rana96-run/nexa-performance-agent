"""Create Asana task for the manual UI steps required to complete the
2 ZATCA Phase 2 campaigns we just programmatically created."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.asana import create_task

DESC = """\
## Context

Two ZATCA Phase 2 Search campaigns created via API on 2026-05-18 in **PAUSED state** in Google Ads Account 1 (1513020554):

**Campaign 1 — Phase 2 Integration (direct buyer)**
- Name: `Google_Search_AR_ZATCAPhase2_Broad`
- Campaign ID: `23851270716`
- Ad Group ID: `198246169404`
- Budget: $50/day · tCPA $90
- 14 keywords (6 EXACT + 8 PHRASE) + 18 negatives
- 12-headline / 4-description RSA, Arabic + English
- LP: `lp.qoyod.com/einvoice-integration/`

**Campaign 2 — Vendor Shopping (comparison buyers)**
- Name: `Google_Search_AR_ZATCAVendorShop_Broad`
- Campaign ID: `23861101390`
- Ad Group ID: `196918264495`
- Budget: $35/day · tCPA $100
- 15 keywords + 18 negatives
- 12-headline / 4-description RSA
- LP: `lp.qoyod.com/einvoice-integration/`

## Manual steps required before enabling (Google Ads UI — ~10 min total)

### Both campaigns
1. **Verify location targeting** = Saudi Arabia only (not "people interested in")
2. **Verify language targeting** = Arabic + English (Phase 2 has English-speaking IT buyers)
3. **Add Sitelink Extensions** (4 min, must add at least 4):
   - حاسبة موعد المرحلة الثانية → `/einvoice-integration/#deadline`
   - خطط الأسعار → `/pricing` page
   - احجز عرض توضيحي → demo booking link
   - تواصل مع المبيعات → call booking / phone link
4. **Add Callout Extensions** (8 minimum):
   - متوافق مع ZATCA
   - REST API
   - XML + PDF/A-3
   - دعم 24/7 بالعربية
   - بدون بطاقة ائتمان
   - تجربة 14 يوم
   - ربط في دقائق
   - آلاف الشركات السعودية
5. **Add Structured Snippet Extension** — Header: Features
   - XML, PDF/A-3, REST API, QR Code, Encrypted Seal
6. **Add Call Extension** — Saudi 800 number
7. **Review each RSA** — check no headline pinning is wrongly applied
8. **Verify final URLs** include the UTM string (auto-added by executor)
9. **Cleanup orphan budgets** from failed earlier attempts:
   - `Google_Search_AR_Invoice_Broad_budget`
   - `Google_Search_AR_ZATCAPhase2_Broad_budget`
   - Delete in Tools & Settings → Shared library → Budgets

## When to enable

After manual steps complete:
1. Verify each campaign in **Drafts/Preview** mode looks correct
2. Enable Campaign 1 first (higher-priority Phase 2 buyer)
3. Wait 24 hours, check no policy disapprovals
4. Enable Campaign 2

## Performance gates

After enable, monitor:
- Week 1: CPQL < $120 (allow learning phase)
- Week 2: CPQL < $90 (should approach target)
- Week 3+: CPQL ≤ $75 target (proof of fit)
- If CPQL > $140 by Day 10 → spend_drift.py will auto-flag for review
"""

gid = create_task(
    title       = "ZATCA Phase 2 — complete manual UI setup for 2 created campaigns",
    description = DESC,
    project_key = "optimization",
    task_type   = "Optimization",
    channel     = "google_ads",
    asset_level = "campaign",
    action      = "launch",
)
print(f"Asana task created: {gid}")
print(f"URL: https://app.asana.com/0/0/{gid}")
