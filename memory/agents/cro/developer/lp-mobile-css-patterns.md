# LP Mobile CSS Patterns — Developer Playbook

> **Private memory for the `developer` agent in the CRO chain.**
> Read this before touching any LP at `lp.qoyod.com`. Updated 2026-06-09.

---

## Page Inventory (canonical — update when pages are added)

| Page ID | Slug | Template | Widget prefix | Notes |
|---------|------|----------|---------------|-------|
| 303 | accounting | old-nav | `cdf7261` | cta-band container deleted; old `header.nav` template |
| 463 | einvoice-integration | old-nav | `52c8fee` | cta-band container deleted; old `header.nav` template |
| 683 | tech-sector | qnav | `b000001_w` … `b000012_w` (12 widgets) | Light blue hero, `.form-card-outer` form wrapper |
| 773 | qawaem | qnav-mega | `9c6c229` (single mega-widget — all sections in one) | All 6 mobile fixes applied directly inside the one widget |
| 850 | accounting-system | qnav | `acc0001_w` … `acc0012_w` (12 widgets) | Same template as 683 |
| 851 | zatca-einvoice | qnav-dark | `ein0001_w` … `ein0013_w` (13 widgets) | Dark navy hero, gold accents, ZATCA compliance badge, `.form-card-shell` form wrapper |

---

## Template Types

### A — `old-nav` (pages 303, 463)
- Nav: `header.nav > .nav-inner` structure
- No `.qnav` class
- Simpler; these pages only needed the cta-band container deletion

### B — `qnav` (pages 683, 773, 850)
- Nav: `<nav class="qnav">` → `.qnav-inner` (flex row: logo | links | cta)
- Hero: light blue background (`#E1EDFF` / `background:#E1EDFF`), navy text
- Form wrapper: `.form-card-outer` → `.hero-form-wrap` (older pages 683, 773, 850)
- Mobile nav override lives in the **hero widget** (second widget in the page), not the nav widget

### C — `qnav-dark` (page 851 — zatca-einvoice)
- Same `.qnav` nav structure as type B
- Hero: **dark navy gradient** `background:linear-gradient(225deg,#010E35 0%,#021544 45%,#01355A 100%)`
- Gold/amber accent: `#FCD34D` (headings `em`, trust pills SVGs, ZATCA badge)
- Form wrapper: `.form-card-shell` (newer name — cleaner than `.form-card-outer`)
- Additional hero layers: `.hero-dots` (dot grid overlay), `.hero-glow-a` / `.hero-glow-b` (radial glow orbs)
- ZATCA compliance badge: `.hero-zatca-badge` (gold border, inline icon + cert text) — must be above the fold

---

## CSS Design Tokens (shared across all pages)

```css
:root {
  --navy: #021544;
  --navy-900: #0B143A;
  --blue-600: #1B63FF;
  --blue-100: #E1EDFF;
  --turq: #17A3A4;
  --gray-100: #F5F7FB;
  --gray-200: #E8ECF3;
  --gray-600: #5A6478;
  --ink: #0B1220;
  --muted: #6B7280;
  --radius-xl: 24px;
  --radius-md: 12px;
  --font: 'LamaSans', 'IBM Plex Sans Arabic', sans-serif;
}
```

---

## Mobile Fix Patterns

### Fix 1 — Nav mobile overflow (`qnav` template) ★ CRITICAL

**Problem:** On mobile (<767px), `.qnav-links` (navigation list) push the CTA button off screen; the nav row overflows horizontally.

**Fix location:** **Hero widget** (second widget), inside its `<style>` block. NOT in the nav widget itself.

**Correct mobile CSS for qnav:**
```css
@media(max-width:767px) {
  .qnav-inner {
    flex-wrap: wrap;
    height: auto;
    padding: 10px 16px 0 !important;
    gap: 0 !important;
    align-items: center;
    justify-content: flex-start !important;
  }
  /* Separate margin-right rule — applied before order rules (cleaner cascade) */
  .qnav-cta { margin-right: 12px !important; }
  /* Layout order: logo (1) → cta (2) → links row (3) */
  .qnav-logo { order: 1; flex-shrink: 0; }
  .qnav-logo svg { height: 26px; }
  .qnav-cta { order: 2; flex-shrink: 0; padding: 6px 14px !important; font-size: 12px !important; }
  .qnav-links {
    order: 3;
    display: flex !important;
    width: 100% !important;
    overflow-x: auto;
    gap: 0;
    padding: 8px 0 6px;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }
  .qnav-links::-webkit-scrollbar { display: none; }
  .qnav-links li { display: flex !important; flex-shrink: 0; }
  .qnav-links a { font-size: 12px !important; white-space: nowrap; padding: 5px 10px !important; }
}
```

**Note on `margin-right`:** Page 851 (zatca-einvoice) separates `margin-right: 12px !important` into its own `.qnav-cta` rule placed BEFORE the `order/padding/font-size` block. This is the **preferred pattern** going forward — it avoids cascade conflicts where a later rule might inadvertently reset `margin-right`.

