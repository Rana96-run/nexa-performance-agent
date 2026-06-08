# Qoyod — Landing Page Reference (Paid & Conversion)
**Identity:** lp.qoyod.com and qoyod.com are the **same brand, same design system, same tokens**.  
**Single source of truth:** `docs-rana/docs-rana/brand/design-system.md` — that file built the main website.  
**This file:** A paid-ads/conversion-focused *view* of the same system. No new tokens. No divergence.  
**What's different on lp.qoyod.com:** Content type only — paid campaigns and conversion pages, not blogs or SEO articles.  
**Maintained by:** Rana Khalid — based on design-system.md (May 2026) + qoyod.com live audit.

---

## 1. Brand Truth (from live site)

| Signal | Value |
|---|---|
| Customers | +25,000 Saudi companies |
| Monthly users | +100,000 |
| Monthly accounting operations | +25 million |
| Years in market | 10+ |
| Google rating | ⭐ 4.7 / 5 · 1,000+ reviews |
| Phone | 8004330088 |
| Support email | support@qoyod.com |
| Signup URL | https://www.qoyod.com/signup/ |

**Product suite:**
- برنامج قيود المحاسبي — core accounting
- نظام نقاط البيع — POS (general retail)
- قيود فليفرز — POS for F&B
- خدمات قيود الاحترافية — Professional Services (bookkeeping, tax, setup)

---

## 2. Color Tokens

**Canonical source: `docs-rana/docs-rana/brand/design-system.md`** — these are the tokens that built qoyod.com and are the single source of truth for all Qoyod properties including lp.qoyod.com.

```css
:root {
  /* Brand — from design-system.md */
  --navy-900:   #0B143A;   /* Headlines, nav, dark card headers, chips */
  --navy-800:   #121D49;   /* Dark card surfaces */
  --navy-deep:  #010B2A;   /* Footer background */
  --turq-dark:  #01355A;   /* Gradient end, eyebrow pill text */
  --blue-600:   #1B63FF;   /* Primary CTA buttons, active fills, progress bars */
  --blue-500:   #3C7EFF;   /* Avatar fills, secondary interactive */
  --blue-100:   #E1EDFF;   /* Section backgrounds */
  --blue-50:    #EDF5FF;   /* Row highlights, stat tiles, subtle fills */
  --turq:       #17A3A4;   /* Accent color, icons, hover states */
  --turq-soft:  #CFECEC;   /* Eyebrow pill border, tinted surface borders */
  --turq-50:    #EAF6F6;   /* Eyebrow pill bg, icon tile backgrounds */
  --green-500:  #3ABF60;   /* Positive values, active status, growth % */
  --green-100:  #DEF5E5;   /* Green badge backgrounds */

  /* Neutral — from design-system.md */
  --white:      #FFFFFF;   /* Card backgrounds, text on dark */
  --gray-100:   #F5F7FB;   /* Alternating section bg */
  --gray-200:   #E8ECF3;   /* Dividers, borders, input strokes */
  --gray-400:   #9CA4B4;   /* Placeholder text, column headers */
  --gray-600:   #5A6478;   /* Body copy, sub-labels */

  /* Retained from V3 brand (used in gradients and CTA band) */
  --navy:       #021544;   /* V3 Primary Navy — hero gradient start, CTA band */
  --ink:        #0B1220;   /* Near-black body text */
  --ink-soft:   #2A3345;   /* Secondary text */
  --muted:      #6B7280;   /* Captions, form sub-labels */
  --bg-soft:    #F7FAFB;   /* Form field bg (≈ gray-100) */

  /* Radius */
  --radius-xl:  24px;      /* Cards, forms, modals */
  --radius-lg:  18px;      /* Smaller cards */
  --radius-md:  12px;      /* Inputs, buttons, small components */

  /* Shadows — from design-system.md */
  --shadow-card: 0 4px 16px rgba(11,20,58,.08), 0 24px 60px rgba(11,20,58,.10);
  --shadow-pop:  0 24px 60px rgba(11,20,58,.18);
  --shadow-btn:  0 8px 24px rgba(27,99,255,.25);   /* blue-600 CTA shadow */

  /* Gradients */
  --grad-primary: linear-gradient(225deg, #021544 0%, #01355A 100%);   /* CTA band, nav dark bar */
  --grad-accent:  linear-gradient(225deg, #0B143A 0%, #1B63FF 100%);   /* navy-900 → blue-600 */
}
```

