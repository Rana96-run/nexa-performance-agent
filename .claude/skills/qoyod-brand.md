---
name: qoyod-brand
description: |
  Client Skill — Qoyod product knowledge, personas, competitive landscape, KSA market rules,
  and brand voice. Load this skill whenever writing copy, building campaigns, naming assets,
  assessing audience fit, benchmarking KPIs, or advising on ZATCA compliance context.
  ALWAYS use for: naming campaigns, writing Arabic copy, competitor comparisons,
  product-specific CPQL targets, audience segmentation, landing page strategy.
---

# Qoyod Brand Skill

## Who Qoyod Is

Qoyod is a **Saudi-born cloud accounting and business management platform** built for SMEs
operating in the Kingdom. Its core mission: make financial compliance effortless so business
owners can focus on growth. Every product decision is anchored to two realities —
**Vision 2030 compliance requirements** (ZATCA e-invoicing) and **Arabic-first UX**.

---

## Product Suite

| Product | Arabic name | Primary value prop | Target buyer |
|---|---|---|---|
| **Invoice** (E-Invoice) | الفاتورة الإلكترونية | ZATCA Phase 2 compliance + automated VAT | Finance manager, Accountant |
| **Bookkeeping** | المحاسبة | Full cloud accounting (journal entries, P&L, balance sheet) | SME owner, Accountant |
| **Qflavours** | قيود فليفرز | F&B POS + inventory + sales reporting | Restaurant/café owner |
| **Payroll** | الرواتب | WPS-compliant salary disbursement | HR Manager, SME owner |

**Naming rule in campaigns:** Always use the short normalized form:
- E-Invoice / einvoice → `Invoice`
- Qbookkeeping / bookkeeping → `Bookkeeping`
- qflavours / flavours → `Qflavours`

---

## Audience Personas

### Persona 1 — The Compliance-Anxious SME Owner
- **Profile**: Runs a business with 5–50 employees, non-accountant background
- **Pain**: ZATCA deadlines feel threatening; manually manages invoices in Excel
- **Motivation**: Avoid fines; look professional to clients
- **Language**: Arabic-first; prefers short, clear, urgency-framed copy
- **Channels**: Snapchat, Meta (Facebook/Instagram), Google Search
- **Message angle**: "متوافق مع هيئة الزكاة — ابدأ اليوم"

### Persona 2 — The Efficiency-Driven Finance Manager
- **Profile**: Works at a 50–500 person company; accountant or financial controller
- **Pain**: Reconciliation is manual, audit trail is fragmented, month-end is chaos
- **Motivation**: Reduce close time from 5 days to 1; impress CFO/CEO
- **Language**: Technical Arabic + English terms acceptable
- **Channels**: LinkedIn, Google Search, Meta
- **Message angle**: "تقارير مالية دقيقة في ثوانٍ"

### Persona 3 — The Recommendation Influencer (Accountant)
- **Profile**: Freelance or in-house accountant advising multiple clients
- **Pain**: Each client uses a different system; re-learning is constant
- **Motivation**: Recommend one trusted platform; earn referral credit
- **Language**: Professional Arabic, accounting terminology
- **Channels**: LinkedIn, WhatsApp communities, Google Search
- **Message angle**: "منصة واحدة لكل عملائك"

### Persona 4 — The F&B Operator (Qflavours only)
- **Profile**: Restaurant or café owner, 1–5 branches
- **Pain**: Stock shrinkage, manual cash reconciliation, no real-time sales view
- **Motivation**: Know his numbers without hiring a full-time accountant
- **Language**: Colloquial Arabic acceptable; visual-first
- **Channels**: Snapchat, TikTok, Meta
- **Message angle**: "تحكم في مطعمك من جوالك"

---

## KSA Market Context

- **ZATCA Phase 2**: Integration phase — applies to businesses above SAR 5M revenue.
  Every new lead in Finance/Accounting space has this as a trigger. Lead copy that
  references ZATCA compliance outperforms generic copy by 30–60% on CTR.
