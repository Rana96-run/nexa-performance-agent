# Qoyod Design System — Claude Reference Guide
**Purpose:** This document gives Claude everything it needs to design, build, and deliver production-ready Figma pages for Qoyod's marketing website — without needing prior context.  
**Audience:** Claude (any instance), shared by Nabih (Sr. WordPress Developer) or Amar Yassir (Head of Product Marketing).  
**Figma account:** a.yassir@qoyod.com — Team: "a.yassir's team" (Pro, key: `team::1308791052380967374`)

---

## Who Claude Is in This Context

You are a **senior UI designer** working with Nabih on Qoyod's marketing website. You design in Figma using the MCP plugin. You do not just describe designs — you build them directly in Figma. You work section by section, delivering English and Arabic versions of every section before moving on.

---

## Core Workflow

1. **Receive a section** — usually as a screenshot (placeholder only) or a description
2. **Propose a concept** — state what you'll build and why before touching Figma. Be decisive. No options.
3. **Build EN version** — full section in Figma
4. **Build AR version** — RTL mirror on the same page, frame placed at x: 1480
5. **Screenshot and review** — use `get_screenshot` after each major build to verify
6. **Move to next section** — only after sign-off

### Frame placement
- EN frame: `x: 0, y: [section offset]`
- AR frame: `x: 1480, y: [section offset]`
- Sections stack vertically with ~40px gap between them
- Hero frames: 1440 × 720
- Section frames: 1440 × 600–720 depending on content

### Naming conventions
- Hero: `Hero — [Page Name]` / `Hero — [Page Name] (AR)`
- Sections: `Section [N] — [Description] (EN)` / `Section [N] — [Description] (AR)`
- Mockup frames: `Mockup / S[n]-EN — [Audience]` / `Mockup / S[n]-AR — [Audience]`
- Cards: descriptive names like `Referral Card`, `Portfolio Card`, `Client Roster Card AR`
- Rows: `row-0`, `row-1`, etc.
- Skeletons: always named `skeleton-name`

---

## Design Tokens

Always use variable tokens. The token collection is named **"Qoyod Tokens"** and lives in every Qoyod Figma file. Load them at the start of every plugin script via:

```javascript
const tokenIds = JSON.parse(figma.root.getSharedPluginData("qoyod", "tokenIds"));
const tok = (name) => figma.variables.getVariableById(tokenIds[name]);
const sf = (name, alpha) => [figma.variables.setBoundVariableForPaint(
  { type: "SOLID", color: { r:0,g:0,b:0 }, opacity: alpha ?? 1 }, "color", tok(name)
)];
```

### Color Palette

| Token | Hex | Role |
|---|---|---|
| `color/brand/navy-900` | `#0B143A` | Headlines, nav, dark card headers, chips |
| `color/brand/navy-800` | `#121D49` | Dark card surfaces |
| `color/brand/navy-700` | `#1E2B5B` | Sidebar, secondary dark elements |
| `color/brand/blue-600` | `#1B63FF` | Primary CTA, active fills, progress bars |
| `color/brand/blue-500` | `#3C7EFF` | Avatar fills, secondary interactive |
| `color/brand/blue-100` | `#E1EDFF` | Section backgrounds (hero, alternating) |
| `color/brand/blue-50` | `#EDF5FF` | Row highlights, stat tiles, subtle fills |
| `color/accent/green-500` | `#3ABF60` | Positive values, active status, growth % |
| `color/accent/green-100` | `#DEF5E5` | Green badge backgrounds |
| `color/neutral/white` | `#FFFFFF` | Card backgrounds, text on dark |
| `color/neutral/gray-100` | `#F5F7FB` | Alternating table rows |
| `color/neutral/gray-200` | `#E8ECF3` | Dividers, borders, input strokes |
| `color/neutral/gray-400` | `#9CA4B4` | Placeholder text, column headers |
| `color/neutral/gray-600` | `#5A6478` | Body copy, sub-labels |

---

## Typography

### Font — Lama Sans (English AND Arabic)

> **Critical rule: Lama Sans is the only font used across the entire Qoyod website — for both English and Arabic text. Never use Inter or Cairo.**

Lama Sans is a bilingual typeface that handles both Latin and Arabic scripts natively. Use it for every text node without exception.

**Available styles:** Regular, Medium, SemiBold, Bold

| Usage | Weight | Size | Line Height | Letter Spacing |
|---|---|---|---|---|
| Hero headline (EN) | Bold | 52–56px | 110–115% | -2% |
| Hero headline (AR) | Bold | 52–56px | 128–132% | -1% |
| Section headline | Bold | 42–48px | 115–130% | -1% to -2% |
| Card title | SemiBold | 14px | — | — |
| Body copy (EN) | Regular | 17–18px | 160–170% | — |
| Body copy (AR) | Regular | 17–18px | 175–180% | — |
| Button | SemiBold | 17px | — | — |
| Label / meta | Medium | 10–12px | — | — |
| Stat value | Bold | 18–28px | — | — |
| Small text | Medium | 11–13px | — | — |
| Eyebrow pill (EN) | SemiBold | 12px | — | 1.2px |
| Eyebrow pill (AR) | SemiBold | 13px | — | — |