**Gradient direction:** 225° CSS = visual 45° top-right → bottom-left (brand guideline).  
**`--grad-accent`** (navy-900→blue-600): H1 accent spans, price badges, success icons.

> ⚠️ **Existing LP HTML files** (`qoyod-cloud-accounting.html`, `qoyod-einvoice-zatca-phase2.html`, etc.) were built with the older V3 brand values (`#021544` as `--navy`, `#13778D` as `--blue`, `#E4E8EE` as `--line`). New pages use the canonical design-system.md tokens above. If visual consistency with existing pages is needed, the old HTML files should be updated to match.

---

## 3. Typography

**One font only: Lama Sans** (Arabic + English, all weights).  
Web fallback: `'IBM Plex Sans Arabic', system-ui, sans-serif`. Never Inter, Cairo, or Tajawal.

```css
font-family: 'Lama Sans', 'IBM Plex Sans Arabic', system-ui, sans-serif;
/* ⚠️ Note: "Lama Sans" with a space — not "LamaSans" */
```

| Usage | Weight | Size | Line Height |
|---|---|---|---|
| Hero H1 | Bold | 52–56px | 110–115% |
| Section H2 | Bold | 42–48px | 115–130% |
| Card title / H3 | SemiBold | 20–24px | 130% |
| Body copy | Regular | 16–18px | 170–180% |
| Button | SemiBold | 16–17px | — |
| Eyebrow pill | SemiBold | 12–13px | — |
| Meta / caption | Medium | 12–13px | — |
| Trust stat value | Bold | 28–36px | — |

**Arabic line-height:** always 10–15% taller than EN equivalent.

---

## 4. Spacing Grid (8pt)

`8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 60 · 80 · 90`

Section padding: `90px 24px` top/bottom, `24px` sides.  
Content max-width: `1200px`, centered.

---

## 5. Component Specs

### Eyebrow Pill
```css
/* From design-system.md: fill:none, stroke:1px blue-600, text:blue-600 */
background: transparent;
border: 1px solid #1B63FF;   /* blue-600 */
color: #1B63FF;              /* blue-600 */
border-radius: 999px;
padding: 8px 16px;
font-weight: 600;
font-size: 12px;             /* 12–13px */
font-family: 'Lama Sans', 'IBM Plex Sans Arabic', system-ui, sans-serif;
/* EN only: */
text-transform: uppercase;
letter-spacing: 1.2px;
/* AR: normal case, font-size: 13px */
```

### Primary CTA Button (on light backgrounds)
```css
background: #1B63FF;         /* var(--blue-600) — from design-system.md */
color: #ffffff;
border-radius: 12px;
padding: 18px 32px;
font-weight: 600;
font-size: 17px;
font-family: 'Lama Sans', 'IBM Plex Sans Arabic', system-ui, sans-serif;
box-shadow: 0 8px 24px rgba(27,99,255,0.25);   /* blue-600 shadow */
border: none; cursor: pointer;
/* Hover: */
background: #0B143A;         /* var(--navy-900) */
transform: translateY(-2px);
```

### CTA Button (on dark/gradient backgrounds — inverted)
```css
/* White button on dark gradient section */
background: #ffffff;
color: #0B143A;              /* var(--navy-900) */
box-shadow: 0 12px 30px rgba(0,0,0,0.25);
border-radius: 12px;
padding: 15px 30px;
font-weight: 600;
font-size: 16px;
/* Hover: */
background: #17A3A4;         /* var(--turq) */
color: #ffffff;
```

### White Card
```css
background: #ffffff;
border-radius: 20px;         /* design-system.md: 20–24px */
padding: 30px 24px;
border: 1px solid #E8ECF3;  /* var(--gray-200) — from design-system.md */
box-shadow:
  0 4px 16px rgba(11,20,58,0.08),
  0 24px 60px rgba(11,20,58,0.10);
/* var(--shadow-card) */
```

### Problem Card (icon + title + body)
Same as White Card. Icon tile: `40×40px`, `border-radius:12px`, `background:#EAF6F6`.

