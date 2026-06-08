# LP Brief — EXAMPLE (reference only, not a live test)

> This is a worked example showing a complete brief end-to-end. Real tests use
> the template at `../_templates/lp-brief-template.md` and a dated filename
> (`YYYY-MM-DD_product_slug.md`). The `_example_` prefix marks this as reference.

---
test_id: _example_invoice_zatca-above-fold
product: Invoice
channel: Meta
status: example
---

## 1. Hypothesis
If we move the **ZATCA Phase-2 compliance badge above the fold** on the Invoice
LP, then **CPQL will drop** because Saudi finance buyers qualify trust before
reading the offer, lifting form-start rate.

## 2. Current state (live BQ, 14-day window)
Window: 2026-05-25 to 2026-06-07 · current CPQL: $84 · form-start rate: 6.1%
destination_url: https://lp.qoyod.com/invoice-zatca

## 3. Target audience & OCEAN persona
Segment: SMB finance owners, Meta Interests. Persona: high Conscientiousness +
low Openness → lead with compliance/trust, not novelty.

## 4. Offer & message
Above the fold: "Issue ZATCA Phase-2 compliant e-invoices in minutes" + the ZATCA
badge + 25,000-companies proof point.

## 5. Page structure (sections, order)
Hero (badge above fold) → social proof stats → problem → features → testimonials
→ pricing → FAQ → CTA. ZATCA badge pinned in hero, visible on mobile without scroll.

## 6. Form & tracking
Fields: name, phone, company, sector. UTM passthrough on every field. Both pixels
fire (CRM 1782671302631317 + Web 3036579196577051). Lead event on submit.

## 7. Success criteria
Ship if CPQL drops ≥ 12% (to ≤ $74) over a 14-day post-launch window at the same
spend level, with form-start rate up. Otherwise keep control.

## 8. Risks & kill criterion
Risk: badge crowds the hero on small screens → watch bounce. Kill early if CPQL
rises > 10% in the first 7 days; revert to control (pre-approved).
