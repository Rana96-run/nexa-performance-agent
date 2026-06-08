# Prompt: POS for Retailers

**Slug (AR):** `/نقاط-البيع-للتجزئة/`
**Slug (EN):** `/en/pos-for-retailers/`
**Language:** Arabic (default)
**Status:** Draft

---

## Audience

Physical retail store owners — groceries, boutiques, electronics shops, salons, repair shops. Operational mindset. Primary pain: POS disconnected from accounting, ZATCA compliance, manual double-entry. Tone: practical, operational, fast-to-value.

---

## Primary CTA

`ابدأ تجربتك المجانية` → `https://www.qoyod.com/signup/`
Secondary: `شاهد كيف يعمل نظام نقاط البيع`

---

## Page Structure (Campaign LP)

### Section 1 — Hero
- **Eyebrow:** نظام نقاط البيع للتجزئة
- **H1:** بيع، سجّل، وامتثل — كل شيء في نقطة بيع واحدة.
- **Subhead:** قيود POS يُصدر فواتير إلكترونية متوافقة مع زاتكا لحظة البيع، ويزامن مخزونك ومحاسبتك تلقائيًا — دون إدخال يدوي.
- **3 trust bullets:**
  - ✓ فواتير إلكترونية متوافقة مع زاتكا في كل معاملة
  - ✓ مزامنة تلقائية مع المخزون والمحاسبة
  - ✓ يعمل على Android وأجهزة Sunmi
- **CTA:** ابدأ تجربتك المجانية
- **Trust signal:** موثوق من آلاف متاجر التجزئة السعودية

### Section 2 — Problem
- **Eyebrow:** لماذا يواجه أصحاب المتاجر هذه التحديات
- **H2:** أنظمة نقاط البيع المنفصلة تخلق أعباءً يومية.
- **Card 1:** سجلات النقد وصناديق المبيعات التقليدية لا تُصدر فواتير زاتكا — ما يعرّضك للغرامات.
- **Card 2:** عندما لا يتصل POS بالمحاسبة، تُضطر لإدخال نفس البيانات مرتين.
- **Card 3:** المخزون يُدار بشكل منفصل — لا تعرف ما بقي في المستودع إلا عند الجرد اليدوي.

### Section 3 — Solution
- **Eyebrow:** ما يقدمه قيود POS
- **H2:** معاملة واحدة. فاتورة زاتكا. تحديث مخزون. قيد محاسبي. كل ذلك في ثوانٍ.
- **Card 1 — فواتير زاتكا تلقائية:** كل بيع = فاتورة إلكترونية متوافقة بتوقيع رقمي ورمز QR.
- **Card 2 — مخزون لحظي:** كل بيع يُحدّث المخزون فورًا — لا تخمين ولا نقص مفاجئ.
- **Card 3 — محاسبة متصلة:** كل بيع ينتقل مباشرةً لدفاتر قيود — لا تصدير، لا إدخال يدوي.
- **Features:**
  - إدارة السلة وتطبيق الخصومات
  - وضع عدم الاتصال مع مزامنة تلقائية
  - طرق دفع متعددة (نقد، بطاقة، هلا)
  - تقارير اليومية وتسوية الوردية
  - دعم طابعات الإيصالات (Epson)
  - تعدد المستخدمين مع PIN
  - شاشة العميل

### Section 4 — Hardware Compatibility
- **H3:** يعمل على أجهزتك الحالية
- Android · Huawei · Sunmi · متصفح الويب

### Section 5 — Proof
Approved testimonials.

### Section 6 — Final CTA
- Form + 3-step expectations
- **CTA:** ابدأ تجربتك المجانية

---

## SEO Meta

- **Title:** نظام نقاط البيع للتجزئة مع فواتير زاتكا | قيود
- **Description:** قيود POS يُصدر فواتير إلكترونية زاتكا، يزامن المخزون، ويُحدّث المحاسبة تلقائيًا. ابدأ مجانًا.
- **Focus keyword:** نظام نقاط البيع للتجزئة

---

## Design Identity (WP ID 548 — baseline)

**Visual tone:** Clean blue with dark hardware section — professional retail tech.
**Hero image:** `https://www.qoyod.com/wp-content/uploads/2026/04/POS_Artboard-6-copy-15.png`
**Icon style:** Blue-100 (`#E1EDFF`) background + blue-600 stroke — default palette for most sections.
**Feature grid:** 3-column.
**Stats band:** Solid navy `#021544`.
**Hardware section:** Dark navy background (`#021544`), 2 horizontal SUNMI device cards only:
  - SUNMI V2s: `https://www.qoyod.com/wp-content/uploads/2026/04/POS_Artboard-6-copy-9.png` (700×480)
  - SUNMI D2 mini: `https://www.qoyod.com/wp-content/uploads/2026/04/POS_Artboard-6-copy-10.png` (700×480)
  - Note in small text: "يعمل قيود POS أيضًا على أي جهاز Android أو متصفح الويب"
**Testimonials:** 3 equal cards — use `[general]` + `[zatca]` tags.

**CSS variation block (inject at top of `<style>`):**
```css
/* VARIATION-548 */
.q-sec-dark{background:var(--navy,#021544)}
.hw-card-h{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);border-radius:20px;display:flex;align-items:center;gap:32px;padding:32px}
.hw-tag{color:#17A3A4;font-size:12px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px}
.hw-specs li::before{background:#17A3A4}
/* /VARIATION */
```

---

## A/B Test Suggestions

| Variable | Version A (current) | Version B |
|---|---|---|
| `headline` | بيع، سجّل، وامتثل لزاتكا من نقطة بيع واحدة. | نظام POS يُصدر فواتير زاتكا تلقائيًا — دون جهد يدوي. |
| `cta-text` | ابدأ تجربتك المجانية | اطلب عرضًا توضيحيًا الآن |
| `hero-layout` | 2-col with lead form | 2-col with POS retail hero image (POS_Artboard-6-copy-15.png) |
| `subhead` | ZATCA compliance focused | Revenue & operations focused ("كل عملية بيع تُحدّث المخزون والمحاسبة فورًا") |
| `offer` | Free trial | Free SUNMI device for first branch (if promotion active) |
| `hardware-section` | 2 SUNMI cards dark section (current) | Grid of 4: SUNMI V2s · D2 mini · Android generic · Web browser |