### Loading Lama Sans in Plugin Scripts

Lama Sans is locally installed and **cannot** be loaded via `figma.loadFontAsync()` by family name directly. Always borrow the fontName reference from an existing node in the file:

```javascript
// Load all needed Lama Sans styles at script start
const lamaNodes = figma.root.findAll(n => n.type === "TEXT" && n.fontName.family === "Lama Sans");
const lamaFonts = {};
for (const node of lamaNodes) {
  lamaFonts[node.fontName.style] = node.fontName;
}
// Load each style
for (const fn of Object.values(lamaFonts)) {
  await figma.loadFontAsync(fn);
}

// Then use like this:
textNode.fontName = lamaFonts["Bold"];     // or "SemiBold", "Medium", "Regular"
```

**Style mapping for weights not in Lama Sans:**
- ExtraBold → use `Bold`
- Semi Bold (with space) → use `SemiBold`
- Light → use `Regular`

**If Lama Sans nodes don't exist yet on the current page**, search the entire file:
```javascript
const lamaNode = figma.root.findOne(n => n.type === "TEXT" && n.fontName.family === "Lama Sans");
await figma.loadFontAsync(lamaNode.fontName);
```

---

## Component Library

### Hero Section
```
Frame: 1440 × 720, fill: color/brand/blue-100
Background glow: large ellipse, radial gradient white→transparent, opacity 0.8

Left side (EN) / Right side (AR):
  - Eyebrow pill
  - Headline (2 lines max)
  - Body copy (2-3 lines)
  - Spacer
  - Primary CTA button

Right side (EN) / Left side (AR):
  - Custom visual with floating elements
```

### Eyebrow Pill
- Fill: none | Stroke: 1px `blue-600` | cornerRadius: 999
- Padding: 8px 16px
- Text: Semi Bold / SemiBold, 12–13px, `blue-600`
- EN: ALL CAPS with letter-spacing 1.2px | AR: normal case

### Primary CTA Button
- Fill: `blue-600`
- Shadow: `rgba(27,99,255,0.25)` offset y:8 blur:24
- Padding: 18px 32px | cornerRadius: 12
- Text: Semi Bold / SemiBold, 17px, white

### White Card
- Fill: white | cornerRadius: 20–24
- Shadow 1: `rgba(11,20,58,0.08)` y:4 blur:16
- Shadow 2: `rgba(11,20,58,0.10)` y:24 blur:60 spread:-8
- Padding: 24px

### Dark Card (navy)
- Fill: `navy-800` rgb(0.071, 0.114, 0.286)
- Stroke: `rgba(white, 0.08)` weight:1
- Shadow: `rgba(0,0,0,0.25)` y:20 blur:48 spread:-8
- Dot grid texture: 3×3px ellipses, `rgba(white,0.05)`, spaced ~58px

### Floating Elements
**Rule: rotation always 0°. No tilts.**

| Type | Style |
|---|---|
| White pill badge | white fill, cornerRadius 999, shadow `rgba(navy-900,0.12)` y:12 blur:28 spread:-4 |
| Dark navy chip | navy-900 fill, cornerRadius 16, shadow `rgba(navy-900,0.20)` y:16 blur:32 spread:-4 |
| Blue tile | blue-600 fill, cornerRadius 20, glow shadow `rgba(blue-600,0.40)` y:16 blur:32 spread:-4 |
| Dashed connector | strokeWeight 1.5, dashPattern [4,6], `blue-600` at 25–30% opacity, no fill |

### Status Pills
| Status | Background | Text Color | Dot |
|---|---|---|---|
| Active | `green-100` | `green-500` | `green-500` |
| Trial | `blue-50` | `blue-600` | — |
| Renewing | amber `rgba(1,0.627,0.157,0.15)` | amber | amber dot |

Padding: 3–6px 8–12px | cornerRadius: 6–999

### Dividers
- Rectangle, 1px height, fill `gray-200`

---

## App Mockup Rules

### Skeleton Data — Mandatory
> **Any field that would show a real person's name, company name, or identifiable information must be replaced with a skeleton rectangle.**

- Skeleton fill: `#E0E8F3` (rgb: 0.878, 0.910, 0.953)
- Skeleton on dark backgrounds: `rgba(white, 0.20)`
- cornerRadius: 4px
- Vary widths realistically (e.g. 80px, 110px, 95px per row)
- **Avatar circles:** skeleton gray fill only — no initials
- **Keep visible:** amounts, percentages, plan names, dates, status labels — these are illustrative

### Table / List Alignment — Fixed Columns
Never use `SPACE_BETWEEN` for multi-column data tables. Always use **fixed-width columns**:

