# Prompt: Qoyod Flavours — F&B

**Slug (AR):** `/فليفرز/`
**Slug (EN):** `/en/qoyod-flavours/`
**Language:** Arabic (default)
**Status:** Draft

---

## Audience

Restaurant, café, and F&B business owners. Practical, operational mindset. Primary pain: managing orders, kitchen workflow, and compliance simultaneously. Tone: practical, energetic, fast-to-value.

## Sub-product name
**فليفرز** (Flavours) — نظام نقاط البيع لقطاع الأغذية والمشروبات

---

## Primary CTA

`اشترك الآن` / `ابدأ الآن` → `https://www.qoyod.com/signup/`
Secondary: `شاهد كيف يعمل فليفرز`

---

## Page Structure (Campaign LP)

### Section 1 — Hero
- **Eyebrow:** نظام نقاط البيع للمطاعم والكافيهات
- **H1:** إدارة مطعمك كلها في مكان واحد.
- **Subhead:** فليفرز من قيود — نظام نقاط بيع مصمَّم لقطاع الأغذية والمشروبات. طلبات، مطبخ، فواتير، ومحاسبة — كل شيء متصل.
- **3 trust bullets:**
  - ✓ بدون بطاقة ائتمان
  - ✓ جاهز خلال دقيقتين
  - ✓ معتمد من هيئة الزكاة والضريبة والجمارك
- **CTA:** ابدأ الآن
- **Right side:** Lead form (الاسم · الجوال · البريد · نوع المطعم · عدد الفروع)

### Section 2 — Problem
- **Eyebrow:** مشاكل المطاعم اليومية
- **H2:** الأنظمة المنفصلة تُضيّع وقتك وتُضاعف أخطاءك.
- **Card 1:** الطلبات تصل للمطبخ متأخرة أو غير مكتملة عند العمل بورق أو أنظمة قديمة.
- **Card 2:** نقاط البيع المنفصلة عن المحاسبة تعني إدخالًا يدويًا مزدوجًا وأرقامًا غير متطابقة.
- **Card 3:** الفواتير الإلكترونية ومتطلبات زاتكا تُضاف فوق كل هذا — دون أتمتة.

### Section 3 — Features (4 cards)
- **Eyebrow:** ما يقدمه فليفرز
- **H2:** كل ما يحتاجه مطعمك — في نظام واحد.
- **Card 1 — بيانات لحظية:** تابع مبيعاتك وأداء الفروع في الوقت الفعلي من أي جهاز.
- **Card 2 — عميلك يطلب بنفسه:** QR ordering — العميل يطلب من طاولته مباشرةً.
- **Card 3 — إدارة مطبخ أسرع:** الطلبات تصل للمطبخ فور إتمامها — بدون ورق وبدون تأخير.
- **Card 4 — كل الطلبات في شاشة واحدة:** سواء كانت طلبات داخلية أو توصيل أو طلب طاولة — كلها في مكان واحد.

### Section 4 — How it works (3 steps)
1. **سجّل مجاناً** — أنشئ حسابك في دقيقتين
2. **جهّز قائمتك** — أضف منتجاتك وأسعارك وفروعك
3. **ابدأ البيع** — ابدأ باستقبال الطلبات فورًا مع فواتير إلكترونية متوافقة

### Section 5 — Proof
Use approved testimonials, especially Amal Al-Turki (THE BEST SALADS — POS audience).

### Section 6 — Final CTA
- **H2:** ابدأ تجربتك المجانية مع فليفرز اليوم.
- Form + CTA

---

## Brand Note

فليفرز is a sub-product of Qoyod. Use the logo: قيود + فليفرز side-by-side. The sub-product color accent can lean toward turquoise while keeping the navy primary.

---

## SEO Meta

- **Title:** فليفرز — نظام نقاط البيع للمطاعم والكافيهات | قيود
- **Description:** فليفرز من قيود — نظام POS لقطاع الأغذية والمشروبات. طلبات، مطبخ، فواتير زاتكا، ومحاسبة في مكان واحد. ابدأ مجانًا.
- **Focus keyword:** نظام نقاط البيع للمطاعم

---

## Design Identity (WP ID 558 — baseline)

**Visual tone:** Warm amber-orange — F&B energy, appetite, fast-paced operations.
**Hero image:** `https://www.qoyod.com/wp-content/uploads/Flavours-1.webp`
**Icon style:** `#FFF3E0` background + `#F57C00` orange stroke — warm F&B palette.
**Feature grid:** 2-column (matches operational density of F&B workflow).
**Stats band:** Teal gradient `linear-gradient(225deg, #01355A 0%, #17A3A4 100%)`.
**Testimonials:** 3 equal cards — use `[food]` tag (Amal Al-Turki + Saleh Al-Eidan priority).

**CSS variation block (inject at top of `<style>`):**
```css
/* VARIATION-558 */
.prob-icon{background:#FFF3E0!important;border:1px solid #FFCC80!important}
.prob-icon svg{stroke:#F57C00!important}
.stats-band{background:linear-gradient(225deg,#01355A 0%,#17A3A4 100%)}
.feat-grid{grid-template-columns:repeat(2,1fr)!important}
/* /VARIATION */
```

---

## A/B Test Suggestions

| Variable | Version A (current) | Version B |
|---|---|---|
| `headline` | أدِر مطعمك من الطلب حتى الفاتورة في نظام واحد. | فليفرز — POS المطاعم الذي يُدير الطلبات والمحاسبة معًا. |
| `cta-text` | اشترك الآن | ابدأ مجانًا مع فليفرز |
| `hero-layout` | 2-col with lead form | 2-col with Flavours product visual (Flavours-1.webp) |
| `subhead` | Operations-focused ("من الطلب للمطبخ للفاتورة تلقائيًا") | Compliance-focused ("فواتير زاتكا تصدر تلقائيًا مع كل طلب") |
| `offer` | 14-day free trial | Free POS setup for the first branch |
| `problem-framing` | Operational chaos (3 disconnected systems) | Revenue leakage (errors in manual order entry) |