### Testimonial Card
```css
/* Same as White Card */
/* Stars row: 5× ⭐ in #F59E0B, 16px, gap:4px */
/* Avatar: 44×44px circle, gradient fill, initials Bold 18px white */
/* Reviewer name: Bold 15px #021544 */
/* Reviewer title: 13px #6B7280 */
```

### Section (wrapper)
```css
padding: 90px 24px;
max-width: 1200px;
margin: 0 auto;
```

### Alternating section backgrounds
- Odd sections: `#FFFFFF`
- Even sections: `#F7FAFB`
- CTA section: gradient `linear-gradient(225deg, #021544 0%, #01355A 100%)`
- Footer: `#010B2A`

---

## 6. Page Architecture — Conversion LP

Every paid campaign page uses this order. Never skip, never reorder.

```
Nav (sticky, minimal)
│
├── 1. HERO — hook + offer + CTA
│        Hook = #1 pain of the segment
│        Offer = what Qoyod solves in 1 line
│        CTA = primary action (trial / consultation)
│
├── 2. PROBLEM — 3 pain cards
│        Each card = 1 daily friction point, specific to this segment
│        Title: the problem in 4–6 words
│        Body: why it hurts and what it costs
│
├── 3. SOLUTION — features as outcomes
│        Eyebrow → H2 → 3–4 differentiator cards
│        Each card: icon + capability + benefit (not feature names)
│        Optional: 6-item feature grid below cards
│
├── 4. PROOF — testimonials + trust stats
│        3 shuffled reviews from testimonials.js (sector-matched)
│        Below: 4 trust stats from §1 Brand Truth
│
├── 5. CTA (final)
│        Dark gradient section
│        H2 + subhead + primary button (turquoise on dark)
│        3-step expectation list (numbered, RTL-aware)
│
└── Footer (minimal: logo, links, ZATCA badge, copyright)
```

**Note:** Pricing and FAQ are optional. Add for full product pages, skip for campaign LPs.

---

## 7. RTL Rules (Arabic pages — mandatory)

```html
<html lang="ar" dir="rtl">
```
```css
direction: rtl;
text-align: right;
```

| Element | AR position |
|---|---|
| Hero copy block | RIGHT column (54% width) |
| Hero form / visual | LEFT column (43% width) |
| Primary CTA in pair | RIGHT (reads first in RTL) |
| Secondary CTA | LEFT |
| Step 1 in numbered list | RIGHTMOST |
| Most important card in row | RIGHTMOST |
| Footer logo | RIGHT |
| Nav logo | RIGHT, CTA at LEFT |

**Numbers:** always English digits (0–9). `⃁ 240` for SAR (symbol first, space, number). `20%` not `٢٠٪`.

---

## 8. Hero Variants

### Campaign LP Hero (2-column)
```css
/* Hero section background — from design-system.md */
background: #E1EDFF;         /* blue-100 */
/* + large radial glow: */
background:
  radial-gradient(ellipse 900px 600px at 80% 0%, rgba(255,255,255,0.80) 0%, transparent 60%),
  #E1EDFF;
```
```
[RIGHT col — 54%]          [LEFT col — 43%]
Eyebrow pill               Lead form  OR  product visual
H1 (3 lines max, 52–56px)
Subhead (2 lines max, 17–18px)
3 trust bullets (✓ icon)
[Primary CTA]  [Secondary CTA]
Trust signal line
```

### Full-width Hero (single message, no form)
```
[CENTER — max 720px wide]
Eyebrow pill (centered)
H1 (2 lines, centered)
Subhead (centered)
CTA button (centered)
Trust signal (centered, muted)
```

---

## 9. Conversion Copy Rules

These rules apply to every section of every page. Non-negotiable.

1. **Lead with pain, not product** — hero H1 names the buyer's biggest problem, not Qoyod's name
2. **"You" language** — address the reader directly: "تبيع، تسجّل، وتمتثل"
3. **Benefits over features** — always translate capabilities: "فواتير زاتكا تلقائية" → "لا غرامات ولا تأخير"
4. **Concrete over abstract** — "175,000 ريال" not "خسائر كبيرة"
5. **One CTA per section** — never split attention with multiple competing actions
6. **Social proof near every CTA** — testimonial or stat within visible scroll of each CTA
7. **No fake urgency** — no countdown timers, no "limited offer" unless genuinely true
8. **No dark patterns** — no hidden unsubscribe, no pre-checked boxes, no misleading copy
9. **Short paragraphs** — max 2 sentences per body block in Arabic
10. **Trust before ask** — always place at least 1 trust signal before the primary CTA