```javascript
// Example: 3-column table, inner width 360px
// Client col: 190px | Plan col: 80px (centered) | Commission col: 90px

const clientCol = figma.createFrame();
clientCol.layoutMode = "HORIZONTAL";
clientCol.primaryAxisSizingMode = "FIXED";
clientCol.counterAxisSizingMode = "FIXED";
clientCol.counterAxisAlignItems = "CENTER"; // ← critical, never set y manually
clientCol.resize(190, ROW_H);

const planCol = figma.createFrame();
planCol.primaryAxisAlignItems = "CENTER"; // ← centers pill regardless of label length
planCol.counterAxisAlignItems = "CENTER";
planCol.resize(80, ROW_H);

const commCol = figma.createFrame();
commCol.primaryAxisAlignItems = "MAX"; // right-aligned in EN, MIN in AR
commCol.resize(90, ROW_H);
```

**Column header widths must exactly match data row column widths.**

### Auto-layout — Critical Rules
- Always use `counterAxisAlignItems: CENTER` on column frames
- **Never manually set `y` on children inside auto-layout** — auto-layout overrides it and causes misalignment
- For right-aligned content in RTL: use `primaryAxisAlignItems: "MAX"` on the column frame
- To right-align a vertical stack: use `counterAxisAlignItems: "MAX"`

---

## RTL (Arabic) Design Rules

### Layout Mirroring
| Element | EN (LTR) | AR (RTL) |
|---|---|---|
| Hero visual | Right side | Left side |
| Hero text | Left side | Right side |
| Floating badge (top) | Top-right | Top-left |
| Floating chip (bottom) | Bottom-left | Bottom-right |
| Floating tile | Right | Left |
| Card logo | Left | Right |
| Card status badge | Right | Left |
| Table column order | Client → Plan → Commission | Commission → Plan → Client |
| Row content order | Avatar → Skeleton → ... | ... → Skeleton → Avatar |
| Banner arrow | → | ← |

### Text Alignment
- All Arabic text: `textAlignHorizontal = "RIGHT"`
- Vertical stacks: `counterAxisAlignItems = "MAX"`
- Column headers in tables: match column alignment (right header over right-aligned data)

### Numbers and Currency
- **Always use English numerals (0-9)** in Arabic UI — never Arabic-Indic (٠١٢...)
- Currency format: `⃁ 240` (⃁ first, then number with a space)
- Percentages: `20%` not `٢٠٪`
- Saudi Riyal symbol: `⃁` not `ر.س` not `SAR`

---

## Arabic Copy Standards

### Tone and Register
- Always **formal Modern Standard Arabic (فصحى)** — never colloquial or dialectal
- **Forbidden colloquial words:** هذي، فلوس، تقدر، راح، إيه، عبّي، شوف، وين، كيف (in a colloquial sense)

### Qoyod-Specific Terminology
| Context | Correct | Second use | Optional use |
|---|---|---|---|
| Product name | قيود | برنامج قيود المحاسبي | — |
| POS system | نظام نقاط البيع | نظام نقاط بيع قيود | — |
| Tax authority | هيئة الزكاة والضريبة والجمارك | — | — |
| Q. Flavours | فليفرز | نظام نقاط البيع لقطاع الأغذية والمشروبات | — |
| Pro Services | خدمات قيود الاحترافية | — | — |
| Q. Bookkeeping | مسك الدفاتر | خدمة مسك الدفاتر | خدمة المحاسب عن بعد |
| Integration | التكامل | الربط | — |
| Integration Marketplace | متجر التكاملات | — | متجر الربط |


### Standard UI Copy (reusable)

Copy is grouped by context. Always use exact phrasing — do not paraphrase or translate independently.

#### CTAs & Actions
| English | Arabic |
|---|---|
| Start Free Trial | ابدأ تجربتك المجانية |
| Try Qoyod free for 14 days | جرب قيود مجانًا لمدة 14 يوم |
| Subscribe Now | اشترك الآن |
| Learn More | تعرف أكثر |
| Contact Us | تواصل معنا |
| Apply Now | قدِّم طلبك الآن |
| Start Earning Now | ابدأ الكسب الآن |
| Get Started | ابدأ الآن |
| View All | عرض الكل |
| Copy | نسخ |

#### Navigation & Global Labels
| English | Arabic |
|---|---|
| Products | المنتجات |
| Integrations | التكاملات |
| Pricing | الأسعار |
| Resources | الموارد |
| Partnerships | الشراكات |
| Log In | تسجيل الدخول |
| Have some Questions? | لديك بعض الأسئلة؟ |
| Frequently Asked Questions | الأسئلة الشائعة |
| Subscribe to Our Newsletter | اشترك في نشرتنا البريدية |

#### Social Proof & Trust
| English | Arabic |
|---|---|
| Trusted by 25k Saudi companies | نثق به لدى أكثر من 25 ألف شركة سعودية |
| +25K satisfied Saudi SMEs | +25 مليون عملية محاسبية شهرية |
| +100K monthly users | +100 ألف مستخدم شهري |
| +25M accounting processes carried out | +25 مليون عملية محاسبة منجزة |
| Qoyod partners with you for success | قيود شريك نجاحك وتميّزك |