**960px tablet breakpoint (in nav widget, not hero):**
```css
@media(max-width:960px) {
  .qnav-links { display: none; }
  /* other layout adjustments */
}
```

---

### Fix 2 — Hero layout stacking on mobile

**Problem:** Two-column hero (copy + form) doesn't collapse to single column on mobile.

**Fix:**
```css
@media(max-width:960px) {
  .hero-inner { flex-direction: column; }
  .hero-copy, .hero-form-col { flex: 0 0 auto; width: 100%; }
  .hero h1 { font-size: 36px; }
}

@media(max-width:767px) {
  .hero-inner { flex-direction: column !important; gap: 24px !important; }
  .hero h1 { font-size: 24px !important; }
  /* qnav-dark (page 851): */
  .hero-copy { overflow: visible !important; max-width: 100% !important; width: 100% !important; box-sizing: border-box !important; }
  /* qnav light (pages 683, 773, 850): */
  /* .hero-copy { width: 100% !important; box-sizing: border-box !important; padding-left: 0 !important; padding-right: 0 !important; } */
}
```

**Prefer `overflow:visible + max-width:100%` over `padding-left:0`** — the newer approach (page 851) is cleaner and avoids fighting Elementor's default padding injections.

---

### Fix 3 — Form fields compact on mobile

**Problem:** Form fields overflow or look oversized on small screens.

**Form wrapper targeting** depends on the page template:
- Old (683, 773, 850): target `.hero-form-wrap` and `.form-card-outer`
- New (851): target `.form-card-shell`

```css
@media(max-width:767px) {
  /* Replace WRAPPER with either .hero-form-wrap or .form-card-shell */
  WRAPPER { width: 100% !important; max-width: 100% !important; box-sizing: border-box !important; }
  WRAPPER .elementor-field-group { margin-bottom: 8px !important; }
  WRAPPER .elementor-field-group .elementor-field {
    padding: 8px 11px !important; font-size: 13px !important;
    min-height: auto !important; height: auto !important;
  }
  WRAPPER .elementor-field-group .elementor-field-textual {
    height: auto !important; padding: 8px 11px !important;
    font-size: 13px !important; line-height: normal !important;
  }
  WRAPPER .elementor-field-label { font-size: 12px !important; margin-bottom: 3px !important; }
  WRAPPER .elementor-select-wrapper select {
    padding: 8px 11px !important; font-size: 13px !important;
    height: 34px !important; min-height: 34px !important;
  }
  WRAPPER input, WRAPPER textarea {
    height: 34px !important; min-height: 34px !important;
    padding: 0 12px !important; font-size: 13px !important; box-sizing: border-box !important;
  }
  WRAPPER select {
    height: 34px !important; min-height: 34px !important;
    font-size: 13px !important; padding: 0 8px !important; box-sizing: border-box !important;
  }
}
```

---

### Fix 4 — Form 2-column grid on mobile (pages 683, 773, 850 only)

**Problem:** On narrow screens, all form fields stack as 1 column making the form excessively tall.

**Fix** (old `.hero-form-wrap` pattern):
```css
@media(max-width:767px) {
  .hero-form-wrap .elementor-form-fields-wrapper {
    display: flex !important; flex-wrap: wrap !important;
    gap: 0 8px !important; align-items: flex-start !important;
  }
  .hero-form-wrap .elementor-field-group { flex: 1 1 calc(50% - 4px) !important; min-width: 0 !important; }
  /* Full-width exceptions */
  .hero-form-wrap .elementor-field-group:nth-child(1),
  .hero-form-wrap .elementor-field-group:nth-child(6),
  .hero-form-wrap .elementor-field-type-acceptance,
  .hero-form-wrap .elementor-field-type-html,
  .hero-form-wrap .elementor-field-type-submit { flex: 1 1 100% !important; }
  .hero-form-wrap .elementor-field-type-hidden { display: none !important; }
}
```

**Note:** Page 851 (`zatca-einvoice`) does NOT use this 2-column grid — the form is full-width single column. Only apply to old-template pages.

---

### Fix 5 — Trust row wrapping on mobile

```css
@media(max-width:767px) {
  .trust-row { width: 100% !important; flex-wrap: wrap !important; }
  .trust-sep { display: none !important; }   /* hide separators between trust pills */
}
```

---

### Fix 6 — Dark hero glow orb scaling (page 851 only)

**Problem:** `.hero-glow-a` and `.hero-glow-b` are large absolute-positioned orbs (700px/440px) that cause horizontal scroll on mobile.

**Fix:**
```css
@media(max-width:767px) {
  .hero-glow-a { width: 220px !important; height: 220px !important; }
  .hero-glow-b { width: 150px !important; height: 150px !important; }
}
```

---

### Fix 7 — ZATCA badge mobile overflow (page 851 only)