---

## 10. CTA Rules by Page Type

| Page | Primary CTA (AR) | URL |
|---|---|---|
| Accounting / ZATCA | ابدأ تجربتك المجانية | https://www.qoyod.com/signup/ |
| Bookkeeping service | احجز استشارتك المجانية | `#consultation-form` |
| Flavours (F&B) | اشترك الآن / ابدأ الآن | https://www.qoyod.com/signup/ |
| POS / Retail | ابدأ تجربتك المجانية | https://www.qoyod.com/signup/ |
| Sectors | ابدأ تجربتك المجانية | https://www.qoyod.com/signup/ |

---

## 11. Trust Signals (use these verbatim)

```
+25,000 شركة سعودية تثق في قيود
+100,000 مستخدم شهري
+25 مليون عملية محاسبية شهرياً
تقييم 4.7 / 5 من أكثر من 1000 مراجعة على Google
10+ سنوات في السوق السعودي
متوافق 100% مع زاتكا — المرحلة الثانية
```

---

## 12. Approved Terminology (use exactly, never paraphrase)

| Context | Correct AR | Correct EN |
|---|---|---|
| Product name | قيود | Qoyod |
| Full product name | برنامج قيود المحاسبي | Qoyod Accounting Software |
| POS system | نظام نقاط البيع | Point of Sale System |
| Flavours | قيود فليفرز | Qoyod Flavours |
| Pro Services | خدمات قيود الاحترافية | Qoyod Professional Services |
| Bookkeeping | مسك الدفاتر | Bookkeeping |
| Tax authority | هيئة الزكاة والضريبة والجمارك | ZATCA |
| E-invoice | الفوترة الإلكترونية | E-Invoice |
| Integration | التكامل / الربط | Integration |
| Free trial | التجربة المجانية | Free Trial |
| Start free | ابدأ مجاناً | Start Free |

---

## 13. Standard UI Copy (verbatim)

### CTAs
| AR | EN |
|---|---|
| ابدأ تجربتك المجانية | Start Your Free Trial |
| احجز استشارتك المجانية | Book Your Free Consultation |
| اشترك الآن | Subscribe Now |
| ابدأ الآن | Get Started |
| جرّب مجاناً لمدة 14 يوماً | Try free for 14 days |

### Trust bullets (hero)
| AR |
|---|
| ✓ بدون بطاقة ائتمان |
| ✓ جاهز خلال دقيقتين |
| ✓ متوافق مع زاتكا المرحلة الثانية |
| ✓ 14 يوماً مجاناً بدون إلزام |
| ✓ فواتير إلكترونية متوافقة مع زاتكا |
| ✓ مزامنة تلقائية مع المخزون والمحاسبة |

### Pain points (problem section openers)
| AR |
|---|
| هل ما زلت تضيع وقتك في تصحيح أخطاء كان يمكن تفاديها؟ |
| أدوات غير متصلة تُبطئك |
| العمل اليدوي يرفع احتمالية الخطأ والتأخير |
| رؤية مالية متأخرة حتى نهاية الشهر |

---

## 14. Testimonials

**Source file:** `prompts/testimonials.js`  
**Usage:** `getTestimonials(3, 'ar', sector)` — returns 3 shuffled, sector-prioritized reviews.

Sector tags: `'food'` · `'zatca'` · `'services'` · `'general'`

**Pool (6 AR, 8 EN) — never invent, never paraphrase:**

| Name | Company | Sector tag |
|---|---|---|
| صالح العيدان | لحامم | food |
| أمل التركي | THE BEST SALADS | food |
| عبدالله زيد أبو حادر | الوائل البري | general |
| عبدالكريم الصفوق | TSMEEN | zatca |
| خلود المطلق | CATTLEYA Studio | services |
| فراس العتيق | BIOTIC & BIO X | general |

---

## 15. Feature → Benefit Map

Full feature list: `prompts/features-integrations.md`