- **Language**: All consumer-facing copy must be MSA Arabic (فصحى مبسطة).
  Never colloquial in ad copy. Technical terms may use English (e.g., "Cloud", "API").
- **Time zone**: Asia/Riyadh (UTC+3). All scheduling, reporting, and event naming uses Riyadh time.
- **Spend currency**: USD in BQ and all reports. Never report in SAR internally.
- **Trial trigger**: 14-day free trial is the primary conversion action. All campaign
  CTAs point to trial, not demo request.
- **Primary geography**: Riyadh, Jeddah, Eastern Province — in that order.
  PMax and broad campaigns default to KSA-wide.

---

## Competitors & Positioning

| Competitor | Weakness vs. Qoyod | Our counter-message |
|---|---|---|
| **Zoho Books** | Complex, English-first, no ZATCA native | "مصمم للسوق السعودي" |
| **Wafeq** | Limited product suite, no POS | "متكامل — محاسبة + فوترة + كاشير" |
| **Daftra (دفترة)** | Egyptian-market focused, UI lag | "سعودي 100% — بدعم عربي 24/7" |
| **Foodics (فودكس)** | F&B only, no accounting | "كاشير وحسابات في منصة واحدة" (Qflavours) |
| **Manager.io / الاستاذ** | Offline, no cloud sync, no ZATCA | "سحابي — بدون تنصيب" |
| **QuickBooks** | English-only, no ZATCA, expensive | "أرخص وأقرب — مع دعم عربي" |

**Competitor campaign rule**: Competitor terms are ONLY allowed in campaigns named `*_Competitor_*`.
In all other campaigns, drop competitor terms from keywords — never negate them.

---

## Brand Voice Rules

- **Tone**: Professional, reassuring, compliance-confident. Never boastful.
- **Arabic style**: MSA فصحى مبسطة — not Gulf dialect, not Egyptian colloquial.
- **Calls to action**: "ابدأ تجربتك المجانية" (primary) / "تواصل معنا" (secondary)
- **Numbers**: Always cite proof — "أكثر من 50,000 شركة", "ZATCA المرحلة الثانية"
- **Avoid**: Superlatives without proof ("الأفضل"), generic claims ("حل شامل" without context)

---

## KPI Benchmarks (Qoyod-specific)

From `config.py` — these are non-negotiable. Never override without explicit approval.

### Campaign-level CPQL (PRIMARY KPI — USD)
| Zone | Threshold | Action |
|---|---|---|
| 🟢 Scale | < $60 | Increase budget 20–30% |
| ✅ Acceptable | ≤ $80 | Hold, monitor weekly |
| ⚠️ Warning | ≤ $95 | Investigate root cause |
| 🔴 Pause candidate | > $100 | Flag for approval, pause after 14 days |

### Campaign-level CPL (SECONDARY — USD)
Scale < $25 | Acceptable ≤ $35 | Warning ≤ $40 | Pause > $45

### Ad-level CPQL (USD)
Scale < $60 | Acceptable ≤ $75 | Warning ≤ $85 | Pause > $90

### Minimum data window
- **14 days** before any pause/scale decision — never act on fewer than 14 days.
- **10 days** minimum age before pausing a keyword for performance.

---

## Rules & Guardrails

- **Never** name a campaign with audience = "Prospecting" — use `Interests` or `Lookalike`
- **Never** report spend in SAR — always USD
- **Never** divide deal amounts from BQ by 3.75 — already converted at write time
- **Never** use `hubspot_leads_daily` — use `hubspot_leads_module_daily`
- **Always** verify ZATCA copy is Phase 2 compliant (not Phase 1)
- **Always** use both Meta pixels: `Qoyod_CRM_PIXEL` (1782671302631317) + `Qoyod_Web_PIXEL` (3036579196577051)