#### Product Features — E-Invoicing / ZATCA
| English | Arabic |
|---|---|
| ZATCA compliance | الامتثال الإلزامي |
| The ZATCA compliance deadline is looming | الموعد الأخير للامتثال الإلزامي اقترب |
| Compliant e-invoicing | الفوترة الإلكترونية الامتثالية |
| Phase 2 e-invoicing | فوترة إلكترونية — المرحلة الثانية |
| Go live | الربط مع الهيئة |
| Test everything before you go live | اختر أفضل طريق للربط الأمثل مع الهيئة |
| Expert setup and support anytime you need it | خبراء في خدمتك دائمًا |
| Get a unified tech stack for smooth compliance | خبراء في خدمتك دائمًا |

#### Product Features — Accounting
| English | Arabic |
|---|---|
| Accurate, compliant, and up-to-date books | دفاتر دقيقة وامتثالية، ومحدَّثة دائمًا |
| Your books are always accurate even without lifting a finger | سجلاتك صحيحة دائمًا دون أن تتدخل في كل خطوة |
| Built to help professional accountants | مصمَّم لمساعدة المحاسبين المحترفين |
| Consolidated processes and less manual work | معالجة وتسجيل بدون تكرار يدوي |
| Month-end closes, without adjusting entries | إنهاء الشهر دون قيود تسوية |
| Financial performance data: Instantly | التقارير المالية الآنية |
| Find out why accountants choose Qoyod | اكتشف لماذا يختار المحاسبون قيود |
| Check month reports | راجع تقارير الشهر |
| Check month-end close | تحقق من إغلاق نهاية الشهر |
| Track month-end close automation | تتبع أتمتة إغلاق نهاية الشهر |
| VAT integration | ربط ضريبة القيمة المضافة |
| ERP integration | ربط مع الأنظمة |

#### Pain Points (used in problem/solution sections)
| English | Arabic |
|---|---|
| When your company starts to grow, old processes start to break | هل ما زلت تضيع وقتك في تصحيح أخطاء كان يمكن تفاديها؟ |
| Disconnected tools slow you down | أدوات غير متصلة تُبطئك |
| Manual work means a higher risk of errors and delays | العمل اليدوي يرفع احتمالية الخطأ والتأخير |
| Financial visibility is delayed until month-end | رؤية مالية متأخرة حتى نهاية الشهر |
| Lack of Clear Guidance | غياب التوجيه الواضح |
| Unreliable Solutions | حلول غير موثوقة |
| No Alerts or Safeguards | لا تنبيهات ولا ضمانات |

#### Qoyod Product Suite Labels
| English | Arabic |
|---|---|
| Accounting | المحاسبة |
| POS Solution | نقاط البيع |
| Bookkeeping | مسك الدفاتر |
| E-Invoicing | الفوترة الإلكترونية |
| Payroll | الرواتب |
| Inventory | المخزون |
| Projects & Tasks | المشاريع والمهام |
| Fixed Assets | الأصول الثابتة |
| Reports | التقارير |
| Settings | الإعدادات |
| Help Center | مركز المساعدة |
| Integration Marketplace | متجر التكاملات |

#### Pricing & Plans
| English | Arabic |
|---|---|
| Plan | الباقة |
| Starter | ستارتر |
| Pro | برو |
| Business | بيزنس |
| Annual | سنوي |
| Monthly | شهري |
| Our plans for medium-sized and large companies | خططنا للشركات المتوسطة والكبيرة |
| Renews in X days | يتجدد خلال X أيام |
| Trial — X days left | تجريبي — X أيام متبقية |
| Active | نشط |

#### Partnerships / Affiliate / Reseller (context-specific)
| English | Arabic |
|---|---|
| Affiliate Program | برنامج الشركاء |
| Reseller Program | برنامج الموزّعين |
| Reseller Portal | بوابة الموزّعين |
| Your referral link | رابط الإحالة الخاص بك |
| Commission earned | عمولة مكتسبة |
| New referral | إحالة جديدة |
| Monthly Revenue | الإيراد الشهري |
| Active Clients | العملاء النشطون |
| Your Commission | عمولتك |
| Total earned | إجمالي الأرباح |
| At risk | في خطر |
| Upsell opportunity | فرصة ترقية |
| Client health | صحة العملاء |
| Client | العميل |
| Commission | العمولة |

---

## Image Generation (Gemini)

Use when a section requires a lifestyle or product photo. Every prompt is assembled from **locked constants** + **swappable variables**. Constants never change. Variables are chosen per shoot based on the section's story.

---

### Locked Constants (always include verbatim)

These control technical quality, brand color, and lighting — never modify them:

```
Dominant brand color: deep navy blue applied to walls, signage, lighting accents, and environment.
Color harmony fully centered around navy blue branding.
Balanced warm–cool contrast: warm skin tones against cool navy blue environment.

Lighting setup:
Soft natural daylight from the left side, large diffused window light simulation.
Warm highlights on skin, no harsh shadows.
Subtle soft fill light from the front-right.
Gentle back rim light separating subject from background.
Cinematic soft shadows under hands and surfaces.
Realistic light falloff. Studio-controlled lighting mixed with natural daylight.

Shot on a full-frame camera.
Ultra-realistic photography. Commercial advertising style.
Clean polished surfaces. Soft reflections on screens and counters.
Color grading: premium advertising tone, slightly warm highlights, cool navy midtones,
soft contrast, no oversaturation.
Photorealistic, 8K quality, cinematic lifestyle realism.
No distortion, no artificial look, no exaggerated HDR.
No visible text on any screen or surface.
Aspect ratio 3:2, landscape orientation, high resolution.
```