| Feature | Benefit (plain Arabic) |
|---|---|
| تكامل زاتكا | امتثل دون خطوات إضافية أو دخول لموقع الهيئة |
| وحدة المبيعات | أصدر فواتير دقيقة سريعاً بدون إدخال يدوي |
| وحدة المشتريات | سجل مشترياتك وتتبع التدفق النقدي بوضوح |
| إدارة المخزون | اعرف رصيدك الفعلي دائماً — بدون جرد يدوي |
| الرواتب | ادفع موظفيك بدقة وفي الوقت المحدد |
| الأصول الثابتة | دفاتر دقيقة وسجلات أصول نظيفة بدون تعقيد |
| التقارير اللحظية | اتخذ قرارات العمل بثقة وبيانات حية |
| واجهة عربية كاملة | سهّل تأهيل فريقك وقلّل أخطاء الاستخدام |
| سحابي بالكامل | راجع بياناتك من أي مكان وفي أي وقت |
| إعداد احترافي | ابدأ خلال دقيقتين بدون مساعدة خارجية |

---

## 16. Competitive Positioning (use in problem/alternatives sections)

| vs. | Their edge | Their gap | Qoyod wins by |
|---|---|---|---|
| Wafeq | Simple UI, MENA-native | No POS, no payroll, no assets | Full platform + ZATCA Phase 2 native |
| Rewaa | Strong inventory/retail | Not full accounting, weak reporting | Integrated accounting + POS + compliance |
| Daftra | Flexible modules | Complex for SMBs, slow to set up | Purpose-built for ease, fast onboarding |
| Excel | Familiar, free | ZATCA non-compliant, error-prone | Compliance built-in, no spreadsheet chaos |
| Global tools | Free/cheap, mobile | No Arabic, no VAT, no ZATCA | Built for Saudi market from the ground up |

---

## 17. Integrations (use as trust signals)

Full integration details: `prompts/features-integrations.md`

**E-commerce:** Salla (سلة) · Zid (زد) · WooCommerce · Shopify  
**Payments:** Geidea · Moyasar · HyperPay · Tamara · Tabby · Hala  
**HR/Payroll:** Jisr (جسر) — payroll, GOSI  
**Automation:** Zapier · Open API  
**Messaging:** WhatsApp  
**Productivity:** Google Sheets  
**F&B:** Foodics  
**Government:** ZATCA (Phase 1 & 2)  

**What Salla syncs:** Orders → invoices, inventory quantities, accounting records  
**What Zid syncs:** Financial entries, inventory, ZATCA compliance  
**What Jisr syncs:** Payroll, employee data, GOSI  

---

## 18. Hard Rules (never violate)

- ❌ No emojis as icons — SVG only
- ❌ Lama Sans only — no Inter / Cairo / Tajawal
- ❌ Never invent quotes or stats — only approved sources
- ❌ Signup CTA → `https://www.qoyod.com/signup/` always
- ❌ No fake urgency, no fake scarcity, no dark patterns
- ❌ Never publish — always `status: draft`
- ❌ Arabic slug: no `/en/` prefix. English: must have `/en/`
- ❌ Never touch global header/footer (theme-level, separate task)
- ❌ Never use `elementor_canvas` template — use default
- ❌ No Yoast — use Rank Math for SEO meta
- ❌ Arabic pages: `direction:rtl; text-align:right` on ALL wrappers
- ❌ Never edit `_elementor_data` without backing up first

---

## 19. WordPress Deploy Checklist

Before every POST to WordPress:

- [ ] Status is `draft` (never `publish`)
- [ ] Slug follows pattern (AR: no `/en/`, EN: has `/en/`)
- [ ] `_elementor_edit_mode: 'builder'`
- [ ] `_elementor_template_type: 'wp-page'`
- [ ] Rank Math meta set: title, description, focus keyword
- [ ] Cache busted: `DELETE /wp-json/elementor/v1/cache`
- [ ] Screenshot taken: desktop (1440px) + mobile (390px)
- [ ] Backup of `_elementor_data` saved to `backups/<slug>_<id>_<timestamp>.json`

---

*Qoyod LP Design System — Paid Ads & Conversion Pages*  
*Built from design-system.md + live qoyod.com audit, May 2026*  
*Maintained by: Rana Khalid (rana.khalid@qoyod.com)*
