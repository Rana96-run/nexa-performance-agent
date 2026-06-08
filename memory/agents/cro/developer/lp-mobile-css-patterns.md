# LP Mobile CSS Patterns — lp.qoyod.com

Accumulated across sessions fixing pages 683, 850, 303, 463, 773. Apply these
patterns to every new or modified landing page before publishing.

## WordPress / Elementor access

- **REST API:** `PUT https://lp.qoyod.com/wp-json/wp/v2/pages/{id}`
- **Auth:** `Basic Content-OS:ks1c wZ6h HKR8 kcFs xkQj JzjC`
- **Payload:** `{"meta": {"_elementor_data": json.dumps(data)}}`
- **Cache clear (always run after upload):**
  1. `DELETE /wp-json/elementor/v1/cache`
  2. `GET /{slug}/?nc=N` with header `X-LiteSpeed-Purge: *`
- **Pull live state before editing:** `GET /wp-json/wp/v2/pages/{id}?context=edit`
  then `json.loads(page['meta']['_elementor_data'])` — never edit stale local JSON.

## Page inventory

| Page ID | Slug | Template type |
|---------|------|---------------|
| 683 | tech-sector | qnav (new template) |
| 850 | accounting-system | qnav (new template) |
| 303 | accounting | nav/btn-primary (old template) |
| 463 | einvoice-integration | nav/btn-primary (old template) |
| 773 | qawaem | qnav (new template) — single mega-widget |

## Template types

### qnav (new) — pages 683, 850, 773
Uses `.qnav`, `.qnav-inner`, `.qnav-links`, `.qnav-cta`, `.hero`, `.hero-inner`,
`.hero-form-wrap`, `.form-card-outer`.

### nav/btn-primary (old) — pages 303, 463
Uses `header.nav`, `.nav-inner`, `<nav><ul>`, `<a class="btn btn-primary">`.
Nav UL is hidden at `@media(max-width:900px){nav ul{display:none;}}`.
CTA (`btn btn-primary`) is already outside `</nav>` — no CTA-in-UL bug.

## Fix 1 — Nav CTA scrolls off-screen (qnav pages only)

**Root cause:** CTA (`<a class="qnav-cta">`) was the last `<li>` inside
`.qnav-links`. In RTL `overflow-x:auto`, it scrolled off the left edge on mobile.

**Fix in HTML:**
```html
<!-- Before -->
<li><a class="qnav-cta" href="#hero-h1">ابدأ مجاناً</a></li>
</ul>

<!-- After -->
</ul>
<a class="qnav-cta" href="#hero-h1">ابدأ مجاناً</a>
```
Some pages have `onclick` attributes on the CTA — preserve them exactly.

**Required mobile CSS (767px block):**
```css
@media(max-width:767px){
  .qnav-inner{flex-wrap:wrap;height:auto;padding:10px 16px 0!important;gap:0!important;align-items:center;justify-content:flex-start!important}
  .qnav-logo{order:1;flex-shrink:0}
  .qnav-logo svg{height:26px}
  .qnav-cta{order:2;flex-shrink:0;margin-right:12px!important;padding:6px 14px!important;font-size:12px!important}
  .qnav-links{order:3;display:flex!important;width:100%!important;overflow-x:auto;gap:0;padding:8px 0 6px;scrollbar-width:none;-webkit-overflow-scrolling:touch}
  .qnav-links::-webkit-scrollbar{display:none}
  .qnav-links li{display:flex!important;flex-shrink:0}
  .qnav-links a{font-size:12px!important;white-space:nowrap;padding:5px 10px!important}
}
```

## Fix 2 — Hero overflow / equal left-right padding

**Root cause:** `.hero` had asymmetric or missing mobile padding; in RTL flex
the left side got clipped.

**Fix:** Add to 767px block on `.hero` directly (not `.hero-inner`):
```css
.hero{padding:40px 16px!important;min-height:auto!important;overflow:hidden!important}
.hero-inner{grid-template-columns:1fr!important;gap:24px!important}
.hero h1{font-size:24px!important}
```
`padding:40px 16px` = top/bottom 40px, left/right 16px symmetrically regardless of RTL.

## Fix 3 — Form fields touching card edges

**Root cause:** `.hero-form-wrap` had `padding:24px 0` — zero horizontal padding.
On mobile (full-width card) labels and inputs abutted the card borders.

**Fix:** In 767px block:
```css
.hero-form-wrap{width:100%!important;padding:20px 16px!important}
```

## Fix 4 — Form 2 columns per row on mobile

Makes the form shorter vertically. Uses flex `calc(50% - 4px)` approach:
```css
.hero-form-wrap .elementor-form-fields-wrapper{display:flex!important;flex-wrap:wrap!important;gap:0 8px!important;align-items:flex-start!important}
.hero-form-wrap .elementor-field-group{flex:1 1 calc(50% - 4px)!important;min-width:0!important}
.hero-form-wrap .elementor-field-group:nth-child(1),
.hero-form-wrap .elementor-field-group:nth-child(6),
.hero-form-wrap .elementor-field-type-acceptance,
.hero-form-wrap .elementor-field-type-html,
.hero-form-wrap .elementor-field-type-submit{flex:1 1 100%!important}
.hero-form-wrap .elementor-field-type-hidden{display:none!important}
```
**Note:** nth-child numbers are form-specific — verify field order via
`document.querySelectorAll('.elementor-field-group')` in DevTools before applying.

## Fix 5 — Navy "ابدأ تجربتك المجانية" header block inside form card

Remove the `<div class="form-card-header">` block and its CSS rules from the
hero widget HTML entirely.

## Fix 6 — Footer CTA-band section

**For separate widgets** (acc0012_w, cdf7261, 52c8fee): delete the entire widget
from the `elements` array.

**For single mega-widgets** (page 773): remove the `<section class="cta-band">
...</section>` from the HTML using regex:
```python
html = re.sub(r'<section[^>]*class="cta-band"[^>]*>.*?</section>', '', html, flags=re.DOTALL)
```

## Verification checklist (run before reporting done)

```python
checks = {
    'Nav CTA outside </ul>':      bool(re.search(r'</ul>\s*<a[^>]*qnav-cta', html)),
    'Hero 40px 16px mobile':      'padding:40px 16px!important' in html,
    'Form-wrap 20px 16px':        'padding:20px 16px' in html,
    'form-card-header deleted':   '<div class="form-card-header">' not in html,
    'cta-band HTML section gone': not bool(re.search(r'<section[^>]*class="[^"]*cta-band', html)),
    'Form 2-col on mobile':       'calc(50% - 4px)' in html or '1fr 1fr' in html,
}
```
`cta-band` appearing in CSS only (`.cta-band{...}`) is a false positive — check
for the HTML `<section>` element specifically.

## Browser cache trap

Server can serve correct CSS while the user's phone shows old version.
- Confirm server-side via `curl` with Android user-agent — check `x-cache-nxaccel: BYPASS`
- Tell user to open in incognito / clear Chrome cache
- Hard-clear on device: Chrome → Settings → Privacy → Clear browsing data → Cached images

## Single mega-widget pages (773 pattern)

Page 773 has ALL sections in one widget `9c6c229`. Every fix (nav, hero, cta-band,
mobile CSS) is a surgical HTML edit inside that single widget's `html` field.
No separate widget IDs to target.
