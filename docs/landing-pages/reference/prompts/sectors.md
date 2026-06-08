# Prompt: All Sectors / Industry Pages

**Slug pattern (AR):** `/برنامج-محاسبي-لـ[القطاع]/`
**Slug pattern (EN):** `/en/accounting-for-[sector]/`
**Language:** Arabic (default)
**Status:** Draft

---

## Available Sectors (from navigation IA)

| Sector | AR Slug | EN Slug | Key Pain |
|---|---|---|---|
| Retail | `/برنامج-محاسبي-للتجزئة/` | `/en/accounting-for-retail/` | POS + accounting disconnect |
| Manufacturing | `/برنامج-محاسبي-للتصنيع/` | `/en/accounting-for-manufacturing/` | Inventory + cost of goods |
| Legal | `/برنامج-محاسبي-للمكاتب-القانونية/` | `/en/accounting-for-legal/` | Billing hours, client trust accounts |
| Rental | `/برنامج-محاسبي-لشركات-الإيجار/` | `/en/accounting-for-rental/` | Recurring invoices, asset tracking |
| Education | `/برنامج-محاسبي-للتعليم/` | `/en/accounting-for-education/` | Tuition invoicing, payroll |
| Services | `/برنامج-محاسبي-لشركات-الخدمات/` | `/en/accounting-for-services/` | Project billing, time tracking |
| Technology | `/برنامج-محاسبي-لشركات-التقنية/` | `/en/accounting-for-technology/` | SaaS/recurring revenue, multi-currency |
| F&B / Restaurants | `/برنامج-محاسبي-للمطاعم/` | `/en/accounting-for-restaurants/` | POS + kitchen + ZATCA |

---

## Audience

Sector-specific business owners and managers. The page speaks directly to their industry context. Tone: empathetic to their specific workflow, practical.

---

## Primary CTA

`ابدأ تجربتك المجانية` → `https://www.qoyod.com/signup/`

---

## Page Template (adapt per sector)

### Section 1 — Hero
- **Eyebrow:** برنامج المحاسبة لـ[القطاع]
- **H1:** [headline specific to sector pain] — e.g., "إدارة حسابات [القطاع] بدون تعقيدات."
- **Subhead:** [1-2 sentences hitting the sector's top 2 pains and Qoyod's solution]
- **3 trust bullets:** (pick 3 most relevant to sector)
- **CTA + trust signal**

### Section 2 — Sector-Specific Problems (3 cards)
Customize the 3 problem cards to the exact daily pain of this sector. Do NOT use generic problems.

### Section 3 — How Qoyod solves it
- Pick the 4–6 features most relevant to this sector from `value-proposition.md`
- Use the Feature → Benefit mapping from `design-system.md`

### Section 4 — Proof
Use approved testimonials — if a sector-specific testimonial exists, prioritize it.

### Section 5 — CTA
Standard final CTA section.

---

## Sector-Specific Copy Hooks

| Sector | Hero Hook |
|---|---|
| Retail | "بيعة واحدة = فاتورة زاتكا + تحديث مخزون + قيد محاسبي" |
| Manufacturing | "تكلفة الإنتاج الحقيقية — في لوحة تحكم واحدة" |
| Legal | "فواتير الساعات ومدفوعات الموكلين — منظّمة وواضحة" |
| Rental | "فواتير متكررة، أصول ثابتة، وامتثال زاتكا — كل شيء أوتوماتيك" |
| Education | "رسوم دراسية، رواتب، وتقارير مالية — في نظام واحد" |
| Services | "ربط المشاريع بالفواتير والتقارير — دون إدخال يدوي" |
| Technology | "دخل متكرر، عملاء متعددون، عملات مختلفة — محاسبة واحدة" |
| F&B | "الطلبات، المطبخ، والفواتير — في مكان واحد" (→ use qflavours-fnb.md instead) |

---

## SEO Meta Pattern

- **Title:** برنامج محاسبة لـ[القطاع] | قيود
- **Description:** قيود — برنامج المحاسبة السحابي لـ[القطاع]. فوترة إلكترونية، مخزون، تقارير لحظية. متوافق مع زاتكا. جرّب مجانًا.
- **Focus keyword:** برنامج محاسبة لـ[القطاع]

---

## Design Identity (WP ID 559 — Retail baseline)

**Visual tone:** Deep professional navy — conveys operational reliability for retail.
**Hero image:** `https://www.qoyod.com/wp-content/uploads/2026/04/POS_Artboard-6-copy-15.png`
**Icon style:** `#021544` background + `#17A3A4` stroke — dark icon tiles with teal highlight.
**Feature grid:** 2-column (retail has dense feature list).
**Stats band:** Dark dual-navy `linear-gradient(225deg, #0B143A 0%, #021544 100%)`.
**Testimonials:** 3 equal cards — match sector tag to page (retail → `[general]`, services → `[services]`, food → `[food]`).

**CSS variation block (inject at top of `<style>` for Retail page):**
```css
/* VARIATION-559 */
.prob-icon{background:#021544!important}
.prob-icon svg{stroke:#17A3A4!important}
.stats-band{background:linear-gradient(225deg,#0B143A 0%,#021544 100%)}
.feat-grid{grid-template-columns:repeat(2,1fr)!important}
/* /VARIATION */
```

**Per-sector accent overrides** (swap icon color to sector feel):
- Retail: `#021544` bg + `#17A3A4` stroke (default above)
- Services: `#EAF6F6` bg + `#17A3A4` stroke (soft teal)
- Manufacturing: `#F0F4FF` bg + `#1B63FF` stroke (technical blue)
- Legal: `#0B143A` bg + `#fff` stroke (authoritative dark)
- Education: `#FFF3E0` bg + `#F57C00` stroke (warm amber)

---

## A/B Test Suggestions

| Variable | Version A (current) | Version B |
|---|---|---|
| `headline` | برنامج محاسبي يفهم طبيعة عملك في [القطاع]. | محاسبة [القطاع] بدون تعقيد — قيود مبني لعملك تحديدًا. |
| `cta-text` | ابدأ تجربتك المجانية | جرّب قيود مجانًا 14 يومًا |
| `hero-layout` | 2-col with lead form | 2-col with sector-specific screenshot |
| `subhead` | Sector pain-focused | ZATCA compliance-focused |
| `offer` | Free trial (no card) | Free setup call with sector specialist |
| `problem-framing` | Disconnected tools pain | Compliance + penalty risk |