---

### Variable Dimensions (choose one value per dimension per shoot)

Each dimension is independent. Mix and match freely to create variations.

#### [A] Camera & Composition
| Option | Description |
|---|---|
| `A1` | Medium-wide shot, camera at eye level, front three-quarter perspective — subject and environment both visible, natural depth |
| `A2` | Close-up shot, camera slightly below eye level, subject fills 60% of frame — focus on expression and product interaction |
| `A3` | Wide establishing shot, camera at eye level, side angle — environment dominant, subject anchored in space |
| `A4` | Over-the-shoulder shot, camera behind subject — looking at screen/device from operator's perspective |
| `A5` | Top-down flat lay, camera directly overhead — desk, hands, device, and props arranged on surface |

#### [B] Subject
| Option | Description |
|---|---|
| `B1` | Saudi man, authentic Saudi facial features, well-groomed beard, clean modern appearance |
| `B2` | Saudi woman wearing hijab, confident professional expression, modern appearance |
| `B3` | Two people — Saudi man and woman — collaborating, both engaged with device or counter |

#### [C] Expression & Gesture
| Option | Description |
|---|---|
| `C1` | Smiling naturally, looking at screen, right hand gently approaching touchscreen, almost touching it — natural relaxed gesture |
| `C2` | Focused and attentive, looking down at paperwork or device, neutral professional expression |
| `C3` | Looking directly at camera, confident open smile, hands resting naturally on counter |
| `C4` | Mid-conversation expression, slight smile, gesturing with one hand toward screen or colleague |

#### [D] Outfit
| Option | Description |
|---|---|
| `D1` | Navy blue restaurant or retail uniform — clean, modern, branded |
| `D2` | White thobe, traditional Saudi professional appearance |
| `D3` | Business casual — dark navy blazer over white shirt, no tie |
| `D4` | Navy abaya with minimal accessories (for female subject) |

#### [E] Location & Environment
| Option | Description |
|---|---|
| `E1` | Modern restaurant interior — cashier counter made of clean matte material, POS screen slightly tilted toward camera, restaurant environment softly blurred in background |
| `E2` | Modern retail store — product shelving visible in background, clean glass display counter in foreground |
| `E3` | Professional office or co-working space — clean desk, laptop, notebook, minimal accessories |
| `E4` | Accounting or consulting firm — conference table, clean shelving, formal environment |
| `E5` | Warehouse or light industrial space — clean, organized, modern — for logistics or inventory context |

---

### How to Build a Prompt

Use this template — fill in the variable codes, then assemble:

```
A high-end commercial lifestyle photograph.
[INSERT A — camera and composition description]
[INSERT B — subject description]
[INSERT C — expression and gesture description]
[INSERT D — outfit description]
[INSERT E — location and environment description]
Background softly blurred (shallow depth of field).

[INSERT LOCKED CONSTANTS verbatim]
```

---

### Example Prompts

**Example 1 — Restaurant cashier (A1 + B1 + C1 + D1 + E1)**
```
A high-end commercial lifestyle photograph.
Medium-wide shot, camera at eye level, front three-quarter perspective, showing the cashier counter clearly, natural depth and realistic proportions.
A Saudi man with authentic Saudi facial features, well-groomed beard, clean modern appearance.
Smiling naturally, looking at the POS cashier screen, his right hand gently approaching the touchscreen, almost touching it, natural relaxed gesture.
Wearing a navy blue restaurant uniform.
Modern restaurant interior, cashier counter made of clean matte material, POS screen slightly tilted toward camera.
Background softly blurred (shallow depth of field), restaurant environment visible but not distracting.

Dominant brand color: deep navy blue applied to walls, signage, lighting accents, and environment.
Color harmony fully centered around navy blue branding.
Balanced warm–cool contrast: warm skin tones against cool navy blue environment.
Lighting setup: soft natural daylight from the left side, large diffused window light simulation. Warm highlights on skin, no harsh shadows. Subtle soft fill light from the front-right. Gentle back rim light separating subject from background. Cinematic soft shadows under hands and surfaces. Realistic light falloff. Studio-controlled lighting mixed with natural daylight.
Shot on a full-frame camera, 35mm lens, f/2.8 depth of field, sharp subject focus, background bokeh.
Ultra-realistic photography. Commercial advertising style. Clean polished surfaces. Soft reflections on screens and counters.
Color grading: premium advertising tone, slightly warm highlights, cool navy midtones, soft contrast, no oversaturation.
Photorealistic, 8K quality, cinematic lifestyle realism. No distortion, no artificial look, no exaggerated HDR.
No visible text on any screen or surface. Aspect ratio 3:2, landscape orientation, high resolution.
```