**Problem:** `.hero-zatca-badge` inline-flex can overflow narrow viewports if badge text is long.

**Fix:**
```css
@media(max-width:767px) {
  .hero-zatca-badge {
    display: flex !important; width: 100% !important;
    max-width: 100% !important; box-sizing: border-box !important;
  }
  .zatca-badge-text { flex: 1 !important; min-width: 0 !important; overflow: hidden !important; }
}
```

---

## Widget Structure — Where to Place Which Fix

For multi-widget qnav pages (683, 850, 851), the CSS for EACH section lives in that section's widget. The NAV mobile override is the exception — it lives in the **hero widget** (widget 2), not widget 1 (nav).

| Widget | Section | Owns |
|--------|---------|------|
| `*0001_w` | Nav (`<nav class="qnav">`) | Nav desktop CSS + 960px hide-links breakpoint |
| `*0002_w` | Hero (copy + form) | **Nav 767px mobile override** + hero layout + form CSS |
| `*0003_w` | Hero content / features | Section-specific CSS + 767px media queries |
| … | … | Section-specific CSS |
| Last widget | Footer / scroll-reveal JS | `<script>` scroll-reveal observer (no CSS) |

For mega-widget page 773 (qawaem), ALL CSS and HTML is in a single widget `9c6c229`.

---

## WordPress REST API — How to Read / Write

```python
import base64, json, requests

WP = "https://lp.qoyod.com"
creds = base64.b64encode(b"Content-OS:ks1c wZ6h HKR8 kcFs xkQj JzjC").decode()
HEADERS = {"Authorization": f"Basic {creds}"}

# READ a page
def get_page(page_id):
    r = requests.get(f"{WP}/wp-json/wp/v2/pages/{page_id}?context=edit", headers=HEADERS)
    return json.loads(r.json()['meta']['_elementor_data'])

# WRITE (update) a page
def save_page(page_id, elements):
    payload = {"meta": {"_elementor_data": json.dumps(elements)}}
    r = requests.post(f"{WP}/wp-json/wp/v2/pages/{page_id}", headers=HEADERS, json=payload)
    return r.status_code

# PURGE LiteSpeed cache (required after every write)
def purge_cache(slug, n=1):
    requests.delete(f"{WP}/wp-json/elementor/v1/cache", headers=HEADERS)
    requests.get(f"{WP}/{slug}/?nc={n}", headers={**HEADERS, "X-LiteSpeed-Purge": "*"})
```

**Walk widgets:**
```python
def walk_widgets(elements):
    for el in elements:
        if el.get('elType') == 'widget':
            yield el  # el['id'], el['settings']['html']
        yield from walk_widgets(el.get('elements', []))
```

---

## Verification Checklist (before sign-off on any LP fix)

- [ ] On 320px viewport: nav CTA visible, no horizontal scroll
- [ ] On 375px viewport: hero columns stack, h1 ≤ 24px, form fields compact
- [ ] On 900px viewport: nav links HIDDEN (only logo + CTA), single-column hero
- [ ] On 768px viewport: nav links HIDDEN (only logo + CTA) — NOT showing a cramped full row
- [ ] On 961px viewport: links visible, two-column hero intact
- [ ] On 1280px viewport: full desktop layout, no regressions
- [ ] LiteSpeed cache purged (HTTP 200 from slug after purge)
- [ ] Browser hard-refresh (Ctrl+Shift+R) confirms live changes

---

## Common Pitfalls

1. **Don't put the nav 767px override in the nav widget** — it will be ignored because the nav widget's `<style>` scope is processed before the hero. Put it in the **hero widget** instead.
2. **Form wrapper class differs by page age** — check whether the page uses `.hero-form-wrap` (older) or `.form-card-shell` (newer, page 851+). Using the wrong class = mobile styles never apply.
3. **`margin-right` on `.qnav-cta`** — separate into its own rule BEFORE the order block to prevent it being reset by the cascade. See Fix 1 above.
4. **Mega-widget pages (773)** — all fixes go into one widget, don't navigate by `*_w` ID pattern.
5. **Cache** — always purge after saving. LiteSpeed can serve a stale version for up to 10 minutes even after a correct WP API write.
6. **`!important` everywhere** — Elementor injects its own inline styles with high specificity; you MUST use `!important` in mobile overrides or they won't apply.
7. **`.qnav-links{display:none}` in the 960px breakpoint MUST have `!important`** — each widget's `<style>` block re-declares `.qnav-links{display:flex}` unconditionally (for desktop default). Since this re-declaration is LATER in the DOM than the 960px `display:none` rule in the nav widget, it overrides it via cascade order. Without `!important` on the `display:none`, links show at 768–960px, cramming the CTA to the left edge (the "left side cropped" bug). Fix: `.qnav-links{display:none!important}` in the `@media(max-width:960px)` block of the nav widget. The 767px mobile rule `display:flex!important` still wins because it comes later in the DOM AND has `!important`. Fixed on pages 683, 850, 851 on 2026-06-09.
