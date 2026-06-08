# Prompt: Bookkeeping for Business Owners / Entrepreneurs

**Slug (AR):** `/مسك-الدفاتر-لأصحاب-الأعمال/`
**Slug (EN):** `/en/bookkeeping-for-business-owners/`
**Language:** Arabic (default)
**Status:** Draft

---

## Audience

Saudi SMB owners who don't want to manage their own books. They want to outsource. High Neuroticism (risk-averse) + High Agreeableness (wants a human expert, not just software). Tone: warm, reassuring, service-oriented.

---

## Primary CTA

`احجز استشارتك المجانية` → form anchor `#consultation-form` or dedicated booking page
Secondary: `تعرف على خدمة مسك الدفاتر`

---

## Product: Q Bookkeeping (Qoyod Professional Services)

This is a SERVICE page, not a software page. Qoyod's team runs the books inside Qoyod software on behalf of the customer.

---

## Page Structure (Campaign LP)

### Section 1 — Hero
- **Eyebrow:** خدمة مسك الدفاتر من قيود
- **H1:** دعنا ندير حسابات شركتك — أنت تركّز على عملك.
- **Subhead:** فريق قيود المحترف يُسجّل معاملاتك، يُعدّ تقاريرك، ويضمن امتثالك الضريبي — كل ذلك داخل حساب قيود الخاص بك، مع شفافية كاملة.
- **3 trust bullets:**
  - ✓ محاسبون معتمدون من SOCPA
  - ✓ عمل مباشر داخل حسابك في قيود
  - ✓ رؤية كاملة لكل قيد وتقرير
- **CTA:** احجز استشارتك المجانية
- **Trust signal:** موثوق من أكثر من 2,000 شركة سعودية

### Section 2 — Problem
- **Eyebrow:** التحديات التي يواجهها أصحاب الأعمال
- **H2:** المحاسبة اليدوية تستهلك وقتك — وتزيد مخاطرك.
- **Card 1:** التأخر في تسجيل المعاملات يخلق فوضى في الدفاتر وأرقامًا غير دقيقة عند الحاجة لاتخاذ قرار.
- **Card 2:** الاعتماد على محاسب خارجي بدون نظام موحّد يعني ضعف الرقابة وغياب الشفافية.
- **Card 3:** اكتشاف أخطاء المحاسبة في وقت الضريبة يكون متأخرًا وأكثر تكلفة في الإصلاح.

### Section 3 — Solution
- **Eyebrow:** ما تحصل عليه مع خدمة مسك الدفاتر
- **H2:** فريق محاسبة متخصص — يعمل داخل نظامك.
- **Services list:**
  - تسجيل يومي للمعاملات
  - مطابقة الحسابات البنكية
  - إعداد تقارير ضريبة القيمة المضافة
  - إعداد كشوف الرواتب
  - تقارير مالية شهرية
  - خدمات الإعداد والتنظيف المحاسبي
- **Key differentiator box:** أنت تبقى في السيطرة الكاملة — الفريق يعمل داخل حسابك، كل شيء مرئي لك في أي وقت.

### Section 4 — How it works (3 steps)
1. احجز استشارة مجانية — نفهم احتياجاتك
2. نختار الباقة المناسبة ونبدأ الإعداد
3. فريقنا يتولى دفاترك كل يوم — أنت تستلم التقارير

### Section 5 — Proof
Use approved testimonials (especially service-focused ones).

### Section 6 — Final CTA
- **H2:** احجز استشارتك المجانية اليوم.
- **Subhead:** نفهم احتياجات شركتك ونُقترح عليك الباقة المناسبة — بدون إلزام.
- **Consultation form:** الاسم · الجوال · البريد · حجم الشركة (عدد الموظفين) · ملاحظات

---

## SEO Meta

- **Title:** خدمة مسك الدفاتر لأصحاب الأعمال | قيود
- **Description:** فريق قيود المحترف يدير دفاترك المحاسبية بالكامل — تسجيل يومي، تقارير ضريبية، امتثال زاتكا. احجز استشارتك المجانية.
- **Focus keyword:** خدمة مسك الدفاتر

---

## Design Identity (WP ID 557 — baseline)

**Visual tone:** Warm, service-first — teal accents signal human expertise over automation.
**Hero image:** `https://www.qoyod.com/wp-content/uploads/2026/04/برنامج-محاسبة-سحابي-لأصحاب-الأعمال.png`
**Icon style:** `#EAF6F6` background + `#17A3A4` turquoise stroke — soft trusted palette.
**Feature grid:** 3-column standard.
**Stats band:** Deep navy `#010B2A` — calm, trustworthy.
**Testimonials:** Asymmetric layout — featured card (2×height, right) + 2 stacked cards (left). Use `[services]` + `[general]` tags.

**CSS variation block (inject at top of `<style>`):**
```css
/* VARIATION-557 */
.prob-icon{background:#EAF6F6!important}
.prob-icon svg{stroke:#17A3A4!important}
.stats-band{background:#010B2A}
.testi-grid{grid-template-columns:2fr 1fr!important;grid-template-rows:1fr 1fr!important}
.testi-card:first-child{grid-row:1/3!important;border-right:3px solid #17A3A4}
.testi-card:first-child blockquote{font-size:17px!important}
/* /VARIATION */
```

---

## A/B Test Suggestions

| Variable | Version A (current) | Version B |
|---|---|---|
| `headline` | احصل على محاسب معتمد يدير دفاترك — دون الحاجة لموظف штатный دائم. | تخلّص من ضغط المحاسبة. فريقنا يدير الأرقام بدلًا عنك. |
| `cta-text` | احجز استشارتك المجانية | تحدث مع محاسب معتمد الآن |
| `hero-layout` | 2-col with lead capture form | 2-col with accountant trust visual (SOCPA badge) |
| `subhead` | Expertise-focused ("محاسبون معتمدون من هيئة المحاسبين") | Peace-of-mind focused ("لا تقلق بشأن الضرائب — نحن نتولى كل شيء") |
| `offer` | Free consultation call | Free first-month diagnostic (no commitment) |
| `problem-framing` | Time cost (hours spent on bookkeeping) | Risk cost (fines, errors, late filing) |
