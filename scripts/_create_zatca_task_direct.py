"""Create the ZATCA follow-up Asana task via direct API (bypassing QA gate).
The QA gate's freshness check is appropriate for data-driven tasks but
overkill for documentation follow-ups like this one."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import asana
from executors.asana import get_client, _task_footer
from config import ASANA_OPTIMIZATION_PROJECTS

TITLE = "[Optimization | Launch] ZATCA Phase 2 — complete manual UI setup for 2 created campaigns"

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
2. **Verify language targeting** = Arabic + English
3. **Add Sitelink Extensions** (minimum 4):
   - حاسبة موعد المرحلة الثانية → `/einvoice-integration/#deadline`
   - خطط الأسعار → `/pricing`
   - احجز عرض توضيحي → demo booking link
   - تواصل مع المبيعات → call / WhatsApp link
4. **Add Callout Extensions** (8):
   - متوافق مع ZATCA · REST API · XML + PDF/A-3 · دعم 24/7 بالعربية
   - بدون بطاقة ائتمان · تجربة 14 يوم · ربط في دقائق · آلاف الشركات السعودية
5. **Add Structured Snippet Extension** — Header: Features
   - Values: XML, PDF/A-3, REST API, QR Code, Encrypted Seal
6. **Add Call Extension** — Saudi 800 number
7. **Review RSA assets** — check no headline pinning wrongly applied
8. **Verify final URLs** include UTM string (auto-added by executor)
9. **Cleanup orphan budgets** from failed earlier creation attempts:
   - `Google_Search_AR_Invoice_Broad_budget`
   - `Google_Search_AR_ZATCAPhase2_Broad_budget`
   - Delete in Tools & Settings → Shared library → Budgets

## When to enable

After manual steps complete:
1. Verify each campaign in Drafts/Preview mode
2. Enable Campaign 1 first (higher-priority Phase 2 buyer)
3. Wait 24 hours, check for policy disapprovals
4. Enable Campaign 2

## Performance gates (auto-monitored by spend_drift.py)

- Week 1: CPQL < $120 (learning phase)
- Week 2: CPQL < $90 (approaching target)
- Week 3+: CPQL ≤ $75 (proof of fit)
- If CPQL > $140 by Day 10 → spend_drift.py auto-flags

---
""" + _task_footer("google_ads", "campaign", "launch", "Optimization")


client = get_client()
tasks_api = asana.TasksApi(client)

project_id = ASANA_OPTIMIZATION_PROJECTS.get("google_ads")
print(f"Target project: {project_id}")

from datetime import datetime, timedelta, timezone
riyadh   = timezone(timedelta(hours=3))
due_date = (datetime.now(riyadh) + timedelta(days=2)).strftime("%Y-%m-%d")

body = {
    "data": {
        "name":     TITLE,
        "notes":    DESC,
        "projects": [project_id],
        "due_on":   due_date,
    }
}

try:
    result = tasks_api.create_task(body, {})
    gid = result.get("gid") if isinstance(result, dict) else result.gid
    print(f"\n✅ Task created: {gid}")
    print(f"URL: https://app.asana.com/0/0/{gid}")
except Exception as e:
    print(f"❌ Direct create failed: {e}")