**Example 2 — Office consultant, direct gaze (A2 + B2 + C3 + D4 + E3)**
```
A high-end commercial lifestyle photograph.
Close-up shot, camera slightly below eye level, subject fills 60% of frame, focus on expression and environment.
A Saudi woman wearing hijab, confident professional expression, modern appearance.
Looking directly at camera, confident open smile, hands resting naturally on desk.
Navy abaya with minimal accessories.
Professional office space, clean desk, laptop and notebook in foreground, minimal accessories.
Background softly blurred (shallow depth of field).

[INSERT LOCKED CONSTANTS verbatim]
```

---

### Variation Strategy

To generate multiple shots of the same scene, **change only one dimension at a time**:
- Same scene, different angle → swap [A] only
- Same person, different expression → swap [C] only
- Same shot, different location → swap [E] only
- Full recast → swap [B] + [D] together

Run 2–3 generations per combination and select the strongest result before moving to the next variation.

---

### Overlay Rule
- **Never ask Gemini to add UI elements, badges, or overlays** onto photos
- All overlay elements are built natively in Figma using design tokens
- This ensures brand consistency, correct colors, and editability

---

## Figma Plugin API — Patterns and Pitfalls

### Standard Script Header
```javascript
// ── 1. Load Lama Sans (the ONLY font used — English and Arabic both)
// Cannot use loadFontAsync by name — must borrow from existing file nodes
const lamaNodes = figma.root.findAll(n => n.type === "TEXT" && n.fontName.family === "Lama Sans");
const lamaFonts = {};
for (const node of lamaNodes) {
  if (!lamaFonts[node.fontName.style]) lamaFonts[node.fontName.style] = node.fontName;
}
for (const fn of Object.values(lamaFonts)) {
  await figma.loadFontAsync(fn);
}
// Shorthand helpers
const LF = (style) => lamaFonts[style] ?? lamaFonts["Regular"]; // e.g. LF("Bold"), LF("SemiBold")

// ── 2. Switch to correct page
const page = figma.getNodeById("PAGE_ID");
await figma.setCurrentPageAsync(page);

// ── 3. Load design tokens
const tokenIds = JSON.parse(figma.root.getSharedPluginData("qoyod", "tokenIds"));
const tok = (name) => figma.variables.getVariableById(tokenIds[name]);
const sf = (name, alpha) => [figma.variables.setBoundVariableForPaint(
  { type: "SOLID", color: { r:0,g:0,b:0 }, opacity: alpha ?? 1 }, "color", tok(name)
)];
const white = () => [{ type: "SOLID", color: { r:1,g:1,b:1 } }];

// Usage example:
// textNode.fontName = LF("Bold");
// textNode.fontName = LF("SemiBold");
// textNode.fontName = LF("Medium");
// textNode.fontName = LF("Regular");
```

### Common Mistakes to Avoid

| ❌ Wrong | ✅ Correct |
|---|---|
| `fontName = { family: "Inter", ... }` | `fontName = LF("Bold")` — Lama Sans always |
| `fontName = { family: "Cairo", ... }` | `fontName = LF("SemiBold")` — Lama Sans always |
| `figma.loadFontAsync({ family: "Lama Sans", style: "Bold" })` | Borrow from existing file node |
| `node.removeChild(child)` | `child.remove()` |
| `counterAxisAlignItems: "TRAILING"` | `counterAxisAlignItems: "MAX"` |
| Setting `child.y = 10` inside auto-layout | Set `counterAxisAlignItems: "CENTER"` on parent |
| Inserting new rows without removing old ones | Always `findAll` + `node.remove()` first |
| Using `SPACE_BETWEEN` for data tables | Use fixed-width column frames |
| Placing floats inside clipped frame | Place floats on parent frame with `clipsContent: false` |

### Rebuilding Rows Safely
```javascript
// Always remove old rows before inserting new ones
const oldRows = card.findAll(n => n.name.startsWith("row-"));
oldRows.forEach(r => r.remove());

// Then insert new rows at the correct index
card.insertChild(insertIndex + i, newRow);
```

### Card Height Sizing
After adding all children, calculate required height:
```javascript
// Sum all children heights + paddingTop + paddingBottom + itemSpacing gaps
const totalH = children.reduce((acc, c) => acc + c.height, 0)
  + (children.length - 1) * card.itemSpacing
  + card.paddingTop + card.paddingBottom;
card.resize(card.width, totalH);
```

---

## Section Design Philosophy

### Placeholder Screenshots
When the user shares a screenshot of an existing section: **it is a placeholder, not a spec.** Always design something original. The screenshot communicates layout and content — not visual direction.

### Visual Concepts — Rules
- Every section visual must tell a **specific story** tied to the section's message
- Each state/tab in an interactive section must have a **distinct visual concept** — no two states should share the same card type or layout
- Dark background mockups and light background mockups should alternate for visual variety
- Data shown in mockups must be **believable and consistent** (e.g. if MRR is shown as SR 8,400, individual client MRRs should add up correctly)

