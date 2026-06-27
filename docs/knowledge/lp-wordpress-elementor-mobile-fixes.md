# LP WordPress/Elementor Mobile Fixes — 2026-06-27

## What was done

Fixed mobile responsiveness across landing pages at `lp.qoyod.com`. All edits were made
programmatically via the **WordPress REST API** + **Claude in Chrome** (WP admin JS) — no
local files changed, no git commit needed. Changes live directly in the WP database.

---

## Pages fixed

### know-qflavours (post ID 240)

Widget map: separate HTML widgets — `h000001` (global styles), `h000003` (hero), `h000011` (footer CTA).

Changes applied:
- **Nav breakpoint fix** (`h000001`): Removed `.qnav-links{display:none}` from `@media(max-width:960px)` — it was hiding the nav between 769–960px with no hamburger replacement.
- **Hero responsive rewrite** (`h000003`): Full `@media(max-width:960px)` + `@media(max-width:480px)` CSS. Key fix: CSS grid `1fr` column won't shrink below min-content without `min-width:0` — added it to `.fv-hero-inner`, `.fv-hero-copy`, `.fv-hero-form-col`. Also `overflow-wrap:break-word` on `.fv-hero-h1` for Arabic long words.
- **Form header text**: `ابدأ تجربتك المجانية` → `اشترك الآن`
- **CTA button**: made smaller via `padding:11px 24px;font-size:15px` at 960px, smaller at 480px.
- **Form fields**: reduced font-size, padding, label size at `max-width:480px`.
- **Footer CTA section** (`h000011`): Deleted entirely via `h11con.model.destroy()`.

### qawaem (post ID 773)

Widget map: single HTML widget `9c6c229` containing ALL page content (CSS + HTML + JS).

Problem: Nav had `<ul class="qnav-links">` that hides at ≤768px but had NO hamburger toggle at all.
Hero was already fine at 360px (scrollWidth 328 < 360 viewport).

Changes applied:
- **Hamburger toggle added**: `<button class="qnav-toggle" id="qnav-toggle">` inserted before `<ul class="qnav-links" id="qnav-links">`.
- **Mobile CSS added** inside the `<style>` block:
  - `.qnav-toggle` — hidden by default, shown as `flex` at ≤768px, `background:none!important` to override WP button styles
  - `.qnav-links` — `display:none!important` at ≤768px, `display:flex!important` when `.open`
  - `.qnav` — `position:relative` so dropdown is anchored
- **Toggle JS**: IIFE added at end of widget HTML — clicks toggle the `open` class on `#qnav-links` and update `aria-expanded`.

Verified live at 360px: `toggleCount:1`, `toggleBg:rgba(0,0,0,0)`, `toggleDisplay:flex`, `linksDisplay:none`.

### einvoice-integration + accounting

Verified clean at 360px, hero already stacks, no changes needed.

### qflavours (ID 8)

Different page structure — no nav/hero. No changes needed.

---

## Editing method — WP REST API via admin JS

**Never use the Elementor visual editor for programmatic edits.** Use this flow:

1. Navigate to `https://lp.qoyod.com/wp-admin/profile.php` in a Claude in Chrome tab.
2. Get nonce: `wpApiSettings.nonce` (or `document.querySelector('#_wpnonce').value`).
3. Fetch Elementor data: `GET /wp-json/wp/v2/pages/{ID}?context=edit` with `X-WP-Nonce` header.
4. Parse `data.meta._elementor_data` as JSON.
5. Walk the elements tree with a recursive `findWidget(els, id)` helper to find the target widget by ID.
6. Modify `widget.settings.html` as a string.
7. Save: `POST /wp-json/wp/v2/pages/{ID}` with `{meta: {_elementor_data: JSON.stringify(elData)}}`.

**Critical pitfalls:**
- All JS must run in a single `.then()` chain — `window._variable` reads are blocked by Claude in Chrome if the stored value contains URL-like patterns (query strings, base64).
- Never call the fetch chain in separate tool calls — each call is independent. Do strip + insert + save in ONE chain.
- `replace()` only replaces the FIRST match. If the string to replace appears multiple times (e.g. duplicate saves stacked the same block), count occurrences first before assuming one replace is enough.
- Repeated saves accumulate. Each failed attempt that called `POST` BEFORE verifying the strip is clean will layer duplicates. Always check count before saving.
- `background:none!important` and `border:none!important` are needed on `.qnav-toggle` because WP themes apply aggressive button styles.
- The Elementor JS API (`elementor.documents.getCurrent()`, `$e.run('document/save/publish')`) works from the editor tab but the editor URL (`?post=N&action=elementor`) triggers the Claude in Chrome cookie/query-string block. Use the REST API approach from profile.php instead.

---

## Widget ID reference (qawaem)

| Widget ID | Content |
|-----------|---------|
| `9c6c229` | Full page HTML — nav, hero, all sections, CSS, JS |

## Widget ID reference (know-qflavours)

| Widget ID | Content |
|-----------|---------|
| `h000001` | Global styles |
| `h000003` | Hero section |
| `h000011` | Footer CTA with form (deleted) |
