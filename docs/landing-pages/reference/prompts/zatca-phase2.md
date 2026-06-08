# Prompt: ZATCA Phase 2

**Slug (AR):** `/زاتكا-المرحلة-الثانية/`
**Slug (EN):** `/en/zatca-phase-2/`
**Language:** Arabic (default)
**Status:** Draft

---

## Audience

Saudi businesses in the current wave of ZATCA Phase 2 rollout. Mixed segment — both SMB owners and accounting professionals. More technical than the compliance page; explains what Phase 2 actually requires. Tone: clear, informative, action-oriented.

---

## Primary CTA

`سجّـل بياناتك الآن` → `https://www.qoyod.com/signup/`
Secondary: `اختبر الربط قبل الانطلاق`

---

## Page Structure (Campaign LP)

### Section 1 — Hero
- **Eyebrow:** فوترة إلكترونية — المرحلة الثانية من زاتكا
- **H1:** اربط شركتك بهيئة الزكاة. قبل الموعد النهائي.
- **Subhead:** قيود يُولّد فواتيرك الإلكترونية ويرسلها لهيئة الزكاة تلقائيًا — بتوقيع رقمي ورمز QR وربط كامل عبر بروتوكول PEPPOL.
- **3 trust bullets:**
  - ✓ ربط تلقائي مع بوابة زاتكا (PEPPOL API)
  - ✓ توقيع رقمي ورمز QR في كل فاتورة
  - ✓ محاسب معتمد SOCPA يتولى الإعداد
- **CTA:** سجّـل بياناتك الآن
- **Urgency note (honest):** تحقق من موعد امتثال قطاعك على موقع هيئة الزكاة

### Section 2 — What is Phase 2 (educational)
- **H2:** ما هي المرحلة الثانية من زاتكا؟
- Brief explanation: الربط التكاملي — إرسال الفواتير مباشرةً لمنظومة زاتكا لحظة إصدارها
- 3 key requirements: XML + QR + Digital Signature + Real-time submission
- Timeline info (pull from product/features.md if available)

### Section 3 — How Qoyod handles it
- **H2:** كيف يتولى قيود الربط كاملًا.
- Step 1 — إعداد الحساب مع متخصص معتمد
- Step 2 — اختبار الربط قبل الانطلاق الفعلي
- Step 3 — ربط وإرسال لحظي لكل فاتورة
- Step 4 — مراقبة وتنبيهات مستمرة

### Section 4 — Features
- XML متوافق مع متطلبات هيئة الزكاة
- رمز QR تلقائي
- توقيع رقمي معتمد
- إرسال لحظي (Clearance mode)
- سجل كامل قابل للتدقيق
- تقارير الامتثال

### Section 5 — Proof + CTA
- Approved testimonials
- Final form + 3-step expectations

---

## SEO Meta

- **Title:** زاتكا المرحلة الثانية — الربط التكاملي | قيود
- **Description:** اربط شركتك بمنظومة زاتكا المرحلة الثانية مع قيود المعتمد. ربط تلقائي، توقيع رقمي، محاسب معتمد.
- **Focus keyword:** زاتكا المرحلة الثانية

---

## Design Identity (WP ID 556 — baseline)

**Visual tone:** Deep blue-navy — technical authority, urgency through compliance.
**Hero image:** `https://www.qoyod.com/wp-content/uploads/2026/01/V2-02-scaled1.png`
**Icon style:** `#0B143A` background + `#17A3A4` turquoise SVG stroke — dark icon tiles.
**Feature grid:** 2-column (denser technical spec layout).
**Stats band:** Blue gradient `linear-gradient(225deg, #0B143A 0%, #1B63FF 100%)`.
**Testimonials:** 3 equal cards — use `[zatca]` tag.

**CSS variation block (inject at top of `<style>`):**
```css
/* VARIATION-556 */
.feat-icon{background:#0B143A!important}
.feat-icon svg{stroke:#17A3A4!important}
.stats-band{background:linear-gradient(225deg,#0B143A 0%,#1B63FF 100%)}
.feat-grid{grid-template-columns:repeat(2,1fr)!important}
/* /VARIATION */
```

---

## A/B Test Suggestions

| Variable | Version A (current) | Version B |
|---|---|---|
| `headline` | اربط شركتك بالمرحلة الثانية من زاتكا قبل فوات الأوان. | الامتثال للمرحلة الثانية أسهل مما تظن — قيود يربطك تلقائيًا. |
| `cta-text` | سجّل بياناتك الآن | ابدأ الربط بزاتكا مجانًا |
| `hero-layout` | 2-col with lead form | Full-width hero + single CTA button |
| `subhead` | Compliance penalty focused (5,000 ⃁ per violation) | Time-to-live focused ("أقل من ساعة للربط الكامل") |
| `offer` | 14-day free trial | Free setup call with SOCPA accountant |
| `problem-framing` | Technical gap (XML, digital signature, clearance mode) | Business risk (penalties, audit trail, ZATCA rejection) |