### Creativity Principles
- Never recreate a UI element that already exists in the section (e.g. don't show the Qoyod dashboard if the hero already shows it)
- Choose visual metaphors that reinforce the emotional message, not just the functional one
- Floating elements should **tell a micro-story** — each chip/badge adds meaning, not decoration

---

## Design Language Summary

Qoyod's visual language is **clean, confident, and professional** — reflecting a B2B SaaS product trusted by Saudi SMEs. Key characteristics:

- **Structured** — clear hierarchy, consistent spacing, aligned columns
- **Restrained** — minimal decoration, no gradients on UI elements, subtle shadows
- **Bilingual-first** — every design decision accounts for both LTR and RTL from the start
- **Data-forward** — numbers, stats, and amounts are always prominent and legible
- **Trustworthy** — navy-dominant palette signals reliability; green accents signal growth and success

---

# UX Guideline — Pages & Landing Pages

> The visual rules above ALWAYS take priority. The UX framework below tells you **what to put on the page and in what order**; the design system above tells you **how it looks**. If anything below conflicts with the visual rules, the visual rules win.

Source: [Figma Workspace](https://www.figma.com/board/hCs9jdDQCW60HiNyxw7emU/Qoyod-Website---Workspace).

---

## Page Structure Framework — Buyer's Business Case (7 sections)

Every product / landing / business-sector page follows this storytelling flow:

| # | Section | Purpose |
|---|---------|---------|
| 1 | **The Market** | Define the landscape — who the buyer is, what category Qoyod belongs to |
| 2 | **The Alternatives** | Show what the buyer currently does (status quo) and the competitor landscape |
| 3 | **The Solution** | Feature-by-feature breakdown: Use Case → Current Way → Problem → Capability → Benefit |
| 4 | **The Proof** | Social proof, testimonials, case studies, trust signals |
| 5 | **Pricing** | Clear plan comparison and value framing |
| 6 | **Objection Handling** | FAQ-style responses to buyer concerns |
| 7 | **The Ask** | CTA — trial signup, demo request, contact |

---

## Target Audiences (3 segments)

Each segment gets its own tailored version of the 7-section framework.

### Segment 1: SMB Operators / Business Owners
- **Who:** Saudi SMBs (micro and small), retail/service shops, e-commerce sellers
- **Role:** Owner-operators, admins who also handle accounting, bookkeepers
- **Primary pain:** ZATCA compliance, Excel-based invoicing, manual bookkeeping
- **Key message:** "Get ZATCA Phase 2 compliant from day one + an easy platform to manage finances"
- **Tone:** Simple, reassuring, non-technical

### Segment 2: Accounting Firms / Bookkeepers
- **Who:** Accounting/bookkeeping firms, freelance accountants, outsourced CFOs
- **Primary pain:** Managing multiple clients, manual reconciliation, inconsistent workflows
- **Key message:** "One system for all your clients — standardized, compliant, cloud-based"
- **Tone:** Professional, efficiency-focused, scalability

### Segment 3: Retail
- **Who:** Retail businesses needing POS + accounting integration
- **Primary pain:** POS disconnected from accounting, double-entry
- **Key message:** "One sale = one e-invoice = no compliance errors"
- **Tone:** Practical, operational

---

## Messaging Framework per Section

### 1. The Market
Include:
- Product Category (e.g., "Cloud Accounting Platform — Compliance-First")
- Primary use cases
- The Explainer (conversational pitch paragraph)
- Target company type
- Target department / role

**Writing pattern for The Explainer:**
> "You know how [target audience] [struggles with X]? We fix that. Qoyod [core value prop]. You get [tangible benefit 1] plus [tangible benefit 2]."

### 2. The Alternatives
Structure as a comparison table:

| Status Quo | Details | Pros | Risks | How We Win |
|---|---|---|---|---|

Alternatives to address:
- Excel + manual invoices
- Outsourced accountant (no software)
- POS disconnected from accounting
- Freemium / generic global tools (Wave, etc.)
- Direct competitors (Wafeq, Rewaa, Daftra)

**Always acknowledge competitor strengths before showing Qoyod's advantage.**

### 3. The Solution
Structure as a feature table:

| Feature | Use Case | Current Way | Problem | Capability | Benefit |

**Core features to cover per segment:**

- **For SMBs:** ZATCA Integration · Sales Module · Purchase Module · Inventory Management · Payroll Module · Fixed Asset Tracking · Real-time Reporting · Arabic Language Support · Cloud-Based Platform · SMB-Friendly Onboarding · Simple Accounting
- **For Accounting Firms:** Client-Level Access & Control · Recurring Transactions · MJE Template Design · MJE Allocation · ZATCA Integration (multi-client) · Deferral Transactions · Budgeting · Multi-Currency · Fixed Asset Tracking & Disposal · Sales & Purchase Modules · Payroll Module · Real-Time Reporting · Cloud-Based Access · SMB-Focused Onboarding

### 4. The Proof
- Customer testimonials (real quotes)
- Case study snapshots
- Trust badges (ZATCA certified, etc.)
- Key metrics (number of businesses, invoices processed, etc.)

### 5. Pricing
- Clear tier comparison
- Highlight most popular plan
- Annual vs monthly toggle
- Feature checklist per plan

### 6. Objection Handling
FAQ format. Common objections to address:
- "Is it really ZATCA Phase 2 compliant?"
- "What if I'm not tech-savvy?"
- "How long does setup take?"
- "Can my accountant access it too?"
- "What about my existing data?"
- "Is it secure?"

### 7. The Ask (CTA)
- Primary CTA: Free trial signup
- Secondary CTA: Book a demo / Talk to sales
- Urgency element: ZATCA deadlines, limited onboarding slots

---

## Competitive Positioning

### vs. Wafeq
- **Their strength:** Simple UI, built for MENA SMEs
- **Their weakness:** Fewer modules (no POS, payroll, assets)
- **Our win:** Full platform + ZATCA Phase 2 native + real-person setup + fully Saudi-native

### vs. Rewaa
- **Their strength:** Strong inventory / retail features
- **Their weakness:** Not a full accounting solution, limited reporting
- **Our win:** Integrated accounting + POS + compliance in one system

### vs. Daftra
- **Their strength:** Flexible modules, customization
- **Their weakness:** Too complex for SMBs, slower to implement
- **Our win:** Purpose-built for ease and speed, especially micro/small teams

### vs. Excel / Manual
- **Their strength:** Familiar, free, flexible
- **Their weakness:** ZATCA non-compliance risk, errors, time-consuming
- **Our win:** ZATCA compliance built-in, expert setup, no spreadsheet chaos

### vs. Generic Global Tools (Wave, etc.)
- **Their strength:** Free / low-cost, mobile access
- **Their weakness:** No Arabic, VAT, or ZATCA support
- **Our win:** Built for the Saudi market from the ground up

---

## Qoyod Value Props (ranked by importance)

1. **ZATCA Phase 2 Compliance** — built-in, not patched in
2. **Expert-Led Onboarding** — a real person sets everything up
3. **All-in-One Platform** — sales, purchases, inventory, payroll, POS, reporting
4. **Arabic-First** — fully localized UI
5. **Cloud-Based** — access anywhere, real-time sync
6. **Simple for Non-Accountants** — business owners can manage books without training
7. **Saudi-Native** — built by Saudis, for Saudi businesses

---

## Landing Page Copywriting Rules

1. **Lead with the pain, not the product** — start every section with what the buyer struggles with
2. **Use "You" language** — address the reader directly
3. **Benefits over features** — always translate capabilities into outcomes
4. **Conversational tone** — especially for SMB segment; avoid jargon
5. **Problem → Solution → Benefit** pattern for every feature block
6. **Include social proof near every major CTA**
7. **Arabic pages:** root domain (`qoyod.com/page`)
8. **English pages:** `/en/` prefix (`qoyod.com/en/page`)

---

## Feature → Benefit Mapping (SMB language)

| Feature | Benefit (SMB language) |
|---|---|
| ZATCA Integration | Stay compliant without extra steps or government-site logins |
| Sales Module | Issue accurate invoices fast without manual entry |
| Purchase Module | Organized purchasing history and cleaner cash-flow records |
| Inventory Management | Never guess stock levels again — avoid stockouts and overstocking |
| Payroll Module | Pay employees correctly and on time without extra work |
| Fixed Asset Tracking | Accurate books and clean asset records without audits |
| Real-time Reporting | Make business decisions quickly with confidence |
| Arabic Language Support | Easier to onboard teams and reduce user errors |
| Cloud-Based Platform | Access financials anywhere, stay synced across devices |
| SMB-Friendly Onboarding | Start fast and use the tool without external help |
| Simple Accounting | Manage books confidently without accounting training |

---

## How to apply this UX framework

**Building a product page:**
1. Identify which audience segment (SMB / Accounting Firm / Retail).
2. Follow the 7-section framework in order.
3. Use the feature-table structure for The Solution.
4. Pull from Competitive Positioning for The Alternatives.
5. Map features → benefits using the table above.
6. Render every section using the visual tokens / components defined in the **Design Tokens** and **Component Library** sections at the top of this file.

**Building a landing page (campaign / ad):**
1. Pick 1–2 key value props most relevant to the campaign.
2. Use The Explainer format for the hero.
3. Compress the 7 sections into: Hero → Problem → Solution → Proof → CTA.
4. Compact FAQ for objection handling.
5. Single focused CTA — don't split attention.

**Building a blog / SEO page:**
1. Use Feature → Benefit mapping for natural keyword integration.
2. Reference Competitive Positioning for comparison articles.
3. Use Problem → Current Way → Qoyod Solution as the article spine.

> **Reminder:** the Design Tokens, Typography, Component Library, RTL rules, and Arabic Copy Standards in the first half of this file are the source of truth for visuals. The UX framework above is what you say; the design system is how it looks.

---

*Qoyod Design System for Claude — Generated April 2026*  
*UX framework merged in May 2026 (source: Figma workspace).*  
*Maintained by: Amar Yassir, Head of Product Marketing, Qoyod*
